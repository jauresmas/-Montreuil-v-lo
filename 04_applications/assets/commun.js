/* Ressources partagées par le portail, la carte web et le tableau de bord.
   Symbologie : palette catégorielle validée (contrôle daltonisme), mêmes valeurs que publication.py. */
(function () {
  const D = window.MV_DATA;
  if (!D) {
    document.body.innerHTML = '<p style="font:16px sans-serif;padding:24px">Données absentes : lancez la chaîne ' +
      '(<code>05_mise_a_jour/maj_annuelle.bat</code>) pour générer <code>data/&lt;commune&gt;/donnees.js</code>.</p>';
    throw new Error("MV_DATA manquant");
  }

  const TYPES = [
    { id: "Piste cyclable", court: "Piste", clair: "#2a78d6", sombre: "#3987e5", tirets: false, sitePropre: true },
    { id: "Bande cyclable", court: "Bande", clair: "#eb6834", sombre: "#d95926", tirets: false },
    { id: "Double-sens cyclable", court: "Double-sens", clair: "#1baf7a", sombre: "#199e70", tirets: true },
    { id: "Couloir bus-vélo", court: "Couloir bus", clair: "#eda100", sombre: "#c98500", tirets: false },
    { id: "Voie verte / mixte", court: "Voie verte", clair: "#e87ba4", sombre: "#d55181", tirets: false, sitePropre: true },
    { id: "Vélorue", court: "Vélorue", clair: "#008300", sombre: "#008300", tirets: false },
    { id: "Autre (marquage partagé)", court: "Autre", clair: "#8a8a8a", sombre: "#8a8a8a", tirets: true },
  ];
  const NATURES = [
    { id: "Création", clair: "#2a78d6", sombre: "#3987e5" },
    { id: "Requalification", clair: "#eb6834", sombre: "#d95926" },
    { id: "Existant", clair: "#9aa0a6", sombre: "#6b6b6b", libelle: `Existant avant ${D.indicateurs.meta.annee_reference}` },
  ];
  // Rampe séquentielle bleue (claire -> foncée) pour l'année de réalisation
  const RAMPE = ["#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
  const GRIS_AVANT = "#a3a8ae";

  const meta = D.indicateurs.meta;
  const A0 = meta.annee_reference, A1 = meta.annee_partielle;

  // Commune affichée : son nom vient des données, jamais du code des pages
  const nom = meta.commune;
  const commune = {
    nom,
    de: meta.de_commune || (/^Le /.test(nom) ? "du " + nom.slice(3) : /^Les /.test(nom) ? "des " + nom.slice(4)
      : /^[aeiouyàâéèêîïôûœ]/i.test(nom) && !/^La |^L'/.test(nom) ? "d'" + nom : "de " + nom),
    a: /^Le /.test(nom) ? "au " + nom.slice(3) : /^Les /.test(nom) ? "aux " + nom.slice(4) : "à " + nom,
    dossier: window.MV_COMMUNE || meta.dossier,
    autres: ((window.MV_COMMUNES || {}).communes || []).length > 1,
  };
  // Lien vers une autre page en gardant la commune choisie (?commune=…), sauf pour la commune par défaut
  function lien(url) {
    const defaut = (window.MV_COMMUNES || {}).defaut;
    if (!commune.dossier || commune.dossier === defaut) return url;
    const [base, ancre] = url.split("#");
    return `${base}${base.includes("?") ? "&" : "?"}commune=${encodeURIComponent(commune.dossier)}${ancre ? "#" + ancre : ""}`;
  }
  // Crédit du projet d'origine, affiché par le portail, la carte et le tableau de bord (à conserver dans les forks)
  const credit = 'Outil open source « Montreuil à vélo » créé par Jaurès DAA-HINGBANON · ' +
    '<a href="https://github.com/jauresmas/-Montreuil-v-lo" target="_blank" rel="noopener">code source</a> sous licence MIT.';
  // Stations de vélos en libre-service : même valeur que traitement.py ; nom du réseau (Vélib', Vélo'v…) s'il est connu
  const LIBRE_SERVICE = "Station en libre-service";
  const reseau = meta.reseau_libre_service;
  const stations = { titre: reseau ? `Stations ${reseau}` : "Vélos en libre-service",
    nb: (n) => `${n} station${n > 1 ? "s" : ""} ${reseau || "en libre-service"}` };
  const dateDonnees = new Date(meta.date_donnees_osm + "T00:00:00");

  const nf1 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const nf0 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
  const fmt = {
    km: (v) => nf1.format(v) + " km",
    n1: (v) => nf1.format(v),
    n0: (v) => nf0.format(v),
    pct: (v) => nf0.format(v * 100) + " %",
    date: (s) => new Date(s).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }),
    dateLongue: (d) => d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }),
  };

  const IGN = (layer, format, style = "normal") =>
    `https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=${style}` +
    `&TILEMATRIXSET=PM&FORMAT=${format}&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}`;
  // Fonds sans clé d'API : Plan IGN v2 retraité à la volée (désaturé = « gris clair », inversé = « gris foncé »)
  const PLAN = [IGN("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png")];
  const FONDS = [
    { id: "gris", titre: "Gris clair", tuiles: PLAN, sombre: false, attribution: "© IGN Géoplateforme",
      peinture: { "raster-saturation": -1, "raster-contrast": -0.35, "raster-brightness-min": 0.3 },
      filtreCSS: "grayscale(1) contrast(.65) brightness(1.18)" },
    { id: "plan", titre: "Plan IGN", tuiles: PLAN, sombre: false, attribution: "© IGN Géoplateforme", peinture: {}, filtreCSS: "none" },
    { id: "sombre", titre: "Gris foncé", tuiles: PLAN, sombre: true, attribution: "© IGN Géoplateforme",
      peinture: { "raster-saturation": -1, "raster-contrast": -0.3, "raster-brightness-min": 0.72, "raster-brightness-max": 0.06 },
      filtreCSS: "grayscale(1) invert(.92) contrast(.75)" },
    { id: "ortho", titre: "Photographies aériennes", tuiles: [IGN("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg")], sombre: true,
      attribution: "© IGN Géoplateforme", peinture: {}, filtreCSS: "none" },
  ];

  function couleurType(t, sombre) {
    const x = TYPES.find((y) => y.id === t);
    return x ? (sombre ? x.sombre : x.clair) : "#888";
  }
  function couleurAnnee(a) {
    if (a == null) return GRIS_AVANT;
    const i = Math.min(RAMPE.length - 1, Math.floor(((a - A0) / Math.max(1, A1 - A0)) * RAMPE.length));
    return RAMPE[Math.max(0, i)];
  }
  // Expressions MapLibre
  const expr = {
    type: (sombre) => ["match", ["get", "type_amenagement"], ...TYPES.flatMap((t) => [t.id, sombre ? t.sombre : t.clair]), "#888"],
    // Sur fond sombre, la rampe est inversée : l'année la plus récente reste la plus saillante
    annee: (sombre) => ["case", ["==", ["coalesce", ["get", "annee_realisation"], 0], 0], sombre ? "#6b6b6b" : GRIS_AVANT,
      ["interpolate", ["linear"], ["get", "annee_realisation"],
        ...(sombre ? [...RAMPE].reverse() : RAMPE).flatMap((c, i) => [A0 + ((A1 - A0) * i) / (RAMPE.length - 1), c])]],
    nature: (sombre) => ["match", ["get", "nature"], ...NATURES.flatMap((n) => [n.id, sombre ? n.sombre : n.clair]), "#888"],
    largeur: (k = 1) => ["interpolate", ["linear"], ["zoom"],
      11, ["case", ["get", "site_propre"], 2.2 * k, 1.4 * k],
      14, ["case", ["get", "site_propre"], 3.6 * k, 2.4 * k],
      17, ["case", ["get", "site_propre"], 7 * k, 4.6 * k]],
  };

  function libelleAnnee(a) {
    if (a == null) return `Avant ${A0}`;
    return a === A1 ? `${a} (au ${fmt.date(dateDonnees)})` : String(a);
  }

  function emprise(fc) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const visite = (c) => {
      if (typeof c[0] === "number") { x0 = Math.min(x0, c[0]); x1 = Math.max(x1, c[0]); y0 = Math.min(y0, c[1]); y1 = Math.max(y1, c[1]); }
      else c.forEach(visite);
    };
    (fc.features || [fc]).forEach((f) => visite((f.geometry || f).coordinates));
    return [[x0, y0], [x1, y1]];
  }

  function echapper(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* Fenêtre contextuelle : titre, tableau de champs, actions en pied */
  const CHAMPS_POPUP = {
    amenagements_cyclables: ["type_amenagement", "ame_d", "ame_g", "annee_realisation", "nature", "quartier",
      "longueur_m", "regime_d", "trafic_vit", "revet_d", "lumiere", "date_maj", "methode_datation", "id_local", "controle"],
    stationnement_velo: ["type", "reseau", "capacite", "support", "couvert", "operateur", "annee_apparition", "quartier", "osm_id"],
  };
  function valeurChamp(k, v) {
    if (v === null || v === undefined || v === "" || v === "AUCUN") return null;
    if (typeof v === "boolean") return v ? "Oui" : "Non";
    if (k === "longueur_m") return nf0.format(v) + " m";
    if (k === "annee_realisation") return libelleAnnee(v);
    if (k === "date_maj") return fmt.date(v);
    return v;
  }
  function popupHTML(service, props, titre) {
    const alias = Object.fromEntries((D.services[service]?.champs || []).map((c) => [c.nom, c.alias]));
    const lignes = (CHAMPS_POPUP[service] || Object.keys(props)).map((k) => {
      let v = valeurChamp(k, props[k]);
      if (k === "annee_realisation" && props[k] == null) v = `Avant ${A0}`;
      if (k === "annee_apparition" && props[k] == null) v = `Avant ${A0}`;
      if (v === null) return "";
      const cls = k === "controle" ? ' class="alerte"' : "";
      return `<tr${cls}><th>${echapper(alias[k] || k)}</th><td>${echapper(v)}</td></tr>`;
    }).join("");
    return `<div class="pp">
      <header class="pp-tete"><h2>${echapper(titre)}</h2>
        <button class="pp-btn" data-pp="fermer" title="Fermer" aria-label="Fermer"><svg viewBox="0 0 16 16" width="16" height="16"><path d="M3.5 3.5l9 9m0-9l-9 9" stroke="currentColor" stroke-width="1.4"/></svg></button>
      </header>
      <div class="pp-corps"><table class="pp-champs">${lignes}</table></div>
      <footer class="pp-pied">
        <button class="pp-action" data-pp="zoom"><svg viewBox="0 0 16 16" width="16" height="16"><circle cx="6.5" cy="6.5" r="4.5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M10 10l4.5 4.5M4.5 6.5h4M6.5 4.5v4" stroke="currentColor" stroke-width="1.3"/></svg>Zoom à</button>
        ${props.osm_url ? `<a class="pp-action" href="${echapper(props.osm_url)}" target="_blank" rel="noopener"><svg viewBox="0 0 16 16" width="16" height="16"><path d="M9 2.5h4.5V7M13.5 2.5L7 9M11.5 9.5v4h-9v-9h4" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>Fiche OSM</a>` : ""}
      </footer></div>`;
  }

  window.MV = { D, TYPES, NATURES, RAMPE, GRIS_AVANT, FONDS, A0, A1, dateDonnees, fmt, expr,
    couleurType, couleurAnnee, libelleAnnee, emprise, echapper, popupHTML, commune, lien, LIBRE_SERVICE, stations, credit };
})();
