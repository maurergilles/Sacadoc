import logging
from outils.views.procedures import BaseProcedure
from core.models import Activite, Structure

logger = logging.getLogger(__name__)


class Procedure(BaseProcedure):

    def Arguments(self, parser=None):
        pass

    def _nettoyer_nom(self, nom):
        prefix = "ARCHIVE - "
        return nom[len(prefix):] if nom.startswith(prefix) else nom

    def Executer(self, variables=None):
        try:
            structure = variables.get('structure')
            activite = variables.get('activite')

            # =========================
            # Cas invalide
            # =========================
            if not structure and not activite:
                return "Aucune structure ou activité sélectionnée."

            if structure and activite:
                return "Veuillez sélectionner soit une structure, soit une activité, mais pas les deux."

            # =========================
            # Désarchivage activité
            # =========================
            if activite:
                activite.nom = self._nettoyer_nom(activite.nom)
                activite.actif = True
                activite.visible = True
                activite.save()

                return "Activité désarchivée."

            # =========================
            # Désarchivage structure
            # =========================
            structure.nom = self._nettoyer_nom(structure.nom)
            structure.actif = True
            structure.visible = True
            structure.save()

            return "Structure désarchivée."

        except Exception as e:
            logger.exception("Erreur lors du désarchivage")
            return f"Une erreur est survenue : {str(e)}"
