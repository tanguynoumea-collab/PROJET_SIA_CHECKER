// Vue Carte (docs/V5_PLAN.md, partie 3). En ligne : les fonds et calques officiels de geo.admin.ch (carte nationale
// couleur ou grise, orthophoto SWISSIMAGE ; zones à bâtir, desserte TP, arrêts, bruit), et au clic la commune, la zone
// à bâtir, la classe de desserte et l'arrêt le plus proche. Hors ligne : un fond minimum livré avec la page
// (carte-suisse.json : cantons, districts, communes nommées, lacs). Les projets sont placés à leur adresse (registre
// des adresses, hors ligne, côté moteur) ou au centre de leur commune ; un clic les coche ou les décoche.
// Script classique chargé après app.js : il en partage l'état (etat, reference, majReference…). Leaflet (vendor/,
// BSD-2) est chargé à la première ouverture.
"use strict";

const WMTS = (couche, ext = "png") => `https://wmts.geo.admin.ch/1.0.0/${couche}/default/current/3857/{z}/{x}/{y}.${ext}`;
const IDENTIFY = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify";
const LEGENDE = (couche) => `https://api3.geo.admin.ch/static/images/legends/${couche}_fr.png`;
const SWISSTOPO = '© <a href="https://www.swisstopo.admin.ch/" target="_blank" rel="noopener">swisstopo</a>';

/** Fonds : un seul affiché. « horsligne » est toujours disponible (données livrées avec la page). */
const FONDS = [
  // finesse 1 : chaque zoom affiche le niveau suivant de la carte nationale, à demi-taille. Écritures et symboles deux
  // fois plus petits, et l'édition plus détaillée de la carte (1:25 000…) arrive un cran plus tôt.
  { id: "couleur", nom: "Carte nationale couleur", url: WMTS("ch.swisstopo.pixelkarte-farbe", "jpeg"), max: 18, finesse: 1 },
  { id: "gris", nom: "Carte nationale grise", url: WMTS("ch.swisstopo.pixelkarte-grau", "jpeg"), max: 18, finesse: 1 },
  { id: "ortho", nom: "Orthophoto SWISSIMAGE", url: WMTS("ch.swisstopo.swissimage", "jpeg"), max: 20 },
  { id: "horsligne", nom: "Fond hors ligne (cantons, communes)" },
];
/** Le plus récent de plusieurs résultats datés qui ait une valeur (statistiques à l'hectare : une ligne par année de
 *  recensement ; la dernière année peut être vide, valeur non publiée). */
const recent = (tous) => tous.filter((a) => a.number != null)
  .reduce((a, b) => ((b.i_year || 0) > (a.i_year || 0) ? b : a), tous.find((a) => a.number != null) || {});
const fr = (texte) => String(texte ?? "").split("##")[1] || String(texte ?? "");     // « Mittel##Moyenne##… » → Moyenne
const nombre = (v) => (v == null ? "" : F0.format(v));
/** Statut d'un bâtiment au RegBL (OFS, code GSTAT). */
const STATUT_REGBL = { 1001: "projeté", 1002: "autorisé", 1003: "en construction", 1004: "existant", 1005: "non utilisable",
                       1007: "démoli", 1008: "non réalisé" };

/** Thèmes du panneau des calques, dans l'ordre ; seul « Repères » est déplié d'emblée. */
const GROUPES_CALQUES = ["Repères", "Urbanisme et foncier", "Population et emplois", "Contraintes et risques", "Énergie",
                         "Accès et réseaux"];
/** Calques superposables. `identify(a, tous)` : texte affiché au clic (a : premier résultat, tous : tous les résultats) ;
 *  `vecteur` : dessiné depuis les données livrées, donc aussi hors ligne ; `wms` : image WMS (pas de tuiles
 *  précalculées chez geo.admin.ch). Les couches de bruit et de ruissellement sont des images : légende, pas de valeur. */
