# Rapport de contrôle qualité (version 2026.11.13)

- Données OSM au **27/07/2026**, traitement du 13/11/2026 21:23 UTC
- Statut global : **✅ OK**

| Code | Contrôle | Statut | Résultat | Détail |
|---|---|---|---|---|
| C01 | Complétude des sources brutes | ✅ OK | 7/7 fichiers |  |
| C02 | Géométries invalides corrigées (make_valid) | ✅ OK | 0 |  |
| C03 | Micro-segments < 2 m et géométries vides supprimés | ℹ️ INFO | 3 |  |
| C04 | Doublons géométriques exacts supprimés | ✅ OK | 0 |  |
| C10 | Doublons piste sur la route et piste dessinée à part | ℹ️ INFO | 3 voie(s) corrigée(s) (0.44 km) ; 0 tronçon(s) restant(s) à vérifier | Corrigées : Boulevard Chanzy, Boulevard de la Boissière.  |
| C05 | Valeurs conformes aux listes du schéma national | ✅ OK | 0 écart(s) |  |
| C06 | Champs obligatoires renseignés | ✅ OK | 0 valeur(s) manquante(s) |  |
| C07 | Unicité de l'identifiant id_local | ✅ OK | 0 doublon(s) |  |
| C08 | Emprise : objets dans la commune (+ tampon de limite) | ✅ OK | 0 hors emprise |  |
| C09 | Cohérence : somme des bilans annuels = linéaire total | ✅ OK | 75.31 km / 75.31 km |  |
| C14 | Continuité : sous-réseaux disjoints (tolérance 3 m) | ℹ️ INFO | 42 sous-réseaux ; le principal porte 79% du linéaire |  |
| C11 | Complétude attributaire (part du linéaire renseigné) | ℹ️ INFO | nom de voie 87% ; revêtement 84% ; vitesse (trafic_vit) 59% ; éclairage 58% ; largeur 4% |  |
| C15 | Datation | ℹ️ INFO | 72% du linéaire daté (dont 0.0% par start_date) ; 28% antérieur à 2014 |  |
| C12 | Variation du linéaire vs version publiée | ✅ OK | -0.4% (75.6 -> 75.3 km) | version publiée : 2026.11.13 |
| C13 | Fraîcheur des données OSM | ✅ OK | 109 jours | données au 27/07/2026 (décalage de mise à jour de l'API ohsome) |

Règle de publication : tout contrôle **BLOQUANT** interdit la republication ; les **ALERTES** doivent être levées ou acceptées lors de la validation métier.