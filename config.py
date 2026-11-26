"""Paramètres communs de la chaîne « Montreuil à vélo ».

La chaîne est pensée pour Montreuil et ses campagnes de mise à jour annuelles.
Tous les scripts des étapes 01 à 05 importent ce module : c'est ici que se
règlent l'année de référence, les mandats, les tolérances de traitement et
les chemins, pour relancer chaque année la même chaîne sans toucher au code.

Elle peut aussi tourner sur une autre commune française, en donnant son code
INSEE au lancement :

    python 05_mise_a_jour/maj_annuelle.py --commune 34172

(ou la variable d'environnement MV_COMMUNE). Sans précision, c'est Montreuil.
Chaque commune a ses propres dossiers : 01_donnees/brutes/<commune>/,
02_traitement/sorties/<commune>/, 03_publication/services/<commune>/,
04_applications/data/<commune>/, archives/<commune>/.
"""
import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- Sources ------------------------------------------------------------------
USER_AGENT = "montreuil-velo/1.0 (chaine SIG open source)"
GEO_API = "https://geo.api.gouv.fr"
WFS_IGN = "https://data.geopf.fr/wfs/ows"
OHSOME = "https://api.ohsome.org/v1"

# --- Territoire -------------------------------------------------------------
COMMUNE_PAR_DEFAUT = "93048"

# Réglages propres à certaines communes. Une commune absente de cette liste
# fonctionne aussi : son nom et son département sont lus sur geo.api.gouv.fr,
# et ses quartiers sont ses IRIS.
COMMUNES = {
    "93048": {
        "nom": "Montreuil",
        "departement": "Seine-Saint-Denis (93)",
        "dossier": "montreuil",
        # Les IRIS numérotés (« Bas Montreuil Est 1 », « 2 »…) sont regroupés,
        # puis leurs noms mis en forme :
        "quartiers": {
            "Bas Montreuil Est": "Bas-Montreuil Est",
            "Bas Montreuil Ouest": "Bas-Montreuil Ouest",
            "Bel-Air Grands Pêchers": "Bel-Air / Grands-Pêchers",
            "Branly Boissière": "Branly / Boissière",
            "Centre Ville Jean Moulin Espoir": "Centre-ville / Jean-Moulin / Espoir",
            "La Noue-Clos Français-Guilands": "La Noue / Clos-Français / Guilands",
            "Montreau Ruffins Clos Arachis": "Montreau / Ruffins / Clos-Arachis",
            "Paul Signac Murs à Pêches": "Paul-Signac / Murs-à-Pêches",
            "Ramenas Fabien Lagrange": "Ramenas / Fabien / Lagrange",
            "Solidarité Carnot": "Solidarité / Carnot",
            "Villiers Barbusse": "Villiers / Barbusse",
        },
    },
}


def _code_demande() -> str:
    """Code INSEE passé avec --commune (prioritaire) ou MV_COMMUNE, sinon Montreuil."""
    code = os.environ.get("MV_COMMUNE", "")
    for i, arg in enumerate(sys.argv):
        if arg == "--commune" and i + 1 < len(sys.argv):
            code = sys.argv[i + 1]
        elif arg.startswith("--commune="):
            code = arg.split("=", 1)[1]
    code = (code or COMMUNE_PAR_DEFAUT).strip().upper()
    if not re.fullmatch(r"\d[\dAB]\d{3}", code):
        raise SystemExit(f"Code INSEE invalide : {code!r} (exemple : 93048 pour Montreuil)")
    os.environ["MV_COMMUNE"] = code  # transmis aux étapes lancées par maj_annuelle.py
    return code


def _dossier(nom: str) -> str:
    """« Saint-Denis » -> « saint-denis » : nom de dossier et paramètre d'URL des applis."""
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sans_accents.lower()).strip("-")


def _infos_commune(code: str) -> dict:
    """Nom et département d'une commune hors liste, lus une fois sur geo.api.gouv.fr puis gardés en cache."""
    cache = ROOT / "01_donnees" / "brutes" / "communes.json"
    connues = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    if code not in connues:
        url = f"{GEO_API}/communes/{code}?fields=nom,departement"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"Commune {code} introuvable sur geo.api.gouv.fr ({exc})")
        dep = d.get("departement") or {}
        connues[code] = {"nom": d["nom"], "departement": f"{dep.get('nom', '')} ({dep.get('code', code[:2])})"}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(connues, ensure_ascii=False, indent=2), encoding="utf-8")
    return connues[code]


def de(nom: str) -> str:
    """« de Montreuil », « d'Aubervilliers », « du Havre », « des Lilas »."""
    if nom.startswith("Le "):
        return "du " + nom[3:]
    if nom.startswith("Les "):
        return "des " + nom[4:]
    if nom[:1].lower() in "aeiouyàâéèêîïôûœ" and not nom.startswith(("La ", "L'")):
        return "d'" + nom
    return "de " + nom


CODE_INSEE = _code_demande()
_reglages = COMMUNES.get(CODE_INSEE) or _infos_commune(CODE_INSEE)
NOM_COMMUNE = _reglages["nom"]
DEPARTEMENT = _reglages["departement"]
DOSSIER_COMMUNE = _reglages.get("dossier") or _dossier(NOM_COMMUNE)
NOMS_QUARTIERS = _reglages.get("quartiers", {})
EST_PAR_DEFAUT = CODE_INSEE == COMMUNE_PAR_DEFAUT

# --- Datation ---------------------------------------------------------------
# Le réseau présent dans OSM au 1er janvier de ANNEE_REFERENCE est classé
# « Avant <ANNEE_REFERENCE> ». Chaque tronçon apparu ensuite reçoit son année.
ANNEE_REFERENCE = 2014
# Mandats municipaux (pour les vues par mandat du tableau de bord)
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

# --- Arborescence (un dossier par commune) ------------------------------------
DIR_DONNEES = ROOT / "01_donnees"
DIR_BRUTES = DIR_DONNEES / "brutes" / DOSSIER_COMMUNE
DIR_TRAITEMENT = ROOT / "02_traitement"
DIR_SORTIES = DIR_TRAITEMENT / "sorties" / DOSSIER_COMMUNE
DIR_PUBLICATION = ROOT / "03_publication"
DIR_SERVICES = DIR_PUBLICATION / "services" / DOSSIER_COMMUNE
DIR_APPLIS = ROOT / "04_applications"
DIR_APPLIS_DATA = DIR_APPLIS / "data" / DOSSIER_COMMUNE
DIR_MAJ = ROOT / "05_mise_a_jour"
DIR_ARCHIVES = ROOT / "archives" / DOSSIER_COMMUNE

for _d in (DIR_BRUTES, DIR_SORTIES, DIR_SERVICES, DIR_APPLIS_DATA, DIR_ARCHIVES):
    _d.mkdir(parents=True, exist_ok=True)