const CALQUES = [
  // Repères
  { groupe: "Repères", id: "communes", nom: "Limites et noms des communes (dès l'échelle régionale)", vecteur: true, actif: true, opacite: 0.9 },
  { groupe: "Repères", id: "districts", nom: "Limites des districts", vecteur: true, actif: false, opacite: 0.9 },
  // Quartiers statistiques de l'OFS (unités statistiques de base, niveau 1) : découpage infracommunal national, nommé
  { groupe: "Repères", id: "ch.bfs.statistische-grundeinheiten_stufe1", nom: "Quartiers (quartiers statistiques OFS)", actif: false,
    opacite: 0.9, source: "OFS", tolerance: 0,
    identify: (a) => a.u1_name && `Quartier : ${String(a.u1_name).replace(/^USPAT\d\s*[–-]\s*/, "")}` },
  // Urbanisme et foncier
  { groupe: "Urbanisme et foncier", id: "ch.are.bauzonen", nom: "Zones à bâtir (ARE)", actif: false, opacite: 0.55, source: "ARE",
    identify: (a) => a.ch_bez_f && `Zone à bâtir : ${a.ch_bez_f}` },
  { groupe: "Urbanisme et foncier", id: "ch.kantone.cadastralwebmap-farbe", nom: "Parcelles cadastrales (mensuration officielle)",
    wms: true, desature: true, actif: false, opacite: 0.8, source: "cantons" },   // plan en couleur : gris sur le fond gris
  { groupe: "Urbanisme et foncier", id: "ch.bfs.gebaeude_wohnungs_register", nom: "Bâtiments RegBL : existants, projetés, en construction",
    actif: false, opacite: 0.85, source: "OFS", tolerance: 12,     // un point par bâtiment : clic à proximité
    identify: (a) => a.egid && [`Bâtiment ${a.strname_deinr || `EGID ${a.egid}`} : ${STATUT_REGBL[a.gstat] || "statut inconnu"}`,
      a.gbauj ? `construit en ${a.gbauj}` : "", a.gastw ? `${a.gastw} niveaux` : "", a.ganzwhg ? `${a.ganzwhg} logements` : "",
      a.lparz ? `parcelle ${a.lparz}` : ""].filter(Boolean).join(" · ") },
  { groupe: "Urbanisme et foncier", id: "ch.bak.bundesinventar-schuetzenswerte-ortsbilder", nom: "Sites construits à protéger (ISOS, OFC)",
    actif: false, opacite: 0.6, source: "OFC", identify: (a) => a.name && `ISOS : ${a.name}${a.siedlungskategorie ? ` (${a.siedlungskategorie})` : ""}` },
  // Population et emplois (à l'hectare, année la plus récente)
  { groupe: "Population et emplois", id: "ch.bfs.volkszaehlung-bevoelkerungsstatistik_einwohner", nom: "Habitants à l'hectare (STATPOP)",
    wms: true, actif: false, opacite: 0.7, source: "OFS", tolerance: 0,
    identify: (a, tous) => { const r = recent(tous); return r.number != null && `Habitants : ${nombre(r.number)} à l'hectare (${r.i_year})`; } },
  { groupe: "Population et emplois", id: "ch.bfs.volkszaehlung-gebaeudestatistik_wohnungen", nom: "Logements à l'hectare (StatBL)",
    wms: true, actif: false, opacite: 0.7, source: "OFS", tolerance: 0,
    identify: (a, tous) => { const r = recent(tous); return r.number != null && `Logements : ${nombre(r.number)} à l'hectare (${r.i_year})`; } },
  { groupe: "Population et emplois", id: "ch.bfs.betriebszaehlungen-beschaeftigte_vollzeitaequivalente", nom: "Emplois à l'hectare (STATENT, EPT)",
    wms: true, actif: false, opacite: 0.7, source: "OFS", tolerance: 0,
    identify: (a, tous) => { const r = recent(tous); return r.number != null && `Emplois : ${nombre(r.number)} EPT à l'hectare (${r.i_year})`; } },
  // Contraintes et risques
  { groupe: "Contraintes et risques", id: "ch.bafu.laerm-strassenlaerm_tag", nom: "Bruit routier, jour (OFEV)", actif: false, opacite: 0.5, source: "OFEV" },
  { groupe: "Contraintes et risques", id: "ch.bafu.laerm-strassenlaerm_nacht", nom: "Bruit routier, nuit (OFEV)", actif: false, opacite: 0.5, source: "OFEV" },
  { groupe: "Contraintes et risques", id: "ch.bafu.laerm-bahnlaerm_tag", nom: "Bruit ferroviaire, jour (OFEV)", actif: false, opacite: 0.5, source: "OFEV" },
  { groupe: "Contraintes et risques", id: "ch.bafu.laerm-bahnlaerm_nacht", nom: "Bruit ferroviaire, nuit (OFEV)", actif: false, opacite: 0.5, source: "OFEV" },
  { groupe: "Contraintes et risques", id: "ch.bafu.gefaehrdungskarte-oberflaechenabfluss", nom: "Aléa ruissellement (OFEV)",
    actif: false, opacite: 0.6, source: "OFEV" },
  { groupe: "Contraintes et risques", id: "ch.bag.radonkarte", nom: "Radon (OFSP)", wms: true, actif: false, opacite: 0.5, source: "OFSP",
    identify: (a) => a.probability_prozent != null && `Radon : ${a.probability_prozent} % de probabilité de dépasser 300 Bq/m³` },
  { groupe: "Contraintes et risques", id: "ch.bafu.gefahren-baugrundklassen", nom: "Classes de sol de fondation (SIA 261)",
    actif: false, opacite: 0.55, source: "OFEV", tolerance: 0, identify: (a) => a.bgk && `Sol de fondation : classe ${a.bgk} (SIA 261)` },
  // Énergie
  { groupe: "Énergie", id: "ch.bfe.solarenergie-eignung-daecher", nom: "Solaire : aptitude des toitures (OFEN)", actif: false, opacite: 0.75,
    source: "OFEN", tolerance: 0, identify: (a) => a.klasse_text && `Toiture : aptitude ${fr(a.klasse_text).toLowerCase()}, ` +
      `${nombre(a.flaeche)} m², ${nombre(a.stromertrag)} kWh/an possibles` },
  { groupe: "Énergie", id: "ch.bfe.solarenergie-eignung-fassaden", nom: "Solaire : potentiel des façades (OFEN)", actif: false, opacite: 0.75,
    source: "OFEN", tolerance: 2, identify: (a) => a.klasse_text && `Façade : potentiel ${fr(a.klasse_text).toLowerCase()}, ` +
      `${nombre(a.flaeche)} m², ${nombre(a.stromertrag)} kWh/an possibles` },
  { groupe: "Énergie", id: "ch.bfe.fernwaerme-nachfrage_wohn_dienstleistungsgebaeude", nom: "Demande de chaleur des bâtiments (OFEN)",
    actif: false, opacite: 0.7, source: "OFEN", tolerance: 0,
    identify: (a) => a.needtotal != null && `Demande de chaleur : ${nombre(a.needtotal)} MWh/an (logement ${nombre(a.needhome)}, services ${nombre(a.needservice)})` },
  // Accès et réseaux
  { groupe: "Accès et réseaux", id: "ch.are.gueteklassen_oev", nom: "Desserte en transports publics (ARE)", actif: false, opacite: 0.55,
    source: "ARE", identify: (a) => a.klasse_fr && `Desserte TP : classe ${a.klasse_fr}` },
  { groupe: "Accès et réseaux", id: "ch.are.erreichbarkeit-oev", nom: "Accessibilité en transports publics (ARE)", actif: false, opacite: 0.6,
    source: "ARE", tolerance: 0,
    identify: (a) => a.oev_erreichb_ewap != null && `Accessibilité TP : ${nombre(a.oev_erreichb_ewap)} (habitants et emplois atteignables, pondérés)` },
  { groupe: "Accès et réseaux", id: "ch.are.reisezeit-oev", nom: "Temps de parcours en TP au centre le plus proche (ARE)", actif: false,
    opacite: 0.6, source: "ARE", tolerance: 0, identify: (a) => a.oev_reisezeit_z != null && `Temps TP jusqu'au centre : ${a.oev_reisezeit_z} min` },
  { groupe: "Accès et réseaux", id: "ch.bav.haltestellen-oev", nom: "Arrêts de transports publics (OFT)", actif: false, opacite: 1, source: "OFT",
    identify: (a) => a.name && `Arrêt : ${a.name}${a.verkehrsmittel_fr ? ` (${a.verkehrsmittel_fr})` : ""}`, tolerance: 25 },
  { groupe: "Accès et réseaux", id: "ch.bakom.anschlussart-glasfaser", nom: "Fibre optique FTTB/FTTH (OFCOM)", actif: false, opacite: 0.7, source: "OFCOM" },
  { groupe: "Accès et réseaux", id: "ch.bakom.standorte-mobilfunkanlagen", nom: "Antennes de téléphonie mobile (OFCOM)", actif: false,
    opacite: 0.9, source: "OFCOM", tolerance: 15,
    identify: (a) => a.station && `Antenne : ${a.station}${a.techno_fr ? `, ${a.techno_fr.replace(/^Technologie\s*/i, "")}` : ""}` },
];
const TYPO_COULEURS = ["#2563EB", "#E8590C", "#0E9F6E", "#7C3AED", "#DB2777", "#0891B2"];
const NON_IDENTIFIEE_COULEUR = "#64748B";
const CENTRE_SUISSE = [46.8, 8.23];
const CLE_FOND = "benchmark.carte.fond";
const CLE_CALQUES = "benchmark.carte.calques";

