"""Correspondance OpenStreetMap -> schéma national des aménagements cyclables (Etalab).

Schéma : https://schema.data.gouv.fr/etalab/schema-amenagements-cyclables/
Une voie OSM porte au plus un aménagement par côté (ame_d = droite, ame_g = gauche).
Les aménagements en site propre (highway=cycleway, chemins bicycle=designated…)
sont décrits sur le côté droit, côté gauche = AUCUN.
"""
from __future__ import annotations

import re

# Valeurs autorisées par le schéma (champ ame_d / ame_g)
AME_VALEURS = {
    "PISTE CYCLABLE", "BANDE CYCLABLE", "DOUBLE SENS CYCLABLE PISTE", "DOUBLE SENS CYCLABLE BANDE",
    "DOUBLE SENS CYCLABLE NON MATERIALISE", "VOIE VERTE", "VELO RUE", "COULOIR BUS+VELO", "RAMPE",
    "GOULOTTE", "AMENAGEMENT MIXTE PIETON VELO HORS VOIE VERTE", "CHAUSSEE A VOIE CENTRALE BANALISEE",
    "ACCOTEMENT REVETU HORS CVCB", "AUTRE", "AUCUN",
}
REGIME_VALEURS = {"ZONE 30", "AIRE PIETONNE", "ZONE DE RENCONTRE", "EN AGGLOMERATION", "HORS AGGLOMERATION", "AUTRE"}
SENS_VALEURS = {"UNIDIRECTIONNEL", "BIDIRECTIONNEL"}
REVET_VALEURS = {"LISSE", "RUGUEUX", "MEUBLE"}

# Regroupement lisible par les élus (typologie physique)
TYPE_SIMPLE = {
    "PISTE CYCLABLE": "Piste cyclable",
    "DOUBLE SENS CYCLABLE PISTE": "Piste cyclable",
    "VOIE VERTE": "Voie verte / mixte",
    "AMENAGEMENT MIXTE PIETON VELO HORS VOIE VERTE": "Voie verte / mixte",
    "BANDE CYCLABLE": "Bande cyclable",
    "DOUBLE SENS CYCLABLE BANDE": "Bande cyclable",
    "COULOIR BUS+VELO": "Couloir bus-vélo",
    "VELO RUE": "Vélorue",
    "DOUBLE SENS CYCLABLE NON MATERIALISE": "Double-sens cyclable",
    "AUTRE": "Autre (marquage partagé)",
}
# Ordre de « structuration » : sert à choisir le type principal d'une voie
PRIORITE = ["Piste cyclable", "Voie verte / mixte", "Bande cyclable", "Couloir bus-vélo",
            "Vélorue", "Double-sens cyclable", "Autre (marquage partagé)"]
SITE_PROPRE = {"Piste cyclable", "Voie verte / mixte"}

ROUTES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
          "living_street", "primary_link", "secondary_link", "tertiary_link", "trunk_link", "road",
          "busway"}
CHEMINS = {"path", "footway", "pedestrian", "bridleway", "track", "service"}


def _oneway(t: dict) -> bool:
    return t.get("oneway") in ("yes", "1", "true", "-1") or t.get("junction") == "roundabout"


def _valeur_cote(t: dict, cote: str, oneway: bool) -> str | None:
    v = t.get(f"cycleway:{cote}") or t.get("cycleway:both")
    if v is None:
        g = t.get("cycleway")
        if g:
            if g.startswith("opposite"):
                v = g if cote == "left" else None
            elif oneway and cote == "left":
                v = None
            else:
                v = g
    return v


def _ame_cote(t: dict, cote: str, oneway: bool) -> tuple[str, str | None]:
    v = _valeur_cote(t, cote, oneway)
    if not v:
        return "AUCUN", None
    contre = v.startswith("opposite") or (
        oneway and cote == "left" and (t.get("oneway:bicycle") == "no" or t.get(f"cycleway:{cote}:oneway") == "-1"))
    if v in ("lane", "opposite_lane"):
        return ("DOUBLE SENS CYCLABLE BANDE" if contre else "BANDE CYCLABLE"), "UNIDIRECTIONNEL"
    if v in ("track", "opposite_track"):
        sens = "BIDIRECTIONNEL" if t.get(f"cycleway:{cote}:oneway") == "no" else "UNIDIRECTIONNEL"
        return ("DOUBLE SENS CYCLABLE PISTE" if contre else "PISTE CYCLABLE"), sens
    if v in ("share_busway", "opposite_share_busway", "shared_busway"):
        return "COULOIR BUS+VELO", "UNIDIRECTIONNEL"
    if v == "opposite":
        return "DOUBLE SENS CYCLABLE NON MATERIALISE", "UNIDIRECTIONNEL"
    if v == "shared_lane":
        return "AUTRE", None
    return "AUCUN", None  # no, none, separate, sidepath, crossing…


