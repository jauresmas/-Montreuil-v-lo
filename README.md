# Montreuil à vélo : suivi annuel des aménagements cyclables

Une **carte interactive** des aménagements cyclables réalisés chaque année à Montreuil (93) et un **tableau de bord**
de synthèse, produits par une chaîne SIG complète et automatisée : données → traitement → publication →
carte web et tableau de bord → mise à jour annuelle. Tout est construit sur des **données réelles** et des
briques ouvertes, sans logiciel sous licence.

> Projet indépendant, non officiel. Données © contributeurs OpenStreetMap (ODbL), © IGN.

## Voir en ligne

**https://jauresmas.github.io/-Montreuil-v-lo/**

- **Portail** : présentation, catalogue des données, état de la chaîne, contrôle qualité et versions
- **Carte web** : couches, légende, filtres, fonds de carte, recherche d'adresse, fiches au clic, curseur temporel
- **Tableau de bord** : indicateurs, graphiques liés entre eux, liste des réalisations, carte, sélecteurs

Les applications acceptent des paramètres d'URL pour partager une vue précise :
`carte/index.html?fond=sombre&mode=annee&annee=2020` · `tableau-de-bord/index.html?periode=m2020`.

Pour ouvrir le projet en local, double-cliquer `ouvrir_portail.bat` (ou `04_applications/index.html`).
Une connexion Internet est nécessaire pour les fonds IGN et les bibliothèques (Calcite, MapLibre, Chart.js).

| Carte web (couleur par année, fond sombre, 2020) | Tableau de bord (mandat 2020-2026) |
|---|---|
| ![Carte web](docs/captures/04_carte_annee_2020_fond_sombre.png) | ![Tableau de bord](docs/captures/06_tableau_de_bord_mandat_2020.png) |

Les autres captures (portail, fiche au clic, affichage mobile) sont dans `docs/captures/`.

## Chiffres clés (données OSM au 27/07/2026)

| Indicateur | Valeur |
|---|---|
| Réseau cyclable | **75,3 km**, dont 17,1 km en site propre (23 %) |
| Réalisé depuis 2014 | 54,3 km (40,8 km créés, 13,5 km requalifiés) |
| Mandat 2014-2020 / 2020-2026 | 17,2 km / **37,1 km**, soit un rythme de 2,9 puis 5,7 km/an |
| Année record | 2020 : +14,7 km |
| Densité | 61 km d'aménagements pour 100 km de rues (de 31 à 91 selon les quartiers) |
| Stationnement | 3 295 places recensées sur 358 sites, 28 stations Vélib' |

## La chaîne de production

| Étape | Script / dossier | Ce qui est fait |
|---|---|---|
| **1. Données** | `01_donnees/collecte.py` | Collecte multi-sources : historique complet OSM des aménagements et du stationnement (API ohsome), IRIS (WFS Géoplateforme IGN), limite communale (geo.api.gouv.fr), linéaire de voirie. Manifeste des sources avec empreinte SHA-256. |
| **2. Traitement** | `02_traitement/traitement.py`, `osm_vers_schema.py` | Nettoyage (géométries, micro-segments, doublons), normalisation au **schéma national des aménagements cyclables**, Lambert-93, datation annuelle, rattachement aux quartiers, **15 contrôles qualité** dont certains bloquants. |
| **3. Publication** | `03_publication/publication.py` | Couches publiées en GeoJSON avec leur descripteur de service (champs, alias, emprise), vignettes, catalogue, export au schéma national. Refus si un contrôle bloque, validateur obligatoire en cas d'alerte, archivage de la version précédente. |
| **4. Carte web + tableau de bord** | `04_applications/` | Portail, carte web et tableau de bord, en HTML statique (MapLibre GL JS, Chart.js, Calcite Design System). |
| **5. Mise à jour annuelle** | `05_mise_a_jour/`, `.github/workflows/` | Campagne en deux temps : traitement et rapport d'écarts, puis publication après validation métier. Journal, checklist, modèle de saisie des chantiers livrés. |

### Méthode de datation (clé du « réalisé chaque année »)

Le réseau actuel est découpé en tronçons de 25 m. Chaque tronçon est comparé à l'historique OpenStreetMap
au 1er janvier de chaque année (tampon de 7 m, 80 % de recouvrement) :

- l'année d'apparition d'un aménagement **du même type** donne l'**année de réalisation** ;
- s'il existait déjà un aménagement **d'un autre type**, c'est une **requalification** (ex. bande → piste) ;
- le réseau présent au 1er janvier 2014 est classé « Avant 2014 » ;
- un `start_date` renseigné dans OSM sur une piste en site propre est prioritaire.

## Ce qui garantit la réussite du projet