const carte = { L: null, map: null, fond: null, fonds: {}, calques: {}, hors: null, donnees: null, projets: null,
                rayonCercle: null, outil: null, actif: false, enLigne: navigator.onLine !== false,
                filtres: { phase: "", spMin: null, spMax: null, fiables: false, maquette: false, precision: "" },
                rayon: { id: "", km: 10 } };

/** Couleur d'une typologie : par ordre de fréquence dans toute la base (la plus courante prend le bleu), stable d'un
 *  filtre à l'autre. */
const typoCouleur = (() => {
  let ordre = null;
  return (cat) => {
    if (!cat) return NON_IDENTIFIEE_COULEUR;
    if (!ordre) {
      const n = new Map();
      for (const p of etat.data.projets) if (p.infos?.categorie) n.set(p.infos.categorie, (n.get(p.infos.categorie) || 0) + 1);
      ordre = [...n].sort((a, b) => b[1] - a[1]).map(([c]) => c);
    }
    const i = ordre.indexOf(cat);
    return TYPO_COULEURS[(i < 0 ? ordre.push(cat) - 1 : i) % TYPO_COULEURS.length];
  };
})();

// ------------------------------------------------------------------ coordonnées suisses (formules approchées de swisstopo, ±1 m)

function versWgs84([e, n]) {
  const y = (e - 2600000) / 1e6, x = (n - 1200000) / 1e6;
  const lon = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3;
  const lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.014 * x ** 3;
  return [(lat * 100) / 36, (lon * 100) / 36];
}

function versLv95([lat, lon]) {
  const p = (lat * 3600 - 169028.66) / 10000, l = (lon * 3600 - 26782.5) / 10000;
  return [2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p * p - 44.54 * l ** 3,
          1200147.07 + 308807.95 * p + 3745.25 * l * l + 76.63 * p * p - 194.56 * l * l * p + 119.79 * p ** 3];
}

/** Couleur d'une variable du thème : Leaflet écrit des attributs SVG, où var(--…) ne se résout pas. */
const teinte = (nom) => getComputedStyle(document.documentElement).getPropertyValue(nom).trim() || "#888";

const kmEntre = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]) / 1000;

/** Projets montrés : ceux du pré-filtre qui passent les filtres de la carte (affichage seulement). */
function projetsCarte() {
  const f = carte.filtres;
  return projetsSelection().filter((p) => (!f.fiables || p.fiable) && (!f.maquette || p.maquette)
    && (!f.precision || (f.precision === "adresse" ? ["adresse", "rue"].includes(p.precision) : p.precision === "commune"))
    && (!f.phase || String(p.infos?.phase ?? "").replace(/\.0$/, "") === f.phase) && formeCorrespond(p)
    && (f.spMin == null || (p.totaux?.SP_HS ?? -1) >= f.spMin) && (f.spMax == null || (p.totaux?.SP_HS ?? Infinity) <= f.spMax));
}

// ------------------------------------------------------------------ chargement

function chargerScript(src) {
  return new Promise((ok, ko) => {
    const s = document.createElement("script");
    s.src = src; s.onload = ok; s.onerror = () => ko(new Error(`${src} introuvable`));
    document.head.append(s);
  });
}

async function chargerLeaflet() {
  if (window.L) return window.L;
  const css = document.createElement("link");
  css.rel = "stylesheet"; css.href = "vendor/leaflet/leaflet.css";
  document.head.append(css);
  await chargerScript("vendor/leaflet/leaflet.js");
  return window.L;
}

/** Décodage TopoJSON → GeoJSON (arcs delta-encodés, transformation quantifiée), pour le fond hors ligne. */
function topoVersGeo(topo, objet) {
  const [sx, sy] = topo.transform.scale, [tx, ty] = topo.transform.translate;
  const arcs = topo.arcs.map((a) => { let x = 0, y = 0; return a.map(([dx, dy]) => [(x += dx) * sx + tx, (y += dy) * sy + ty]); });
  const anneau = (ids) => ids.flatMap((i, k) => { const a = i >= 0 ? arcs[i] : arcs[~i].slice().reverse(); return k ? a.slice(1) : a; });
  const geom = (g) => g.type === "Polygon" ? { type: "Polygon", coordinates: g.arcs.map(anneau) }
    : g.type === "MultiPolygon" ? { type: "MultiPolygon", coordinates: g.arcs.map((p) => p.map(anneau)) } : null;
  return { type: "FeatureCollection", features: topo.objects[objet].geometries.map((g) => ({ type: "Feature", id: g.id, properties: {}, geometry: geom(g) })).filter((f) => f.geometry) };
}