def regime(t: dict) -> str:
    hw = t.get("highway")
    if hw == "living_street":
        return "ZONE DE RENCONTRE"
    if hw == "pedestrian":
        return "AIRE PIETONNE"
    if t.get("maxspeed") == "30" or "30" in str(t.get("zone:maxspeed", "")) or "zone30" in str(t.get("source:maxspeed", "")).lower():
        return "ZONE 30"
    return "EN AGGLOMERATION"


def revetement(t: dict) -> str | None:
    s = t.get("surface")
    if s in ("asphalt", "concrete", "paved", "paving_stones", "concrete:plates", "concrete:lanes", "metal", "wood"):
        return "LISSE"
    if s in ("sett", "cobblestone", "unhewn_cobblestone", "grass_paver"):
        return "RUGUEUX"
    if s in ("compacted", "fine_gravel", "gravel", "unpaved", "ground", "dirt", "earth", "sand", "grass", "pebblestone"):
        return "MEUBLE"
    return None


def _nombre(v) -> float | None:
    if v is None:
        return None
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)", str(v))
    return float(m.group(1).replace(",", ".")) if m else None


def classer(t: dict) -> dict | None:
    """Renvoie les attributs du schéma pour une voie OSM, ou None si pas d'aménagement."""
    hw = t.get("highway")
    if hw is None or t.get("access") in ("private", "no") or hw in ("construction", "proposed"):
        return None
    oneway = _oneway(t)
    r = {"regime_d": regime(t), "regime_g": regime(t), "sens_d": None, "sens_g": None,
         "largeur_d": None, "largeur_g": None, "revet_d": revetement(t), "revet_g": None,
         "site_propre_osm": False}

    if t.get("bicycle_road") == "yes" or t.get("cyclestreet") == "yes":
        r.update(ame_d="VELO RUE", ame_g="VELO RUE", sens_d="BIDIRECTIONNEL", sens_g="BIDIRECTIONNEL",
                 revet_g=r["revet_d"])
    elif hw == "cycleway" or (hw in CHEMINS and t.get("bicycle") == "designated"):
        if hw == "cycleway":
            ame = "VOIE VERTE" if (t.get("foot") == "designated" and t.get("segregated") == "no") else "PISTE CYCLABLE"
        elif t.get("segregated") == "yes":
            ame = "PISTE CYCLABLE"
        elif hw == "path" and t.get("foot") == "designated" and t.get("segregated") == "no":
            ame = "VOIE VERTE"
        else:
            ame = "AMENAGEMENT MIXTE PIETON VELO HORS VOIE VERTE"
        sens = "UNIDIRECTIONNEL" if (oneway or t.get("oneway:bicycle") == "yes") else "BIDIRECTIONNEL"
        r.update(ame_d=ame, ame_g="AUCUN", sens_d=sens, largeur_d=_nombre(t.get("width")), site_propre_osm=True)
    elif hw in ROUTES or hw == "service":
        ame_d, sens_d = _ame_cote(t, "right", oneway)
        ame_g, sens_g = _ame_cote(t, "left", oneway)
        if oneway and t.get("oneway:bicycle") == "no" and ame_g == "AUCUN":
            ame_g, sens_g = "DOUBLE SENS CYCLABLE NON MATERIALISE", "UNIDIRECTIONNEL"
        r.update(ame_d=ame_d, ame_g=ame_g, sens_d=sens_d, sens_g=sens_g,
                 largeur_d=_nombre(t.get("cycleway:right:width") or t.get("cycleway:both:width")),
                 largeur_g=_nombre(t.get("cycleway:left:width") or t.get("cycleway:both:width")),
                 revet_g=r["revet_d"] if ame_g != "AUCUN" else None)
        if ame_d == "AUCUN":
            r.update(regime_d=None, revet_d=None)
        if ame_g == "AUCUN":
            r.update(regime_g=None)
    else:
        return None

    if r["ame_d"] == "AUCUN" and r["ame_g"] == "AUCUN":
        return None
    if r["ame_g"] == "AUCUN":
        r["regime_g"] = None

    types = {TYPE_SIMPLE[a] for a in (r["ame_d"], r["ame_g"]) if a in TYPE_SIMPLE}
    r["type_amenagement"] = min(types, key=PRIORITE.index)
    r["site_propre"] = r["type_amenagement"] in SITE_PROPRE
    r["trafic_vit"] = int(_nombre(t["maxspeed"])) if _nombre(t.get("maxspeed")) else None
    r["lumiere"] = {"yes": True, "no": False}.get(t.get("lit"))
    r["nom_voie"] = t.get("name")
    return r
