from core.models import Sondage, SondageRepondant, Rattachement, Inscription


def Get_sondages_manquants(famille=None):
    """
    Retourne la liste des sondages (formulaires) que la famille n'a pas encore complétés.

    La liste peut être retrouvé en trouvant tous les structures de la famille et en choppant tous les sondages de la structure qui ont le bon type de public.

    Retourne une liste de dictionnaires avec les informations sur chaque sondage manquant.
    """
    if not famille:
        return []

    sondages_manquants = []

    # Récupérer toutes les structures auxquelles la famille est rattachée via ses inscriptions
    inscriptions = Inscription.objects.select_related('activite', 'activite__structure').filter(famille=famille)
    structure_ids = inscriptions.values_list('activite__structure', flat=True).distinct()

    # Récupérer tous les sondages actifs pour ces structures
    sondages = Sondage.objects.filter(structure__in=structure_ids, structure__visible=True)

    # Récupérer tous les répondants existants pour cette famille
    repondants_existants = SondageRepondant.objects.filter(famille=famille)

    # Créer un dictionnaire des réponses existantes pour un accès rapide
    # Pour les sondages de type "famille" : {idsondage: True}
    # Pour les sondages de type "individu" : {idsondage: {idindividu: True}}
    dict_reponses_famille = {}
    dict_reponses_individu = {}

    for repondant in repondants_existants:
        if repondant.sondage.public == "famille":
            dict_reponses_famille[repondant.sondage.idsondage] = True
        else:  # type "individu"
            if repondant.sondage.idsondage not in dict_reponses_individu:
                dict_reponses_individu[repondant.sondage.idsondage] = set()
            if repondant.individu_id:
                dict_reponses_individu[repondant.sondage.idsondage].add(repondant.individu_id)

    # Récupérer les rattachements de la famille (individus non décédés)
    rattachements = Rattachement.objects.select_related('individu').filter(
        famille=famille,
        individu__deces=False
    )

    # Parcourir tous les sondages et vérifier s'ils sont complétés
    for sondage in sondages:
        if sondage.public == "famille":
            # Sondage de type famille : vérifier si une réponse existe
            if sondage.idsondage not in dict_reponses_famille:
                sondages_manquants.append({
                    'sondage': sondage,
                    'titre': sondage.titre,
                    'code': sondage.code,
                    'type': 'famille',
                    'article': None,  # Pour compatibilité avec le template
                    'individu': None,
                })

        else:  # public == "individu"
            # Sondage de type individu : vérifier pour chaque individu concerné
            # Filtrer les rattachements selon les catégories définies dans le sondage
            rattachements_concernes = rattachements
            if sondage.categories_rattachements:
                # categories_rattachements est un MultiSelectField qui retourne une liste
                categories = [int(cat) for cat in sondage.categories_rattachements]
                rattachements_concernes = [r for r in rattachements if r.categorie in categories]

            # Vérifier pour chaque individu concerné
            for rattachement in rattachements_concernes:
                individu = rattachement.individu

                # Vérifier si cet individu a déjà répondu à ce sondage
                reponses_sondage = dict_reponses_individu.get(sondage.idsondage, set())
                if individu.pk not in reponses_sondage:
                    sondages_manquants.append({
                        'sondage': sondage,
                        'titre': sondage.titre,
                        'code': sondage.code,
                        'type': 'individu',
                        'article': None,  # Pour compatibilité avec le template
                        'individu': individu,
                    })

    return sondages_manquants