async function ouvrirCarte() {
  if (etat.vue3d) fermer3D(true);
  if (!etat.carte) etat.defilement = window.scrollY;
  etat.carte = true;
  document.querySelector(".centre").classList.add("mode-3d");
  document.documentElement.classList.add("mode-3d");
  document.getElementById("vue-carte").hidden = false;
  document.getElementById("bouton-carte").setAttribute("aria-pressed", "true");
  window.scrollTo(0, 0);
  ajuster3D();
  const statut = document.getElementById("carte-etat");
  if (!carte.map) {
    statut.hidden = false;
    statut.textContent = "Chargement de la carte…";
    try {
      carte.L = await chargerLeaflet();
      const r = await fetch("carte-suisse.json");
      if (!r.ok) throw new Error(`fond hors ligne : erreur ${r.status}`);
      carte.donnees = await r.json();
      construireCarte();
      statut.hidden = true;
    } catch (e) {
      statut.textContent = `La carte ne peut pas s'afficher : ${e.message || e}.`;
      return;
    }
  }
  carte.map.invalidateSize();
  majCarte();
}

function fermerCarte(sansRetour = false) {
  if (!etat.carte) return;
  etat.carte = false;
  document.getElementById("vue-carte").hidden = true;
  document.getElementById("bouton-carte").setAttribute("aria-pressed", "false");
  if (sansRetour) return;
  document.querySelector(".centre").classList.remove("mode-3d");
  document.documentElement.classList.remove("mode-3d");
  requestAnimationFrame(() => { FIGURES.forEach((b) => b.isConnected && b._dessiner?.()); window.scrollTo(0, etat.defilement); });
}

// ------------------------------------------------------------------ construction

function construireCarte() {
  const L = carte.L, d = carte.donnees;
  const map = L.map("carte-leaflet", { zoomControl: false, scrollWheelZoom: false, zoomSnap: 0.5, minZoom: 7, maxZoom: 19,
    maxBounds: [[45.4, 5.5], [48.2, 11]], attributionControl: true, preferCanvas: false });
  map.attributionControl.setPrefix(false);
  carte.map = map;
  map.setView(CENTRE_SUISSE, 8);
  // Empilement fixe, quel que soit l'ordre d'ajout : fond en tuiles (200) < fond hors ligne (250) < calques en tuiles
  // (350) < communes et districts (450) < projets (650). Sans panneaux dédiés, changer de fond le remettait par-dessus
  // les calques actifs, qui disparaissaient.
  map.createPane("fondVecteur").style.zIndex = 250;
  map.createPane("calques").style.zIndex = 350;
  map.createPane("vecteurs").style.zIndex = 450;
  map.createPane("projets").style.zIndex = 650;

  // Fonds en ligne. Des tuiles en erreur ne suffisent pas à conclure qu'on est hors ligne (une tuile refusée par un
  // proxy, un zoom rapide…) : elles déclenchent un test du réseau, et seul son échec bascule sur le fond minimum.
  // Les tuiles ne sont demandées qu'une fois le zoom posé (updateWhenIdle) : moins de requêtes pendant la molette.
  for (const f of FONDS.filter((x) => x.url)) {
    const finesse = f.finesse || 0;
    const t = L.tileLayer(f.url, { maxNativeZoom: f.max - finesse, maxZoom: 19, zoomOffset: finesse, tileSize: 256 >> finesse,
      updateWhenIdle: true, updateWhenZooming: false, keepBuffer: 1, attribution: SWISSTOPO, crossOrigin: true, pane: "tilePane" });
    t.on("tileload", () => majEnLigne(true));
    t.on("tileerror", () => testerReseau());
    carte.fonds[f.id] = t;
  }
  // fond hors ligne : pays, cantons, lacs (toujours dessinés sous les tuiles quand il n'y a pas de réseau)
  const vecteur = (objet, style, extra = {}) => L.geoJSON(topoVersGeo(d.topo, objet), { pane: "vecteurs", style, ...extra });
  carte.fonds.horsligne = L.layerGroup([
    vecteur("cantons", () => ({ color: teinte("--texte-2"), weight: 1.2, fillColor: teinte("--surface"), fillOpacity: 1 }), {
      pane: "fondVecteur",
      onEachFeature: (f, couche) => couche.bindTooltip(d.cantons[String(f.id)] || "", { sticky: true, className: "carte-info-bulle" }) }),
    vecteur("lakes", () => ({ stroke: false, fillColor: "#7DB3DA", fillOpacity: 0.55 }), { pane: "fondVecteur", interactive: false }),
  ]);
  // calques vectoriels (livrés) : communes nommées au survol, districts
  const nomCommune = (id) => d.communes[String(id)];
  for (const c of CALQUES) {
    if (c.id === "communes")
      carte.calques[c.id] = vecteur("municipalities", () => ({ color: "#5B6170", weight: 0.8, opacity: c.opacite, fill: true, fillOpacity: 0 }), {
        onEachFeature: (f, couche) => { const n = nomCommune(f.id); if (n) couche.bindTooltip(`${n[0]} (${n[1]})`, { sticky: true, className: "carte-info-bulle" }); } });
    else if (c.id === "districts")
      carte.calques[c.id] = vecteur("districts", () => ({ color: "#3A3F4B", weight: 1.6, dashArray: "6 4", opacity: c.opacite, fill: false }), { interactive: false });
    // couche WMS (pas de tuiles précalculées chez geo.admin.ch : cadastre, statistiques à l'hectare…) ou WMTS
    else if (c.wms) carte.calques[c.id] = L.tileLayer.wms("https://wms.geo.admin.ch/", { layers: c.id, format: "image/png",
      transparent: true, version: "1.3.0", maxZoom: 19, opacity: c.opacite, crossOrigin: true, pane: "calques",
      className: c.desature ? "calque-desature" : "", attribution: `${SWISSTOPO}, ${c.source}` });
    else carte.calques[c.id] = L.tileLayer(WMTS(c.id), { maxNativeZoom: 18, maxZoom: 19, opacity: c.opacite, crossOrigin: true,
      pane: "calques", attribution: `${SWISSTOPO}, ${c.source}` });
  }
  carte.projets = L.layerGroup().addTo(map);

  // réglages mémorisés (fond, calques actifs et opacités) ; hors ligne au départ : fond minimum
  let fond = "couleur";
  try { fond = localStorage.getItem(CLE_FOND) || fond; } catch { /* stockage indisponible */ }
  try {
    const memo = JSON.parse(localStorage.getItem(CLE_CALQUES) || "null");
    if (memo) for (const c of CALQUES) if (memo[c.id]) Object.assign(c, memo[c.id]);
  } catch { /* idem */ }
  choisirFond(carte.enLigne ? fond : "horsligne", false);
  for (const c of CALQUES) if (c.actif) appliquerCalque(c);
  panneauFondsCalques();
  brancherCarte();
  window.addEventListener("online", () => majEnLigne(true));
  window.addEventListener("offline", () => majEnLigne(false));
}

