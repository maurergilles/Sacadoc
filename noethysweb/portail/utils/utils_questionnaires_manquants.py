# -*- coding: utf-8 -*-
#  Copyright (c) 2019-2021 Ivan LUCAS.
#  Noethysweb, application de gestion multi-activités.
#  Distribué sous licence GNU GPL.

from django.db.models import Q
from core.models import Individu, Rattachement, Inscription, QuestionnaireQuestion, QuestionnaireReponse, Activite

def est_question_complétée(reponse):
    """
    Vérifie si une réponse à une question est réellement complétée.
    """
    if not reponse:
        return False

    valeur = reponse.Get_reponse_for_ctrl()  # récupère la valeur réelle comme pour le formulaire

    if valeur is None:
        return False

    # Cas booléen : False est une réponse valide
    if isinstance(reponse.question.controle, str) and reponse.question.controle == "case_coche":
        return True

    # Cas texte / textarea
    if isinstance(valeur, str):
        return bool(valeur.strip())

    # Cas liste à choix multiples
    if isinstance(valeur, (list, tuple)):
        return len(valeur) > 0

    # Cas entier / decimal / slider / date
    if isinstance(valeur, (int, float, complex)):
        return True
    if hasattr(valeur, 'isoformat'):  # date ou datetime
        return True

    return False

def Get_question_individu(individu):
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