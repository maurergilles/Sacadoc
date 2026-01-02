# -*- coding: utf-8 -*-
#  Copyright (c) 2019-2021 Ivan LUCAS.
#  Noethysweb, application de gestion multi-activités.
#  Distribué sous licence GNU GPL.

from django.db.models import Q
from core.models import Individu, Rattachement, Inscription, QuestionnaireQuestion, QuestionnaireReponse, Activite


def Get_information_individu(individu):
    """
    Retourne la liste des questions non complétées pour l'individu.
    """
    # Activités de l'individu
    inscriptions = Inscription.objects.filter(individu=individu)
    activite_ids = inscriptions.values_list('activite', flat=True).distinct()
    activites = Activite.objects.filter(idactivite__in=activite_ids, structure__visible=True)

    # Toutes les questions
    questions = QuestionnaireQuestion.objects.filter(
        categorie="individu",
        visible_portail=True,
        activite__in=activites
    ).order_by("ordre")

    # Filtrage des questions non complétées
    questions_non_complétées = []
    for question in questions:
        reponse = QuestionnaireReponse.objects.filter(
            individu=individu,
            question=question
        ).first()
        if not reponse or not est_question_complétée(reponse):
            questions_non_complétées.append(question)

    return questions_non_complétées


def Get_questions_manquantes_famille(famille):
    """
    Retourne un dict avec, pour chaque individu de la famille,
    la liste des questions individu non répondues.
    """
    if not famille:
        return {}

    result = {}

    rattachements = Rattachement.objects.select_related('individu').filter(
        famille=famille,
        individu__deces=False
    )

    for rattachement in rattachements:
        individu = rattachement.individu

        questions_manquantes = Get_question_individu(individu)

        result[individu.pk] = {
            "individu": individu,
            "rattachement": rattachement,
            "questions": questions_manquantes,
            "nbre": len(questions_manquantes),
        }

    return result