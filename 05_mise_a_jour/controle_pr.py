"""Contrôle automatique d'une pull request (lancé par .github/workflows/controle-pull-request.yml).

Vérifie ce qu'un relecteur vérifierait à la main avant de fusionner :

  * fichiers modifiés : données de quelles communes, code, workflows ;
  * pour chaque commune touchée : traitement lisible, contrôle qualité non bloquant, version publiée
    identique au traitement, données des applications à la même version ;
  * fichiers communs : liste des communes publiées et comparaison à jour, crédit et licence présents ;
  * applications (option --applis) : portail, carte, tableau de bord et comparaison s'ouvrent sans erreur
    et affichent la bonne commune.

Le script est toujours pris dans la branche main : une pull request ne peut pas affaiblir son propre contrôle.

Usage : python 05_mise_a_jour/controle_pr.py --pr <dossier de la pull request> --fichiers <liste des fichiers modifiés> [--applis]
Code de sortie : 1 si un problème bloquant est trouvé, 0 sinon (les points à relire ne bloquent pas).
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "03_publication"))

# Fichiers propres à une commune : (motif, rôle)
DONNEES = [
    (re.compile(r"^01_donnees/brutes/([^/]+)/manifest\.json$"), "manifest"),
    (re.compile(r"^01_donnees/brutes/([^/]+)/"), "brutes"),
    (re.compile(r"^02_traitement/sorties/([^/]+)/"), "sorties"),
    (re.compile(r"^03_publication/services/([^/]+)/"), "services"),
    (re.compile(r"^04_applications/data/([^/]+)/"), "data"),
    (re.compile(r"^05_mise_a_jour/journaux/([^/]+)\.md$"), "journal"),
]
# Fichiers communs régénérés à chaque publication
GENERES = {"03_publication/services/comparaison.json", "04_applications/data/communes.js",
           "04_applications/data/comparaison.js"}
CREDIT = "github.com/jauresmas/-Montreuil-v-lo"
AUTEUR = "Jaurès DAA-HINGBANON"


class Rapport:
    def __init__(self):
        self.lignes, self.bloquants, self.a_relire = ["## Contrôle de la pull request", ""], 0, 0

    def titre(self, t):
        self.lignes += ["", f"### {t}", ""]

    def ok(self, t):
        self.lignes.append(f"- ✅ {t}")

    def info(self, t):
        self.lignes.append(f"- ℹ️ {t}")

    def relire(self, t):
        self.a_relire += 1
        self.lignes.append(f"- ⚠️ {t}")

    def bloquant(self, t):
        self.bloquants += 1
        self.lignes.append(f"- ❌ {t}")

    def texte(self):
        if self.bloquants:
            res = f"**Résultat : ❌ {self.bloquants} problème(s) à corriger avant de fusionner.**"
        elif self.a_relire:
            res = f"**Résultat : ✅ rien de bloquant, {self.a_relire} point(s) à relire.**"
        else:
            res = "**Résultat : ✅ rien de bloquant.**"
        return "\n".join(self.lignes[:2] + [res] + self.lignes[2:]) + "\n"


def lire_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def lire_js(p: Path, prefixe: str):
    t = p.read_text(encoding="utf-8")
    return json.loads(t[t.index(prefixe) + len(prefixe):].strip().rstrip(";"))


def date_fr(s) -> str:
    s = str(s or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if re.fullmatch(r"\d{4}-\d\d-\d\d", s) else (s or "?")


def km(x) -> str:
    return f"{x:,.1f}".replace(",", " ").replace(".", ",") + " km"


def classer(fichiers):
    par_commune, communs, code = {}, [], []
    for f in fichiers:
        if f in GENERES:
            communs.append(f)
            continue
        for motif, role in DONNEES:
            m = motif.match(f)
            if m:
                par_commune.setdefault(m.group(1), {}).setdefault(role, []).append(f)
                break
        else:
            code.append(f)
    return par_commune, communs, code


def controle_commune(r: Rapport, pr: Path, d: str, roles: dict):
    sorties, services = pr / "02_traitement" / "sorties" / d, pr / "03_publication" / "services" / d
    ind_s = ind_p = None
    if (sorties / "indicateurs.json").exists():
        try:
            ind_s = lire_json(sorties / "indicateurs.json")
            qc = lire_json(sorties / "controle_qualite.json")
        except Exception as e:  # noqa: BLE001
            r.bloquant(f"Traitement illisible : {e}")
            return
        m = ind_s["meta"]
        if m.get("dossier") not in (None, d):
            r.bloquant(f"Le traitement annonce le dossier « {m.get('dossier')} » au lieu de « {d} »")
        if not re.fullmatch(r"\d[\dAB]\d{3}", str(m.get("code_insee", ""))):
            r.bloquant(f"Code INSEE invalide : {m.get('code_insee')}")
        alertes = [f"{c['code']} {c['controle']}" for c in qc["controles"] if c["statut"] == "ALERTE"]
        if qc["statut_global"] == "BLOQUANT":
            r.bloquant("Contrôle qualité BLOQUANT : " + ", ".join(f"{c['code']} {c['controle']}" for c in qc["controles"] if c["statut"] == "BLOQUANT"))
        else:
            r.ok(f"Traitement du {date_fr(m.get('date_traitement'))} (données OSM au {date_fr(m.get('date_donnees_osm'))}) : "
                 f"{km(ind_s['totaux']['km_total'])}, contrôle qualité {qc['statut_global']}")
            for a in alertes:
                r.info(f"Alerte du contrôle qualité à lire : {a}")
    elif "sorties" in roles:
        r.bloquant("Fichiers de traitement modifiés mais indicateurs.json absent")

    if "services" in roles or "data" in roles:
        if not (services / "indicateurs.json").exists():
            if (services).exists() or "data" in roles:
                r.bloquant("Version publiée incomplète : 03_publication/services/" + d + "/indicateurs.json absent")
            else:
                r.relire("La pull request retire la version publiée de cette commune")
            return
        ind_p = lire_json(services / "indicateurs.json")
        v = ind_p["meta"]["version"]
        if ind_s is not None and ind_p != ind_s:
            r.bloquant("La version publiée ne correspond pas au traitement joint (relancer la publication)")
        else:
            r.ok(f"Version publiée {v} identique au traitement")
        if lire_json(services / "controle_qualite.json")["statut_global"] == "BLOQUANT":
            r.bloquant("La version publiée a un contrôle qualité BLOQUANT")
        donnees = pr / "04_applications" / "data" / d / "donnees.js"
        if not donnees.exists():
            r.bloquant(f"Données des applications absentes : 04_applications/data/{d}/donnees.js")
        elif f'"version":"{v}"' not in donnees.read_text(encoding="utf-8")[:400]:
            r.bloquant(f"04_applications/data/{d}/donnees.js n'est pas à la version {v}")
        else:
            r.ok(f"Données des applications à la version {v}")
        hist = services / "historique_publications.json"
        if hist.exists():
            h = lire_json(hist)
            if h and h[-1].get("version") == v:
                r.info(f"Publication validée par {h[-1].get('valide_par', '?')}")
            else:
                r.relire("L'historique des publications ne mentionne pas cette version")
    elif ind_s is not None:
        r.info("Campagne à publier : la fusion publiera cette commune avec le nom de la personne qui fusionne")

    autres = [f for f in roles.get("brutes", [])]
    if autres:
        r.relire(f"{len(autres)} fichier(s) de données brutes ajouté(s) (seul manifest.json est normalement versionné) : "
                 + ", ".join(Path(f).name for f in autres[:5]))


def controle_communs(r: Rapport, pr: Path, base: Path):
    services = sorted(p.parent.name for p in (pr / "03_publication" / "services").glob("*/indicateurs.json"))
    try:
        liste = lire_js(pr / "04_applications" / "data" / "communes.js", "window.MV_COMMUNES = ")
    except Exception as e:  # noqa: BLE001
        r.bloquant(f"Liste des communes illisible : {e}")
        return services, None
    dossiers = sorted(c["dossier"] for c in liste["communes"])
    if dossiers != services:
        r.bloquant(f"Liste des communes ({', '.join(dossiers)}) différente des communes publiées ({', '.join(services)})")
    else:
        r.ok(f"Liste des communes à jour : {', '.join(c['nom'] for c in liste['communes'])}")
    try:
        defaut_main = lire_js(base / "04_applications" / "data" / "communes.js", "window.MV_COMMUNES = ").get("defaut")
    except Exception:  # noqa: BLE001
        defaut_main = liste.get("defaut")
    if liste.get("defaut") != defaut_main:
        r.relire(f"La commune affichée par défaut change : {defaut_main} → {liste.get('defaut')}")

    cmp_json = pr / "03_publication" / "services" / "comparaison.json"
    if cmp_json.exists():
        from comparaison import resume  # version de main : la pull request ne peut pas la modifier
        attendu = sorted((resume(d, lire_json(pr / "03_publication" / "services" / d / "indicateurs.json")) for d in services),
                         key=lambda c: c["nom"])
        fourni = lire_json(cmp_json)
        if fourni.get("communes") != attendu:
            r.bloquant("Comparaison des communes pas à jour : lancer python 03_publication/comparaison.py")
        else:
            js = lire_js(pr / "04_applications" / "data" / "comparaison.js", "window.MV_COMPARAISON = ")
            if js.get("communes") != attendu:
                r.bloquant("04_applications/data/comparaison.js différent de comparaison.json : relancer 03_publication/comparaison.py")
            else:
                r.ok(f"Comparaison à jour ({len(attendu)} communes)")

    commun_js = pr / "04_applications" / "assets" / "commun.js"
    licence = pr / "LICENSE"
    if CREDIT not in commun_js.read_text(encoding="utf-8"):
        r.bloquant("Le crédit du projet d'origine a été retiré de 04_applications/assets/commun.js")
    elif not licence.exists() or AUTEUR not in licence.read_text(encoding="utf-8"):
        r.bloquant("La licence MIT ou la mention de l'auteur a été retirée")
    else:
        r.ok("Crédit et licence présents")
    return services, liste


def controle_applis(r: Rapport, pr: Path, a_voir: list, defaut: str, nb: int):
    from playwright.sync_api import sync_playwright

    class Discret(SimpleHTTPRequestHandler):
        def log_message(self, *a):  # pas de journal des requêtes dans le rapport
            pass

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Discret, directory=str(pr)))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    racine = f"http://127.0.0.1:{serveur.server_port}/"
    base = racine + "04_applications/"
    pages = [("portail", "index.html", "() => document.title"),
             ("carte", "carte/index.html", "() => (document.querySelector('calcite-navigation-logo') || {}).heading || ''"),
             ("tableau de bord", "tableau-de-bord/index.html", "() => (document.getElementById('titre') || {}).textContent || ''")]
    canal = os.environ.get("MV_NAVIGATEUR") or None
    with sync_playwright() as p:
        nav = p.chromium.launch(channel=canal, headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = nav.new_context(viewport={"width": 1280, "height": 800}, locale="fr-FR")

        def ouvrir(url, test):
            pg, err = ctx.new_page(), []
            pg.on("pageerror", lambda e: err.append(str(e)[:160]))
            pg.on("response", lambda x: x.status >= 400 and x.url.startswith(racine) and "favicon" not in x.url
                  and err.append(f"HTTP {x.status} {x.url[len(racine):]}"))
            pg.goto(url, wait_until="load", timeout=60000)
            pg.wait_for_timeout(2500)
            val = pg.evaluate(test)
            pg.close()
            return val, err

        for d, nom in a_voir:
            q = "" if d == defaut else f"?commune={d}"
            pb = []
            for libelle, url, test in pages:
                texte, err = ouvrir(base + url + q, test)
                if err:
                    pb.append(f"{libelle} : {'; '.join(err[:2])}")
                elif nom not in str(texte):
                    pb.append(f"{libelle} : « {nom} » absent ({str(texte)[:60]})")
            if pb:
                r.bloquant(f"{nom} : " + " · ".join(pb))
            else:
                r.ok(f"{nom} : portail, carte et tableau de bord s'ouvrent sans erreur")
        lignes, err = ouvrir(base + "comparaison/index.html", "() => document.querySelectorAll('#t-comparaison tbody tr').length")
        if err or lignes != nb:
            r.bloquant(f"Comparaison : {'; '.join(err[:2]) or f'{lignes} ligne(s) au lieu de {nb}'}")
        else:
            r.ok(f"Comparaison : {nb} communes affichées sans erreur")
        nav.close()
    serveur.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pr", required=True, help="dossier contenant la pull request (état après fusion)")
    ap.add_argument("--fichiers", required=True, help="fichier texte : un chemin modifié par ligne")
    ap.add_argument("--applis", action="store_true", help="ouvrir aussi les applications dans un navigateur")
    a = ap.parse_args()
    pr = Path(a.pr).resolve()
    fichiers = [l.strip() for l in Path(a.fichiers).read_text(encoding="utf-8").splitlines() if l.strip()]
    r = Rapport()

    par_commune, communs, code = classer(fichiers)
    r.titre("Fichiers modifiés")
    noms = {}
    for d in par_commune:
        for p in (pr / "03_publication" / "services" / d / "indicateurs.json", pr / "02_traitement" / "sorties" / d / "indicateurs.json"):
            if p.exists():
                noms[d] = lire_json(p)["meta"]["commune"]
                break
    for d, roles in sorted(par_commune.items()):
        r.info(f"Données de {noms.get(d, d)} : {sum(len(v) for v in roles.values())} fichier(s)")
    if communs:
        r.info("Fichiers communs régénérés : " + ", ".join(Path(f).name for f in communs))
    workflows = [f for f in code if f.startswith(".github/")]
    if workflows:
        r.relire("Modifie l'automatisation GitHub, à relire très attentivement : " + ", ".join(workflows))
    autre_code = [f for f in code if f not in workflows]
    if autre_code:
        r.relire(f"Modifie {len(autre_code)} fichier(s) de code ou de documentation, à relire : " + ", ".join(autre_code[:12])
                 + (" …" if len(autre_code) > 12 else ""))
    gros = [(f, (pr / f).stat().st_size) for f in fichiers if (pr / f).is_file()]
    for f, taille in gros:
        if taille > 50e6:
            r.bloquant(f"{f} pèse {taille / 1e6:.0f} Mo (limite : 50 Mo)")
        elif taille > 20e6:
            r.relire(f"{f} pèse {taille / 1e6:.0f} Mo")
    if not fichiers:
        r.info("Aucun fichier modifié")

    for d, roles in sorted(par_commune.items()):
        r.titre(noms.get(d, d))
        controle_commune(r, pr, d, roles)

    r.titre("Fichiers communs")
    services, liste = controle_communs(r, pr, BASE)

    if a.applis and liste:
        r.titre("Applications")
        defaut = liste.get("defaut")
        noms_pub = {c["dossier"]: c["nom"] for c in liste["communes"]}
        # Code modifié : toutes les communes ; sinon les communes touchées et la commune par défaut
        cibles = list(noms_pub) if code else [d for d in noms_pub if d in par_commune or d == defaut]
        try:
            controle_applis(r, pr, [(d, noms_pub[d]) for d in cibles], defaut, len(services))
        except Exception as e:  # noqa: BLE001
            r.bloquant(f"Contrôle des applications impossible : {e}")

    texte = r.texte()
    print(texte)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(texte)
    return 1 if r.bloquants else 0


if __name__ == "__main__":
    sys.exit(main())
