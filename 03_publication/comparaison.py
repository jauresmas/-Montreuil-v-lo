"""Comparaison des communes publiées.

Rassemble les indicateurs de chaque commune publiée (03_publication/services/<commune>/indicateurs.json)
dans un seul fichier léger, lu par la page de comparaison :

  * 03_publication/services/comparaison.json : le jeu de données ouvert ;
  * 04_applications/data/comparaison.js      : la même chose pour les applications.

Lancé automatiquement à la fin de publication.py. On peut aussi le relancer seul :
    python 03_publication/comparaison.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402

TOTAUX = ["km_total", "km_site_propre", "part_site_propre", "km_voirie", "km_pour_100km_voirie",
          "stationnements", "places_declarees", "stations_libre_service"]


def resume(dossier: str, ind: dict) -> dict:
    m, t = ind["meta"], ind["totaux"]
    return {
        "dossier": dossier,
        "nom": m["commune"],
        "de_commune": m.get("de_commune"),
        "code_insee": m["code_insee"],
        "departement": m.get("departement"),
        "population": m.get("population"),
        # Les IRIS couvrent toute la commune : leur somme donne la surface communale
        "surface_ha": round(sum(q.get("surface_ha", 0) for q in ind.get("par_quartier", [])), 1),
        "date_donnees_osm": m["date_donnees_osm"],
        "annee_reference": m["annee_reference"],
        "annee_partielle": m["annee_partielle"],
        "reseau_libre_service": m.get("reseau_libre_service"),
        "version": m.get("version"),
        "statut_qc": m.get("statut_qc"),
        "totaux": {k: t.get(k) for k in TOTAUX},
        # Réseau au 31/12 de chaque année (la première ligne : avant l'année de référence)
        "par_annee": [{"annee": p["annee"], "km": p["km"], "km_cumule": p["km_cumule"]} for p in ind["par_annee"]],
    }


def ecrire_comparaison() -> int:
    services = C.ROOT / "03_publication" / "services"
    communes = []
    for f in sorted(services.glob("*/indicateurs.json")):
        communes.append(resume(f.parent.name, json.loads(f.read_text(encoding="utf-8"))))
    communes.sort(key=lambda c: c["nom"])
    donnees = {"genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "source": "Aménagements et stationnement : OpenStreetMap (ODbL) ; population légale : INSEE via geo.api.gouv.fr",
               "communes": communes}
    texte = json.dumps(donnees, ensure_ascii=False)
    (services / "comparaison.json").write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    (C.DIR_APPLIS / "data" / "comparaison.js").write_text(
        "/* Généré par 03_publication/comparaison.py : indicateurs des communes publiées, ne pas modifier à la main */\n"
        f"window.MV_COMPARAISON = {texte};\n", encoding="utf-8")
    return len(communes)


if __name__ == "__main__":
    n = ecrire_comparaison()
    print(f"Comparaison écrite : {n} commune(s)")
