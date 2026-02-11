# -*- coding: utf-8 -*-
#  Copyright (c) 2019-2021 Ivan LUCAS.
#  Noethysweb, application de gestion multi-activités.
#  Distribué sous licence GNU GPL.

import datetime
from django import forms
from django.forms import ModelForm, CheckboxSelectMultiple, ModelMultipleChoiceField, HiddenInput
from django.db.models import Q
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Hidden, HTML, Div, Field
from crispy_forms.bootstrap import Field
from core.models import Activite, Rattachement, Groupe, PortailRenseignement, CategorieTarif, NomTarif, Tarif, Structure, TarifLigne, PortailDocument
from core.utils.utils_commandes import Commandes
from portail.forms.fiche import FormulaireBase
from individus.utils import utils_pieces_manquantes


class Formulaire_extra(FormulaireBase, forms.Form):
    groupe = forms.ModelChoiceField(
        label=_("Groupe"),
        queryset=Groupe.objects.none(),
        required=True,
        help_text=_("Sélectionnez le groupe pour l'inscription.")
    )

    def __init__(self, *args, **kwargs):
        activite = kwargs.pop("activite", None)
        famille = kwargs.pop("famille", None)
        individu = kwargs.pop("individu", None)
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.label_class = 'col-md-3'
        self.helper.field_class = 'col-md-9'

        # 1. Configuration du Groupe
        groupes = Groupe.objects.filter(activite=activite).order_by("nom")
        self.fields["groupe"].queryset = groupes
        if groupes.count() == 1:
            self.fields["groupe"].initial = groupes.first()

        layout_elements = [Field("groupe")]

        # 2. Image de l'activité (juste après le groupe)
        if activite and activite.image:
            layout_elements.append(HTML(
                f'<div class="text-center my-3">'
                f'<img src="{activite.image.url}" class="img-fluid rounded shadow-sm" style="max-height: 200px;">'
                f'</div>'
            ))

        # 3. Tarifs (Radio boutons)
        noms_tarifs = NomTarif.objects.filter(activite=activite, visible=True).order_by("nom")
        for nt in noms_tarifs:
            tarifs = Tarif.objects.filter(nom_tarif=nt, activite=activite, visible=True)
            if tarifs.exists():
                f_name = f"tarifs_{nt.idnom_tarif}"
                choices = []
                for t in tarifs:
                    ligne = TarifLigne.objects.filter(tarif=t).first()
                    montant = f"{ligne.montant_unique:,.2f} €".replace('.', ',') if ligne else "0,00 €"
                    choices.append((t.pk, f"{t.description} ({montant})"))

                self.fields[f_name] = forms.ModelChoiceField(
                    label=nt.nom,
                    queryset=tarifs,
                    widget=forms.RadioSelect(),
                    required=True
                )
                self.fields[f_name].choices = choices
                layout_elements.append(Field(f_name))

        # 4. Pièces jointes
        if activite.portail_inscriptions_imposer_pieces:
            pieces = utils_pieces_manquantes.Get_liste_pieces_necessaires(activite, famille, individu)
            for p in pieces:
                if not p["valide"]:
                    f_id = f"document_{p['type_piece'].pk}"
                    self.fields[f_id] = forms.FileField(
                        label=p['type_piece'].nom,
                        required=True,
                        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'png', 'jpg'])]
                    )
                    layout_elements.append(Field(f_id))

        self.helper.layout = Layout(*layout_elements)


