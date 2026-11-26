"""Étape 2 : traitement : nettoyage, normalisation, datation, contrôle qualité.

Entrées  : 01_donnees/brutes/<commune>/*
Sorties  : 02_traitement/sorties/<commune>/
  <commune>_velo.gpkg ............................ couches Lambert-93 (travail SIG)
  amenagements_cyclables.geojson ................. couche enrichie (WGS84, publication)
  amenagements_cyclables_<code INSEE>_schema_etalab.geojson  export conforme au schéma national
  stationnement_velo.geojson, quartiers.geojson, commune.geojson
  indicateurs.json ............................... chiffres clés pour le tableau de bord
  controle_qualite.json / rapport_controle_qualite.md

Méthode de datation : le réseau actuel est découpé en tronçons de 25 m. Pour chaque
tronçon on regarde, au 1er janvier de chaque année, s'il était déjà couvert dans
OpenStreetMap (tampon de 8 m, 80 % de recouvrement) :
  * par un aménagement de même type  -> année de réalisation de l'aménagement actuel
  * par un aménagement quel qu'il soit -> année d'apparition sur le réseau
Si les deux diffèrent, il s'agit d'une requalification (ex. bande -> piste).

Code retour : 0 = OK / ALERTE, 2 = contrôle BLOQUANT (la publication sera refusée).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, shape
from shapely.ops import substring

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from osm_vers_schema import (AME_VALEURS, PRIORITE, REGIME_VALEURS, REVET_VALEURS,  # noqa: E402
                             SENS_VALEURS, classer)

ETALAB = ["id_local", "id_osm", "num_iti", "code_com_d", "ame_d", "regime_d", "sens_d", "largeur_d",
          "local_d", "statut_d", "revet_d", "code_com_g", "ame_g", "regime_g", "sens_g", "largeur_g",
          "local_g", "statut_g", "revet_g", "access_ame", "date_maj", "trafic_vit", "lumiere",
          "d_service", "comm", "source", "project_c", "ref_geo"]
ENRICHIS = ["nom_voie", "type_amenagement", "site_propre", "annee_realisation", "periode", "nature",
            "methode_datation", "quartier", "longueur_m", "controle", "osm_url"]

# Type des stations de vélos en libre-service (Vélib', Vélo'v, Vélomagg…), nom du réseau dans le champ « reseau »
LIBRE_SERVICE = "Station en libre-service"


def log(msg: str) -> None:
    print(f"[traitement {datetime.now():%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
def charger_historique(nom: str) -> gpd.GeoDataFrame:
    d = json.loads((C.DIR_BRUTES / nom).read_text(encoding="utf-8"))
    rows = []
    for f in d["features"]:
        p = f["properties"]
        rows.append({
            "osm_id": p["@osmId"],
            "vf": p["@validFrom"], "vt": p["@validTo"],
            "tags": {k: v for k, v in p.items() if not k.startswith("@")},
            "geometry": shape(f["geometry"]) if f.get("geometry") else None,
        })
    g = gpd.GeoDataFrame(rows, geometry="geometry", crs=C.CRS_WEB)
    g["vf"] = pd.to_datetime(g["vf"], utc=True)
    g["vt"] = pd.to_datetime(g["vt"], utc=True)
    return g


def lignes(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    t = geom.geom_type
    if t == "LineString":
        return [geom]
    if t == "MultiLineString":
        return list(geom.geoms)
    if t == "Polygon":
        return [LineString(geom.exterior.coords)]
    if t in ("MultiPolygon", "GeometryCollection"):
        return [l for g in geom.geoms for l in lignes(g)]
    return []


def natif(v):
    """Convertit une valeur pandas/numpy en type JSON natif."""
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 2)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float):
        return round(v, 2)
    return v


def ecrire_geojson(gdf: gpd.GeoDataFrame, chemin: Path, champs: list[str]) -> None:
    g = gdf.to_crs(C.CRS_WEB)
    geoms = shapely.set_precision(g.geometry.values, 1e-6)
    feats = []
    for (_, row), geom in zip(g.iterrows(), geoms):
        feats.append({"type": "Feature",
                      "properties": {c: natif(row[c]) for c in champs},
                      "geometry": shapely.geometry.mapping(geom)})
    chemin.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                 ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# ---------------------------------------------------------------------------
# Datation
# ---------------------------------------------------------------------------
def premiere_presence_continue(P: np.ndarray) -> np.ndarray:
    """Indice du premier instantané à partir duquel le tronçon est présent sans interruption."""
    n, k = P.shape
    idx = np.full(n, k - 1)
    for j in range(k - 2, -1, -1):
        continu = P[:, j] & (idx == j + 1)
        idx[continu] = j
    return idx


def lisser(valeurs: list[int], max_run: int = 2) -> list[int]:
    """Supprime les micro-ruptures internes (<= 50 m) dues aux retouches de géométrie OSM."""
    v = list(valeurs)
    runs, i = [], 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[j + 1] == v[i]:
            j += 1
        runs.append((i, j))
        i = j + 1
    for r in range(1, len(runs) - 1):
        a, b = runs[r]
        if b - a + 1 <= max_run and v[runs[r - 1][0]] == v[runs[r + 1][0]]:
            for x in range(a, b + 1):
                v[x] = v[runs[r - 1][0]]
    return v


def main() -> int:
    debut_traitement = datetime.now(timezone.utc)
    controles: list[dict] = []

    def controle(code, libelle, statut, valeur, detail=""):
        controles.append({"code": code, "controle": libelle, "statut": statut,
                          "valeur": valeur, "detail": detail})
        log(f"  QC {code} [{statut}] {libelle} : {valeur}")

    # -- C01 Sources -----------------------------------------------------------
    attendus = ["manifest.json", "commune.geojson", "iris.geojson", "osm_amenagements_historique.geojson",
                "osm_stationnement_historique.geojson", "voirie_longueur_annuelle.json", "voirie_longueur_iris.json"]
    manquants = [f for f in attendus if not (C.DIR_BRUTES / f).exists() or (C.DIR_BRUTES / f).stat().st_size < 50]
    controle("C01", "Complétude des sources brutes", "BLOQUANT" if manquants else "OK",
             f"{len(attendus) - len(manquants)}/{len(attendus)} fichiers", ", ".join(manquants))
    if manquants:
        return 2
    manifest = json.loads((C.DIR_BRUTES / "manifest.json").read_text(encoding="utf-8"))

    # -- Référentiels ----------------------------------------------------------
    commune = gpd.read_file(C.DIR_BRUTES / "commune.geojson").to_crs(C.CRS_METRIQUE)
    limite = commune.geometry.iloc[0]
    zone = limite.buffer(C.TAMPON_COMMUNE_M)
    iris = gpd.read_file(C.DIR_BRUTES / "iris.geojson").to_crs(C.CRS_METRIQUE)
    iris["quartier"] = iris["nom_iris"].str.replace(r"\s+\d+$", "", regex=True).map(lambda n: C.NOMS_QUARTIERS.get(n, n))
    quartiers = iris.dissolve("quartier", as_index=False)[["quartier", "geometry"]]
    quartiers["surface_ha"] = (quartiers.area / 1e4).round(1)
    log(f"{len(iris)} IRIS regroupés en {len(quartiers)} quartiers")

    # -- Historique OSM des aménagements --------------------------------------------
    hist = charger_historique("osm_amenagements_historique.geojson").to_crs(C.CRS_METRIQUE)
    nb_versions = len(hist)
    attrs = hist["tags"].map(classer)
    hist = hist[attrs.notna()].copy()
    hist["attr"] = attrs[attrs.notna()]
    hist["type"] = hist["attr"].map(lambda a: a["type_amenagement"])
    invalides = int((~hist.geometry.is_valid).sum())
    hist["geometry"] = shapely.make_valid(hist.geometry.values)
    vt_max = hist["vt"].max()
    log(f"{nb_versions} versions OSM lues, {len(hist)} portent un aménagement ; données au {vt_max:%d/%m/%Y}")

    # -- Réseau actuel : découpe à la commune, explosion, nettoyage --------------------
    actuel = hist[hist["vt"] == vt_max].copy()
    actuel["geometry"] = actuel.geometry.intersection(zone)
    rows = []
    for _, r in actuel.iterrows():
        for l in lignes(r.geometry):
            rows.append({**{k: r[k] for k in ("osm_id", "vf", "tags", "attr", "type")}, "geometry": l})
    actuel = gpd.GeoDataFrame(rows, geometry="geometry", crs=C.CRS_METRIQUE)
    vides = int(actuel.geometry.is_empty.sum())
    micro = int((actuel.length < C.LONGUEUR_MIN_M).sum())
    actuel = actuel[~actuel.geometry.is_empty & (actuel.length >= C.LONGUEUR_MIN_M)]
    cle = pd.Series(shapely.to_wkb(shapely.normalize(actuel.geometry.values), hex=True), index=actuel.index) + actuel["type"]
    doublons = int(cle.duplicated().sum())
    actuel = actuel[~cle.duplicated()].reset_index(drop=True)
    controle("C02", "Géométries invalides corrigées (make_valid)", "OK" if invalides == 0 else "INFO", invalides)
    controle("C03", f"Micro-segments < {C.LONGUEUR_MIN_M} m et géométries vides supprimés", "INFO", micro + vides)
    controle("C04", "Doublons géométriques exacts supprimés", "OK" if doublons == 0 else "INFO", doublons)
    log(f"Réseau actuel : {len(actuel)} voies, {actuel.length.sum() / 1000:.1f} km")

    # -- C10 Doublons : piste notée sur la route ET dessinée à part ----------------------
    # Convention OSM : si la piste est tracée comme une voie séparée, la route doit porter
    # cycleway:*=separate. On applique cette convention aux routes encore notées « track »
    # le long d'une piste séparée (80 % de la route à moins de 10 m). Les autres côtés
    # (bande, couloir bus, double-sens) sont conservés ; la route disparaît s'il ne reste rien.
    cles_piste = ("cycleway", "cycleway:both", "cycleway:left", "cycleway:right")
    sp_osm = actuel["attr"].map(lambda a: a["site_propre_osm"])
    piste_route = ~sp_osm & actuel["tags"].map(lambda t: any(t.get(k) in ("track", "opposite_track") for k in cles_piste))
    corriges, supprimes, km_corr = [], [], 0.0
    if sp_osm.any() and piste_route.any():
        u = shapely.union_all(shapely.buffer(actuel.geometry[sp_osm].values, 10))
        cand = actuel[piste_route]
        frac = shapely.length(shapely.intersection(cand.geometry.values, u)) / cand.length.values
        for i in cand.index[frac >= 0.8]:
            tags = {k: ("separate" if k in cles_piste and v in ("track", "opposite_track") else v)
                    for k, v in actuel.at[i, "tags"].items()}
            attr = classer(tags)
            km_corr += actuel.geometry[i].length / 1000
            corriges.append(f"{actuel.at[i, 'attr']['nom_voie'] or actuel.at[i, 'osm_id']}")
            if attr is None:
                supprimes.append(i)
            else:
                actuel.at[i, "tags"], actuel.at[i, "attr"], actuel.at[i, "type"] = tags, attr, attr["type_amenagement"]
        actuel = actuel.drop(index=supprimes).reset_index(drop=True)
    noms_corr = sorted(set(corriges))
    log(f"Doublons piste corrigés : {len(corriges)} voie(s), {km_corr:.2f} km ({', '.join(noms_corr) or 'aucune'})")

    # -- Découpage en tronçons de 25 m --------------------------------------------
    t_feat, t_rang, t_geom = [], [], []
    for i, geom in enumerate(actuel.geometry):
        L = geom.length
        n = max(1, int(round(L / C.LONGUEUR_TRONCON_M)))
        for k in range(n):
            t_feat.append(i)
            t_rang.append(k)
            t_geom.append(substring(geom, L * k / n, L * (k + 1) / n))
    t_feat = np.array(t_feat)
    t_geom = np.array(t_geom, dtype=object)
    t_len = shapely.length(t_geom)
    t_type = actuel["type"].values[t_feat]
    log(f"{len(t_geom)} tronçons de ~{C.LONGUEUR_TRONCON_M} m à dater")

    # -- Instantanés annuels ----------------------------------------------------
    annee_fin = vt_max.year
    dates = [pd.Timestamp(f"{a}-01-01", tz="UTC") for a in range(C.ANNEE_REFERENCE, annee_fin + 1)] + [vt_max]
    P_any = np.zeros((len(t_geom), len(dates)), bool)
    P_typ = np.zeros_like(P_any)
    for k, t in enumerate(dates):
        snap = hist[hist["vt"] >= vt_max] if k == len(dates) - 1 else hist[(hist["vf"] <= t) & (hist["vt"] > t)]
        if snap.empty:
            continue
        tout = shapely.union_all(shapely.buffer(snap.geometry.values, C.TAMPON_PRESENCE_M))
        shapely.prepare(tout)
        P_any[:, k] = shapely.length(shapely.intersection(t_geom, tout)) / t_len >= C.TAUX_PRESENCE
        for ty in PRIORITE:
            m = t_type == ty
            sub = snap[snap["type"] == ty]
            if not m.any() or sub.empty:
                continue
            u = shapely.union_all(shapely.buffer(sub.geometry.values, C.TAMPON_PRESENCE_M))
            P_typ[m, k] = shapely.length(shapely.intersection(t_geom[m], u)) / t_len[m] >= C.TAUX_PRESENCE
        log(f"  instantané {t:%Y-%m-%d} : {len(snap)} voies, {P_any[:, k].mean():.0%} du réseau actuel déjà présent")

    def annee_de(idx: np.ndarray) -> np.ndarray:
        # 0 = avant l'année de référence ; sinon année de réalisation
        out = np.array([dates[i].year - 1 for i in idx])
        out[idx == 0] = 0
        out[idx == len(dates) - 1] = annee_fin
        return out

    a_typ = annee_de(premiere_presence_continue(P_typ))
    a_any = annee_de(premiere_presence_continue(P_any))
    methode = np.array(["Historique OSM"] * len(t_geom), dtype=object)

    # start_date renseigné sur un aménagement en site propre : prioritaire
    for i, r in actuel.iterrows():
        sd = r["tags"].get("start_date") or r["tags"].get("cycleway:start_date")
        m = re.match(r"^(\d{4})", str(sd or ""))
        if m and (r["attr"]["site_propre_osm"] or r["tags"].get("cycleway:start_date")):
            y = int(m.group(1))
            if 1950 <= y <= annee_fin:
                sel = t_feat == i
                a_typ[sel] = y if y >= C.ANNEE_REFERENCE else 0
                a_any[sel] = np.minimum(a_any[sel], a_typ[sel])
                methode[sel] = "start_date OSM"

    # -- Recomposition des tronçons en objets homogènes ---------------------------------
    pieces = []
    for i, geom in enumerate(actuel.geometry):
        sel = np.where(t_feat == i)[0]
        at = lisser(list(a_typ[sel]))
        aa = lisser(list(a_any[sel]))
        aa = [min(x, y) for x, y in zip(aa, at)]
        n, L = len(sel), geom.length
        k0 = 0
        for k in range(1, n + 1):
            if k == n or at[k] != at[k0] or aa[k] != aa[k0]:
                pieces.append({"feat": i, "geometry": substring(geom, L * k0 / n, L * k / n),
                               "a_typ": at[k0], "a_any": aa[k0], "methode": methode[sel[k0]]})
                k0 = k
    seg = gpd.GeoDataFrame(pieces, geometry="geometry", crs=C.CRS_METRIQUE)
    seg = seg.join(actuel.drop(columns="geometry"), on="feat")

    # -- Attributs (schéma national + enrichissements) ------------------------------
    A = pd.DataFrame(list(seg["attr"]), index=seg.index)
    seg["id_osm"] = seg["osm_id"].str.replace("way/", "", regex=False)
    seg["id_local"] = C.CODE_INSEE + "-W" + seg["id_osm"] + "-" + (seg.groupby("osm_id").cumcount() + 1).astype(str)
    seg["num_iti"] = None
    seg["code_com_d"] = C.CODE_INSEE
    seg["code_com_g"] = C.CODE_INSEE
    for c in ("ame_d", "ame_g", "regime_d", "regime_g", "sens_d", "sens_g", "largeur_d", "largeur_g",
              "revet_d", "revet_g", "trafic_vit", "lumiere", "nom_voie", "type_amenagement", "site_propre"):
        seg[c] = A[c]
    seg["local_d"] = None
    seg["local_g"] = None
    seg["statut_d"] = np.where(seg["ame_d"] != "AUCUN", "EN SERVICE", None)
    seg["statut_g"] = np.where(seg["ame_g"] != "AUCUN", "EN SERVICE", None)
    seg["access_ame"] = None
    seg["date_maj"] = seg["vf"].dt.strftime("%Y-%m-%d")
    seg["d_service"] = seg["tags"].map(lambda t: t.get("start_date") if re.match(r"^\d{4}", str(t.get("start_date", ""))) else None)
    seg.loc[~A["site_propre_osm"], "d_service"] = None
    seg["comm"] = None
    seg["source"] = "OpenStreetMap"
    seg["project_c"] = "WGS84"
    seg["ref_geo"] = "OpenStreetMap"
    seg["annee_realisation"] = seg["a_typ"].map(lambda a: None if a == 0 else int(a))
    seg["periode"] = seg["a_typ"].map(lambda a: f"Avant {C.ANNEE_REFERENCE}" if a == 0 else str(a))
    seg["nature"] = np.where(seg["a_any"] < seg["a_typ"], "Requalification", "Création")
    seg.loc[seg["a_typ"] == 0, "nature"] = "Existant"
    seg["methode_datation"] = seg["methode"]
    seg["longueur_m"] = seg.length.round(1)
    seg["osm_url"] = "https://www.openstreetmap.org/" + seg["osm_id"]
    seg["controle"] = None

    # Quartier : celui qui contient le milieu du tronçon
    milieux = gpd.GeoDataFrame(geometry=seg.geometry.interpolate(0.5, normalized=True), crs=C.CRS_METRIQUE)
    j = gpd.sjoin_nearest(milieux, quartiers[["quartier", "geometry"]], how="left")
    seg["quartier"] = j.groupby(level=0)["quartier"].first()

    # -- C10 (suite) : doublons résiduels, sur une partie seulement de la route ------------------
    sp = seg[A["site_propre_osm"]]
    sur_route = seg[(~A["site_propre_osm"]) & (seg["type_amenagement"] == "Piste cyclable")]
    nb_dbl, km_dbl = 0, 0.0
    if len(sp) and len(sur_route):
        u = shapely.union_all(shapely.buffer(sp.geometry.values, 10))
        frac = shapely.length(shapely.intersection(sur_route.geometry.values, u)) / sur_route.length.values
        dbl = sur_route.index[frac >= 0.8]
        seg.loc[dbl, "controle"] = "Doublon potentiel : piste aussi tracée en voie séparée"
        nb_dbl, km_dbl = len(dbl), float(seg.loc[dbl].length.sum() / 1000)
    controle("C10", "Doublons piste sur la route et piste dessinée à part",
             "ALERTE" if nb_dbl else ("INFO" if corriges else "OK"),
             f"{len(corriges)} voie(s) corrigée(s) ({km_corr:.2f} km) ; {nb_dbl} tronçon(s) restant(s) à vérifier",
             ("Corrigées : " + ", ".join(noms_corr) + ". " if noms_corr else "")
             + ("Restants signalés dans le champ « controle »." if nb_dbl else ""))

    # -- Contrôles de conformité au schéma ------------------------------------------
    def hors_liste(col, valeurs):
        s = seg[col].dropna()
        return int((~s.isin(valeurs)).sum())
    ecarts = sum(hors_liste(c, AME_VALEURS) for c in ("ame_d", "ame_g")) + \
        sum(hors_liste(c, REGIME_VALEURS) for c in ("regime_d", "regime_g")) + \
        sum(hors_liste(c, SENS_VALEURS) for c in ("sens_d", "sens_g")) + \
        sum(hors_liste(c, REVET_VALEURS) for c in ("revet_d", "revet_g"))
    controle("C05", "Valeurs conformes aux listes du schéma national", "OK" if ecarts == 0 else "BLOQUANT", f"{ecarts} écart(s)")
    obligatoires = ["id_local", "code_com_d", "ame_d", "date_maj", "code_com_g", "ame_g"]
    vides_obl = int(seg[obligatoires].isna().sum().sum())
    controle("C06", "Champs obligatoires renseignés", "OK" if vides_obl == 0 else "BLOQUANT", f"{vides_obl} valeur(s) manquante(s)")
    dup_id = int(seg["id_local"].duplicated().sum())
    controle("C07", "Unicité de l'identifiant id_local", "OK" if dup_id == 0 else "BLOQUANT", f"{dup_id} doublon(s)")
    hors_zone = int((~seg.geometry.within(zone.buffer(0.5))).sum())
    controle("C08", "Emprise : objets dans la commune (+ tampon de limite)", "OK" if hors_zone == 0 else "BLOQUANT", f"{hors_zone} hors emprise")

    # -- Indicateurs -------------------------------------------------------------
    km = seg.length / 1000
    total = float(km.sum())
    par_annee = []
    cumul = float(km[seg["a_typ"] == 0].sum())
    for a in [0] + list(range(C.ANNEE_REFERENCE, annee_fin + 1)):
        m = seg["a_typ"] == a
        if a:
            cumul += float(km[m].sum())
        par_annee.append({
            "annee": a or None, "libelle": f"Avant {C.ANNEE_REFERENCE}" if a == 0 else (f"{a} (au {vt_max:%d/%m})" if a == annee_fin else str(a)),
            "km": round(float(km[m].sum()), 2),
            "km_creation": round(float(km[m & (seg["nature"] == "Création")].sum()), 2),
            "km_requalification": round(float(km[m & (seg["nature"] == "Requalification")].sum()), 2),
            "km_site_propre": round(float(km[m & seg["site_propre"]].sum()), 2),
            "km_cumule": round(cumul, 2),
            "par_type": {t: round(float(km[m & (seg["type_amenagement"] == t)].sum()), 2) for t in PRIORITE},
        })
    somme = sum(float(km[seg["a_typ"] == a].sum()) for a in [0] + list(range(C.ANNEE_REFERENCE, annee_fin + 1)))
    controle("C09", "Cohérence : somme des bilans annuels = linéaire total", "OK" if abs(somme - total) < 0.001 else "BLOQUANT",
             f"{somme:.2f} km / {total:.2f} km")

    voirie_serie = json.loads((C.DIR_BRUTES / "voirie_longueur_annuelle.json").read_text(encoding="utf-8"))["result"]
    km_voirie = voirie_serie[-1]["value"] / 1000
    voirie_iris = json.loads((C.DIR_BRUTES / "voirie_longueur_iris.json").read_text(encoding="utf-8"))["groupByResult"]
    v_iris = pd.Series({g["groupByObject"]: g["result"][-1]["value"] / 1000 for g in voirie_iris})
    iris["km_voirie"] = iris["code_iris"].map(v_iris).fillna(0)
    quartiers["km_voirie"] = quartiers["quartier"].map(iris.groupby("quartier")["km_voirie"].sum()).round(2)

    par_quartier = []
    for q in quartiers.itertuples():
        m = seg["quartier"] == q.quartier
        k = float(km[m].sum())
        par_quartier.append({
            "quartier": q.quartier, "km": round(k, 2), "km_voirie": round(float(q.km_voirie), 2),
            "km_pour_100km_voirie": round(100 * k / q.km_voirie, 1) if q.km_voirie else None,
            "part_site_propre": round(float(km[m & seg["site_propre"]].sum()) / k, 3) if k else 0,
            "km_depuis_2020": round(float(km[m & (seg["a_typ"] >= 2020)].sum()), 2),
            "surface_ha": float(q.surface_ha),
        })
    quartiers = quartiers.merge(pd.DataFrame(par_quartier)[["quartier", "km", "km_pour_100km_voirie", "km_depuis_2020"]], on="quartier")

    # Continuité : sous-réseaux disjoints (tolérance 3 m)
    blocs = shapely.get_parts(shapely.union_all(shapely.buffer(seg.geometry.values, 3)))
    longueurs_blocs = sorted((float(shapely.length(shapely.intersection(seg.geometry.values, b)).sum()) for b in blocs), reverse=True)
    part_principal = longueurs_blocs[0] / sum(longueurs_blocs) if longueurs_blocs else 0
    controle("C14", "Continuité : sous-réseaux disjoints (tolérance 3 m)", "INFO",
             f"{len(blocs)} sous-réseaux ; le principal porte {part_principal:.0%} du linéaire")

    # Complétude attributaire
    def part_km(mask):
        return float(km[mask].sum() / total) if total else 0
    completude = {
        "nom de voie": part_km(seg["nom_voie"].notna()),
        "revêtement": part_km(seg["revet_d"].notna() | seg["revet_g"].notna()),
        "vitesse (trafic_vit)": part_km(seg["trafic_vit"].notna()),
        "éclairage": part_km(seg["lumiere"].notna()),
        "largeur": part_km(seg["largeur_d"].notna() | seg["largeur_g"].notna()),
    }
    controle("C11", "Complétude attributaire (part du linéaire renseigné)", "INFO",
             " ; ".join(f"{k} {v:.0%}" for k, v in completude.items()))
    part_sd = part_km(seg["methode_datation"] == "start_date OSM")
    part_av = part_km(seg["a_typ"] == 0)
    controle("C15", "Datation", "INFO",
             f"{1 - part_av:.0%} du linéaire daté (dont {part_sd:.1%} par start_date) ; {part_av:.0%} antérieur à {C.ANNEE_REFERENCE}")

    # -- Stationnement vélo et vélos en libre-service -----------------------------------
    hs = charger_historique("osm_stationnement_historique.geojson").to_crs(C.CRS_METRIQUE)
    hs = hs[hs.geometry.notna() & ~hs.geometry.is_empty].copy()
    hs["amenity"] = hs["tags"].map(lambda t: t.get("amenity"))
    hs = hs[~hs["tags"].map(lambda t: t.get("access") in ("private", "no"))]
    hs["capacite"] = hs["tags"].map(lambda t: int(t["capacity"]) if str(t.get("capacity", "")).isdigit() else None)

    def est_velib(t):
        txt = " ".join(str(t.get(k, "")) for k in ("network", "brand", "operator", "name")).lower()
        return "vélib" in txt or "velib" in txt or "smovengo" in txt

    def type_stat(t):
        if t.get("amenity") == "bicycle_rental":
            # Station d'un réseau (borne, réseau nommé) ou simple loueur de vélos
            if est_velib(t) or t.get("bicycle_rental") in ("docking_station", "dropoff_point") or t.get("network"):
                return LIBRE_SERVICE
            return "Location de vélos"
        return "Stationnement vélo"

    def reseau(t):
        if type_stat(t) != LIBRE_SERVICE:
            return None
        return "Vélib'" if est_velib(t) else (t.get("network") or t.get("brand") or t.get("operator"))
    SUPPORTS = {"stands": "Arceaux", "wall_loops": "Pince-roues", "rack": "Râtelier", "shed": "Abri / consigne",
                "building": "Consigne collective", "lockers": "Box individuels", "bollard": "Potelets",
                "two-tier": "Double étage", "ground_slots": "Rainures au sol", "floor": "Stationnement libre"}
    hs["type"] = hs["tags"].map(type_stat)
    hs["geometry"] = hs.geometry.representative_point()
    premiere = hs.groupby("osm_id")["vf"].min()
    st = hs[hs["vt"] == hs["vt"].max()].copy()
    st = st[st.geometry.within(zone)].reset_index(drop=True)
    st["annee_apparition"] = st["osm_id"].map(premiere).map(lambda d: None if d <= dates[0] else int(d.year))
    st["support"] = st["tags"].map(lambda t: SUPPORTS.get(t.get("bicycle_parking"), t.get("bicycle_parking")))
    st["couvert"] = st["tags"].map(lambda t: {"yes": True, "no": False}.get(t.get("covered")))
    st["nom"] = st["tags"].map(lambda t: t.get("name"))
    st["operateur"] = st["tags"].map(lambda t: t.get("operator") or t.get("network"))
    st["reseau"] = st["tags"].map(reseau)
    st["osm_url"] = "https://www.openstreetmap.org/" + st["osm_id"]
    j = gpd.sjoin(st[["geometry"]], quartiers[["quartier", "geometry"]], how="left", predicate="within")
    st["quartier"] = j.groupby(level=0)["quartier"].first()

    serie_stat = []
    for k, t in enumerate(dates):
        snap = hs[hs["vt"] >= hs["vt"].max()] if k == len(dates) - 1 else hs[(hs["vf"] <= t) & (hs["vt"] > t)]
        snap = snap[snap.geometry.within(zone)]
        p = snap[snap["type"] == "Stationnement vélo"]
        serie_stat.append({"date": t.strftime("%Y-%m-%d"), "sites": int(len(p)),
                           "places": int(p["capacite"].fillna(0).sum()),
                           "stations_libre_service": int((snap["type"] == LIBRE_SERVICE).sum())})
    parkings = st[st["type"] == "Stationnement vélo"]

    # -- C12 Variation par rapport à la dernière version publiée -------------------------
    precedent = C.DIR_SERVICES / "indicateurs.json"
    if precedent.exists():
        old = json.loads(precedent.read_text(encoding="utf-8"))
        old_km = old["totaux"]["km_total"]
        var = (total - old_km) / old_km if old_km else 0
        statut = "BLOQUANT" if var < -0.20 else ("ALERTE" if var < -0.05 else "OK")
        controle("C12", "Variation du linéaire vs version publiée", statut,
                 f"{var:+.1%} ({old_km:.1f} -> {total:.1f} km)", f"version publiée : {old['meta'].get('version')}")
    else:
        controle("C12", "Variation du linéaire vs version publiée", "INFO", "première publication")
    age = (debut_traitement - vt_max.to_pydatetime()).days
    controle("C13", "Fraîcheur des données OSM", "OK" if age <= 120 else "ALERTE", f"{age} jours",
             f"données au {vt_max:%d/%m/%Y} (décalage de mise à jour de l'API ohsome)")

    # -- Synthèse QC --------------------------------------------------------------
    statuts = [c["statut"] for c in controles]
    statut_global = "BLOQUANT" if "BLOQUANT" in statuts else ("ALERTE" if "ALERTE" in statuts else "OK")
    version = debut_traitement.strftime("%Y.%m.%d")

    def mandat(m):
        sel = (seg["a_typ"] >= m["debut"]) & (seg["a_typ"] <= m["fin"])
        return {**m, "km": round(float(km[sel].sum()), 2),
                "km_creation": round(float(km[sel & (seg["nature"] == "Création")].sum()), 2),
                "km_requalification": round(float(km[sel & (seg["nature"] == "Requalification")].sum()), 2),
                "km_site_propre": round(float(km[sel & seg["site_propre"]].sum()), 2)}

    indicateurs = {
        "meta": {"commune": C.NOM_COMMUNE, "de_commune": C.de(C.NOM_COMMUNE), "code_insee": C.CODE_INSEE,
                 "dossier": C.DOSSIER_COMMUNE, "departement": C.DEPARTEMENT,
                 "nb_iris": int(len(iris)), "nb_quartiers": int(len(quartiers)),
                 "reseau_libre_service": (st["reseau"].dropna().mode().iloc[0] if st["reseau"].notna().any() else None),
                 "version": version, "date_traitement": debut_traitement.isoformat(timespec="seconds"),
                 "date_donnees_osm": vt_max.strftime("%Y-%m-%d"), "annee_reference": C.ANNEE_REFERENCE,
                 "annee_partielle": annee_fin, "statut_qc": statut_global,
                 "population": json.loads((C.DIR_BRUTES / "commune.geojson").read_text(encoding="utf-8"))["properties"].get("population"),
                 "sources": [{"fichier": f["fichier"], "source": f["source"], "extrait_le": f["extrait_le"]} for f in manifest["fichiers"]]},
        "totaux": {
            "km_total": round(total, 2), "nb_objets": int(len(seg)),
            "km_site_propre": round(float(km[seg["site_propre"]].sum()), 2),
            "part_site_propre": round(float(km[seg["site_propre"]].sum()) / total, 3),
            "km_voirie": round(km_voirie, 2), "km_pour_100km_voirie": round(100 * total / km_voirie, 1),
            "sous_reseaux": len(blocs), "part_reseau_principal": round(part_principal, 3),
            "stationnements": int(len(parkings)), "places_declarees": int(parkings["capacite"].fillna(0).sum()),
            "stationnements_sans_capacite": int(parkings["capacite"].isna().sum()),
            "stations_libre_service": int((st["type"] == LIBRE_SERVICE).sum()),
        },
        "par_annee": par_annee,
        "par_type": [{"type": t, "km": round(float(km[seg["type_amenagement"] == t].sum()), 2)} for t in PRIORITE],
        "par_quartier": par_quartier,
        "par_mandat": [mandat(m) for m in C.MANDATS],
        "voirie_serie": [{"date": r["timestamp"][:10], "km": round(r["value"] / 1000, 2)} for r in voirie_serie],
        "stationnement_serie": serie_stat,
        "completude": {k: round(v, 3) for k, v in completude.items()},
    }

    # -- Écriture ----------------------------------------------------------------
    out = C.DIR_SORTIES
    seg_out = seg[ETALAB + ENRICHIS + ["geometry"]].copy()
    gpkg = out / f"{C.DOSSIER_COMMUNE}_velo.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    g2154 = seg_out.copy()
    g2154["project_c"] = "Lambert93"
    for c in ("lumiere", "site_propre"):
        g2154[c] = g2154[c].astype("object")
    g2154.to_file(gpkg, layer="amenagements_cyclables", driver="GPKG")
    st_cols = ["osm_id", "type", "capacite", "support", "couvert", "nom", "operateur", "reseau", "annee_apparition", "quartier", "osm_url"]
    st[st_cols + ["geometry"]].assign(couvert=st["couvert"].astype("object")).to_file(gpkg, layer="stationnement_velo", driver="GPKG")
    quartiers.to_file(gpkg, layer="quartiers", driver="GPKG")
    commune[["nom", "code", "geometry"]].to_file(gpkg, layer="commune", driver="GPKG")

    ecrire_geojson(seg_out, out / "amenagements_cyclables.geojson", ETALAB + ENRICHIS)
    ecrire_geojson(seg_out, out / f"amenagements_cyclables_{C.CODE_INSEE}_schema_etalab.geojson", ETALAB)
    ecrire_geojson(st, out / "stationnement_velo.geojson", st_cols)
    ecrire_geojson(quartiers, out / "quartiers.geojson", ["quartier", "surface_ha", "km_voirie", "km", "km_pour_100km_voirie", "km_depuis_2020"])
    ecrire_geojson(commune.assign(nom=C.NOM_COMMUNE), out / "commune.geojson", ["nom", "code"])
    (out / "indicateurs.json").write_text(json.dumps(indicateurs, ensure_ascii=False, indent=2), encoding="utf-8")

    qc = {"version": version, "date": debut_traitement.isoformat(timespec="seconds"),
          "statut_global": statut_global, "controles": controles}
    (out / "controle_qualite.json").write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    icones = {"OK": "✅", "INFO": "ℹ️", "ALERTE": "⚠️", "BLOQUANT": "⛔"}
    md = [f"# Rapport de contrôle qualité (version {version})", "",
          f"- Données OSM au **{vt_max:%d/%m/%Y}**, traitement du {debut_traitement:%d/%m/%Y %H:%M} UTC",
          f"- Statut global : **{icones[statut_global]} {statut_global}**", "",
          "| Code | Contrôle | Statut | Résultat | Détail |", "|---|---|---|---|---|"]
    md += [f"| {c['code']} | {c['controle']} | {icones[c['statut']]} {c['statut']} | {c['valeur']} | {c['detail']} |" for c in controles]
    md += ["", "Règle de publication : tout contrôle **BLOQUANT** interdit la republication ; "
           "les **ALERTES** doivent être levées ou acceptées lors de la validation métier."]
    (out / "rapport_controle_qualite.md").write_text("\n".join(md), encoding="utf-8")

    log(f"Linéaire total : {total:.1f} km dont {indicateurs['totaux']['km_site_propre']:.1f} km en site propre")
    log(f"Statut QC : {statut_global} -> {out}")
    return 2 if statut_global == "BLOQUANT" else 0


if __name__ == "__main__":
    sys.exit(main())
