"""Paramètres communs de la chaîne « Montreuil à vélo ».

Tous les scripts des étapes 01 à 05 importent ce module : c'est le seul
endroit à modifier pour changer de commune, de millésime de référence ou
de chemins de sortie.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- Territoire -------------------------------------------------------------
CODE_INSEE = "93048"
NOM_COMMUNE = "Montreuil"
DEPARTEMENT = "Seine-Saint-Denis (93)"

# --- Datation ---------------------------------------------------------------
# Le réseau présent dans OSM au 1er janvier de ANNEE_REFERENCE est classé
# « Avant <ANNEE_REFERENCE> ». Chaque tronçon apparu ensuite reçoit son année.
ANNEE_REFERENCE = 2014
# Mandats municipaux (pour les vues « élus » du tableau de bord)
MANDATS = [
    {"id": "m2014", "libelle": "Mandat 2014-2020", "debut": 2014, "fin": 2019},
    {"id": "m2020", "libelle": "Mandat 2020-2026", "debut": 2020, "fin": 2026},
]

# --- Projections ------------------------------------------------------------
CRS_WEB = "EPSG:4326"
CRS_METRIQUE = "EPSG:2154"  # Lambert-93, pour toutes les longueurs

# --- Paramètres de traitement -----------------------------------------------
TAMPON_COMMUNE_M = 12        # garde les boulevards dont l'axe suit la limite communale
LONGUEUR_TRONCON_M = 25      # découpage fin pour dater les prolongements de voies
TAMPON_PRESENCE_M = 7        # tolérance de recouvrement entre deux versions OSM
TAUX_PRESENCE = 0.8          # part d'un tronçon couverte pour le considérer présent
LONGUEUR_MIN_M = 2           # en dessous : micro-segment supprimé au contrôle qualité

# --- Sources ------------------------------------------------------------------
USER_AGENT = "montreuil-velo/1.0 (chaine SIG open source)"
GEO_API = "https://geo.api.gouv.fr"
WFS_IGN = "https://data.geopf.fr/wfs/ows"
OHSOME = "https://api.ohsome.org/v1"

# --- Arborescence -----------------------------------------------------------
DIR_DONNEES = ROOT / "01_donnees"
DIR_BRUTES = DIR_DONNEES / "brutes"
DIR_TRAITEMENT = ROOT / "02_traitement"
DIR_SORTIES = DIR_TRAITEMENT / "sorties"
DIR_PUBLICATION = ROOT / "03_publication"
DIR_SERVICES = DIR_PUBLICATION / "services"
DIR_APPLIS = ROOT / "04_applications"
DIR_APPLIS_DATA = DIR_APPLIS / "data"
DIR_MAJ = ROOT / "05_mise_a_jour"
DIR_ARCHIVES = ROOT / "archives"

for _d in (DIR_BRUTES, DIR_SORTIES, DIR_SERVICES, DIR_APPLIS_DATA, DIR_ARCHIVES):
    _d.mkdir(parents=True, exist_ok=True)
