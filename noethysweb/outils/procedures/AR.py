import logging
from outils.views.procedures import BaseProcedure
from core.models import Article, Activite, Structure, PortailDocument, SignatureEmail, Album, ModeleDocument, QuestionnaireQuestion
from django.db.models import F, Value
from django.db.models.functions import Concat

logger = logging.getLogger(__name__)


class Procedure(BaseProcedure):
    def Arguments(self, parser=None):
        # Aucune modification nécessaire ici pour le moment
        pass

    def Executer(self, variables=None):
        activites_archives = Activite.objects_all.filter(nom__startswith='ARCHIVE - ')

        activites_archives.update(
                actif=False,
                structure=12
            )

        return (
                f"FAIT"
            )
