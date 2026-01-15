# -*- coding: utf-8 -*-
#  Copyright (c) 2019-2021 Ivan LUCAS.
#  Noethysweb, application de gestion multi-activités.
#  Distribué sous licence GNU GPL.

import datetime, decimal, json
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Sum
from core.views.mydatatableview import MyDatatable, columns, helpers
from core.views import crud
from core.models import Inscription, Activite, Rattachement, Cotisation, Groupe, Prestation, Ventilation, Mail, Destinataire
from core.utils import utils_texte
from fiche_individu.forms.individu_inscriptions import Formulaire
from django.shortcuts import redirect
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.views import View
from outils.utils import utils_email
# Import des utils pour les éléments manquants
from individus.utils import (
    utils_pieces_manquantes,
    utils_vaccinations,
    utils_assurances,
)
from decimal import Decimal
from cotisations.utils import utils_cotisations_manquantes
from portail.utils import utils_renseignements_manquants, utils_questionnaires_manquants, utils_sondages_manquants


class Page(crud.Page):
    model = Inscription
    url_liste = "suivi_administratif_liste"
    url_modifier = "suivi_administratif_modifier"
    url_supprimer = "suivi_administratif_supprimer"
    description_liste = "Sélectionnez une activité puis effectuez la demande souhaitée. Vous pouvez soit demander à tous les inscrits de vérifier leurs informations personnelles ou relancer ceux qui ne l'ont pas encore fait."
    description_saisie = "Saisissez toutes les informations concernant l'inscription à saisir et cliquez sur le bouton Enregistrer."
    objet_singulier = "une vérification"
    objet_pluriel = "des vérifications"