class Formulaire(FormulaireBase, ModelForm):
    activite = forms.ModelChoiceField(label=_("Activité"), queryset=Activite.objects.none(), required=True, help_text=_("Sélectionnez l'activité souhaitée dans la liste."))
    structure = forms.ModelChoiceField(label=_("Structures"), queryset=Structure.objects.none(), required=True, help_text=_("Sélectionnez la structure souhaitée dans la liste."))
    groupe = forms.ModelChoiceField(
        label=_("Groupe"),
        queryset=Groupe.objects.none(),
        required=True
    )
    class Meta:
        model = PortailRenseignement
        fields = "__all__"
        labels = {
            "individu": _("Individu"),
        }
        help_texts = {
            "individu": _("Sélectionnez le membre de la famille à inscrire."),
        }

    def __init__(self, *args, **kwargs):
        super(Formulaire, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_id = 'portail_inscrire_activite_form'
        self.helper.form_method = 'post'

        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-md-2 col-form-label'
        self.helper.field_class = 'col-md-10'
        self.helper.use_custom_control = False
        self.helper.attrs = {'enctype': 'multipart/form-data'}

        # Individu (avec filtrage de la catégorie 2)
        rattachements = Rattachement.objects.select_related("individu").filter(
            famille=self.request.user.famille).exclude(individu__in=self.request.user.famille.individus_masques.all()).order_by("categorie")

        self.fields["individu"].choices = [(rattachement.individu_id, rattachement.individu.Get_nom()) for rattachement
                                           in rattachements]
        self.fields["individu"].required = True

        # Activité
        conditions = (Q(visible=True) & Q(portail_inscriptions_affichage="TOUJOURS") | (Q(portail_inscriptions_affichage="PERIODE") & Q(
            portail_inscriptions_date_debut__lte=datetime.datetime.now()) & Q(
            portail_inscriptions_date_fin__gte=datetime.datetime.now())))
        self.fields["activite"].queryset = Activite.objects.filter(conditions).order_by("nom")

        conditions = (Q(visible=True))
        self.fields["structure"].queryset = Structure.objects.filter(conditions).order_by("nom")

        # Affichage
        self.helper.layout = Layout(
            Hidden("famille", value=self.request.user.famille.pk),
            Hidden("etat", value="ATTENTE"),
            Hidden("categorie", value="activites"),
            Hidden("code", value="inscrire_activite"),
            Field("individu"),
            Field("structure"),
            Field("activite"),
            Field("groupe"),
            Div(id="form_extra"),
            HTML(EXTRA_SCRIPT),
            Commandes(
                enregistrer_label="<i class='fa fa-send margin-r-5'></i>%s" % _("Envoyer la demande d'inscription"),
                annuler_url="{% url 'portail_activites' %}", ajouter=False, aide=False, css_class="pull-right"),
        )


EXTRA_SCRIPT = """
<script>
$(function () {
    const $form = $("#portail_inscrire_activite_form");
    const $structure = $("#id_structure");
    const $activite = $("#id_activite");
    const $groupe = $("#id_groupe");
    const $divExtra = $("#form_extra");
    const $placeholder = $("#placeholder_extra");

    let dataActivites = []; 

    // Initialisation : on vide l'activité au chargement de la page
    $activite.empty().append(new Option("Sélectionnez d'abord une structure", ""));
    $groupe.empty().append(new Option("---", ""));

    // --- CASCADE 1 : STRUCTURE -> ACTIVITÉ ---
    $structure.on("change", function() {
        const structureId = $(this).val();

        // On vide tout en dessous immédiatement
        $activite.empty().append(new Option("Chargement...", ""));
        $groupe.empty().append(new Option("---", ""));
        $divExtra.empty();
        $placeholder.show();

        if (!structureId) {
            $activite.empty().append(new Option("Sélectionnez une structure", ""));
            return;
        }

        $.post("{% url 'portail_ajax_get_activites_par_structure' %}", {
            structure_id: structureId,
            csrfmiddlewaretoken: "{{ csrf_token }}"
        }).done(function(data) {
            dataActivites = data.activites;
            $activite.empty().append(new Option("--- Choisir une activité ---", ""));
            $.each(dataActivites, function(_, act) {
                // On s'assure que act.id est le nombre et act.nom le texte
                $activite.append(new Option(act.nom, act.id));
            });
        });
    });

    // --- CASCADE 2 : ACTIVITÉ -> GROUPE & FORM EXTRA ---
    $activite.on("change", function() {
        const activiteId = $(this).val();
        
        if (activiteId) {
        // 1. ON ACTIVE LE CHAMP (on retire le "grisé")
        $groupe.prop('disabled', false);
        $groupe.empty();
        
        // 2. Remplissage des groupes
        const selectedAct = dataActivites.find(a => String(a.id) === String(activiteId));
        
        if (selectedAct && selectedAct.groupes) {
            $.each(selectedAct.groupes, function(_, g) {
                $groupe.append(new Option(g.nom, g.idgroupe));
            });
        } else {
            $groupe.append(new Option("Aucun groupe disponible", ""));
        }

        // 2. Chargement du bloc Extra (Tarifs/Pièces)
        $placeholder.hide();
        $divExtra.html('<div class="text-center py-3"><i class="fa fa-spinner fa-spin"></i> Chargement...</div>');

        // On n'envoie l'AJAX que si on a un ID d'activité valide
        $.post("{% url 'portail_ajax_inscrire_get_form_extra' %}", $form.serialize())
            .done(function (data) {
                $divExtra.html(data.form_html);
            })
            .fail(function () {
                toastr.error("Erreur de chargement.");
            });
    });
});
</script>
"""
