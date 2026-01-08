from django.views import View
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from core.models import Activite
from django.views.generic import TemplateView
from core.views.base import CustomView
from outils.procedures.AR_ACTIVITE import Procedure as AR_ACT
from outils.procedures.AR_STRUCTURE import Procedure as AR_STR
from outils.procedures.DESARCHIVAGE import Procedure as DESAR

class ToggleArchiveView(View):
        """
        Vue pour archiver ou désarchiver une activité.
        """
        procedure_class = None
        def get(self, request, idactivite):
            # Récupère l'activité
            activite = get_object_or_404(Activite.objects_all, idactivite=idactivite)

            # Exécute la procédure en passant l'objet avec la clé attendue
            proc = self.procedure_class()
            result = proc.Executer(variables={"activite": activite})  # <- ici clé = "activite"

            # Message succès
            messages.success(request, result)

            # Redirection
            return redirect("activites_liste")


class ToggleArchiveActivite(ToggleArchiveView):
    procedure_class = AR_ACT

class ToggleDesarchive(ToggleArchiveView):
    procedure_class = DESAR