function choisirFond(id, memoriser = true) {
  const map = carte.map;
  for (const [k, f] of Object.entries(carte.fonds)) if (k !== id && map.hasLayer(f)) map.removeLayer(f);
  carte.fonds[id].addTo(map);
  carte.fond = id;
  map.getContainer().classList.toggle("fond-gris", id === "gris");     // calques en couleur passés en gris (style.css)
  if (memoriser) try { localStorage.setItem(CLE_FOND, id); } catch { /* stockage indisponible */ }
  document.querySelectorAll("#carte-fonds input").forEach((r) => { r.checked = r.value === id; });
}

/** Les 2 134 communes ne se lisent qu'à l'échelle régionale : en dessous, leurs limites sont retirées. */
const ZOOM_COMMUNES = 10;

function appliquerCalque(c) {
  const couche = carte.calques[c.id];
  const visible = c.actif && (c.id !== "communes" || carte.map.getZoom() >= ZOOM_COMMUNES);
  if (visible && !carte.map.hasLayer(couche)) couche.addTo(carte.map);
  if (!visible && carte.map.hasLayer(couche)) carte.map.removeLayer(couche);
  if (couche.setOpacity) couche.setOpacity(c.opacite);
  else couche.setStyle?.({ opacity: c.opacite });
}

function memoriserCalques() {
  try { localStorage.setItem(CLE_CALQUES, JSON.stringify(Object.fromEntries(CALQUES.map((c) => [c.id, { actif: c.actif, opacite: c.opacite }])))); }
  catch { /* stockage indisponible */ }
}

/** Test du réseau après des tuiles en erreur : une petite tuile de geo.admin.ch, au plus une fois toutes les 15 s. */
let dernierTest = 0;
async function testerReseau() {
  if (Date.now() - dernierTest < 15000) return;
  dernierTest = Date.now();
  const ctrl = new AbortController(), delai = setTimeout(() => ctrl.abort(), 8000);
  try {
    const r = await fetch(`${WMTS("ch.swisstopo.pixelkarte-grau", "jpeg").replace("{z}/{x}/{y}", "7/66/45")}?t=${dernierTest}`,
                          { cache: "no-store", signal: ctrl.signal });
    majEnLigne(r.ok);
  } catch {
    majEnLigne(false);
  } finally {
    clearTimeout(delai);
  }
}

/** En ligne ou non : bandeau, fond minimum si le réseau manque, calques en ligne grisés. */
function majEnLigne(enLigne) {
  if (carte.enLigne === enLigne) return;
  carte.enLigne = enLigne;
  document.getElementById("carte-hors-ligne").hidden = enLigne;
  if (!enLigne && carte.fond !== "horsligne") choisirFond("horsligne", false);
  if (enLigne && carte.fond === "horsligne") {     // réseau revenu : le fond choisi par l'utilisateur, s'il en avait un
    let memo = null;
    try { memo = localStorage.getItem(CLE_FOND); } catch { /* stockage indisponible */ }
    choisirFond(memo && memo !== "horsligne" ? memo : "couleur", false);
  }
  panneauFondsCalques();
}

function panneauFondsCalques() {
  document.getElementById("carte-hors-ligne").hidden = carte.enLigne;
  document.getElementById("carte-fonds").replaceChildren(...FONDS.map((f) => {
    const r = el("input", { type: "radio", name: "carte-fond", value: f.id });
    r.checked = carte.fond === f.id;
    r.disabled = !f.url ? false : !carte.enLigne;
    r.addEventListener("change", () => choisirFond(f.id));
    return el("label", { class: "case", title: f.url && !carte.enLigne ? "Hors ligne : fond indisponible" : "" }, r, f.nom);
  }));
  // calques rangés par thème, chaque thème repliable ; un thème qui a un calque actif reste déplié
  carte.groupesOuverts ??= new Set();     // thèmes fermés à l'ouverture : le compteur signale ceux qui ont un calque actif
  const ligneCalque = (c) => {
    const enLigne = c.vecteur || carte.enLigne;
    const cb = el("input", { type: "checkbox", "aria-label": c.nom });
    cb.checked = c.actif;
    cb.disabled = !enLigne;
    cb.addEventListener("change", () => { c.actif = cb.checked; appliquerCalque(c); memoriserCalques(); panneauFondsCalques(); });
    const ligne = el("li", {}, el("label", { class: "case", title: enLigne ? "" : "Hors ligne : calque indisponible" }, cb, c.nom));
    if (!c.actif) return ligne;
    const op = el("input", { type: "range", min: "0.1", max: "1", step: "0.05", "aria-label": `Opacité : ${c.nom}`, title: "Opacité" });
    op.value = String(c.opacite);
    op.disabled = !enLigne;
    op.addEventListener("input", () => { c.opacite = Number(op.value); appliquerCalque(c); memoriserCalques(); });
    ligne.append(op);
    if (!c.vecteur && carte.enLigne)
      ligne.append(el("img", { class: "carte-legende-img", src: LEGENDE(c.id), alt: `Légende : ${c.nom}`, loading: "lazy" }));
    return ligne;
  };
  document.getElementById("carte-calques").replaceChildren(...GROUPES_CALQUES.map((g) => {
    const calques = CALQUES.filter((c) => c.groupe === g), actifs = calques.filter((c) => c.actif).length;
    const bloc = el("details", { class: "carte-groupe" },
      el("summary", {}, g, actifs ? el("span", { class: "carte-groupe-compte", text: String(actifs) }) : null),
      el("ul", {}, ...calques.map(ligneCalque)));
    bloc.open = carte.groupesOuverts.has(g);
    bloc.addEventListener("toggle", () => { bloc.open ? carte.groupesOuverts.add(g) : carte.groupesOuverts.delete(g); });
    return el("li", {}, bloc);
  }));
}

