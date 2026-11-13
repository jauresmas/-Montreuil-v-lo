"""Étape 3 : publication des couches (GeoJSON + descripteur de service).

  * refuse de publier si le contrôle qualité est BLOQUANT ;
  * exige un validateur métier (--valide-par) si le contrôle comporte des ALERTES ;
  * archive la version actuellement publiée dans archives/<version>/ avant de la remplacer ;
  * produit pour chaque couche un descripteur de service (champs, alias, emprise, nb d'entités),
    une vignette SVG et une fiche dans le catalogue du portail ;
  * alimente les applications (04_applications/data/donnees.js).

Usage : python 03_publication/publication.py [--valide-par "Nom Prénom, service"]
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402

# Couleurs par type : mêmes valeurs que 04_applications/assets/commun.js (palette validée daltonisme)
COULEURS = {"Piste cyclable": "#2a78d6", "Bande cyclable": "#eb6834", "Double-sens cyclable": "#1baf7a",
            "Couloir bus-vélo": "#eda100", "Voie verte / mixte": "#e87ba4", "Vélorue": "#008300",
            "Autre (marquage partagé)": "#8a8a8a"}

ALIAS = {
    "id_local": "Identifiant local", "id_osm": "Identifiant OSM", "num_iti": "N° d'itinéraire",
    "code_com_d": "Commune (côté droit)", "ame_d": "Aménagement côté droit", "regime_d": "Régime côté droit",
    "sens_d": "Sens côté droit", "largeur_d": "Largeur côté droit (m)", "local_d": "Localisation côté droit",
    "statut_d": "Statut côté droit", "revet_d": "Revêtement côté droit", "code_com_g": "Commune (côté gauche)",
    "ame_g": "Aménagement côté gauche", "regime_g": "Régime côté gauche", "sens_g": "Sens côté gauche",
    "largeur_g": "Largeur côté gauche (m)", "local_g": "Localisation côté gauche", "statut_g": "Statut côté gauche",
    "revet_g": "Revêtement côté gauche", "access_ame": "Accessibilité", "date_maj": "Dernière modification",
    "trafic_vit": "Vitesse limite (km/h)", "lumiere": "Éclairage", "d_service": "Mise en service",
    "comm": "Commentaire", "source": "Source", "project_c": "Projection", "ref_geo": "Référentiel géométrique",
    "nom_voie": "Voie", "type_amenagement": "Type d'aménagement", "site_propre": "Site propre",
    "annee_realisation": "Année de réalisation", "periode": "Période", "nature": "Nature des travaux",
    "methode_datation": "Méthode de datation", "quartier": "Quartier", "longueur_m": "Longueur (m)",
    "controle": "Contrôle qualité", "osm_url": "Fiche OpenStreetMap",
    "osm_id": "Identifiant OSM", "type": "Type", "capacite": "Capacité (places)", "support": "Type de support",
    "couvert": "Couvert", "nom": "Nom", "operateur": "Opérateur / réseau", "annee_apparition": "Année d'apparition",
    "surface_ha": "Surface (ha)", "km_voirie": "Voirie (km)", "km": "Aménagements (km)",
    "km_pour_100km_voirie": "km d'aménagement / 100 km de voirie", "km_depuis_2020": "Réalisé depuis 2020 (km)",
    "code": "Code INSEE",
}

COUCHES = [
    {"id": "amenagements_cyclables", "titre": "Aménagements cyclables", "geometrie": "Ligne", "icone": "layer-line",
     "description": "Réseau cyclable de Montreuil au format du schéma national des aménagements cyclables (Etalab), "
                    "enrichi de l'année de réalisation, de la nature des travaux (création / requalification) et du quartier."},
    {"id": "stationnement_velo", "titre": "Stationnement vélo et stations Vélib'", "geometrie": "Point", "icone": "layer-points",
     "description": "Arceaux, abris, consignes et stations Vélib' ouverts au public, avec capacité et année d'apparition."},
    {"id": "quartiers", "titre": "Quartiers (regroupement IRIS)", "geometrie": "Polygone", "icone": "layer-polygon",
     "description": "Onze quartiers reconstitués par regroupement des 41 IRIS INSEE/IGN, avec linéaire de voirie "
                    "et densité d'aménagements."},
    {"id": "commune", "titre": "Limite communale", "geometrie": "Polygone", "icone": "layer-polygon",
     "description": "Contour communal (API Découpage administratif)."},
]


def log(msg: str) -> None:
    print(f"[publication {datetime.now():%H:%M:%S}] {msg}", flush=True)


def type_champ(valeurs) -> str:
    v = [x for x in valeurs if x is not None]
    if not v:
        return "Texte"
    if all(isinstance(x, bool) for x in v):
        return "Booléen"
    if all(isinstance(x, int) and not isinstance(x, bool) for x in v):
        return "Entier"
    if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        return "Réel"
    return "Texte"


def coords(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        yield c
    elif t in ("LineString", "MultiPoint"):
        yield from c
    elif t in ("Polygon", "MultiLineString"):
        for r in c:
            yield from r
    elif t == "MultiPolygon":
        for p in c:
            for r in p:
                yield from r


def emprise(fc):
    xs, ys = [], []
    for f in fc["features"]:
        for x, y in coords(f["geometry"]):
            xs.append(x)
            ys.append(y)
    return [round(min(xs), 5), round(min(ys), 5), round(max(xs), 5), round(max(ys), 5)]


# ---------------------------------------------------------------------------
# Vignettes SVG (600 x 400) des éléments du catalogue
# ---------------------------------------------------------------------------
class Projection:
    def __init__(self, bbox, w=600, h=400, marge=28):
        x0, y0, x1, y1 = bbox
        k = math.cos(math.radians((y0 + y1) / 2))
        sx = (w - 2 * marge) / ((x1 - x0) * k)
        sy = (h - 2 * marge) / (y1 - y0)
        self.s = min(sx, sy)
        self.k, self.x0, self.y1 = k, x0, y1
        self.ox = (w - (x1 - x0) * k * self.s) / 2
        self.oy = (h - (y1 - y0) * self.s) / 2

    def __call__(self, x, y):
        return f"{self.ox + (x - self.x0) * self.k * self.s:.1f},{self.oy + (self.y1 - y) * self.s:.1f}"


def chemins(geom, p):
    t, c = geom["type"], geom["coordinates"]
    if t == "LineString":
        c = [c]
    elif t == "Polygon":
        c = c
    elif t == "MultiPolygon":
        c = [r for poly in c for r in poly]
    elif t != "MultiLineString":
        return ""
    return " ".join("M" + " L".join(p(x, y) for x, y in ligne) for ligne in c)


def vignette(nom, fond, commune, p, contenu):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400"><rect width="600" height="400" fill="{fond[0]}"/>'
           f'<path d="{chemins(commune["features"][0]["geometry"], p)}" fill="{fond[1]}" stroke="{fond[2]}" stroke-width="2"/>'
           f'{contenu}</svg>')
    (C.DIR_SERVICES / "vignettes" / f"{nom}.svg").write_text(svg, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--valide-par", default=None, help="référent métier qui valide une version comportant des alertes")
    args = ap.parse_args()

    qc = json.loads((C.DIR_SORTIES / "controle_qualite.json").read_text(encoding="utf-8"))
    ind = json.loads((C.DIR_SORTIES / "indicateurs.json").read_text(encoding="utf-8"))
    version = ind["meta"]["version"]
    if qc["statut_global"] == "BLOQUANT":
        log("Contrôle qualité BLOQUANT : publication refusée. Voir 02_traitement/sorties/rapport_controle_qualite.md")
        return 2
    if qc["statut_global"] == "ALERTE" and not args.valide_par:
        alertes = [c["controle"] for c in qc["controles"] if c["statut"] == "ALERTE"]
        log("Alertes à lever ou accepter : " + " ; ".join(alertes))
        log('Relancer avec --valide-par "Nom, service" après validation métier.')
        return 3

    # -- Archivage de la version en ligne --------------------------------------------
    hist_path = C.DIR_SERVICES / "historique_publications.json"
    historique = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    ancien = C.DIR_SERVICES / "indicateurs.json"
    if ancien.exists():
        v_old = json.loads(ancien.read_text(encoding="utf-8"))["meta"]["version"]
        dest = C.DIR_ARCHIVES / v_old
        if dest.exists():
            dest = C.DIR_ARCHIVES / f"{v_old}_{datetime.now():%H%M%S}"
        shutil.copytree(C.DIR_SERVICES, dest, ignore=shutil.ignore_patterns("historique_publications.json"))
        log(f"Version {v_old} archivée -> {dest.relative_to(C.ROOT)}")

    # -- Copie des couches et descripteurs de service ----------------------------------
    (C.DIR_SERVICES / "vignettes").mkdir(exist_ok=True)
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    couches, services = {}, []
    for c in COUCHES:
        fc = json.loads((C.DIR_SORTIES / f"{c['id']}.geojson").read_text(encoding="utf-8"))
        shutil.copy2(C.DIR_SORTIES / f"{c['id']}.geojson", C.DIR_SERVICES / f"{c['id']}.geojson")
        props = [f["properties"] for f in fc["features"]]
        champs = [{"nom": k, "alias": ALIAS.get(k, k), "type": type_champ([p.get(k) for p in props])}
                  for k in (props[0].keys() if props else [])]
        desc = {"id": c["id"], "titre": c["titre"], "type": "Couche d'entités", "geometrie": c["geometrie"],
                "nb_entites": len(fc["features"]), "emprise_wgs84": emprise(fc), "systeme": "EPSG:4326",
                "champs": champs, "version": version, "modifie": maintenant,
                "url": f"services/{c['id']}.geojson", "description": c["description"]}
        (C.DIR_SERVICES / f"{c['id']}.service.json").write_text(json.dumps(desc, ensure_ascii=False, indent=2), encoding="utf-8")
        couches[c["id"]] = fc
        services.append(desc)
        log(f"Service publié : {c['titre']} ({len(fc['features'])} entités)")
    etalab = f"amenagements_cyclables_{C.CODE_INSEE}_schema_etalab.geojson"
    shutil.copy2(C.DIR_SORTIES / etalab, C.DIR_SERVICES / etalab)
    for f in ("indicateurs.json", "controle_qualite.json", "rapport_controle_qualite.md"):
        shutil.copy2(C.DIR_SORTIES / f, C.DIR_SERVICES / f)

    # -- Vignettes ---------------------------------------------------------------
    commune = couches["commune"]
    p = Projection(emprise(commune))
    lignes = "".join(
        f'<path d="{chemins(f["geometry"], p)}" fill="none" stroke="{COULEURS.get(f["properties"]["type_amenagement"], "#888")}" '
        f'stroke-width="{3.2 if f["properties"]["site_propre"] else 2}" stroke-linecap="round"/>'
        for f in couches["amenagements_cyclables"]["features"])
    vignette("amenagements_cyclables", ("#eef0f2", "#ffffff", "#9aa3ad"), commune, p, lignes)
    pts = "".join(
        f'<circle cx="{p(*f["geometry"]["coordinates"]).split(",")[0]}" cy="{p(*f["geometry"]["coordinates"]).split(",")[1]}" '
        f'r="{6 if f["properties"]["type"] == "Station Vélib\'" else 3.5}" fill="{"#6250d6" if f["properties"]["type"] == "Station Vélib\'" else "#2a78d6"}" '
        f'stroke="#fff" stroke-width="1.2"/>'
        for f in couches["stationnement_velo"]["features"])
    vignette("stationnement_velo", ("#eef0f2", "#ffffff", "#9aa3ad"), commune, p, pts)
    vmax = max(f["properties"]["km_pour_100km_voirie"] or 0 for f in couches["quartiers"]["features"])
    rampe = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]
    polys = "".join(
        f'<path d="{chemins(f["geometry"], p)}" fill="{rampe[min(5, int(6 * (f["properties"]["km_pour_100km_voirie"] or 0) / (vmax + 0.01)))]}" '
        f'stroke="#fff" stroke-width="2"/>' for f in couches["quartiers"]["features"])
    vignette("quartiers", ("#eef0f2", "#ffffff", "#9aa3ad"), commune, p, polys)
    vignette("commune", ("#eef0f2", "#dfe7f1", "#1c5cab"), commune, p, "")
    # Vignette carte web : réseau par année (rampe séquentielle)
    a0, a1 = C.ANNEE_REFERENCE, ind["meta"]["annee_partielle"]
    seq = ["#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]

    def c_annee(a):
        if a is None:
            return "#b9bec5"
        return seq[min(len(seq) - 1, int((a - a0) / max(1, a1 - a0) * (len(seq) - 1)))]
    lignes_a = "".join(
        f'<path d="{chemins(f["geometry"], p)}" fill="none" stroke="{c_annee(f["properties"]["annee_realisation"])}" stroke-width="2.6" stroke-linecap="round"/>'
        for f in couches["amenagements_cyclables"]["features"])
    vignette("carte_web", ("#e9ecef", "#f7f8f9", "#9aa3ad"), commune, p,
             lignes_a + '<rect x="0" y="0" width="600" height="34" fill="#ffffff"/><rect x="0" y="34" width="600" height="1" fill="#d4d4d4"/>'
             '<rect x="12" y="10" width="120" height="14" rx="3" fill="#007ac2"/><rect x="0" y="35" width="44" height="365" fill="#ffffff"/>'
             '<rect x="14" y="52" width="16" height="16" rx="2" fill="#6a6a6a"/><rect x="14" y="84" width="16" height="16" rx="2" fill="#b0b0b0"/>'
             '<rect x="14" y="116" width="16" height="16" rx="2" fill="#b0b0b0"/><rect x="190" y="352" width="300" height="30" rx="4" fill="#ffffff" stroke="#d4d4d4"/>'
             '<rect x="206" y="365" width="268" height="4" rx="2" fill="#007ac2"/>')
    # Vignette tableau de bord : thème sombre, barres annuelles réelles
    pa = [x for x in ind["par_annee"] if x["annee"]]
    kmax = max(x["km"] for x in pa) or 1
    barres = "".join(f'<rect x="{318 + i * 20}" y="{300 - 120 * x["km"] / kmax:.1f}" width="14" height="{120 * x["km"] / kmax:.1f}" rx="2" fill="#3987e5"/>'
                     for i, x in enumerate(pa))
    tuiles = "".join(f'<rect x="{12 + i * 97}" y="44" width="89" height="58" rx="3" fill="#2b2b2b"/>'
                     f'<rect x="{24 + i * 97}" y="62" width="{40 + (i * 13) % 30}" height="16" rx="2" fill="#f0efec"/>' for i in range(6))
    dash = ('<rect width="600" height="400" fill="#1e1e1e"/><rect width="600" height="34" fill="#151515"/>'
            '<rect x="12" y="11" width="190" height="12" rx="2" fill="#f0efec"/>' + tuiles +
            '<rect x="12" y="110" width="290" height="280" rx="3" fill="#2b2b2b"/><rect x="310" y="110" width="278" height="200" rx="3" fill="#2b2b2b"/>'
            + barres + '<rect x="310" y="318" width="278" height="72" rx="3" fill="#2b2b2b"/>')
    p2 = Projection(emprise(commune), w=290, h=280, marge=14)
    lignes_d = "".join(f'<path d="{chemins(f["geometry"], p2)}" fill="none" stroke="{"#3987e5" if (f["properties"]["annee_realisation"] or 0) >= 2020 else "#5b5b5b"}" stroke-width="1.6"/>'
                       for f in couches["amenagements_cyclables"]["features"])
    (C.DIR_SERVICES / "vignettes" / "tableau_de_bord.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400">{dash}<g transform="translate(12,110)">{lignes_d}</g></svg>', encoding="utf-8")

    # -- Catalogue du portail ------------------------------------------------------------
    t = ind["totaux"]
    catalogue = [
        {"id": "carte", "titre": "Carte des aménagements cyclables", "type": "Application web", "icone": "map",
         "description": "Carte interactive : réseau par type, par année de réalisation ou par nature de travaux, "
                        "curseur temporel, filtres par quartier, recherche d'adresse.",
         "url": "carte/index.html", "vignette": "../03_publication/services/vignettes/carte_web.svg",
         "partage": "Public", "tags": ["vélo", "mobilité", "carte"]},
        {"id": "tableau", "titre": "Tableau de bord des élus", "type": "Tableau de bord", "icone": "dashboard",
         "description": "Indicateurs clés, réalisations annuelles, bilans par mandat et par quartier.",
         "url": "tableau-de-bord/index.html", "vignette": "../03_publication/services/vignettes/tableau_de_bord.svg",
         "partage": "Organisation", "tags": ["élus", "indicateurs", "pilotage"]},
    ] + [
        {"id": s["id"], "titre": s["titre"], "type": "Couche d'entités", "icone": next(c["icone"] for c in COUCHES if c["id"] == s["id"]),
         "description": s["description"], "url": f"../03_publication/services/{s['id']}.geojson",
         "vignette": f"../03_publication/services/vignettes/{s['id']}.svg", "partage": "Public",
         "nb_entites": s["nb_entites"], "geometrie": s["geometrie"], "service": s["id"],
         "tags": ["données ouvertes", "OSM"]} for s in services
    ] + [
        {"id": "etalab", "titre": "Export au schéma national (transport.data.gouv.fr)", "type": "Fichier GeoJSON", "icone": "file",
         "description": "Fichier conforme au schéma Etalab des aménagements cyclables, prêt à être déposé sur "
                        "transport.data.gouv.fr / data.gouv.fr.", "url": f"../03_publication/services/{etalab}",
         "vignette": "../03_publication/services/vignettes/amenagements_cyclables.svg", "partage": "Public",
         "tags": ["schéma national", "interopérabilité"]},
        {"id": "qc", "titre": "Rapport de contrôle qualité", "type": "Document", "icone": "file-report",
         "description": f"Résultat des {len(qc['controles'])} contrôles automatiques de la version {version}.",
         "url": "../03_publication/services/rapport_controle_qualite.md", "vignette": None, "partage": "Organisation",
         "tags": ["qualité"]},
    ]
    for it in catalogue:
        it.update({"proprietaire": "Service SIG", "modifie": maintenant, "version": version})
    (C.DIR_SERVICES / "catalogue.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=2), encoding="utf-8")

    historique = [h for h in historique if h["version"] != version]
    historique.append({"version": version, "publie_le": maintenant, "donnees_osm": ind["meta"]["date_donnees_osm"],
                       "statut_qc": qc["statut_global"], "valide_par": args.valide_par,
                       "km_total": t["km_total"], "nb_objets": t["nb_objets"]})
    hist_path.write_text(json.dumps(historique, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- Données des applications --------------------------------------------------------
    paquet = {"version": version, "indicateurs": ind, "qc": qc, "catalogue": catalogue, "historique": historique,
              "services": {s["id"]: {k: v for k, v in s.items() if k != "description"} for s in services},
              "couches": couches}
    (C.DIR_APPLIS_DATA / "donnees.js").write_text(
        "/* Généré par 03_publication/publication.py, ne pas modifier à la main */\n"
        "window.MV_DATA = " + json.dumps(paquet, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    log(f"Version {version} publiée ({t['km_total']} km), applications à jour : 04_applications/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
