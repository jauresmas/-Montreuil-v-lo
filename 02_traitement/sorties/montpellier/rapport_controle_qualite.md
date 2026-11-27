# Rapport de contrôle qualité (version 2026.11.27)

- Données OSM au **27/07/2026**, traitement du 27/11/2026 10:33 UTC
- Statut global : **⚠️ ALERTE**

| Code | Contrôle | Statut | Résultat | Détail |
|---|---|---|---|---|
| C01 | Complétude des sources brutes | ✅ OK | 7/7 fichiers |  |
| C02 | Géométries invalides corrigées (make_valid) | ℹ️ INFO | 1 |  |
| C03 | Micro-segments < 2 m et géométries vides supprimés | ℹ️ INFO | 3 |  |
| C04 | Doublons géométriques exacts supprimés | ✅ OK | 0 |  |
| C10 | Doublons piste sur la route et piste dessinée à part | ⚠️ ALERTE | 14 voie(s) corrigée(s) (1.33 km) ; 2 tronçon(s) restant(s) à vérifier | Corrigées : Avenue Georges Frêche, Avenue de Maurin, Avenue de la Pompignane, Avenue du Pont Juvénal, Boulevard Vieussens, Boulevard d'Antigone, Boulevard de Strasbourg, Carrefour Jules Rimet, Pont Jean Zuccarelli, Route de Ganges, Rue Doria, Rue Gerhardt, Rue Rouget de Lisle, Rue Saint-Louis. Restants signalés dans le champ « controle ». |
| C05 | Valeurs conformes aux listes du schéma national | ✅ OK | 0 écart(s) |  |
| C06 | Champs obligatoires renseignés | ✅ OK | 0 valeur(s) manquante(s) |  |
| C07 | Unicité de l'identifiant id_local | ✅ OK | 0 doublon(s) |  |
| C08 | Emprise : objets dans la commune (+ tampon de limite) | ✅ OK | 0 hors emprise |  |
| C09 | Cohérence : somme des bilans annuels = linéaire total | ✅ OK | 190.20 km / 190.20 km |  |
| C14 | Continuité : sous-réseaux disjoints (tolérance 3 m) | ℹ️ INFO | 143 sous-réseaux ; le principal porte 20% du linéaire |  |
| C11 | Complétude attributaire (part du linéaire renseigné) | ℹ️ INFO | nom de voie 40% ; revêtement 62% ; vitesse (trafic_vit) 30% ; éclairage 32% ; largeur 9% |  |
| C15 | Datation | ℹ️ INFO | 61% du linéaire daté (dont 4.3% par start_date) ; 39% antérieur à 2014 |  |
| C12 | Variation du linéaire vs version publiée | ℹ️ INFO | première publication |  |
| C13 | Fraîcheur des données OSM | ⚠️ ALERTE | 123 jours | données au 27/07/2026 (décalage de mise à jour de l'API ohsome) |

Règle de publication : tout contrôle **BLOQUANT** interdit la republication ; les **ALERTES** doivent être levées ou acceptées lors de la validation métier.