1. **Un référentiel unique et normé** : le schéma national Etalab rend la donnée comparable d'une année à
   l'autre et publiable telle quelle sur transport.data.gouv.fr.
2. **Une date de réalisation fiable** : ici reconstituée par l'historique OSM. En production, elle vient de la
   voirie (plans de récolement, fiches chantier, DAO), rapprochée chaque année via `modele_saisie_chantiers.csv`.
3. **Deux clés avant publication** : un contrôle qualité automatique qui bloque, puis une validation métier
   humaine tracée (`--valide-par` en local, fusion de la pull request sur GitHub).
4. **La traçabilité** : manifeste des sources, journal des campagnes, historique Git, historique des
   publications visible sur le portail.
5. **Des indicateurs définis avec les élus et stables** : définitions écrites (km de voie, site propre,
   densité, création ou requalification) et inchangées d'une année sur l'autre, pour que les séries restent comparables.
6. **L'automatisation et un calendrier** : une campagne automatique le 15 janvier. Le paramétrage est
   concentré dans `config.py`, ce qui facilite la transmission.
7. **L'accessibilité** : palette testée pour le daltonisme, vue tableau de chaque graphique, affichage mobile.
8. **L'ouverture et le retour à la source** : données sous ODbL ; les erreurs repérées sont corrigées dans OSM,
   ce qui améliore la campagne suivante.

## Mise à jour annuelle sur GitHub

Deux workflows GitHub Actions font tourner la chaîne sans poste de travail :

1. **`mise-a-jour-annuelle.yml`**, le 15 janvier (ou à la demande depuis l'onglet Actions) : collecte, traitement
   et contrôle qualité. Si rien ne bloque, il ouvre une **pull request** dont la description est le rapport
   d'écarts ; la couche des écarts est jointe au workflow pour être ouverte dans QGIS.
2. **`publier-et-mettre-en-ligne.yml`**, à chaque envoi sur `main` : quand une pull request de campagne est
   fusionnée, il republie les services avec le nom de la personne qui a fusionné (la fusion vaut validation
   métier), puis met le site en ligne sur GitHub Pages.

Réglages à faire une fois dans le dépôt (**Settings**) :

- **Pages** → *Build and deployment* → *Source* : **GitHub Actions** ;
- **Actions** → *General* → *Workflow permissions* : cocher **Allow GitHub Actions to create and approve pull requests**.

## Lancer une campagne en local (Windows)

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
05_mise_a_jour\maj_annuelle.bat     :: collecte, traitement, contrôle, rapport d'écarts
05_mise_a_jour\publier.bat          :: après relecture de la checklist : archive la version précédente et republie
```

## Arborescence

```
index.html                   redirection vers le portail (page d'accueil du site)
config.py                    paramètres communs (commune, année de référence, tolérances)
01_donnees/                  collecte.py, brutes/ (seul manifest.json est versionné)
02_traitement/               traitement.py, osm_vers_schema.py, sorties/ (GPKG Lambert-93, GeoJSON, QC, indicateurs)
03_publication/              publication.py, services/ (couches, descripteurs, vignettes, catalogue)
04_applications/             index.html (portail), carte/, tableau-de-bord/, assets/, data/donnees.js
05_mise_a_jour/              maj_annuelle.py, checklist, modèle de saisie, journal
.github/workflows/           campagne annuelle et mise en ligne
docs/captures/               captures d'écran des applications
```

## Limites connues

- La date de cartographie dans OSM peut suivre de quelques semaines à quelques mois la date des travaux.
  Les premières années (2014-2016) reflètent aussi le rattrapage de la cartographie.
- 2026 est partiel : l'API ohsome a environ trois mois de décalage (données au 27/07/2026).
- Le linéaire est mesuré en axe de voie : une rue équipée des deux côtés compte une fois.
- Trois voies portaient une piste notée sur la route alors qu'elle est déjà dessinée à part (boulevard Chanzy,
  boulevard de la Boissière), soit 0,44 km compté deux fois. Le traitement les corrige automatiquement (contrôle C10),
  mais la correction n'est pas faite dans OSM : il faut la reporter dans OSM pour assainir la source.
- Les quartiers sont un regroupement des 41 IRIS de l'INSEE, pas le découpage officiel des quartiers de la Ville.
- Le stationnement est un inventaire OSM : sa progression reflète aussi l'effort de recensement.

## Briques utilisées

Python (geopandas, shapely, pyproj) · API ohsome (HeiGIT) · Géoplateforme IGN (WFS, WMTS, géocodage) ·
API Découpage administratif · Calcite Design System (Apache-2.0) · MapLibre GL JS (BSD-3) · Chart.js (MIT) ·
GitHub Actions et GitHub Pages.