def Get_sondages_manquants_par_inscriptions(inscriptions):
    """
    Version optimisée : retourne les sondages manquants par individu pour une liste d'inscriptions.
    BATCH : 2-3 requêtes SQL au total peu importe le nombre d'inscriptions.

    Args:
        inscriptions: QuerySet ou liste d'instances Inscription

    Returns:
        dict[individu.pk] -> liste de sondages manquants
    """
    inscriptions_list = list(inscriptions)
    
    if not inscriptions_list:
        return {}

    # Extraire les individus, familles et structures
    individus = list({ins.individu for ins in inscriptions_list})
    individu_ids = [ind.pk for ind in individus]
    famille_ids = list({ins.famille_id for ins in inscriptions_list})
    structure_ids = list({ins.activite.structure_id for ins in inscriptions_list})

    # UNE requête pour tous les sondages actifs
    sondages = Sondage.objects.filter(
        structure__in=structure_ids,
        structure__visible=True
    )

    # UNE requête pour tous les répondants de ces individus
    repondants = SondageRepondant.objects.filter(
        sondage__in=sondages,
        individu__in=individu_ids
    ).select_related('sondage')

    # UNE requête pour tous les rattachements
    rattachements = Rattachement.objects.filter(
        famille__in=famille_ids,
        individu__deces=False
    ).select_related('individu')
    
    # Dict de rattachements par individu
    dict_rattachements = {r.individu_id: r for r in rattachements}

    # Construire les dicts de réponses
    dict_reponses_par_individu = {}
    for individu in individus:
        reponses_famille = set()
        reponses_individu = set()
        
        for r in repondants:
            if r.individu_id == individu.pk:
                if r.sondage.public == "famille":
                    reponses_famille.add(r.sondage_id)
                elif r.sondage.public == "individu":
                    reponses_individu.add(r.sondage_id)
        
        dict_reponses_par_individu[individu.pk] = {
            'famille': reponses_famille,
            'individu': reponses_individu
        }

    # Construire les résultats par individu
    dict_resultats = {}
    for individu in individus:
        sondages_manquants_individu = []
        reponses = dict_reponses_par_individu.get(individu.pk, {'famille': set(), 'individu': set()})
        rattachement = dict_rattachements.get(individu.pk)

        for sondage in sondages:
            # Sondage famille
            if sondage.public == "famille":
                if sondage.idsondage not in reponses['famille']:
                    sondages_manquants_individu.append({
                        'sondage': sondage,
                        'titre': sondage.titre,
                        'code': sondage.code,
                        'type': 'famille',
                        'article': None,
                        'individu': None,
                    })

            # Sondage individu
            else:
                # Vérifier la catégorie de rattachement si définie
                if rattachement and sondage.categories_rattachements:
                    categories = [int(c) for c in sondage.categories_rattachements]
                    if rattachement.categorie not in categories:
                        continue

                # Vérifier si l'individu a répondu
                if sondage.idsondage not in reponses['individu']:
                    sondages_manquants_individu.append({
                        'sondage': sondage,
                        'titre': sondage.titre,
                        'code': sondage.code,
                        'type': 'individu',
                        'article': None,
                        'individu': individu,
                    })

        dict_resultats[individu.pk] = sondages_manquants_individu

    return dict_resultats


def Get_sondages_manquants_individu(individu=None, famille=None, structure=None):
    """
    Retourne la liste des sondages que l'individu n'a pas encore complétés.

    - Pour les sondages de type "individu" : vérifie la réponse pour cet individu
    - Pour les sondages de type "famille" : vérifie si la famille a répondu

    Retourne une liste de dictionnaires compatibles avec le template existant.
    """

    sondages_manquants = []

    # Tous les sondages actifs de ces structures
    sondages = Sondage.objects.filter(
        structure__in=structure,
        structure__visible=True
    )

    # Réponses existantes
    repondants = SondageRepondant.objects.filter(
        sondage__in=sondages,
        individu=individu.idindividu
    )

    # Réponses famille
    reponses_famille = set(
        r.sondage_id for r in repondants
        if r.sondage.public == "famille"
    )

    # Réponses individu (uniquement pour cet individu)
    reponses_individu = set(
        r.sondage_id for r in repondants
        if r.sondage.public == "individu" and r.individu_id == individu.pk
    )

    # Parcours des sondages
    for sondage in sondages:

        # --- SONDAGE FAMILLE ---
        if sondage.public == "famille":
            if sondage.idsondage not in reponses_famille:
                sondages_manquants.append({
                    'sondage': sondage,
                    'titre': sondage.titre,
                    'code': sondage.code,
                    'type': 'famille',
                    'article': None,
                    'individu': None,
                })

        # --- SONDAGE INDIVIDU ---
        else:
            # Vérifier la catégorie de rattachement si définie
            if sondage.categories_rattachements:
                categories = [int(c) for c in sondage.categories_rattachements]
                if rattachement.categorie not in categories:
                    continue

            # Vérifier si l'individu a répondu
            if sondage.idsondage not in reponses_individu:
                sondages_manquants.append({
                    'sondage': sondage,
                    'titre': sondage.titre,
                    'code': sondage.code,
                    'type': 'individu',
                    'article': None,
                    'individu': individu,
                })

    return sondages_manquants