class Liste(Page, crud.Liste):
    template_name = "individus/suivi_administratif.html"

    def get_queryset(self):
        """Renvoie les inscriptions visibles pour les structures de l'utilisateur et l'activité sélectionnée."""
        condition = Q(activite__structure__in=self.request.user.structures.all())
        condition &= Q(activite__visible=True)
        qs = Inscription.objects.select_related(
            "famille", "individu", "activite"
        ).filter(self.Get_filtres("Q"), condition, activite=self.Get_activite())
        return qs

    def Get_activite(self):
        activite = self.kwargs.get("activite", None)
        if activite:
            activite = activite.replace("A", "")
            return activite
        return None

    def Get_solde_par_individu(self, individus, parametres):
            """
            Retourne un dictionnaire avec le solde de chaque individu.
            Inspiré de ton modèle familles -> prestations/règlements.
            """

            # Filtre activités si fourni
            activites_data = json.loads(parametres.get("activites", "{}"))
            ids_activites = activites_data.get("ids", [])
            conditions_prestations = Q(activite__in=ids_activites)

            # Prestations par individu
            prestations_qs = Prestation.objects.filter(
                conditions_prestations,
                individu__in=individus
            )

            dict_prestations = {
                temp["individu"]: temp["total"]
                for temp in prestations_qs.values("individu").annotate(total=Sum("montant"))
            }

            # Ventilations filtrées uniquement sur les prestations récupérées
            dict_reglements = {
                temp["prestation__individu"]: temp["total"]
                for temp in Ventilation.objects.filter(prestation__in=prestations_qs)
                .values("prestation__individu")
                .annotate(total=Sum("montant"))
            }

            # Création du solde par individu
            dict_solde = {}
            for individu in individus:
                total_prestations = dict_prestations.get(individu.pk, Decimal(0))
                total_reglements = dict_reglements.get(individu.pk, Decimal(0))
                solde = total_reglements - total_prestations
                dict_solde[individu.pk] = {
                    "solde": float(solde),
                    "prestations": float(total_prestations),
                    "reglements": float(total_reglements),
                }

            return dict_solde


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_par_individu = []
        context['activite'] = int(self.Get_activite()) if self.Get_activite() else None
        condition = Q(visible=True)
        liste_activites = []
        for activite in Activite.objects.filter(self.Get_condition_structure(), condition).order_by("-date_fin", "nom"):
            if activite.date_fin.year == 2999:
                liste_activites.append((activite.pk, "%s - Activité illimitée" % activite.nom))
            elif activite.date_fin:
                liste_activites.append((activite.pk, "%s - Du %s au %s" % (
                activite.nom, activite.date_debut.strftime("%d/%m/%Y"), activite.date_fin.strftime("%d/%m/%Y"))))
            else:
                liste_activites.append(
                    (activite.pk, "%s - A partir du %s" % (activite.nom, activite.date_debut.strftime("%d/%m/%Y"))))
        context['liste_activites'] = [(None, "--------")] + liste_activites

        inscriptions = self.get_queryset()

        structure = self.Get_condition_structure()
        data_par_individu = []

        individus = [ins.individu for ins in inscriptions]


        # Calcul des soldes
        parametres = {"activites": json.dumps({"ids": [ins.activite.pk for ins in inscriptions]}),}
        dict_solde = self.Get_solde_par_individu(individus, parametres)


        for ins in inscriptions:
            individu = ins.individu
            famille = ins.famille

            solde_info = dict_solde.get(individu.pk, {"solde": 0, "prestations": 0, "reglements": 0})
            nb_pieces = len(utils_pieces_manquantes.Get_pieces_manquantes_individu(famille, individu, ins.activite) or [])
            nb_vaccins = len(utils_vaccinations.Get_vaccins_obligatoires_by_inscriptions([ins]).get(individu, []) or [])
            nb_questions = len(utils_questionnaires_manquants.Get_question_individu(individu) or [])
            renseignement = utils_renseignements_manquants.Get_renseignements_manquants_individu(individu)
            nb_renseignements = renseignement.get("nbre", 0) if isinstance(renseignement, dict) else 0
            nb_sondages = len(utils_sondages_manquants.Get_sondages_manquants_individu(individu, famille, structure) or [])

            data_par_individu.append({
                "individu": individu,
                "activite": ins.activite,
                "pieces_manquantes": nb_pieces,
                "vaccins_manquants": nb_vaccins,
                "sondages_manquants": nb_sondages,
                "questions_manquantes": nb_questions,
                "renseignements_manquants": nb_renseignements,
                "besoin_certification": "Oui" if ins.besoin_certification else "Non",
                "solde_a_payer": solde_info["solde"],
            })

        context['data_par_individu'] = data_par_individu
        return context

    class datatable_class(MyDatatable):
        filtres = ["individu__nom", "individu__prenom"]

        individu = columns.CompoundColumn("Individu", sources=["individu__nom", "individu__prenom"])
        activite = columns.TextColumn("Activité", sources=["activite__nom"])
        pieces_manquantes = columns.TextColumn("Pièces manquantes", sources=["pieces_manquantes"])
        vaccins_manquants = columns.TextColumn("Vaccinations manquantes", sources=["vaccins_manquants"])
        sondages_manquants = columns.TextColumn("Sandages manquants", sources=["sondages_manquants"])
        questions_manquantes = columns.TextColumn("Questionnaires manquants", sources=["questions_manquantes"])
        renseignements_manquants = columns.TextColumn("Renseignements manquants", sources=["renseignements_manquants"])
        besoin_certification = columns.TextColumn("Certification", sources=["besoin_certification"])
        solde_a_payer = columns.TextColumn("Solde à payer", sources=["solde_a_payer"])
        prestations = columns.TextColumn("Prestations", sources=["prestations"])
        reglements = columns.TextColumn("Règlements", sources=["reglements"])

    class Meta:
            structure_template = MyDatatable.structure_template
            columns = [
                "individu",
                "activite",
                "pieces_manquantes",
                "vaccins_manquants",
                "sondages_manquants",
                "questions_manquantes",
                "renseignements_manquants",
                "besoin_certification",
                "solde_a_payer"
            ]
            ordering = ["individu"]