# -*- coding: utf-8 -*-
#  Copyright (c) 2019-2021 Ivan LUCAS.
#  Noethysweb, application de gestion multi-activités.
#  Distribué sous licence GNU GPL.

import logging, datetime
logger = logging.getLogger(__name__)
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.template.defaultfilters import truncatechars, striptags
from core.views import crud
from core.models import PortailMessage, Structure, Famille, Activite, Inscription, Individu
from outils.forms.messagerie_portail import Formulaire, Envoi_notification_message
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from datetime import timedelta

def Marquer_lu(request):
    """ Marquer un message comme lu ou non """
    idmessage = int(request.POST.get("idmessage"))
    etat = request.POST.get("etat")
    message = PortailMessage.objects.filter(pk=idmessage)
    if etat == "true":
        message.update(date_lecture=datetime.datetime.now())
    else:
        message.update(date_lecture=None)
    return JsonResponse({"succes": True})


class Page(crud.Page):
    model = PortailMessage
    menu_code = "messagerie_portail"

    def get_context_data(self, **kwargs):
        context = super(Page, self).get_context_data(**kwargs)
        context['page_titre'] = "Messagerie"
        liste_messages_discussion = PortailMessage.objects.select_related("famille", "structure", "utilisateur").filter(famille_id=self.get_idfamille(), structure_id=self.get_idstructure()).order_by("date_creation")
        context['liste_messages_discussion'] = list(liste_messages_discussion)
        messages_non_lus = PortailMessage.objects.select_related("famille", "structure").filter(structure__in=self.request.user.structures.all(), utilisateur__isnull=True, date_lecture__isnull=True).order_by("date_creation")
        context['messagerie_liste_messages_non_lus'] = list(messages_non_lus)

        # Date limite : 3 mois en arrière
        date_limite = timezone.now() - timedelta(days=90)

        # Sous-requête pour récupérer le dernier message par famille dans les 3 derniers mois
        dernier_message_subquery = PortailMessage.objects.filter(
            famille_id=OuterRef('famille_id'),
            structure__in=self.request.user.structures.all(),
            date_creation__gte=date_limite
        ).order_by('-date_creation')

        # Liste des derniers messages par famille, mais exclure celles avec messages non lus
        liste_messages_lus = PortailMessage.objects.filter(
            idmessage__in=Subquery(dernier_message_subquery.values('idmessage')[:1])
        ).exclude(
            famille__in=messages_non_lus.values('famille_id')
        ).select_related('famille', 'structure').order_by('-date_creation')

        context['messagerie_liste_messages_lus'] = list(liste_messages_lus)


        if self.get_idstructure():
            context["structure"] = Structure.objects.get(pk=self.get_idstructure())

        context["structure_all"] = self.request.user.structures.all()


        if self.get_idfamille():
            context["famille"] = Famille.objects.get(pk=self.get_idfamille())

        # Indiquer que les messages de la discussion ouverte sont lus
        if messages_non_lus and self.get_idfamille():
            messages_non_lus.filter(famille_id=self.get_idfamille()).update(date_lecture=datetime.datetime.now())

        # Envoi famille
        activites_accessibles = Activite.objects.filter(structure__in=self.request.user.structures.all())
        inscriptions_accessibles = Inscription.objects.filter(activite__in=activites_accessibles)
        individus_inscrits = Individu.objects.filter(idindividu__in=inscriptions_accessibles.values('individu'))
        famille_inscrite = Famille.objects.filter(idfamille__in=inscriptions_accessibles.values('famille')).order_by('nom')

        context['toutes_les_familles'] = famille_inscrite

        return context

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super(Page, self).get_form_kwargs(**kwargs)
        form_kwargs["idstructure"] = self.get_idstructure()
        form_kwargs["idfamille"] = self.get_idfamille()
        return form_kwargs

    def get_idfamille(self):
        return self.kwargs.get("idfamille", 0)

    def get_idstructure(self):
        return self.kwargs.get("idstructure", 0)

    def get_success_url(self):
        return reverse_lazy("messagerie_portail", kwargs={'idstructure': self.get_idstructure(), 'idfamille': self.get_idfamille()})


class Ajouter(Page, crud.Ajouter):
    form_class = Formulaire
    template_name = "outils/messagerie_portail.html"
    texte_confirmation = "Le message a bien été envoyé"
    titre_historique = "Ajouter un message"

    def Get_detail_historique(self, instance):
        return "Texte=%s" % (truncatechars(striptags(instance.texte), 40))

    def form_valid(self, form):
        """ Envoie une notification de nouveau message à la famille par email """
        Envoi_notification_message(request=self.request, famille=form.cleaned_data["famille"], structure=form.cleaned_data["structure"])
        return super(Ajouter, self).form_valid(form)
