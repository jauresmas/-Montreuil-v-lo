"""Étape 5 : mise à jour annuelle (orchestrateur de la chaîne).

Campagne en deux temps, pour garder une validation humaine avant toute republication :

  1) python 05_mise_a_jour/maj_annuelle.py
       collecte -> traitement + contrôle qualité -> rapport d'écarts avec la version en ligne
       puis s'arrête « en attente de validation métier » (la version publiée reste inchangée)

  2) python 05_mise_a_jour/maj_annuelle.py --publier --valide-par "Nom, service"
       archive la version en ligne (archives/<commune>/<version>/) puis republie couches et applications

Options : --sans-collecte (retraite les données brutes déjà présentes)
          --commune <code INSEE> (autre commune que Montreuil, dans ses propres dossiers)

Chaque exécution est tracée dans 05_mise_a_jour/journaux/<commune>.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402

JOURNAL = C.DIR_MAJ / "journaux" / f"{C.DOSSIER_COMMUNE}.md"
A_VALIDER = C.DIR_MAJ / "a_valider" / C.DOSSIER_COMMUNE
SAISIE = C.DIR_MAJ / "modele_saisie_chantiers.csv"


def journal(msg: str) -> None:
    ligne = f"- {datetime.now():%Y-%m-%d %H:%M} : {msg}"
    print(ligne, flush=True)
    neuf = not JOURNAL.exists()
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        if neuf:
            f.write(f"# Journal des mises à jour : {C.NOM_COMMUNE}\n\n")
        f.write(ligne + "\n")


def etape(script: str, *args: str) -> int:
    print(f"\n=== {script} {' '.join(args)}", flush=True)
    return subprocess.call([sys.executable, str(C.ROOT / script), *args], cwd=C.ROOT)


def km_par(features, cle):
    d = defaultdict(float)
    for f in features:
        d[f["properties"].get(cle)] += f["properties"]["longueur_m"] / 1000
    return d


def rapport_ecarts() -> Path:
    """Compare la version traitée (02_traitement/sorties) à la version en ligne (03_publication/services)."""
    neuf = json.loads((C.DIR_SORTIES / "amenagements_cyclables.geojson").read_text(encoding="utf-8"))["features"]
    ind = json.loads((C.DIR_SORTIES / "indicateurs.json").read_text(encoding="utf-8"))
    qc = json.loads((C.DIR_SORTIES / "controle_qualite.json").read_text(encoding="utf-8"))
    pub = C.DIR_SERVICES / "amenagements_cyclables.geojson"
    ancien = json.loads(pub.read_text(encoding="utf-8"))["features"] if pub.exists() else []
    v_old = json.loads((C.DIR_SERVICES / "indicateurs.json").read_text(encoding="utf-8"))["meta"]["version"] if pub.exists() else "aucune"
    version = ind["meta"]["version"]

    par_osm = lambda fs: {f["properties"]["id_osm"]: f for f in fs}  # noqa: E731
    o, n = par_osm(ancien), par_osm(neuf)
    long_osm = lambda fs: defaultdict(float, {k: sum(x["properties"]["longueur_m"] for x in fs if x["properties"]["id_osm"] == k) for k in {x["properties"]["id_osm"] for x in fs}})  # noqa: E731
    lo, ln = long_osm(ancien), long_osm(neuf)
    ecarts = []
    for f in neuf:
        k = f["properties"]["id_osm"]
        if k not in o:
            ecarts.append({**f, "properties": {**f["properties"], "ecart": "ajout"}})
        elif abs(ln[k] - lo[k]) > 5 or f["properties"]["type_amenagement"] != o[k]["properties"]["type_amenagement"]:
            ecarts.append({**f, "properties": {**f["properties"], "ecart": "modification"}})
    for f in ancien:
        if f["properties"]["id_osm"] not in n:
            ecarts.append({**f, "properties": {**f["properties"], "ecart": "suppression"}})

    A_VALIDER.mkdir(parents=True, exist_ok=True)
    geo = A_VALIDER / f"ecarts_{version}.geojson"
    geo.write_text(json.dumps({"type": "FeatureCollection", "features": ecarts}, ensure_ascii=False), encoding="utf-8")

    tot_o, tot_n = sum(km_par(ancien, "type_amenagement").values()), sum(km_par(neuf, "type_amenagement").values())
    to, tn = km_par(ancien, "type_amenagement"), km_par(neuf, "type_amenagement")
    nb = defaultdict(int)
    for e in ecarts:
        nb[e["properties"]["ecart"]] += 1
    chantiers = []
    if SAISIE.exists():
        with SAISIE.open(encoding="utf-8-sig") as f:
            chantiers = [r for r in csv.DictReader(f, delimiter=";") if (r.get("id_chantier") or "").strip()]

    md = [f"# Rapport d'écarts, version {version} (en ligne : {v_old})", "",
          f"- Données OSM au {ind['meta']['date_donnees_osm']} · statut QC **{qc['statut_global']}**",
          f"- Linéaire : {tot_o:.2f} km → **{tot_n:.2f} km** ({tot_n - tot_o:+.2f} km)",
          f"- Objets OSM : {nb['ajout']} ajout(s), {nb['modification']} modification(s), {nb['suppression']} suppression(s)",
          f"- Couche des écarts à ouvrir dans QGIS ou la carte : `{geo.relative_to(C.ROOT)}`", "",
          "## Linéaire par type", "", "| Type | En ligne (km) | Nouvelle version (km) | Écart |", "|---|---:|---:|---:|"]
    for t in sorted(set(to) | set(tn), key=lambda x: -tn.get(x, 0)):
        md.append(f"| {t} | {to.get(t, 0):.2f} | {tn.get(t, 0):.2f} | {tn.get(t, 0) - to.get(t, 0):+.2f} |")
    md += ["", "## Points à arbitrer", ""]
    md += [f"- ⚠️ {c['code']} {c['controle']} : {c['valeur']}" for c in qc["controles"] if c["statut"] in ("ALERTE", "BLOQUANT")] or ["- Aucun"]
    md += ["", "## Plus gros ajouts (contrôle terrain conseillé)", ""]
    ajouts = sorted((e for e in ecarts if e["properties"]["ecart"] == "ajout"), key=lambda e: -e["properties"]["longueur_m"])[:10]
    md += [f"- {e['properties']['nom_voie'] or 'sans nom'} : {e['properties']['type_amenagement']}, {e['properties']['longueur_m']:.0f} m ({e['properties']['osm_url']})" for e in ajouts] or ["- Aucun ajout"]
    md += ["", "## Rapprochement avec les chantiers livrés (saisie Ville)", "",
           f"- {len(chantiers)} chantier(s) déclaré(s) dans `05_mise_a_jour/modele_saisie_chantiers.csv`"
           + (" : vérifier que chacun apparaît dans la couche des écarts." if chantiers else " (fichier vide : à compléter par la voirie).")]
    if os.environ.get("GITHUB_ACTIONS"):
        md += ["", "## Décision", "", "Relire ce rapport et la checklist `05_mise_a_jour/checklist_validation_metier.md`.",
               "Fusionner cette pull request vaut validation métier : la version est alors publiée et mise en ligne,",
               "avec le nom de la personne qui a fusionné. Fermer la pull request sans fusionner revient à refuser la campagne."]
    else:
        md += ["", "## Décision", "", "Après la checklist `checklist_validation_metier.md` :", "",
               "```", f'python 05_mise_a_jour/maj_annuelle.py --publier --valide-par "Nom, service"'
               + ("" if C.EST_PAR_DEFAUT else f" --commune {C.CODE_INSEE}"), "```"]
    chemin = A_VALIDER / f"rapport_ecarts_{version}.md"
    chemin.write_text("\n".join(md), encoding="utf-8")
    return chemin


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--publier", action="store_true", help="publier la version traitée après validation métier")
    ap.add_argument("--valide-par", help="nom et service du référent qui valide")
    ap.add_argument("--sans-collecte", action="store_true", help="ne pas re-télécharger les données brutes")
    ap.add_argument("--commune", help="code INSEE de la commune (Montreuil par défaut)")
    a = ap.parse_args()

    if a.publier:
        if not a.valide_par:
            print('--valide-par "Nom, service" est obligatoire pour publier.')
            return 1
        code = etape("03_publication/publication.py", "--valide-par", a.valide_par)
        journal(f"Publication {'réussie' if code == 0 else f'refusée (code {code})'}, validée par {a.valide_par}")
        return code

    journal(f"Début de campagne pour {C.NOM_COMMUNE} ({C.CODE_INSEE})" + (" (sans collecte)" if a.sans_collecte else ""))
    if not a.sans_collecte:
        if etape("01_donnees/collecte.py") != 0:
            journal("Échec de la collecte : version en ligne conservée")
            return 1
    code = etape("02_traitement/traitement.py")
    if code == 2:
        journal("Contrôle qualité BLOQUANT : version en ligne conservée (voir rapport_controle_qualite.md)")
        return 2
    if code != 0:
        journal(f"Échec du traitement (code {code})")
        return code
    rapport = rapport_ecarts()
    journal(f"Traitement OK, en attente de validation métier : {rapport.relative_to(C.ROOT)}")
    print(f"\nÀ faire : relire {rapport.relative_to(C.ROOT)} et la checklist, puis publier avec --publier --valide-par.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
