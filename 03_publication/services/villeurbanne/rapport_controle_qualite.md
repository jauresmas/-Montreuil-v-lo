# Rapport de contrôle qualité (version 2026.11.26)

- Données OSM au **27/07/2026**, traitement du 26/11/2026 22:14 UTC
- Statut global : **⚠️ ALERTE**

| Code | Contrôle | Statut | Résultat | Détail |
|---|---|---|---|---|
| C01 | Complétude des sources brutes | ✅ OK | 7/7 fichiers |  |
| C02 | Géométries invalides corrigées (make_valid) | ✅ OK | 0 |  |
| C03 | Micro-segments < 2 m et géométries vides supprimés | ℹ️ INFO | 8 |  |
| C04 | Doublons géométriques exacts supprimés | ✅ OK | 0 |  |
| C10 | Doublons piste sur la route et piste dessinée à part | ℹ️ INFO | 2 voie(s) corrigée(s) (0.15 km) ; 0 tronçon(s) restant(s) à vérifier | Corrigées : Rue Charlie Chaplin, Rue Francis de Pressensé.  |
| C05 | Valeurs conformes aux listes du schéma national | ✅ OK | 0 écart(s) |  |
| C06 | Champs obligatoires renseignés | ✅ OK | 0 valeur(s) manquante(s) |  |
| C07 | Unicité de l'identifiant id_local | ✅ OK | 0 doublon(s) |  |
| C08 | Emprise : objets dans la commune (+ tampon de limite) | ✅ OK | 0 hors emprise |  |
| C09 | Cohérence : somme des bilans annuels = linéaire total | ✅ OK | 112.41 km / 112.41 km |  |
| C14 | Continuité : sous-réseaux disjoints (tolérance 3 m) | ℹ️ INFO | 50 sous-réseaux ; le principal porte 86% du linéaire |  |
| C11 | Complétude attributaire (part du linéaire renseigné) | ℹ️ INFO | nom de voie 77% ; revêtement 95% ; vitesse (trafic_vit) 65% ; éclairage 68% ; largeur 7% |  |
| C15 | Datation | ℹ️ INFO | 78% du linéaire daté (dont 0.2% par start_date) ; 22% antérieur à 2014 |  |
| C12 | Variation du linéaire vs version publiée | ℹ️ INFO | première publication |  |
| C13 | Fraîcheur des données OSM | ⚠️ ALERTE | 122 jours | données au 27/07/2026 (décalage de mise à jour de l'API ohsome) |

Règle de publication : tout contrôle **BLOQUANT** interdit la republication ; les **ALERTES** doivent être levées ou acceptées lors de la validation métier.