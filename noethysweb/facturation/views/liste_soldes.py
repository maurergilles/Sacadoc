# -*- coding: utf-8 -*-
#  Copyright (c) 2019-2021 Ivan LUCAS.
#  Noethysweb, application de gestion multi-activités.
#  Distribué sous licence GNU GPL.

import logging, json, time
logger = logging.getLogger(__name__)
from decimal import Decimal
from django.views.generic import TemplateView
from django.db.models import Q, Sum
from core.views.base import CustomView
from core.models import Famille, Prestation, Reglement, Ventilation, ModeleEmail, Mail, Destinataire, Activite, Inscription
from facturation.forms.liste_soldes import Formulaire
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.contrib import messages

class View(CustomView, TemplateView):
    menu_code = "liste_soldes"
    template_name = "facturation/liste_soldes.html"

    def get_context_data(self, **kwargs):
        context = super(View, self).get_context_data(**kwargs)
        context['page_titre'] = "Liste des soldes"
        if "form_parametres" not in kwargs:
            context['form_parametres'] = Formulaire(request=self.request)
        return context

    def post(self, request, **kwargs):
        form = Formulaire(request.POST, request=self.request)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form_parametres=form))

        data = self.Get_resultats(parametres=form.cleaned_data)
        context = {
            "form_parametres": form,
            "data": data,
            "titre": "Liste des soldes",
        }
        return self.render_to_response(self.get_context_data(**context))

    def Get_resultats(self, parametres={}):
        conditions_prestations = Q(date__lte=parametres["date_situation"])
        activites = parametres.get("activites", [])
        activites_data = json.loads(activites)
        ids_activites = activites_data.get("ids", [])
        inscriptions_accessibles = Inscription.objects.filter(activite__in=ids_activites)
        familles = Famille.objects.filter(idfamille__in=inscriptions_accessibles.values('famille'))
        if ids_activites:
            presta = Prestation.objects.filter(activite__in=ids_activites)
            conditions_prestations &= Q(activite__in=ids_activites)

        if parametres["uniquement_factures"]:
            conditions_prestations &= Q(facture__isnull=False)
            conditions_prestations &= Q(activite__in=ids_activites)

        dict_prestations = {temp["famille"]: temp["total"] for temp in Prestation.objects.filter(conditions_prestations).values('famille').annotate(total=Sum("montant"))}

            # Si pas d'activités spécifiées, récupérer les ventilations sans ce filtre
        dict_reglements = {
                temp["famille"]: temp["total"]
                for temp in Ventilation.objects.filter(prestation__in=Prestation.objects.filter(conditions_prestations))
                .values('famille')
                .annotate(total=Sum("montant"))
            }
        # Création des colonnes
        liste_colonnes = ["Famille", "Solde", "Prestations", "Règlements"]

        # Création des lignes
        liste_lignes = []
        for famille in familles:
            total_prestations = dict_prestations.get(famille.pk, Decimal(0))
            total_reglements = dict_reglements.get(famille.pk, Decimal(0))
            solde = total_reglements - total_prestations
            if (solde < Decimal(0) and parametres["afficher_debits"]) or (solde > Decimal(0) and parametres["afficher_credits"]) or (solde == Decimal(0) and parametres["afficher_nuls"]):
                liste_lignes.append({
                    "0": famille.nom,
                    "1": float(solde),
                    "2": float(total_prestations),
                    "3": float(total_reglements),
                })

        # Préparation des résultats
        data = {
            "liste_colonnes": liste_colonnes,
            "liste_lignes": json.dumps(liste_lignes),
            "activites": activites_data,
        }
        return data

def Envoi_emails_soldes(request):
    logger.debug("Démarrage de la fonction email")
    # Récupération des données envoyées
    soldes = json.loads(request.POST.get("familles", "[]"))
    activites = json.loads(request.POST.get("activites", "[]"))
    liste_activites = [int(x.strip()) for x in activites.split(',') if x.strip().isdigit()]
    activites_objets = Activite.objects.filter(idactivite__in=liste_activites)
    noms_activites = [activite.nom for activite in activites_objets]
    activites_str = " ou ".join(noms_activites)
    logger.debug(f"Activités sélectionnées : {noms_activites}")

    # Création d'un nouveau mail
    logger.debug("Création d'un nouveau mail...")
    modele_email = ModeleEmail.objects.filter(categorie="rappel", defaut=True).first()
    mail = Mail.objects.create(
        categorie="rappel",
        objet=modele_email.objet if modele_email else "Rappel de solde",
        html=modele_email.html if modele_email else "",
        adresse_exp=request.user.Get_adresse_exp_defaut(),
        selection="NON_ENVOYE",
        verrouillage_destinataires=False,
        utilisateur=request.user,
    )

    # Importation des familles
    noms_familles = [valeurs['nom'] for valeurs in soldes]
    dict_familles = {famille.nom: famille for famille in Famille.objects.filter(nom__in=noms_familles)}

    # Création des destinataires
    logger.debug("Enregistrement des destinataires...")
    liste_anomalies = []
    for solde_data in soldes:
        famille_nom = solde_data.get("nom")
        solde = solde_data.get("solde", 0)
        famille = dict_familles.get(famille_nom)

        if not famille:
            liste_anomalies.append(famille_nom)
            continue

        valeurs_fusion = {
            "{NOM_FAMILLE}": famille.nom,
            "{SOLDE_CHIFFRES}": f"{float(solde):.2f}".replace(".", ",").replace("-", ""),
            "{ACTIVITES_CONCERNEES}": activites_str
        }
        #logger.debug(f"Valeurs de fusion pour {famille.nom}: {valeurs_fusion}")

        if famille.mail:
            destinataire = Destinataire.objects.create(
                categorie="famille",
                famille=famille,
                adresse=famille.mail,
                valeurs=json.dumps(valeurs_fusion)
            )
            mail.destinataires.add(destinataire)
        else:
            liste_anomalies.append(famille.nom)

    # Gestion des anomalies
    if liste_anomalies:
        messages.add_message(request, messages.ERROR, "Adresses mail manquantes : %s" % ", ".join(liste_anomalies))

    # Création de l'URL pour ouvrir l'éditeur d'emails
    logger.debug("Redirection vers l'éditeur d'emails...")
    url = reverse_lazy("editeur_emails", kwargs={'pk': mail.pk})
    return JsonResponse({"url": url})