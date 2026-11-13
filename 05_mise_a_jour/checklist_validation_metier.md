# Checklist de validation métier : campagne annuelle

À remplir par le référent mobilité / voirie avant chaque republication.
Version examinée : `__________`  Date : `__________`  Référent : `__________`

## 1. Contrôle qualité automatique
- [ ] Aucun contrôle **BLOQUANT** dans `02_traitement/sorties/rapport_controle_qualite.md`
- [ ] Chaque **ALERTE** est comprise et acceptée, ou corrigée à la source (OSM ou saisie Ville)
- [ ] Variation du linéaire par rapport à la version en ligne (contrôle C12) cohérente avec les travaux de l'année

## 2. Rapport d'écarts (`05_mise_a_jour/a_valider/rapport_ecarts_<version>.md`)
- [ ] Les ajouts correspondent à des chantiers effectivement livrés (rapprochement avec `modele_saisie_chantiers.csv`)
- [ ] Les suppressions sont justifiées (aménagement supprimé, ou erreur de cartographie corrigée)
- [ ] Les requalifications (ex. bande → piste) sont confirmées
- [ ] Contrôle terrain ou sur photo aérienne des 5 plus gros ajouts

## 3. Chiffres destinés aux élus
- [ ] Linéaire total, linéaire réalisé dans l'année et part en site propre relus
- [ ] Bilans par quartier vérifiés (pas d'écart incompréhensible d'un quartier à l'autre)
- [ ] Mention « année en cours, données partielles » présente si la campagne a lieu avant le 31/12

## 4. Décision
- [ ] **Publier** : `python 05_mise_a_jour/maj_annuelle.py --publier --valide-par "Nom, service"`
- [ ] **Reporter** : motif → ____________________________________________

Signature : ____________________