// ------------------------------------------------------------------ projets

function dessinerProjets() {
  const L = carte.L, groupe = carte.projets;
  groupe.clearLayers();
  const places = projetsCarte().filter((p) => p.position);
  const spMax = Math.max(1, ...places.map((p) => p.totaux?.SP_HS || 0));
  // projets d'une même commune (même centre) : écartés en couronne de ~250 m
  const parPos = new Map();
  for (const p of places) { const k = p.position.join(","); if (!parPos.has(k)) parPos.set(k, []); parPos.get(k).push(p); }
  for (const liste of parPos.values()) liste.forEach((p, i) => {
    const a = (2 * Math.PI * i) / liste.length, d = liste.length > 1 ? 250 : 0;
    const latlng = versWgs84([p.position[0] + d * Math.cos(a), p.position[1] + d * Math.sin(a)]);
    const r = 8 + 7 * Math.sqrt((p.totaux?.SP_HS || 0) / spMax);       // 16 à 30 px selon la SP hors-sol
    const couleur = typoCouleur(p.infos?.categorie), coche = p.fiable && !etat.exclus.has(p.id);
    const c = etat.comparees.find((m) => m.id === p.id);
    const approx = p.precision === "commune";
    // Marqueur HTML (et non cercle SVG) : toujours recalé au zoom, et ses couleurs suivent le thème par CSS. Les cercles
    // SVG dans un panneau à part restaient parfois à l'échelle d'un zoom précédent, minuscules ou énormes.
    const diametre = Math.round(2 * r);
    const classes = ["carte-projet", !p.fiable ? "ecarte" : coche ? "coche" : "hors", approx ? "approx" : "", c ? "comparee" : ""];
    const m = L.marker(latlng, { pane: "projets", riseOnHover: true, keyboard: true,
      icon: L.divIcon({ className: classes.filter(Boolean).join(" "), iconSize: [diametre, diametre],
        // pastille + étiquette (ID), l'étiquette à droite de la pastille
        html: `<span class="pastille" style="--c:${couleur};${c ? `--anneau:var(--cmp${c.couleur})` : ""}"></span>` +
              `<span class="etiquette">${String(p.id).replace(/</g, "&lt;")}</span>` }) });
    const sp = p.totaux?.SP_HS, sup = p.kpis?.["SUP/SP_HS"]?.valeur;
    m.bindTooltip([`<b>${nomProjet(p).replace(/</g, "&lt;")}</b>`,
      [p.infos?.adresse, p.infos?.commune, p.infos?.canton].filter(Boolean).join(" · ").replace(/</g, "&lt;"),
      approx ? "<i>Placé au centre de la commune (adresse absente ou introuvable)</i>"
             : p.precision === "rue" ? "<i>Placé au milieu de la rue (numéro introuvable)</i>" : "",
      p.infos?.categorie || "Typologie non identifiée",
      p.infos?.forme ? `Forme : ${p.infos.forme.replace(/</g, "&lt;")}` : "",
      [sp ? `SP hors-sol ${F0.format(sp)} m²` : "", sup != null ? `SUP / SP hors-sol ${F1.format(sup * 100)} %` : ""].filter(Boolean).join(" · "),
      !p.fiable ? "Écarté : hors des références" : coche ? "Dans la référence · clic pour le retirer" : "Hors de la référence · clic pour l'ajouter",
      c ? "Maquette comparée" : ""].filter(Boolean).join("<br>"), { className: "carte-info-bulle", direction: "top", offset: [0, -r] });
    m.on("click", (e) => { L.DomEvent.stopPropagation(e); basculerReference(p.id, etat.exclus.has(p.id)); });
    m.addTo(groupe);
  });
  dessinerRayon();
}

function dessinerRayon() {
  if (!carte.map) return;
  carte.rayonCercle?.remove();
  carte.rayonCercle = null;
  const centre = carte.rayon.id && projet(carte.rayon.id)?.position;
  if (centre) carte.rayonCercle = carte.L.circle(versWgs84(centre), { radius: carte.rayon.km * 1000, color: teinte("--accent"),
    weight: 1.5, dashArray: "6 4", fillOpacity: 0.06, interactive: false }).addTo(carte.map);
}

/** Tout ce qui dépend de la référence ou des maquettes comparées : points et panneau. */
function majCarte() {
  if (!etat.carte || !carte.map) return;
  dessinerProjets();
  panneauCarte();
}

