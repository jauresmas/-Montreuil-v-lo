"""Étape 1 : collecte multi-sources.

Sources (toutes ouvertes, sans compte) :
  * limite communale ............ API Découpage administratif (geo.api.gouv.fr)
  * IRIS -> quartiers ........... Géoplateforme IGN, WFS STATISTICALUNITS.IRISGE
  * aménagements cyclables ...... OpenStreetMap, historique complet via l'API ohsome
  * stationnement vélo / Vélib' . OpenStreetMap, historique complet via ohsome
  * linéaire de voirie .......... OpenStreetMap, agrégats annuels via ohsome

Chaque fichier brut est tracé dans 01_donnees/brutes/manifest.json
(URL, date d'extraction, nombre d'objets, empreinte SHA-256).

Usage : python 01_donnees/collecte.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402

SESSION = requests.Session()
SESSION.headers["User-Agent"] = C.USER_AGENT

# Filtre ohsome : tout ce qui peut porter un aménagement cyclable.
# La classification fine (et l'exclusion des cycleway=no) se fait à l'étape 2.
FILTRE_AMENAGEMENTS = (
    "type:way and ("
    " highway=cycleway"
    " or (highway in (path, footway, pedestrian, bridleway, track, service) and bicycle=designated)"
    " or cycleway=* or \"cycleway:left\"=* or \"cycleway:right\"=* or \"cycleway:both\"=*"
    " or \"oneway:bicycle\"=no or bicycle_road=yes or cyclestreet=yes"
    ")"
)
FILTRE_STATIONNEMENT = "amenity in (bicycle_parking, bicycle_rental)"
FILTRE_VOIRIE = (
    "type:way and highway in (primary, primary_link, secondary, secondary_link, "
    "tertiary, tertiary_link, unclassified, residential, living_street)"
)


def log(msg: str) -> None:
    print(f"[collecte {datetime.now():%H:%M:%S}] {msg}", flush=True)


def requete(methode: str, url: str, essais: int = 5, **kw) -> requests.Response:
    """Requête HTTP avec reprise exponentielle (serveurs publics parfois saturés)."""
    attente = 10
    for i in range(1, essais + 1):
        try:
            r = SESSION.request(methode, url, timeout=kw.pop("timeout", 600), **kw)
            if r.status_code == 200:
                return r
            log(f"  HTTP {r.status_code} sur {url} (essai {i}/{essais})")
        except requests.RequestException as exc:
            log(f"  {type(exc).__name__} sur {url} (essai {i}/{essais})")
        if i < essais:
            time.sleep(attente)
            attente *= 2
    raise RuntimeError(f"Échec définitif : {url}")


def ecrire(nom: str, contenu: bytes, manifest: list, source: str, url: str, nb: int | None) -> Path:
    chemin = C.DIR_BRUTES / nom
    chemin.write_bytes(contenu)
    manifest.append({
        "fichier": nom,
        "source": source,
        "url": url,
        "extrait_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nb_objets": nb,
        "octets": len(contenu),
        "sha256": hashlib.sha256(contenu).hexdigest(),
    })
    log(f"  -> {nom} ({nb if nb is not None else '-'} objets, {len(contenu)/1024:.0f} Ko)")
    return chemin


def bpolys(gdf: gpd.GeoDataFrame, champ_id: str | None = None, tampon=0, simpl=3) -> str:
    """Polygones au format GeoJSON attendu par ohsome (id facultatif pour groupBy)."""
    g = gdf.to_crs(C.CRS_METRIQUE).copy()
    g["geometry"] = g.geometry.buffer(tampon).simplify(simpl) if tampon else g.geometry.simplify(simpl)
    g = g.to_crs(C.CRS_WEB)
    feats = []
    for i, row in g.iterrows():
        props = {"id": str(row[champ_id]) if champ_id else str(i)}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": json.loads(gpd.GeoSeries([row.geometry]).to_json())["features"][0]["geometry"]})
    return json.dumps({"type": "FeatureCollection", "features": feats})


def main() -> None:
    manifest: list[dict] = []

    # 1. Limite communale -----------------------------------------------------
    log("Limite communale (geo.api.gouv.fr)")
    url = f"{C.GEO_API}/communes/{C.CODE_INSEE}?format=geojson&geometry=contour&fields=nom,code,population,surface,codeDepartement"
    r = requete("GET", url, timeout=60)
    ecrire("commune.geojson", r.content, manifest, "API Découpage administratif", url, 1)
    commune = gpd.read_file(C.DIR_BRUTES / "commune.geojson")

    # 2. IRIS (Géoplateforme IGN) -----------------------------------------------
    log("Contours IRIS (Géoplateforme IGN, WFS)")
    params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
              "typeNames": "STATISTICALUNITS.IRISGE:iris_ge", "outputFormat": "application/json",
              "CQL_FILTER": f"code_insee='{C.CODE_INSEE}'"}
    r = requete("GET", C.WFS_IGN, params=params, timeout=120)
    ecrire("iris.geojson", r.content, manifest, "IGN, contours IRIS", r.url, len(r.json()["features"]))
    iris = gpd.read_file(C.DIR_BRUTES / "iris.geojson")

    # 3. Fenêtre temporelle disponible chez ohsome ----------------------------------
    meta = requete("GET", f"{C.OHSOME}/metadata", timeout=60).json()
    fin = meta["extractRegion"]["temporalExtent"]["toTimestamp"]
    debut = f"{C.ANNEE_REFERENCE}-01-01"
    log(f"Historique OSM disponible jusqu'au {fin}")

    zone = bpolys(commune, tampon=60, simpl=5)

    # 4. Aménagements cyclables : historique complet --------------------------------
    log("Aménagements cyclables : historique complet OSM (ohsome, peut prendre 1-3 min)")
    url = f"{C.OHSOME}/elementsFullHistory/geometry"
    r = requete("POST", url, data={"bpolys": zone, "time": f"{debut},{fin}",
                                   "filter": FILTRE_AMENAGEMENTS, "properties": "tags,metadata"})
    ecrire("osm_amenagements_historique.geojson", r.content, manifest,
           "OpenStreetMap via ohsome (elementsFullHistory)", url, len(r.json()["features"]))

    # 5. Stationnement vélo et stations Vélib' --------------------------------------
    log("Stationnement vélo / Vélib' : historique complet OSM")
    r = requete("POST", url, data={"bpolys": zone, "time": f"{debut},{fin}",
                                   "filter": FILTRE_STATIONNEMENT, "properties": "tags,metadata"})
    ecrire("osm_stationnement_historique.geojson", r.content, manifest,
           "OpenStreetMap via ohsome (elementsFullHistory)", url, len(r.json()["features"]))

    # 6. Linéaire de voirie : commune (série annuelle) et IRIS (état actuel) ---------
    log("Linéaire de voirie (agrégats ohsome)")
    dates = [f"{a}-01-01" for a in range(C.ANNEE_REFERENCE, int(fin[:4]) + 1)] + [fin]
    url = f"{C.OHSOME}/elements/length"
    r = requete("POST", url, data={"bpolys": bpolys(commune, simpl=2), "time": ",".join(dates),
                                   "filter": FILTRE_VOIRIE})
    ecrire("voirie_longueur_annuelle.json", r.content, manifest, "OpenStreetMap via ohsome", url, len(dates))

    url = f"{C.OHSOME}/elements/length/groupBy/boundary"
    r = requete("POST", url, data={"bpolys": bpolys(iris, "code_iris", simpl=2), "time": fin,
                                   "filter": FILTRE_VOIRIE})
    ecrire("voirie_longueur_iris.json", r.content, manifest, "OpenStreetMap via ohsome", url, len(iris))

    # 7. Manifeste ------------------------------------------------------------------
    (C.DIR_BRUTES / "manifest.json").write_text(json.dumps({
        "commune": C.NOM_COMMUNE, "code_insee": C.CODE_INSEE,
        "osm_date_donnees": fin, "periode_historique": [debut, fin],
        "fichiers": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    log("Collecte terminée.")


if __name__ == "__main__":
    main()
