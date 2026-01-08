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
        try:
            activite_id = variables.get('activite')
            if not activite_id:
                return "Aucune activité sélectionnée."

            # Récupérer l'activité depuis la base
            try:
                activite_label = Activite.objects.get(idactivite=activite_id.idactivite)
                activite = activite_label.idactivite
            except Activite.DoesNotExist:
                return "L'activité fournie n'existe pas."

            activite_label.actif = False
            activite_label.nom = f"ARCHIVE - {activite_label.nom}"
            activite_label.save()

            return (
                f"Activité archivée"
            )

        except Exception as e:
            logger.error(f"Une erreur est survenue : {str(e)}")
            return f"Une erreur est survenue : {str(e)}"