function panneauCarte() {
  const montres = projetsCarte(), places = montres.filter((p) => p.position), sans = montres.filter((p) => !p.position);
  const exacts = places.filter((p) => p.precision !== "commune").length;
  document.getElementById("carte-compte").textContent = `${places.length} projet${places.length > 1 ? "s" : ""} placé${places.length > 1 ? "s" : ""}` +
    ` (${exacts} à l'adresse)` + (sans.length ? ` · ${sans.length} sans position` : "");
  const typos = new Map();
  for (const p of montres) typos.set(p.infos?.categorie || "", (typos.get(p.infos?.categorie || "") || 0) + 1);
  const symbole = (classe, texte) => el("li", {}, el("i", { class: `carte-symbole ${classe}` }), texte);
  document.getElementById("carte-legende").replaceChildren(
    ...[...typos].sort((a, b) => b[1] - a[1]).map(([t, n]) => el("li", {}, el("i", { class: "carte-symbole coche", style: `--c:${typoCouleur(t)}` }),
      `${t || "Typologie non identifiée"} (${n})`)),
    symbole("coche neutre", "Dans la référence"), symbole("neutre", "Hors de la référence"), symbole("ecarte", "Écarté"),
    symbole("approx", "Au centre de la commune (sans adresse)"),
    el("li", { class: "secondaire" }, "Taille : SP hors-sol · anneau de couleur : maquette comparée"));
  const f = carte.filtres;
  const phases = [...new Set(projetsSelection().map((p) => String(p.infos?.phase ?? "").replace(/\.0$/, "")).filter(Boolean))].sort();
  const phase = document.getElementById("carte-phase");
  phase.replaceChildren(el("option", { value: "", text: "Toutes" }), ...phases.map((v) => el("option", { value: v, text: v })));
  phase.value = phases.includes(f.phase) ? f.phase : "";
  const forme = document.getElementById("carte-forme");     // même filtre que le volet (etat.forme)
  forme.replaceChildren(...optionsForme());
  forme.value = etat.forme;
  const centres = comparees().filter((c) => c.p.position);
  const choix = document.getElementById("carte-rayon-centre");
  choix.replaceChildren(el("option", { value: "", text: centres.length ? "Choisir une maquette comparée" : "Aucune maquette comparée placée" }),
    ...centres.map((c) => el("option", { value: c.id, text: c.id === MIEN ? c.p.nom : nomProjet(c.p) })));
  if (!centres.some((c) => c.id === carte.rayon.id)) carte.rayon.id = "";
  choix.value = carte.rayon.id;
  document.getElementById("carte-rayon-appliquer").disabled = !carte.rayon.id;
  document.getElementById("carte-sans-titre").textContent = `Sans position (${sans.length})`;
  document.getElementById("carte-sans").replaceChildren(...sans.map((p) => {
    const cb = el("input", { type: "checkbox", "aria-label": `Inclure ${nomProjet(p)} dans la référence` });
    cb.checked = p.fiable && !etat.exclus.has(p.id);
    cb.disabled = !p.fiable;
    cb.addEventListener("change", () => basculerReference(p.id, cb.checked));
    return el("li", {}, el("label", { title: p.fiable ? "" : "Écarté : hors des références" }, cb,
      el("span", { class: "mono", text: p.id }), el("span", { class: "nom", text: p.nom })));
  }));
  document.getElementById("carte-sans-bloc").hidden = !sans.length;
  dessinerRayon();
}

function basculerReference(id, dedans) {
  const p = etat.projets.get(id);
  if (!p?.fiable) return;
  dedans ? etat.exclus.delete(id) : etat.exclus.add(id);
  majReference();
}

// ------------------------------------------------------------------ interactions

/** Ce qu'il y a sous le clic : la commune (données livrées), puis, en ligne, les calques interrogeables actifs. */
async function informer(latlng) {
  const L = carte.L, lignes = [];
  const [e, n] = versLv95([latlng.lat, latlng.lng]);
  const d = carte.donnees, communes = carte.calques.communes;
  communes.eachLayer((couche) => {
    if (lignes.length || !couche.getBounds().contains(latlng)) return;
    const poly = couche.feature.geometry, dedans = (ring) => { let c = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > latlng.lat) !== (yj > latlng.lat) && latlng.lng < ((xj - xi) * (latlng.lat - yi)) / (yj - yi) + xi) c = !c; } return c; };
    const polys = poly.type === "Polygon" ? [poly.coordinates] : poly.coordinates;
    if (polys.some((p) => dedans(p[0]) && !p.slice(1).some(dedans))) {
      const nom = d.communes[String(couche.feature.id)];
      if (nom) lignes.push(`<b>${nom[0]}</b> (${nom[1]})`);
    }
  });
  lignes.push(`<span class="secondaire">E ${F0.format(e)} · N ${F0.format(n)}</span>`);
  const popup = L.popup({ className: "carte-info-bulle", maxWidth: 320 }).setLatLng(latlng).setContent(lignes.join("<br>")).openOn(carte.map);
  const interrogeables = CALQUES.filter((c) => c.actif && c.identify);
  if (!carte.enLigne || !interrogeables.length) return;
  popup.setContent([...lignes, '<span class="secondaire">Interrogation des calques…</span>'].join("<br>"));
  const b = carte.map.getBounds(), sw = versLv95([b.getSouth(), b.getWest()]), ne = versLv95([b.getNorth(), b.getEast()]);
  const taille = carte.map.getSize();
  // Une requête par tolérance (et non par calque) : une quinzaine de requêtes simultanées en perdaient une partie
  const parTolerance = new Map();
  for (const c of interrogeables) {
    const t = c.tolerance ?? 3;
    if (!parTolerance.has(t)) parTolerance.set(t, []);
    parTolerance.get(t).push(c);
  }
  const reponses = await Promise.all([...parTolerance].map(async ([tolerance, calques]) => {
    const q = new URLSearchParams({ geometryType: "esriGeometryPoint", geometry: `${Math.round(e)},${Math.round(n)}`, sr: "2056",
      imageDisplay: `${taille.x},${taille.y},96`, mapExtent: `${sw[0]},${sw[1]},${ne[0]},${ne[1]}`, tolerance: String(tolerance),
      layers: `all:${calques.map((c) => c.id).join(",")}`, returnGeometry: "false", lang: "fr" });
    for (let essai = 0; essai < 2; essai++) {
      try {
        const r = await fetch(`${IDENTIFY}?${q}`);
        if (r.ok) return (await r.json()).results || [];
      } catch { /* réseau : un second essai */ }
    }
    return [];
  }));
  // résultats rangés par calque, dans l'ordre des calques du panneau
  const parCalque = new Map();
  for (const x of reponses.flat()) {
    if (!parCalque.has(x.layerBodId)) parCalque.set(x.layerBodId, []);
    parCalque.get(x.layerBodId).push(x.attributes || {});
  }
  const resultats = interrogeables.map((c) => {
    const tous = parCalque.get(c.id) || [];
    if (!tous.length) return [];
    // statistiques à l'hectare : une seule ligne, l'année la plus récente ; ailleurs, jusqu'à deux objets
    return (c.wms && tous[0].i_year != null ? [c.identify(tous[0], tous)] : tous.map((a) => c.identify(a, tous))).filter(Boolean).slice(0, 2);
  });
  const plus = [...new Set(resultats.flat())].map((t) => t.replace(/</g, "&lt;"));
  if (carte.map.hasLayer(popup)) popup.setContent([...lignes, ...(plus.length ? plus : ['<span class="secondaire">Rien dans les calques actifs à cet endroit</span>'])].join("<br>"));
}

