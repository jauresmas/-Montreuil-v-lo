/* Choisit la commune à afficher et charge ses données avant les scripts de la page.
   La commune se choisit dans l'adresse : ?commune=montpellier. Sans précision, c'est la commune par défaut
   de data/communes.js (Montreuil). Ce fichier doit être chargé juste après data/communes.js. */
(function () {
  const liste = window.MV_COMMUNES || { defaut: "montreuil", communes: [] };
  const demandee = new URLSearchParams(location.search).get("commune");
  const connue = liste.communes.some((c) => c.dossier === demandee);
  window.MV_COMMUNE = connue ? demandee : liste.defaut;
  // Le chemin des données se déduit de celui de ce fichier (assets/ et data/ sont voisins)
  const data = document.currentScript.src.replace(/assets\/charger\.js(\?.*)?$/, "data/");
  document.write(`<script src="${data}${window.MV_COMMUNE}/donnees.js"><\/script>`);
})();
