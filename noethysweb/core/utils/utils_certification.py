from datetime import date
from logging import Logger
from typing import Optional

from django.contrib import messages
from django.http import HttpRequest

from core.models import Destinataire, Individu, Inscription, Mail, Rattachement, Activite, Structure, AdresseMail, \
    Famille
from outils.utils import utils_email


def demander_certification(inscription: Inscription, request: Optional[HttpRequest]=None):
    """
    Cette fonction permet aux CG de demander la certification de la famille/parent
    -> afficher sur l'acceuil un besoin de certification
    """
    if inscription.besoin_certification:
        if request:
            messages.error(request,"La demande de certification a déjà été faite pour cette inscription.")
        return # Déjà demandé
    inscription.besoin_certification = True
    inscription.save()

def get_derniere_certification(individu: Individu) -> date:
    """
    Cette fonction permet de récupérer la dernière certification de la famille/parent
    """
    rattachement = Rattachement.objects.filter(individu=individu).last()
    return rattachement.certification_date