function brancherCarte() {
  const map = carte.map, L = carte.L, zone = document.getElementById("carte-scene");
  // molette : zoom après un clic dans la carte (jusqu'à ce que la souris en sorte) ou avec Ctrl ; sinon la page la garde
  map.on("mousedown", () => { carte.actif = true; zone.classList.add("actif"); });
  zone.addEventListener("mouseleave", () => { carte.actif = false; zone.classList.remove("actif"); });
  zone.addEventListener("wheel", (e) => {
    if (!carte.actif && !e.ctrlKey) return;
    e.preventDefault();
    map.setZoomAround(map.mouseEventToContainerPoint(e), map.getZoom() + (e.deltaY < 0 ? 0.5 : -0.5));
  }, { passive: false });
  map.on("click", (e) => { if (!carte.outil) informer(e.latlng); });
  // étiquettes des projets : seulement dès l'échelle régionale (à l'échelle de la Suisse elles se chevauchent)
  const echelle = () => map.getContainer().classList.toggle("vue-large", map.getZoom() < ZOOM_COMMUNES);
  echelle();
  map.on("zoomend", () => { appliquerCalque(CALQUES.find((c) => c.id === "communes")); echelle(); });
  // outils de zone : glisser trace un rectangle ; les projets fiables affichés dedans sont cochés ou décochés
  let depart = null, rect = null;
  map.on("mousedown", (e) => {
    if (!carte.outil) return;
    depart = e.latlng;
    map.dragging.disable();
    rect = L.rectangle([depart, depart], { color: teinte("--accent"), weight: 1.5, fillOpacity: 0.1, interactive: false }).addTo(map);
  });
  map.on("mousemove", (e) => { if (depart && rect) rect.setBounds([depart, e.latlng]); });
  map.on("mouseup", () => {
    if (!depart) return;
    const bornes = rect.getBounds();
    rect.remove(); rect = null; depart = null;
    map.dragging.enable();
    const dedans = projetsCarte().filter((p) => p.fiable && p.position && bornes.contains(versWgs84(p.position)));
    for (const p of dedans) carte.outil === "cocher" ? etat.exclus.delete(p.id) : etat.exclus.add(p.id);
    if (dedans.length) majReference();
  });
}

function zoomer(pas) { carte.map?.setZoom(carte.map.getZoom() + pas); }

function brancherOutilsCarte() {
  document.getElementById("bouton-carte").addEventListener("click", () => (etat.carte ? fermerCarte() : ouvrirCarte()));
  document.getElementById("carte-fermer").addEventListener("click", () => fermerCarte());
  document.getElementById("carte-plus").addEventListener("click", () => zoomer(1));
  document.getElementById("carte-moins").addEventListener("click", () => zoomer(-1));
  document.getElementById("carte-cadrer").addEventListener("click", () => {
    const places = projetsCarte().filter((p) => p.position).map((p) => versWgs84(p.position));
    if (places.length) carte.map.fitBounds(places, { padding: [60, 60], maxZoom: 14 });
    else carte.map.setView(CENTRE_SUISSE, 8);
  });
  for (const [id, outil] of [["carte-zone-cocher", "cocher"], ["carte-zone-decocher", "decocher"]]) {
    document.getElementById(id).addEventListener("click", () => {
      carte.outil = carte.outil === outil ? null : outil;
      for (const x of ["carte-zone-cocher", "carte-zone-decocher"])
        document.getElementById(x).setAttribute("aria-pressed", String(carte.outil === (x.endsWith("decocher") ? "decocher" : "cocher")));
      document.getElementById("carte-scene").classList.toggle("outil-zone", !!carte.outil);
    });
  }
  const f = carte.filtres, nombre = (v) => (v.trim() === "" ? null : Number(v));
  document.getElementById("carte-phase").addEventListener("change", (e) => { f.phase = e.target.value; majCarte(); });
  document.getElementById("carte-forme").addEventListener("change", (e) => choisirForme(e.target.value));
  document.getElementById("carte-precision").addEventListener("change", (e) => { f.precision = e.target.value; majCarte(); });
  document.getElementById("carte-sp-min").addEventListener("input", (e) => { f.spMin = nombre(e.target.value); majCarte(); });
  document.getElementById("carte-sp-max").addEventListener("input", (e) => { f.spMax = nombre(e.target.value); majCarte(); });
  document.getElementById("carte-fiables").addEventListener("change", (e) => { f.fiables = e.target.checked; majCarte(); });
  document.getElementById("carte-maquette").addEventListener("change", (e) => { f.maquette = e.target.checked; majCarte(); });
  document.getElementById("carte-rayon-centre").addEventListener("change", (e) => {
    carte.rayon.id = e.target.value;
    document.getElementById("carte-rayon-appliquer").disabled = !carte.rayon.id;
    dessinerRayon();
    const centre = carte.rayon.id && projet(carte.rayon.id)?.position;
    if (centre) carte.map.fitBounds(carte.L.latLng(versWgs84(centre)).toBounds(carte.rayon.km * 2200));
  });
  document.getElementById("carte-rayon-km").addEventListener("input", (e) => { carte.rayon.km = Math.max(1, Number(e.target.value) || 10); dessinerRayon(); });
  document.getElementById("carte-rayon-appliquer").addEventListener("click", () => {
    const centre = projet(carte.rayon.id)?.position;
    if (!centre) return;
    for (const p of fiablesSelection()) (p.position && kmEntre(p.position, centre) <= carte.rayon.km) ? etat.exclus.delete(p.id) : etat.exclus.add(p.id);
    majReference();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && etat.carte && !e.target.closest?.("input, select, textarea")) fermerCarte();
  });
}
