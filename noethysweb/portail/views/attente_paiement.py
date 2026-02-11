# -*- coding: utf-8 -*-
import logging
import decimal
import stripe
import requests
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from django.views.generic import TemplateView
from portail.views.base import CustomView
from core.models import (
    TokenHA, Prestation, HelloAssoConfig, ModeReglement,
    CompteBancaire, Reglement, Ventilation, ComptaOperation,
    ComptaVentilation, StripeCompte
)

logger = logging.getLogger(__name__)

class View(CustomView, TemplateView):
    menu_code = "portail_attente_paiement"
    template_name = "portail/attente_paiement.html"
    compatible_demo = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_titre'] = "Attente du paiement"
        context['box_titre'] = "Paiement en cours"
        context['box_introduction'] = ""

        # On passe checkoutIntentId et orderId au template
        context['checkout_intent_id'] = self.request.GET.get("checkoutIntentId")
        context['order_id'] = self.request.GET.get("orderId")
        return context

    def get(self, request, *args, **kwargs):
        # Récupération des paramètres pour les deux plateformes
        checkout_intent_id = request.GET.get("checkoutIntentId")  # Spécifique HelloAsso
        stripe_session_id = request.GET.get("session_id")       # Spécifique Stripe
        stripe_compte_id = request.GET.get("compte_id")    # Spécifique Stripe
        orderId = request.GET.get("orderId")

        # --- CAS STRIPE ---
        if stripe_session_id and stripe_compte_id:
            # Sécurité contre l'erreur d'ID mal formaté {stripe_compte.pk}
            if "{" in str(stripe_compte_id):
                messages.error(request, "Erreur de configuration du lien de paiement.")
                return redirect('portail_facturation')
            return self.handle_stripe_logic(request, stripe_session_id, stripe_compte_id)

        # --- CAS HELLOASSO ---
        if checkout_intent_id:
            return self.handle_helloasso_logic(request, checkout_intent_id)

        # Si aucun paramètre valide
        messages.error(request, "Aucune information de paiement reçue.")
        return redirect('portail_facturation')

    def handle_helloasso_logic(self, request, checkout_intent_id):
        """Logique de traitement pour HelloAsso"""
        token_entry = TokenHA.objects.filter(
            checkout_intent_id=checkout_intent_id,
            expires_at__gt=timezone.now()
        ).order_by('-expires_at').first()

        if not token_entry:
            messages.error(request, "Session HelloAsso expirée ou introuvable.")
            return redirect('portail_facturation')

        prestation = token_entry.prestation
        token = token_entry.access_token
        org_slug = token_entry.organisation_slug

        # ⚠️ ATTENTION : L'environnement doit être le MÊME que celui utilisé lors de la création
        # Si tu es en test, assure-toi que ta vue 'paiement_tpe' utilise aussi le sandbox.
        HELLOASSO_FORCE_SANDBOX = True
        api_base = "https://api.helloasso-sandbox.com/v5/organizations" if HELLOASSO_FORCE_SANDBOX else "https://api.helloasso.com/v5/organizations"

        url = f"{api_base}/{org_slug}/checkout-intents/{checkout_intent_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            resp = requests.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            # --- ON SORT LE CODE DU BLOC EXCEPT POUR QU'IL S'EXÉCUTE ---
            order = data.get("order")
            # HelloAsso peut renvoyer Success ou Authorized
            if order and data.get("state") in ["Success", "Authorized"]:
                # Le montant HelloAsso est en centimes dans l'API
                montant = decimal.Decimal(order.get("amount", {}).get("total")) / 100
                tag = f"HELLOASSO_{order.get('id')}"

                # Vérification doublon sur 'observations' (pour être raccord avec ta méthode valider)
                if not Reglement.objects.filter(observations__icontains=tag).exists():
                    self.valider_paiement_final(prestation, montant, tag, order.get("id"))
                    messages.success(request, "Paiement HelloAsso validé !")
                else:
                    messages.info(request, "Paiement HelloAsso déjà enregistré.")

                return redirect('portail_facturation')

        except requests.RequestException as e:
            logger.error(f"Erreur API HelloAsso: {e}")
            messages.error(request, "Impossible de vérifier le statut du paiement auprès de HelloAsso.")
        except Exception as e:
            logger.error(f"Erreur traitement HelloAsso : {e}")
            messages.error(request, "Erreur lors de l'enregistrement du paiement.")

        return redirect('portail_facturation')
    def handle_stripe_logic(self, request, session_id, compte_id):
        """Logique de traitement pour Stripe"""
        try:
            stripe_compte = StripeCompte.objects.get(pk=int(compte_id), actif=True)
            stripe.api_key = stripe_compte.secret_key
            session = stripe.checkout.Session.retrieve(session_id)

            if session.payment_status == "paid":
                id_prestation = session.metadata.get('id_prestation')
                prestation = Prestation.objects.get(pk=int(id_prestation))
                # Le montant Stripe est en centimes
                montant = decimal.Decimal(session.amount_total) / 100
                tag = f"STRIPE_SESSION_{session.id}"

                if not Reglement.objects.filter(observations__icontains=tag).exists():
                    self.valider_paiement_final(prestation, montant, tag, session.id)
                    messages.success(request, "Paiement Stripe validé !")
                return redirect('portail_facturation')

        except Exception as e:
            logger.error(f"Erreur validation Stripe : {str(e)}")
            messages.error(request, "Erreur lors de la validation Stripe.")

        return redirect('portail_facturation')

    def valider_paiement_final(self, prestation, montant, tag, piece_id):
        """Méthode de création UNIQUE pour les écritures Noethys"""
        activite = prestation.activite
        compte_noethys = CompteBancaire.objects.filter(structure=activite.structure).first() or CompteBancaire.objects.first()
        print(montant,tag,piece_id)
        # 1. Règlement Noethys
        reglement = Reglement.objects.create(
            famille=prestation.famille,
            date=timezone.now().date(),
            montant=montant,
            compte=compte_noethys,
            mode_id=6, # CB
            payeur_id=3,  # par défaut
            observations=tag,
            modelimp_id = 2,
        )

        # 2. Ventilation
        Ventilation.objects.create(
            famille=prestation.famille,
            reglement=reglement,
            prestation=prestation,
            montant=montant,
        )

        # 3. Comptabilité
        operation = ComptaOperation.objects.create(
            type="credit",
            date=timezone.now(),
            libelle=f"Paiement en ligne - {prestation.label}",
            montant=montant,
            compte=compte_noethys,
            mode_id=6,
            num_piece=str(piece_id)[:20],
        )

        ComptaVentilation.objects.create(
            date_budget=timezone.now().date(),
            montant=montant,
            analytique_id=1,
            categorie_id=1,
            operation=operation,
        )