// Dashboard du benchmark (docs/DESIGN_PLAN.md, Évolutions 3.1 à 3.5 ; docs/V3_PLAN.md §4 et §9 ; docs/V5_PLAN.md).
// Données : benchmark.json de `sia-check --benchmark`. Dans SIA Check, l'application les transmet par WebView2
// (window.chrome.webview) ; sur un serveur, la page les lit à côté d'elle (?data=… pour un autre chemin).
// Le moteur fait foi pour les totaux, la fiabilité et les distances ; la page refait les médianes, quartiles et
// ratios combinés sur la référence que l'utilisateur coche.
//
// Deux ensembles distincts (V5_PLAN, partie 1) :
//   référence  : projets fiables du pré-filtre, moins ceux que l'utilisateur décoche (etat.exclus). Tous les calculs.
//   comparées  : maquettes situées sur les graphiques, chacune à sa couleur (etat.comparees). Aucun calcul de référence.
"use strict";

const PARAMS = new URLSearchParams(location.search);
const MIN_REFERENCE = 3;     // en dessous, la référence est fragile (V3_PLAN §4.4)
const TAILLE_GROUPE = 5;
const MAX_COMPAREES = 6;     // une couleur chacune (style.css, --cmp1 à --cmp6)
const SVG = "http://www.w3.org/2000/svg";
const MIEN = "mien";

const etat = { data: null, projets: new Map(), kpis: [], tri: null, mien: null, mienSource: "saisie", prix: null,
                exclus: new Set(), comparees: [], recherche: "", forme: "", triReference: "id", vue3d: null, carte: false, defilement: 0 };
/** Dossier des maquettes 3D (MAQ-*.json.gz) : donné par SIA Check (?maquettes=base/), sinon celui de benchmark.json. */
const BASE_MAQUETTES = PARAMS.get("maquettes") ?? (PARAMS.get("data") || "").replace(/[^/]*$/, "");

/** Un projet de la base, ou « Mon projet » (id « mien »). */
const projet = (id) => (id === MIEN ? etat.mien : etat.projets.get(id));

// ------------------------------------------------------------------ formats

const nf = (d) => new Intl.NumberFormat("fr-CH", { minimumFractionDigits: d, maximumFractionDigits: d });
const F0 = nf(0), F1 = nf(1), F2 = nf(2);

function valeur(kpi, v) {
  if (v == null) return "—";
  if (kpi.unite === "%") return `${F1.format(v * 100)} %`;
  if (kpi.unite === "m") return `${F2.format(v)} m`;
  if (!kpi.unite) return F2.format(v);       // rapport sans unité (coefficient de forme)
  return `${F0.format(v)} ${kpi.unite}`;
}

function ecartTexte(kpi, d) {
  const s = d > 0 ? "+" : d < 0 ? "−" : "±";
  const a = Math.abs(d);
  if (kpi.unite === "%") { const p = a * 100; return `${s}${F1.format(p)} pt${p >= 2 ? "s" : ""}`; }
  if (kpi.unite === "m") return `${s}${F2.format(a)} m`;
  if (!kpi.unite) return `${s}${F2.format(a)}`;
  return `${s}${F0.format(a)} ${kpi.unite}`;
}

const signe = (x) => (x > 0 ? "+" : x < 0 ? "−" : "±");

function el(tag, attrs = {}, ...enfants) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k === "text") e.textContent = v; else e.setAttribute(k, v);
  }
  for (const c of enfants) if (c != null) e.append(c);
  return e;
}

function svg(tag, attrs = {}, texte) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (texte != null) e.textContent = texte;
  return e;
}

const titre = (e, t) => { e.append(svg("title", {}, t)); return e; };

/** Icônes au trait (24 × 24, couleur du texte) : boutons et marques qui remplacent les libellés. */
const ICONES = {
  tout: '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M8 12.5l2.8 2.8L16.5 9"/>',
  aucun: '<rect x="3" y="3" width="18" height="18" rx="4"/>',
  partiel: '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M8 12h8"/>',
  proches: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
  alerte: '<path d="M12 3.5L21.5 20h-19z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  horsfiltre: '<path d="M4 5h16l-6 7.5V18l-4 2v-7.5z"/><path d="M3 3l18 18"/>',
  // forme des bâtiments : un plan en L
  forme: '<path d="M5 4h6v10h8v6H5z"/>',
  tri: '<path d="M7 4v16M3.5 7.5L7 4l3.5 3.5M17 20V4M13.5 16.5L17 20l3.5-3.5"/>',
  reinit: '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v5h5"/>',
  replier: '<path d="M6 15l6-6 6 6"/>',
  deplier: '<path d="M6 9l6 6 6-6"/>',
  effacer: '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5"/>',
  ajouter: '<path d="M12 5v14M5 12h14"/>',
  retirer: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  loupe: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>',
  coche: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  cube: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
  dessus: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 12h16M12 4v16"/>',
  excel: '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M9 12l5 6M14 12l-5 6"/>',
  carte: '<path d="M3 6.5l6-2.5 6 2.5 6-2.5v13.5l-6 2.5-6-2.5-6 2.5z"/><path d="M9 4v13.5M15 6.5V20"/>',
  zonePlus: '<rect x="3.5" y="3.5" width="17" height="17" rx="2" stroke-dasharray="3 2.5"/><path d="M12 8.5v7M8.5 12h7"/>',
  zoneMoins: '<rect x="3.5" y="3.5" width="17" height="17" rx="2" stroke-dasharray="3 2.5"/><path d="M8.5 12h7"/>',
  moins: '<path d="M5 12h14"/>',
  cadrer: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
};

function icone(nom) {
  const s = svg("svg", { viewBox: "0 0 24 24", class: "icone", "aria-hidden": "true", fill: "none", stroke: "currentColor",
    "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round" });
  s.innerHTML = ICONES[nom];
  return s;
}

/** Bouton-icône : le libellé passe en infobulle et en nom accessible. */
function boutonIcone(nom, libelle, action, classe = "") {
  const b = el("button", { type: "button", class: `icone-btn ${classe}`.trim(), title: libelle, "aria-label": libelle }, icone(nom));
  b.addEventListener("click", (e) => { e.stopPropagation(); action(); });
  return b;
}

/** Marque discrète (écarté, hors filtre) : une icône et son explication au survol. */
const marque = (nom, libelle, classe = "") =>
  el("span", { class: `marque-icone ${classe}`.trim(), title: libelle, role: "img", "aria-label": libelle }, icone(nom));

/** Icônes des éléments statiques de la page (data-icone). */
function poserIcones(racine = document) {
  for (const e of racine.querySelectorAll("[data-icone]")) e.replaceChildren(icone(e.dataset.icone));
}
const nomProjet = (p) => `${p.id} · ${p.nom}`;

// ------------------------------------------------------------------ calculs

/** Ratio combiné, quartiles et valeurs des projets qui ont les deux termes du KPI. */
function combiner(projets, kpi) {
  const termes = projets.map((p) => [p, p.kpis[kpi.id]]).filter(([, r]) => r);
  if (!termes.length) return { n: 0 };
  const valeurs = termes.map(([p, r]) => ({ p, v: r.valeur })).sort((a, b) => a.v - b.v);
  const sn = termes.reduce((s, [, r]) => s + r.num, 0), sd = termes.reduce((s, [, r]) => s + r.den, 0);
  const q = (f) => { const i = (valeurs.length - 1) * f, lo = Math.floor(i), hi = Math.min(lo + 1, valeurs.length - 1);
                     return valeurs[lo].v + (valeurs[hi].v - valeurs[lo].v) * (i - lo); };
  return { n: valeurs.length, combine: sn / sd, q1: q(0.25), mediane: q(0.5), q3: q(0.75), valeurs };
}

/** Les projets fiables du pré-filtre les plus proches de `ref` (distances du moteur, ou recalculées pour « Mon projet »). */
function candidats(ref) {
  return Object.entries(ref?.distances || {})
    .map(([id, d]) => ({ p: etat.projets.get(id), d }))
    .filter(({ p }) => p && p.fiable && p.id !== ref.id && dansSelection(p))
    .sort((a, b) => a.d - b.d)
    .slice(0, TAILLE_GROUPE);
}

const norm = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase();

// ------------------------------------------------------------------ Sélection (Évolution 3.5)

const CLE_SELECTION = "benchmark.selection";
const CRITERES = [["typologie", "categorie", "Toutes"], ["canton", "canton", "Tous"], ["intervention", "intervention", "Toutes"]];
const NON_IDENTIFIEE = "__non_identifiee";
const KPI_CLES = ["SUP/SP_HS", "VITRE/PLEINE", "FORME"];
/** Groupes de ratios (DESIGN_PLAN, Évolution 4.3), dans l'ordre de l'onglet Ratios de l'application. La pastille
 *  reprend la couleur des surfaces mesurées (SP, SH, façade) ; le titre dit toujours le groupe. */
const GROUPES = [
  { titre: "SIA 416", definition: "surfaces de plancher : utile, dégagement, installations, construction", couleur: "#B1005D",
    familles: ["Rendement", "Pertes", "Sous-sol"] },
  { titre: "USPI 2014", definition: "surfaces habitables et de vente", couleur: "#22A08C", familles: ["USPI 2014"] },
  { titre: "Enveloppe", definition: "façades, vitrages et toitures", couleur: "#A8A29E", familles: ["Enveloppe"] },
  { titre: "Programme", definition: "cages d'escalier et logements", couleur: "#6B7280", familles: ["Programme"] },
];
const sel = { typologie: "", canton: "", intervention: "" };

/** Le projet passe la sélection ; `sauf` ignore un critère (comptes des listes, suggestions d'élargissement). */
function dansSelection(p, sauf = null, s = sel) {
  return CRITERES.every(([cle, info]) => {
    if (cle === sauf || !s[cle]) return true;
    if (s[cle] === NON_IDENTIFIEE) return !p.infos?.[info];
    return p.infos?.[info] != null && norm(p.infos[info]) === norm(s[cle]);
  });
}

const projetsSelection = () => etat.data.projets.filter((p) => dansSelection(p));
const fiablesSelection = () => projetsSelection().filter((p) => p.fiable);
/** La référence : projets fiables du pré-filtre que l'utilisateur n'a pas décochés. Seule base des calculs. */
const reference = () => fiablesSelection().filter((p) => !etat.exclus.has(p.id));
const selectionActive = () => CRITERES.some(([cle]) => sel[cle]);

function libelleSelection() {
  const parts = CRITERES.filter(([cle]) => sel[cle]).map(([cle]) => sel[cle] === NON_IDENTIFIEE ? "Typologie non identifiée" : sel[cle]);
  return parts.length ? parts.join(" · ") : "Tous les projets";
}

function initSelection() {
  try { Object.assign(sel, JSON.parse(localStorage.getItem(CLE_SELECTION) || "{}")); } catch { /* stockage indisponible */ }
  for (const [cle] of CRITERES) if (PARAMS.has(cle)) sel[cle] = PARAMS.get(cle);     // un lien partagé fait foi
  const form = document.getElementById("selection");
  // les volets collent sous la barre (onglets et pré-filtre), quelle que soit sa hauteur (retour à la ligne en fenêtre étroite)
  const barre = document.querySelector(".entete-page");
  const hauteur = () => { document.documentElement.style.setProperty("--haut-selection", `${barre.offsetHeight}px`); ajuster3D(); };
  hauteur();
  if ("ResizeObserver" in window) new ResizeObserver(hauteur).observe(barre);
  form.addEventListener("change", (e) => { sel[e.target.name] = e.target.value; majSelection(); });
  form.addEventListener("submit", (e) => e.preventDefault());
  document.getElementById("selection-reinit").addEventListener("click", () => {
    for (const [cle] of CRITERES) sel[cle] = "";
    majSelection();
  });
  remplirSelection();
}

/** Listes de la barre : valeurs présentes dans la base, chacune avec son nombre de projets fiables selon les autres choix. */
function remplirSelection() {
  const form = document.getElementById("selection").elements;
  for (const [cle, info, tous] of CRITERES) {
    const base = etat.data.projets.filter((p) => p.fiable && dansSelection(p, cle));
    const compte = (v) => base.filter((p) => v === NON_IDENTIFIEE ? !p.infos?.[info] : p.infos?.[info] && norm(p.infos[info]) === norm(v)).length;
    const valeurs = [...new Set(etat.data.projets.map((p) => p.infos?.[info]).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr"));
    if (sel[cle] && sel[cle] !== NON_IDENTIFIEE && !valeurs.some((v) => norm(v) === norm(sel[cle]))) valeurs.push(sel[cle]);
    const options = [el("option", { value: "", text: `${tous} (${base.length})` }),
      ...valeurs.map((v) => el("option", { value: v, text: `${v} (${compte(v)})` }))];
    if (cle === "typologie" && etat.data.projets.some((p) => !p.infos?.categorie))
      options.push(el("option", { value: NON_IDENTIFIEE, text: `Non identifiée (${compte(NON_IDENTIFIEE)})` }));
    form[cle].replaceChildren(...options);
    form[cle].value = valeurs.find((v) => norm(v) === norm(sel[cle])) ?? sel[cle];
  }
  const n = fiablesSelection().length, r = reference().length;
  document.getElementById("selection-resume").textContent =
    `${r} projet${r > 1 ? "s" : ""} de référence sur ${n} fiable${n > 1 ? "s" : ""}`;
  document.getElementById("selection-reinit").hidden = !selectionActive();
}

/** Sélection logement (ou toutes typologies) : seule à donner un sens aux ratios par logement et au mix. */
function selectionLogement() {
  return !sel.typologie || norm(sel.typologie).startsWith("logement");
}

/** KPI de la sélection : ceux propres au logement (SUP par logement…) n'ont pas de sens pour un hôpital. */
function kpisSelection() {
  return etat.kpis.filter((k) => k.typologie !== "logement" || selectionLogement());
}

function majSelection() {
  try { localStorage.setItem(CLE_SELECTION, JSON.stringify(sel)); } catch { /* stockage indisponible */ }
  const url = new URL(location.href);
  for (const [cle] of CRITERES) sel[cle] ? url.searchParams.set(cle, sel[cle]) : url.searchParams.delete(cle);
  try { history.replaceState(null, "", url); } catch { /* adresse non modifiable (aperçu) */ }
  majReference();
}

/** La référence a changé (pré-filtre, case cochée) : tout ce qui en dépend est recalculé. */
function majReference() {
  sauverVolets();
  remplirSelection();
  dessinerVolets();
  dessinerRatios();
  dessinerAnatomie();
  dessinerProgramme();
  dessinerBase();
  dessinerTypologies();
  majVue3D();
  majCarte();
}

/** Les maquettes comparées ont changé : seuls les repères bougent, jamais les valeurs de référence. */
function majComparees() {
  sauverVolets();
  dessinerVolets();
  dessinerRatios();
  dessinerAnatomie();
  majVue3D();
  majCarte();
}

/** Élargissement qui redonne le plus de projets fiables, en retirant un seul critère (canton d'abord). */
function suggestionElargir() {
  for (const cle of ["canton", "intervention", "typologie"]) {
    if (!sel[cle]) continue;
    const n = etat.data.projets.filter((p) => p.fiable && dansSelection(p, cle)).length;
    if (n > fiablesSelection().length) return { cle, n };
  }
  return null;
}

// ------------------------------------------------------------------ Volets : maquettes comparées et projets de référence

const CLE_EXCLUS = "benchmark.exclus";
const CLE_COMPAREES = "benchmark.comparees";
const CLE_MENU = "benchmark.menuComparees";

function initVolets() {
  try {
    for (const id of JSON.parse(localStorage.getItem(CLE_EXCLUS) || "[]")) if (etat.projets.has(String(id))) etat.exclus.add(String(id));
    etat.comparees = JSON.parse(localStorage.getItem(CLE_COMPAREES) || "[]")
      .filter((c) => c && (c.id === MIEN || etat.projets.has(String(c.id))) && c.couleur >= 1 && c.couleur <= MAX_COMPAREES)
      .slice(0, MAX_COMPAREES);
  } catch { /* stockage indisponible : référence complète, rien de comparé */ }
  const recherche = document.getElementById("recherche"), menu = document.getElementById("volet-comparees");
  // une recherche ouvre le menu des maquettes, pour que ses résultats se voient
  recherche.addEventListener("input", () => { etat.recherche = recherche.value; if (etat.recherche) menu.open = true; dessinerVolets(); });
  try { menu.open = localStorage.getItem(CLE_MENU) === "1"; } catch { /* stockage indisponible : menu fermé */ }
  menu.addEventListener("toggle", () => { try { localStorage.setItem(CLE_MENU, menu.open ? "1" : "0"); } catch { /* idem */ } });
  const tri = document.getElementById("references-tri");
  tri.addEventListener("change", () => { etat.triReference = tri.value; dessinerVolets(); });
  document.getElementById("references-forme").addEventListener("change", (e) => choisirForme(e.target.value));
  // un seul bouton : tout cocher s'il manque un projet, sinon tout décocher ; avec un filtre de forme, les projets de
  // cette forme seulement (la référence se réduit ainsi à une forme : « décocher tout », filtrer, « cocher »)
  document.getElementById("references-bascule").addEventListener("click", () => {
    const fiables = fiablesSelection().filter((p) => formeCorrespond(p)), tous = fiables.every((p) => !etat.exclus.has(p.id));
    for (const p of fiables) tous ? etat.exclus.add(p.id) : etat.exclus.delete(p.id);
    majReference();
  });
}

function sauverVolets() {
  try {
    localStorage.setItem(CLE_EXCLUS, JSON.stringify([...etat.exclus]));
    localStorage.setItem(CLE_COMPAREES, JSON.stringify(etat.comparees));
  } catch { /* stockage indisponible */ }
}

const estComparee = (id) => etat.comparees.some((c) => c.id === id);
const couleurDe = (c) => `var(--cmp${c.couleur})`;

/** Maquettes comparées, dans l'ordre d'ajout, avec leur projet ; « Mon projet » sans surfaces saisies est omis des figures. */
function comparees() {
  return etat.comparees.map((c) => ({ ...c, p: projet(c.id), couleur: couleurDe(c) })).filter((c) => c.p);
}

function basculerComparee(id) {
  if (estComparee(id)) etat.comparees = etat.comparees.filter((c) => c.id !== id);
  else {
    if (etat.comparees.length >= MAX_COMPAREES) return;
    const prises = new Set(etat.comparees.map((c) => c.couleur));
    const couleur = [...Array(MAX_COMPAREES).keys()].map((i) => i + 1).find((i) => !prises.has(i));
    etat.comparees.push({ id, couleur });
  }
  if (id === MIEN) document.getElementById("saisie").hidden = !estComparee(MIEN);
  majComparees();
}

/** La référence réduite aux projets les plus proches d'une maquette (proximité de l'ancien onglet Comparer). */
function cocherProches(id) {
  const proches = new Set(candidats(projet(id)).map((c) => c.p.id));
  if (!proches.size) return;
  for (const p of fiablesSelection()) proches.has(p.id) ? etat.exclus.delete(p.id) : etat.exclus.add(p.id);
  majReference();
}

function correspond(p) {
  const q = norm(etat.recherche);
  if (!q) return true;
  return [p.id, p.nom, p.infos?.commune, p.infos?.canton].some((v) => v != null && norm(v).includes(q));
}

// ------------------------------------------------------------------ forme des bâtiments (V5_PLAN, partie 5)

const FORME_ILOT = "ilot", FORME_AUCUNE = "aucune";
/** Formes de la base, dans l'ordre de la liste du moteur (benchmark.json, listes.Forme). */
function formesBase() {
  const ordre = etat.data.listes?.Forme || [];
  const vues = new Set(etat.data.projets.flatMap((p) => Object.values(p.infos?.formes || {})));
  return [...vues].sort((a, b) => (ordre.indexOf(a) + 1 || 99) - (ordre.indexOf(b) + 1 || 99) || a.localeCompare(b, "fr"));
}
/** Filtre de forme (volet et carte, un seul état) : une forme portée par un des bâtiments, l'îlot, ou sans forme. */
function formeCorrespond(p, f = etat.forme) {
  const formes = Object.values(p.infos?.formes || {});
  if (!f) return true;
  if (f === FORME_ILOT) return formes.length > 1;
  if (f === FORME_AUCUNE) return !formes.length;
  return formes.includes(f);
}
/** Options du filtre de forme, avec le nombre de projets du pré-filtre pour chacune. */
function optionsForme() {
  const base = projetsSelection(), n = (f) => base.filter((p) => formeCorrespond(p, f)).length;
  return [el("option", { value: "", text: `Toutes les formes (${base.length})` }),
    ...formesBase().map((f) => el("option", { value: f, text: `${f} (${n(f)})` })),
    el("option", { value: FORME_ILOT, text: `Îlot de bâtiments (${n(FORME_ILOT)})` }),
    el("option", { value: FORME_AUCUNE, text: `Forme non renseignée (${n(FORME_AUCUNE)})` })];
}
function choisirForme(f) {
  etat.forme = f;
  dessinerVolets();
  if (typeof majCarte === "function") majCarte();
}
/** Libellé de la forme d'un projet, pour les listes et les infobulles. */
const formeTexte = (p) => p.infos?.forme || "";

const pastille = (couleur, titre = "") => el("i", { class: "pastille-cmp", style: `background:${couleur}`, title: titre, "aria-hidden": "true" });

function dessinerVolets() {
  // Maquettes à comparer : les comparées d'abord (même hors pré-filtre), puis Mon projet et les projets du pré-filtre
  const pleines = etat.comparees.length >= MAX_COMPAREES;
  const choisies = comparees();
  const autres = [{ id: MIEN }, ...projetsSelection().sort((a, b) => String(a.id).localeCompare(String(b.id), "fr", { numeric: true }))]
    .filter((x) => !estComparee(x.id));
  const items = [...choisies.map((c) => ({ id: c.id, c })), ...autres];
  const ligneComparee = ({ id, c }) => {
    const p = projet(id) || { id, nom: "Mon projet", infos: {} };
    if (id !== MIEN && !c && !correspond(p)) return null;
    const cb = el("input", { type: "checkbox", "aria-label": `Comparer ${id === MIEN ? "Mon projet" : nomProjet(p)}` });
    cb.checked = !!c;
    cb.disabled = !c && pleines;
    cb.addEventListener("change", () => basculerComparee(id));
    const nom = id === MIEN ? el("span", { class: "nom", text: `★ Mon projet${etat.mien?.nom && etat.mien.nom !== "Mon projet" ? " : " + etat.mien.nom : ""}` })
                            : el("span", { class: "nom", text: p.nom, title: [p.nom, p.infos?.commune].filter(Boolean).join(" · ") });
    const label = el("label", { title: cb.disabled ? `${MAX_COMPAREES} maquettes au plus : retirez-en une` : "" }, cb,
      c ? pastille(c.couleur) : el("i", { class: "pastille-cmp vide", "aria-hidden": "true" }),
      id === MIEN ? null : el("span", { class: "mono", text: p.id }), nom);
    const li = el("li", { class: c ? "choisie" : "" }, label);
    if (p.maquette) li.append(boutonCube(p));
    if (id !== MIEN && !p.fiable) li.append(marque("alerte", "Écarté : données incohérentes, hors des références, comparable pour mémoire"));
    if (c && id !== MIEN && !dansSelection(p)) li.append(marque("horsfiltre", "Hors du pré-filtre"));
    if (c && candidats(c.p).length)
      li.append(boutonIcone("proches", `Ne garder dans la référence que les ${TAILLE_GROUPE} projets les plus proches de cette maquette`,
        () => cocherProches(id), "petit"));
    return li;
  };
  document.getElementById("comparees").replaceChildren(...items.map(ligneComparee).filter(Boolean));
  document.getElementById("comparees-compte").textContent = `${etat.comparees.length} / ${MAX_COMPAREES}`;
  // menu fermé : les pastilles disent ce qui est comparé
  document.getElementById("comparees-pastilles").replaceChildren(...choisies.map((c) =>
    pastille(c.couleur, c.id === MIEN ? `★ ${c.p.nom}` : nomProjet(c.p))));

  // Projets de référence : les fiables du pré-filtre, cochés sauf exclusion
  const fiables = fiablesSelection();
  const ordreFormes = formesBase();
  const cleTri = { id: (p) => p.id, nom: (p) => p.nom, sp: (p) => -(p.totaux?.SP_HS ?? -1),
                   // forme : dans l'ordre de la liste, les îlots ensuite, les projets sans forme à la fin
                   forme: (p) => { const f = Object.values(p.infos?.formes || {});
                                   return f.length === 1 ? ordreFormes.indexOf(f[0]) : f.length > 1 ? 900 : 999; } }[etat.triReference];
  const triees = [...fiables].sort((a, b) => {
    const x = cleTri(a), y = cleTri(b);
    return typeof x === "number" ? x - y : String(x).localeCompare(String(y), "fr", { numeric: true });
  });
  const visibles = triees.filter((p) => correspond(p) && formeCorrespond(p));
  const choixForme = document.getElementById("references-forme");
  choixForme.replaceChildren(...optionsForme());
  choixForme.value = etat.forme;
  choixForme.classList.toggle("actif", !!etat.forme);
  document.getElementById("references").replaceChildren(...visibles.map((p) => {
    const cb = el("input", { type: "checkbox", "aria-label": `Inclure ${nomProjet(p)} dans la référence` });
    cb.checked = !etat.exclus.has(p.id);
    cb.addEventListener("change", () => { cb.checked ? etat.exclus.delete(p.id) : etat.exclus.add(p.id); majReference(); });
    const c = etat.comparees.find((x) => x.id === p.id);
    const sp = p.totaux?.SP_HS;
    return el("li", { class: cb.checked ? "" : "decoche" },
      el("label", { title: [nomProjet(p), p.infos?.commune, p.infos?.categorie, formeTexte(p)].filter(Boolean).join(" · ") }, cb,
        el("span", { class: "mono", text: p.id }), el("span", { class: "nom", text: p.nom })),
      c ? pastille(couleurDe(c), "Aussi comparée") : null,
      el("span", { class: "secondaire taille", text: sp ? `${F0.format(sp)} m²` : "" }),
      p.maquette ? boutonCube(p) : el("span", { class: "sans-cube", "aria-hidden": "true" }));
  }));
  const r = reference().length;
  document.getElementById("references-compte").textContent = `${r} / ${fiables.length}`;
  // bouton unique : son icône dit l'état (tout, rien, une partie), son clic fait l'inverse ; sur la forme filtrée s'il y en a une
  const cibles = fiables.filter((p) => formeCorrespond(p)), rc = cibles.filter((p) => !etat.exclus.has(p.id)).length;
  const bascule = document.getElementById("references-bascule"), tous = cibles.length > 0 && rc === cibles.length;
  const quoi = etat.forme ? `les ${cibles.length} projets de cette forme` : "tous les projets de référence";
  bascule.replaceChildren(icone(tous ? "tout" : rc === 0 ? "aucun" : "partiel"));
  bascule.title = `${tous ? "Décocher" : "Cocher"} ${quoi}`;
  bascule.setAttribute("aria-label", bascule.title);
  bascule.disabled = !cibles.length;
  const vide = document.getElementById("references-vide");
  vide.hidden = visibles.length > 0;
  vide.textContent = !fiables.length ? `Aucun projet fiable pour ${libelleSelection()}.`
    : etat.forme && !cibles.length ? "Aucun projet fiable de cette forme." : "Aucun projet ne correspond à la recherche.";
}

// ------------------------------------------------------------------ Tendances (Évolution 4.10)

const NOMS_CRITERES = { typologie: "la typologie", canton: "le canton", intervention: "le type d'intervention" };

function dessinerRatios() {
  const ref = reference(), fiables = fiablesSelection(), tous = projetsSelection();
  const cmp = comparees();
  const bandeau = document.getElementById("ratios-bandeau");
  bandeau.hidden = ref.length >= MIN_REFERENCE;
  if (!bandeau.hidden) {
    bandeau.replaceChildren(ref.length ? `${ref.length} projet${ref.length > 1 ? "s" : ""} de référence : référence fragile.`
                            : fiables.length ? "Aucun projet de référence coché." : `Aucun projet fiable pour ${libelleSelection()}.`);
    if (fiables.length > ref.length) {
      const b = el("button", { type: "button", class: "lien", text: `Recocher les ${fiables.length} projets fiables` });
      b.addEventListener("click", () => { for (const p of fiables) etat.exclus.delete(p.id); majReference(); });
      bandeau.append(" ", b);
    } else {
      const s = suggestionElargir();
      if (s) {
        const b = el("button", { type: "button", class: "lien", text: `Élargir : sans ${NOMS_CRITERES[s.cle]} (${s.n} projets)` });
        b.addEventListener("click", () => { sel[s.cle] = ""; majSelection(); });
        bandeau.append(" ", b);
      }
    }
  }

  const ligne = (kpi, cle) => {
    const c = combiner(ref, kpi);
    if (!c.n) return el("div", { class: cle ? "td-cle" : "td-ligne" }, el("b", { text: kpi.label }),
      el("span", { class: "absent", text: "Aucun projet de référence n'a ce ratio" }), lignesComparees(kpi, null, cmp));
    const st = repartition(c.valeurs.map((x) => x.v));
    const [phrase, court] = PHRASES[kpi.id] || ["", kpi.label];
    const texte = phrase ? `${phrase.replace("{v}", enClair(kpi, st.mediane))} ` : "";
    const details = `${fourchetteTexte(kpi, st)} · ${c.n} projet${c.n > 1 ? "s" : ""} · ratio combiné ${valeur(kpi, c.combine)} · ${SENS_TEXTE[kpi.sens]}`;
    const reperes = cmp.map((m) => ({ ...m, v: m.p.kpis?.[kpi.id]?.valeur })).filter((m) => m.v != null);
    const fig = figureRepartition(kpi, c.valeurs, reperes);
    const lignes = lignesComparees(kpi, st, cmp);
    if (cle) return el("div", { class: "td-cle" },
      el("p", { class: "td-sur", text: court, title: kpi.label }),
      el("div", { class: "td-valeur" }, enClair(kpi, st.mediane), kpi.unite === "%" ? el("small", { text: " m² sur 100" }) : null),
      el("p", { class: "td-phrase", text: texte.trim() || kpi.label }),
      el("p", { class: "secondaire", text: details, title: kpi.note || kpi.label }), fig, lignes);
    return el("div", { class: "td-ligne" },
      el("div", {}, el("div", {}, el("b", { text: court, title: kpi.label }), " · ", el("span", { class: "td-v", text: valeur(kpi, st.mediane) })),
        el("div", { class: "secondaire", text: texte + fourchetteTexte(kpi, st) + "." }),
        el("div", { class: "secondaire td-petit", text: `${kpi.label} · ${c.n} projet${c.n > 1 ? "s" : ""} · ratio combiné ${valeur(kpi, c.combine)} · ${SENS_TEXTE[kpi.sens]}`, title: kpi.note || "" }),
        lignes),
      fig);
  };
  document.getElementById("ratios-cles").replaceChildren(...KPI_CLES
    .map((id) => etat.kpis.find((k) => k.id === id)).filter(Boolean).map((kpi) => ligne(kpi, true)));
  const autres = kpisSelection().filter((k) => !KPI_CLES.includes(k.id));
  document.getElementById("ratios-familles").replaceChildren(...blocsParGroupe(autres, (kpi) => ligne(kpi, false)));
  document.getElementById("ratios-legende").textContent = "Trait noir : la médiane, le projet type. En couleur : la moitié des projets (25e au 75e percentile)." +
      " Échelle : 1er au 99e percentile de la référence" +
      (cmp.length ? ". Traits de couleur : les maquettes comparées (▸ au bord : hors échelle)." : ".");
  dessinerCages(cmp);
  dessinerProjetsSelection(tous, ref);
}

/** Sous un KPI, une ligne par maquette comparée : sa valeur et son écart à la médiane de la référence (en m² et CHF si
 *  le ratio mesure une surface ; repris de l'ancien onglet Comparer, qui mesurait l'écart au ratio combiné). */
function lignesComparees(kpi, st, cmp) {
  if (!cmp.length) return null;
  return el("ul", { class: "td-comparees" }, ...cmp.map((m) => {
    const r = m.p.kpis?.[kpi.id];
    const li = el("li", {}, pastille(m.couleur), el("span", { class: "nom", text: m.id === MIEN ? `★ ${m.p.nom}` : m.p.nom, title: m.id === MIEN ? "" : nomProjet(m.p) }));
    if (!r) { li.append(el("span", { class: "absent", text: m.id === MIEN && etat.mienSource === "saisie" ? "non saisi" : "donnée absente du MDP" })); return li; }
    li.append(el("b", { text: valeur(kpi, r.valeur) }));
    if (!st) return li;
    const d = r.valeur - st.mediane;
    const neutre = kpi.sens === 0 || Math.abs(d) < (kpi.unite === "%" ? 0.0005 : 0.005);
    const favorable = !neutre && Math.sign(d) === kpi.sens;
    li.append(el("span", { class: neutre ? "ecart" : `ecart ${favorable ? "favorable" : "defavorable"}`,
      title: neutre ? "Écart à la médiane de la référence" : favorable ? "Favorable" : "Défavorable",
      text: (neutre ? "" : favorable ? "▲ " : "▼ ") + ecartTexte(kpi, d) }));
    if (kpi.objet && !neutre) {
      const m2 = d * r.den;     // l'écart rapporté à la surface de la maquette : ce qu'elle gagne ou perd face au projet type
      li.append(el("span", { class: "secondaire", text: `${signe(m2)}${F0.format(Math.abs(m2))} m² ${kpi.objet}` }));
      // CHF : seulement pour les m² vendables, au prix de vente saisi ; les pertes restent en m²
      if (CHF_KPIS.has(kpi.id) && etat.prix > 0) {
        const chf = Math.round((m2 * etat.prix) / 1000) * 1000;
        li.append(el("span", { class: "secondaire", title: `${F0.format(Math.abs(m2))} m² × ${F0.format(etat.prix)} CHF/m²`,
          text: `≈ ${signe(chf)}${F0.format(Math.abs(chf))} CHF` }));
      }
    }
    return li;
  }));
}

const MIN_FORME = 10;     // en dessous, la fourchette dit « de … à … » plutôt que les quartiles, et l'échelle va du min au max
/** Le ratio en clair, au projet type ({v} : la médiane). Le premier mot court sert de titre de carte. */
const PHRASES = {
  "SUP/SP_HS": ["Sur 100 m² de SP hors-sol, le projet type a {v} m² de surface utile principale.", "Utile principale hors-sol"],
  "SVN/SP_HS": ["Sur 100 m² de SP hors-sol, le projet type vend {v} m² (SVN).", "Surface vendable"],
  "SN/SP": ["Sur 100 m² de SP, {v} m² de surface nette.", "Surface nette"],
  "SC/SP": ["Sur 100 m² de SP, {v} m² partent dans la construction.", "Construction"],
  "SD/SP_HS": ["Sur 100 m² hors-sol, {v} m² de circulations.", "Circulations hors-sol"],
  "SI/SP": ["Sur 100 m² de SP, {v} m² de locaux techniques.", "Installations"],
  "SUS_HS/SP_HS": ["Sur 100 m² hors-sol, {v} m² d'utile secondaire.", "Utile secondaire hors-sol"],
  "SP_SS/SUP": ["Pour 100 m² de SUP, {v} m² de sous-sol.", "Sous-sol par m² utile"],
  "VITRE/PLEINE": ["Pour 100 m² de façade pleine, {v} m² de vitrage.", "Vitrage / façade pleine"],
  "VITRE/FACADE": ["Sur 100 m² de façade, {v} m² vitrés.", "Part vitrée de la façade"],
  "FORME": ["Chaque m² d'enveloppe abrite {v} m² de SP hors-sol.", "Compacité"],
  "FACADE/SP_HS": ["Chaque m² de SP hors-sol demande {v} m² de façade.", "Façade par m² hors-sol"],
  "VB/SP": ["Un étage fait en moyenne {v} de hauteur brute.", "Hauteur d'étage"],
  "SUP/LOG": ["Le logement type fait {v} de SUP.", "Taille des logements"],
  "SP_HS/LOG": ["Un logement consomme {v} de SP hors-sol.", "SP par logement"],
  "SUP/CAGE": ["Une cage dessert {v} de SUP par étage.", "SUP par cage et par étage"],
  "LOG/CAGE": ["Une cage dessert {v} logements par étage.", "Logements par cage"],
};
const SENS_TEXTE = { 1: "plus c'est haut, mieux c'est", "-1": "plus c'est bas, mieux c'est", 0: "ni bon ni mauvais : un choix de projet" };

/** Valeur dans la phrase « pour 100 m² » : un % s'y lit en m² sur 100 (même décimale que la médiane de la figure). */
function enClair(kpi, v) {
  if (kpi.unite === "%") return F1.format(v * 100);
  return valeur(kpi, v);
}

function quantile(s, f) {
  const i = (s.length - 1) * f, lo = Math.floor(i), hi = Math.min(lo + 1, s.length - 1);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}

function repartition(valeurs) {
  const s = [...valeurs].sort((a, b) => a - b), q = (f) => quantile(s, f);
  return { n: s.length, s, min: s[0], max: s[s.length - 1], p01: q(0.01), p10: q(0.1), p25: q(0.25), mediane: q(0.5),
           p75: q(0.75), p90: q(0.9), p99: q(0.99) };
}

/** Fourchette en clair : la moitié des projets à partir de 10, sinon du plus bas au plus haut (pas de quartiles sur 3 points). */
function fourchetteTexte(kpi, st) {
  return st.n >= MIN_FORME ? `La moitié des projets entre ${valeur(kpi, st.p25)} et ${valeur(kpi, st.p75)}`
                           : `De ${valeur(kpi, st.min)} à ${valeur(kpi, st.max)}`;
}

/** Domaine de la figure : la sélection, du 1er au 99e percentile (les cas extrêmes sont rabattus au bord). */
function domaineSelection(st) {
  const lo = st.n >= MIN_FORME ? st.p01 : st.min, hi = st.n >= MIN_FORME ? st.p99 : st.max;
  const marge = (hi - lo) * 0.12 || Math.abs(st.mediane) * 0.05 || 1;
  return [lo - marge, hi + marge];
}

function graduations(lo, hi, n = 4) {
  const brut = (hi - lo) / n, p = 10 ** Math.floor(Math.log10(brut)), r = brut / p;
  const pas = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * p, out = [];
  for (let t = Math.ceil(lo / pas) * pas; t <= hi + pas * 1e-9; t += pas) out.push(+t.toFixed(10));
  return { pas, valeurs: out };
}

function texteGraduation(kpi, v, pas) {
  if (kpi.unite === "%") return `${(pas * 100 >= 1 ? F0 : F1).format(v * 100)} %`;
  if (kpi.unite === "m²") return `${F0.format(v)} m²`;
  const f = pas >= 1 ? F0 : pas >= 0.1 ? F1 : pas >= 0.01 ? F2 : nf(3);
  return f.format(v) + (kpi.unite === "m" ? " m" : "");
}

const FIGURES = new Set();
const observateur = "ResizeObserver" in window
  ? new ResizeObserver((entrees) => entrees.forEach((e) => e.target._dessiner?.())) : null;

/** Répartition d'un ratio en histogramme, quel que soit le nombre de projets : médiane (trait), moitié
 *  des projets en accent, échelle graduée. Une barre d'histogramme nomme ses projets au survol. Dessinée à la largeur
 *  réelle, redessinée quand elle change (onglet affiché, fenêtre redimensionnée). */
function figureRepartition(kpi, valeurs, reperes = []) {
  const boite = el("div", { class: "td-figure" });
  let largeur = 0;
  boite._dessiner = () => {
    const W = Math.floor(boite.clientWidth);
    if (!W || W === largeur) return;
    largeur = W;
    const st = repartition(valeurs.map((x) => x.v)), [lo, hi] = domaineSelection(st);
    const x = (v) => ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * W;
    // Valeurs écrites au-dessus des traits : la médiane, puis chaque maquette comparée à sa couleur. Une étiquette qui
    // en chevaucherait une autre monte d'une rangée ; la figure grandit d'autant.
    const etiquettes = [{ v: st.mediane, texte: valeur(kpi, st.mediane) },
      ...reperes.map((m) => ({ v: m.v, texte: valeur(kpi, m.v), couleur: m.couleur }))];
    const rangees = [];
    for (const e of etiquettes) {
      const l = e.texte.length * 6.2 + 8;
      e.x = Math.min(W - l / 2, Math.max(l / 2, x(e.v)));
      e.de = e.x - l / 2; e.a = e.x + l / 2;
      e.rang = rangees.findIndex((r) => r.every((o) => e.a <= o.de || e.de >= o.a));
      if (e.rang < 0) { e.rang = rangees.length; rangees.push([]); }
      rangees[e.rang].push(e);
    }
    const H = 38, haut = 4 + 13 * rangees.length, y0 = haut + H;
    const g = svg("g");
    const nb = Math.max(12, Math.min(40, Math.round(W / 16))), pas = (hi - lo) / nb, classes = Array.from({ length: nb }, () => []);
    for (const it of valeurs) classes[Math.min(nb - 1, Math.max(0, Math.floor((it.v - lo) / pas)))].push(it.p);
    const m = Math.max(...classes.map((c) => c.length)), unite = kpi.unite === "%" ? " %" : "";
    const borne = (v) => (kpi.unite === "%" ? F1.format(v * 100) : texteGraduation(kpi, v, pas));
    classes.forEach((projets, i) => {
      const n = projets.length;
      if (!n) return;
      const a = lo + i * pas, b = a + pas, milieu = (a + b) / 2, hh = Math.max(2, (n / m) * H);
      const qui = n <= 5 ? ` : ${projets.map((q) => q.nom).join(", ")}` : "";
      g.append(titre(svg("rect", { x: x(a) + 1, y: y0 - hh, width: Math.max(1, x(b) - x(a) - 2), height: hh, rx: 1.5,
        class: milieu >= st.p25 && milieu <= st.p75 ? "td-moitie" : "td-fond" }),
        `${n} projet${n > 1 ? "s" : ""} entre ${borne(a)} et ${borne(b)}${unite}${qui}`));
    });
    g.append(svg("rect", { x: 0, y: y0, width: W, height: 1, class: "td-axe" }));
    // médiane : le projet type, en trait, sa valeur au-dessus
    g.append(svg("rect", { x: x(st.mediane) - 1.5, y: haut - 3, width: 3, height: H + 3, rx: 1.5, class: "td-mediane" }));
    const yEtiquette = (e) => haut - 6 - 13 * e.rang;
    g.append(svg("text", { x: etiquettes[0].x, y: yEtiquette(etiquettes[0]), "text-anchor": "middle", class: "td-fort" }, etiquettes[0].texte));
    // maquettes comparées : un trait à leur couleur, leur valeur au-dessus et une pointe sous l'axe ; hors échelle,
    // rabattues au bord
    reperes.forEach((m, i) => {
      const hors = m.v < lo ? -1 : m.v > hi ? 1 : 0, xm = Math.min(W - 1, Math.max(1, x(m.v)));
      const nom = m.id === MIEN ? m.p.nom : nomProjet(m.p);
      const ecart = ecartTexte(kpi, m.v - st.mediane);
      const g2 = titre(svg("g", { class: "td-repere", style: `fill:${m.couleur}` }),
        `${nom} : ${valeur(kpi, m.v)} (${ecart} par rapport à la médiane)${hors ? " · hors échelle" : ""}`);
      g2.append(svg("rect", { x: xm - 1, y: haut - 3, width: 2, height: H + 3, rx: 1 }));
      const pointe = hors ? `M${xm},${y0 + 5} l${-6 * hors},-4 v8 Z` : `M${xm},${y0 + 1} l-4.5,7 h9 Z`;
      g2.append(svg("path", { d: pointe }));
      const e = etiquettes[i + 1];
      g2.append(svg("text", { x: e.x, y: yEtiquette(e), "text-anchor": "middle", class: "td-fort", style: `fill:${m.couleur}` }, e.texte));
      g.append(g2);
    });
    const yA = y0 + 18, grad = graduations(lo, hi);
    for (const t of grad.valeurs) {
      if (t < lo || t > hi) continue;
      g.append(svg("rect", { x: x(t), y: y0 + 1, width: 1, height: 4, class: "td-graduation" }));
      g.append(svg("text", { x: x(t), y: yA, "text-anchor": "middle" }, texteGraduation(kpi, t, grad.pas)));
    }
    const bas = yA;
    const figure = svg("svg", { width: W, height: bas + 6, viewBox: `0 0 ${W} ${bas + 6}`, role: "img",
      "aria-label": `${kpi.label} : projet type ${valeur(kpi, st.mediane)}, ${fourchetteTexte(kpi, st).toLowerCase()}, ${st.n} projets` });
    figure.append(g);
    boite.replaceChildren(figure);
  };
  FIGURES.add(boite);
  observateur?.observe(boite);
  requestAnimationFrame(() => boite._dessiner());
  return boite;
}

// ------------------------------------------------------------------ Anatomie de la SP (Évolution 4.10, bas des Tendances)

const PARTS_SP = ["SUP", "SUS", "SD", "SI", "SC"];
const NOMS_SIA = { SUP: "Utile principale", SUS: "Utile secondaire", SD: "Dégagements", SI: "Installations", SC: "Construction" };
const ASSIETTES = [["", "SP totale", "de SP"], ["_HS", "Hors-sol", "de SP hors-sol"], ["_SS", "Sous-sol", "de SP de sous-sol"]];
let assiette = "";

/** Répartition de la SP d'un projet (ou d'une assiette) : SUP, SUS, SD, SI, et SC pour le reste. */
function partsSp(t, suffixe) {
  const sp = t[`SP${suffixe}`] || 0;
  const o = Object.fromEntries(PARTS_SP.slice(0, 4).map((c) => [c, t[`${c}${suffixe}`] || 0]));
  o.SC = Math.max(0, sp - o.SUP - o.SUS - o.SD - o.SI);
  return { sp, o };
}

function dessinerAnatomie() {
  const [, nomAssiette, deQuoi] = ASSIETTES.find(([s]) => s === assiette);
  const groupe = document.getElementById("assiette");
  groupe.replaceChildren(el("span", { class: "secondaire", text: "Assiette :" }), ...ASSIETTES.map(([suffixe, nom]) => {
    const b = el("button", { type: "button", role: "radio", text: nom, "aria-checked": String(suffixe === assiette) });
    b.addEventListener("click", () => { assiette = suffixe; dessinerAnatomie(); });
    return b;
  }));
  document.getElementById("anatomie-legende").replaceChildren(...PARTS_SP.map((c) =>
    el("li", {}, el("i", { style: `background:${COULEURS_SIA[c]}` }), `${c} · ${NOMS_SIA[c]}`)));

  const lignes = reference().map((p) => ({ p, ...partsSp(p.totaux || {}, assiette) })).filter((l) => l.sp > 0)
    .sort((a, b) => b.o.SUP / b.sp - a.o.SUP / a.sp);
  const barres = document.getElementById("anatomie-barres"), lecture = document.getElementById("anatomie-lecture");
  if (!lignes.length) {
    barres.replaceChildren(el("p", { class: "absent", text: `Aucun projet de référence n'a ${deQuoi === "de SP" ? "de SP" : `de ${nomAssiette.toLowerCase()}`}.` }));
    lecture.textContent = "";
    return;
  }
  const ref = { sp: 0, o: Object.fromEntries(PARTS_SP.map((c) => [c, 0])) };
  for (const l of lignes) { ref.sp += l.sp; for (const c of PARTS_SP) ref.o[c] += l.o[c]; }
  const pct = (l, c) => (l.o[c] / l.sp) * 100;
  const pile = (nom, l, reference) => el("div", { class: `an-pile${reference ? " reference" : ""}`, role: "img",
    "aria-label": `${nom} : ` + PARTS_SP.map((c) => `${c} ${F1.format(pct(l, c))} %`).join(", ") },
    ...PARTS_SP.filter((c) => l.o[c] > 0).map((c) => el("span", {
      class: `an-${c}`, style: `flex:${l.o[c]} 1 0;background:${COULEURS_SIA[c]}`, text: pct(l, c) >= 6 ? `${F0.format(pct(l, c))} %` : "",
      title: `${nom} · ${c} ${NOMS_SIA[c]} : ${F1.format(pct(l, c))} % (${F0.format(l.o[c])} m²)` })));
  const rangees = [el("div", { class: "an-nom reference", text: "Référence" }), pile("Référence", ref, true),
                   el("div", { class: "secondaire", text: `${lignes.length} projet${lignes.length > 1 ? "s" : ""}` })];
  // les maquettes comparées sous la référence, bordées de leur couleur (elles n'entrent pas dans la barre Référence)
  for (const m of comparees()) {
    const l = partsSp(m.p.totaux || {}, assiette);
    const nom = m.id === MIEN ? `★ ${m.p.nom}` : m.p.nom;
    rangees.push(el("div", { class: "an-nom comparee", title: m.id === MIEN ? "" : nomProjet(m.p) }, pastille(m.couleur), nom));
    if (l.sp > 0) {
      const b = pile(nom, l, false);
      b.classList.add("comparee");
      b.style.outlineColor = m.couleur;
      rangees.push(b, el("div", { class: "secondaire", text: `${F0.format(l.sp)} m²` }));
    } else rangees.push(el("div", { class: "absent", text: `pas ${deQuoi === "de SP" ? "de SP" : `de ${nomAssiette.toLowerCase()}`} connue` }), el("div"));
  }
  rangees.push(el("div", { class: "an-sep" }));
  for (const l of lignes) {
    const compare = estComparee(l.p.id);
    const nom = el("button", { type: "button", class: "an-nom lien-projet", text: l.p.nom,
      title: `${nomProjet(l.p)} · cliquer pour ${compare ? "ne plus le comparer" : "l'ajouter aux maquettes comparées"}` });
    nom.addEventListener("click", () => basculerComparee(l.p.id));
    rangees.push(nom, pile(nomProjet(l.p), l, false), el("div", { class: "secondaire", text: `${F0.format(l.sp)} m²` }));
  }
  barres.replaceChildren(...rangees);
  const premier = lignes[0], dernier = lignes[lignes.length - 1];
  const sc = [...lignes].sort((a, b) => pct(b, "SC") - pct(a, "SC"))[0];
  lecture.textContent = lignes.length < 2
    ? `Sur 100 m² ${deQuoi}, ${premier.p.nom} met ${F0.format(pct(premier, "SUP"))} m² en utile principale.`
    : `Sur 100 m² ${deQuoi}, la référence met ${F0.format(pct(ref, "SUP"))} m² en utile principale : ${premier.p.nom} le plus ` +
      `(${F0.format(pct(premier, "SUP"))} m²), ${dernier.p.nom} le moins (${F0.format(pct(dernier, "SUP"))} m²). ` +
      `La construction pèse le plus chez ${sc.p.nom} (${F0.format(pct(sc, "SC"))} m² sur 100).`;
}

/** KPI rangés par groupe (SIA 416, USPI 2014, Enveloppe, Programme), puis par famille sous-titrée quand le groupe en
 *  compte plusieurs. Une famille inconnue forme son propre groupe, à la fin. */
function blocsParGroupe(kpis, ligne) {
  const connues = GROUPES.flatMap((g) => g.familles);
  const groupes = [...GROUPES, ...[...new Set(kpis.map((k) => k.famille))].filter((f) => !connues.includes(f))
    .map((f) => ({ titre: f, definition: "", couleur: "#6B7280", familles: [f] }))];
  const blocs = [];
  for (const g of groupes) {
    const dans = kpis.filter((k) => g.familles.includes(k.famille));
    if (!dans.length) continue;
    const bloc = el("section", { class: "famille" },
      el("h2", {}, el("span", { class: "pastille", style: `background:${g.couleur}`, "aria-hidden": "true" }), g.titre,
         g.definition ? el("span", { class: "definition", text: g.definition }) : null));
    for (const famille of g.familles) {
      const ks = dans.filter((k) => k.famille === famille);
      if (!ks.length) continue;
      if (famille !== g.titre && g.familles.length > 1) bloc.append(el("h3", { text: famille }));
      for (const kpi of ks) bloc.append(ligne(kpi));
    }
    blocs.push(bloc);
  }
  return blocs;
}

/** Position d'un projet dans la sélection sur SUP / SP hors-sol, dans le sens favorable du ratio. */
function quartDe(p, fiables) {
  const kpi = etat.kpis.find((k) => k.id === "SUP/SP_HS");
  const v = fiables.filter((q) => q.kpis[kpi.id]).map((q) => q.kpis[kpi.id].valeur * kpi.sens).sort((a, b) => b - a);
  const mien = p.kpis[kpi.id];
  if (!mien || !p.fiable || v.length < 4) return "";
  const rang = v.indexOf(mien.valeur * kpi.sens) + 1;
  return ["meilleur quart", "2e quart", "3e quart", "dernier quart"][Math.min(3, Math.floor(((rang - 1) / v.length) * 4))];
}

function dessinerProjetsSelection(tous, ref) {
  const kpi = etat.kpis.find((k) => k.id === "SUP/SP_HS");
  const tete = el("tr", {}, ...["Projet", "Typologie", "Canton", "SUP / SP hors-sol", "Position", "Référence", ""].map((t) => el("th", { scope: "col", text: t })));
  const lignes = [...tous].sort((a, b) => b.fiable - a.fiable || (b.kpis[kpi.id]?.valeur ?? -1) - (a.kpis[kpi.id]?.valeur ?? -1));
  const pleines = etat.comparees.length >= MAX_COMPAREES;
  const corps = lignes.map((p) => {
    const c = etat.comparees.find((x) => x.id === p.id);
    const dansRef = p.fiable && !etat.exclus.has(p.id);
    const action = c ? boutonIcone("retirer", "Ne plus comparer", () => basculerComparee(p.id), "petit")
                 : pleines ? null : boutonIcone("ajouter", "Ajouter aux maquettes comparées", () => basculerComparee(p.id), "petit");
    const tr = el("tr", { class: p.fiable ? "" : "ecarte", tabindex: "0",
                          title: c ? "Ne plus comparer ce projet" : pleines ? `${MAX_COMPAREES} maquettes comparées au plus` : "Ajouter aux maquettes comparées" },
      el("td", {}, c ? pastille(couleurDe(c)) : null, el("span", { class: "mono", text: p.id }), ` ${p.nom}${p.fiable ? "" : " (écarté)"}`),
      el("td", { text: p.infos?.categorie || "Non identifiée" }), el("td", { class: "mono", text: p.infos?.canton || "—" }),
      el("td", { text: valeur(kpi, p.kpis[kpi.id]?.valeur) }), el("td", { text: quartDe(p, ref) }),
      el("td", { class: "etat-ref" }, !p.fiable ? marque("alerte", "Écarté : hors des références")
        : dansRef ? marque("coche", "Dans la référence", "ok") : el("span", { class: "secondaire", title: "Décoché : hors de la référence", text: "—" })),
      el("td", { class: "lien-ligne" }, action));
    const ouvrir = () => { if (c || !pleines) basculerComparee(p.id); };
    tr.addEventListener("click", ouvrir);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") ouvrir(); });
    return tr;
  });
  document.getElementById("ratios-projets").replaceChildren(el("thead", {}, tete), el("tbody", {}, ...corps));
}

/** SUP par logement selon le nombre de chambres, sur les projets de référence (même calcul que benchmark.typologies). */
function typologiesSelection() {
  const par = new Map();
  for (const p of reference())
    for (const lg of p.logements || []) {
      if (!par.has(lg.chambres)) par.set(lg.chambres, []);
      par.get(lg.chambres).push({ id: p.id, sup: lg.sup });
    }
  return [...par.entries()].sort((a, b) => a[0] - b[0]).map(([chambres, v]) => {
    const s = v.map((x) => x.sup).sort((a, b) => a - b);
    const q = (f) => { const i = (s.length - 1) * f, lo = Math.floor(i), hi = Math.min(lo + 1, s.length - 1); return s[lo] + (s[hi] - s[lo]) * (i - lo); };
    return { chambres, n: s.length, projets: new Set(v.map((x) => x.id)).size, min: s[0], q1: q(0.25), mediane: q(0.5), q3: q(0.75), max: s[s.length - 1] };
  });
}

// ------------------------------------------------------------------ Maquette 3D (V5_PLAN, partie 2)

let module3d = null;     // vue3d.js et three.js, chargés à la première ouverture
/** Version des fichiers de la page (index.html porte la même) : un module chargé à la demande n'est pas repris du cache. */
const VERSION_PAGE = "5.0-18";
const charger3d = () => (module3d ??= import(`./vue3d.js?v=${VERSION_PAGE}`));

function boutonCube(p) {
  const actif = etat.vue3d === p.id;
  return boutonIcone("cube", actif ? "Maquette 3D affichée : fermer" : `Voir la maquette 3D de ${p.nom}`,
    () => (actif ? fermer3D() : ouvrir3D(p.id)), `petit cube${actif ? " actif" : ""}`);
}

/** La zone centrale montre la maquette d'un projet à la place des graphiques ; les volets restent actifs. */
async function ouvrir3D(id) {
  const p = etat.projets.get(id);
  if (!p?.maquette) return;
  if (etat.carte) fermerCarte(true);
  else if (!etat.vue3d) etat.defilement = window.scrollY;
  etat.vue3d = id;
  document.querySelector(".centre").classList.add("mode-3d");
  document.documentElement.classList.add("mode-3d");
  document.getElementById("vue-3d").hidden = false;
  window.scrollTo(0, 0);
  ajuster3D();
  dessinerVolets();
  majVue3D();
  const statut = document.getElementById("v3-etat");
  statut.hidden = false;
  statut.textContent = "Chargement de la maquette…";
  try {
    const vue = await charger3d();
    if (etat.vue3d !== id) return;
    const affichee = await vue.afficher(BASE_MAQUETTES + p.maquette, document.getElementById("v3-scene"), document.getElementById("v3-calques"));
    if (affichee && etat.vue3d === id) statut.hidden = true;
  } catch (e) {
    if (etat.vue3d !== id) return;
    statut.textContent = `La maquette de ${p.nom} ne peut pas s'afficher : ${e.message || e}.`;
    console.error(e);
  }
}

/** `sansRetour` : une autre vue (la carte) prend la place, la page reste en mode vue. */
function fermer3D(sansRetour = false) {
  if (!etat.vue3d) return;
  etat.vue3d = null;
  module3d?.then((vue) => vue.fermer());
  document.getElementById("vue-3d").hidden = true;
  if (sansRetour) { dessinerVolets(); return; }
  document.querySelector(".centre").classList.remove("mode-3d");
  document.documentElement.classList.remove("mode-3d");
  dessinerVolets();
  // les figures ont pu changer de largeur pendant que la vue était ouverte
  requestAnimationFrame(() => { FIGURES.forEach((b) => b.isConnected && b._dessiner?.()); window.scrollTo(0, etat.defilement); });
}

/** En-tête (référence, couleur de comparaison) et KPI de la maquette ouverte, face à la médiane de la référence. */
function majVue3D() {
  const p = etat.vue3d && etat.projets.get(etat.vue3d);
  if (!p) return;
  document.getElementById("v3-titre").textContent = nomProjet(p);
  const cb = document.getElementById("v3-ref"), label = document.getElementById("v3-ref-label");
  const possible = p.fiable && dansSelection(p);
  cb.checked = possible && !etat.exclus.has(p.id);
  cb.disabled = !possible;
  label.title = !p.fiable ? "Écarté : données incohérentes, hors des références" : !dansSelection(p) ? "Hors du pré-filtre" : "";
  const c = etat.comparees.find((x) => x.id === p.id);
  document.getElementById("v3-pastille").replaceChildren(c ? pastille(couleurDe(c), "Maquette comparée") : "");
  const ref = reference();
  document.getElementById("v3-kpi").replaceChildren(el("table", { class: "v3-table" },
    el("thead", {}, el("tr", {}, ...["", "Projet", "Médiane", "Écart"].map((t) => el("th", { scope: "col", text: t })))),
    el("tbody", {}, ...kpisSelection().map((kpi) => {
      const r = p.kpis[kpi.id], cmb = combiner(ref, kpi);
      const med = cmb.n ? repartition(cmb.valeurs.map((x) => x.v)).mediane : null;
      const ecart = el("td", { class: "n" });
      if (r && med != null) {
        const d = r.valeur - med;
        const neutre = kpi.sens === 0 || Math.abs(d) < (kpi.unite === "%" ? 0.0005 : 0.005);
        const favorable = !neutre && Math.sign(d) === kpi.sens;
        ecart.className = `n ${neutre ? "" : favorable ? "favorable" : "defavorable"}`;
        ecart.textContent = (neutre ? "" : favorable ? "▲ " : "▼ ") + ecartTexte(kpi, d);
      }
      return el("tr", {}, el("td", { text: (PHRASES[kpi.id] || [])[1] || kpi.label, title: kpi.label }),
        el("td", { class: "n", text: r ? valeur(kpi, r.valeur) : "—" }), el("td", { class: "n secondaire", text: med != null ? valeur(kpi, med) : "—" }), ecart);
    }))));
}

/** Mode maquette : la vue et les volets tiennent dans la fenêtre, la page ne défile pas (seuls les panneaux défilent). */
function ajuster3D() {
  if (!etat.vue3d && !etat.carte) return;
  const haut = document.querySelector(".centre").getBoundingClientRect().top + window.scrollY;
  document.documentElement.style.setProperty("--haut-3d", `${Math.max(320, window.innerHeight - haut - 16)}px`);
}

function brancher3D() {
  window.addEventListener("resize", ajuster3D);
  document.getElementById("v3-fermer").addEventListener("click", fermer3D);
  document.getElementById("v3-dessus").addEventListener("click", () => module3d?.then((vue) => vue.cadrer("dessus")));
  document.getElementById("v3-perspective").addEventListener("click", () => module3d?.then((vue) => vue.cadrer("3d")));
  document.getElementById("v3-ref").addEventListener("change", (e) => {
    if (!etat.vue3d) return;
    e.target.checked ? etat.exclus.delete(etat.vue3d) : etat.exclus.add(etat.vue3d);
    majReference();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && etat.vue3d && !e.target.closest?.("input, select, textarea")) fermer3D();
  });
}

// ------------------------------------------------------------------ Cages d'escalier des maquettes comparées

/** Détail des cages d'escalier de chaque maquette comparée, bâtiment par bâtiment et étage par étage (benchmark._cages). */
function dessinerCages(cmp) {
  const avec = cmp.filter((m) => (m.p.etages || []).length);
  const section = document.getElementById("cages");
  section.hidden = !avec.length || !selectionLogement();
  if (section.hidden) return;
  const parCage = (v, e) => (e.cages ? v / e.cages : null);
  document.getElementById("cages-tables").replaceChildren(...avec.map((m) => {
    const entete = el("tr", {}, ...["Bâtiment", "Étage", "SUP", "Logements", "Cages", "SUP / cage", "Logements / cage"]
      .map((t, i) => el("th", { text: t, class: i > 1 ? "n" : "" })));
    const lignes = m.p.etages.map((e) => el("tr", {},
      el("td", { class: "mono", text: e.batiment || "—" }), el("td", { class: "mono", text: e.etage }),
      el("td", { class: "n", text: `${F0.format(e.sup)} m²` }), el("td", { class: "n", text: F0.format(e.logements) }),
      el("td", { class: e.cages ? "n" : "n absent", text: e.cages ? F0.format(e.cages) : "aucune",
        title: e.cages ? "" : "Étage de logements sans cage d'escalier : sous-type à vérifier dans le modèle" }),
      el("td", { class: "n", text: e.cages ? `${F0.format(parCage(e.sup, e))} m²` : "—" }),
      el("td", { class: "n", text: e.cages ? F1.format(parCage(e.logements, e)) : "—" })));
    return el("div", { class: "cages-maquette" },
      el("h3", {}, pastille(m.couleur), m.id === MIEN ? `★ ${m.p.nom}` : nomProjet(m.p)),
      el("div", { class: "defile" }, el("table", { class: "table-cages" }, el("thead", {}, entete), el("tbody", {}, ...lignes))));
  }));
}

function remplirEcartes() {
  const ecartes = etat.data.projets.filter((p) => !p.fiable);
  const d = document.getElementById("ecartes");
  d.hidden = !ecartes.length;
  d.querySelector("summary").textContent = `Écartés de la base (${ecartes.length})`;
  d.querySelector("ul").replaceChildren(...ecartes.map((p) => {
    const manque = p.controles.filter((c) => !c.ok).map((c) => c.detail ? `${c.label} (${c.detail})` : c.label).join("\n");
    return el("li", { title: manque }, el("span", { class: "mono", text: p.id }), el("span", { class: "nom", text: p.nom }));
  }));
}

// ------------------------------------------------------------------ Base

function dessinerBase() {
  const t = document.getElementById("table-base");
  const fiables = reference();
  const kpis = kpisSelection();
  const base = Object.fromEntries(kpis.map((k) => [k.id, combiner(fiables, k)]));     // ensemble de la référence
  const colonnes = [{ id: "nom", label: "Projet" }, { id: "canton", label: "Canton" }, ...kpis.map((k) => ({ id: k.id, label: k.id, kpi: k }))];
  const cle = (p, col) => col.id === "nom" ? Number(p.id) || p.id : col.id === "canton" ? (p.infos.canton || "") : p.kpis[col.id]?.valeur ?? -Infinity;
  let lignes = projetsSelection().sort((a, b) => b.fiable - a.fiable || String(a.id).localeCompare(String(b.id), "fr", { numeric: true }));
  if (etat.tri) {
    const col = colonnes.find((c) => c.id === etat.tri.id);
    lignes.sort((a, b) => { const x = cle(a, col), y = cle(b, col); return (x > y ? 1 : x < y ? -1 : 0) * etat.tri.sens; });
  }

  const tete = el("tr", {}, ...colonnes.map((col) => {
    const th = el("th", { scope: "col", tabindex: "0", title: col.kpi ? `${col.kpi.label}${col.kpi.note ? " — " + col.kpi.note : ""}` : "", text: col.label });
    if (etat.tri?.id === col.id) th.setAttribute("aria-sort", etat.tri.sens > 0 ? "ascending" : "descending");
    const trier = () => { etat.tri = { id: col.id, sens: etat.tri?.id === col.id ? -etat.tri.sens : (col.kpi ? -1 : 1) }; dessinerBase(); };
    th.addEventListener("click", trier);
    th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); trier(); } });
    return th;
  }));

  const ensemble = el("tr", { class: "ensemble" }, el("td", { text: `Ensemble de la référence (${fiables.length} projet${fiables.length > 1 ? "s" : ""} coché${fiables.length > 1 ? "s" : ""})` }), el("td"),
    ...kpis.map((k) => el("td", { title: base[k.id]?.n ? `n = ${base[k.id].n}` : "", text: base[k.id]?.n ? `${valeur(k, base[k.id].combine)} (${base[k.id].n})` : "—" })));

  const corps = lignes.map((p) => {
    const horsRef = p.fiable && etat.exclus.has(p.id), c = etat.comparees.find((x) => x.id === p.id);
    const tr = el("tr", { class: p.fiable && !horsRef ? "" : "ecarte", tabindex: "0",
                          title: c ? "Comparée : cliquer pour la voir dans les Tendances" : "Ajouter aux maquettes comparées et ouvrir les Tendances" },
      el("td", {}, c ? pastille(couleurDe(c)) : null, el("span", { class: "mono", text: p.id }),
        ` ${p.nom}${!p.fiable ? " (écarté)" : horsRef ? " (décoché)" : ""}`),
      el("td", { class: "mono", text: p.infos.canton || "—" }),
      ...kpis.map((k) => celluleBase(k, p, base[k.id])));
    const ouvrir = () => { if (!c && etat.comparees.length < MAX_COMPAREES) basculerComparee(p.id); montrerVue("ratios"); };
    tr.addEventListener("click", ouvrir);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") ouvrir(); });
    return tr;
  });
  t.replaceChildren(el("thead", {}, tete), el("tbody", {}, ensemble, ...corps));
}

function celluleBase(kpi, p, b) {
  const r = p.kpis[kpi.id];
  const td = el("td", { text: valeur(kpi, r?.valeur) });
  if (r && p.fiable && kpi.sens && b?.n) {
    const d = r.valeur - b.combine;
    if (Math.abs(d) > 1e-9) {
      const favorable = Math.sign(d) === kpi.sens;
      td.append(el("span", { class: "signe " + (favorable ? "favorable" : "defavorable"), title: (d > 0 ? "Au-dessus" : "Au-dessous") +
        ` de l'ensemble (${valeur(kpi, b.combine)}) : ${favorable ? "favorable" : "défavorable"}`, text: d > 0 ? "▲" : "▼" }));
    } else td.append(el("span", { class: "signe" }));
  } else td.append(el("span", { class: "signe" }));
  return td;
}

// ------------------------------------------------------------------ Typologies

function dessinerTypologies() {
  const typos = typologiesSelection();
  const boites = document.getElementById("boites");
  const titreTypo = document.getElementById("titre-typologies");
  if (!typos.length) {
    titreTypo.textContent = "SUP par logement selon le nombre de chambres";
    boites.replaceChildren(el("p", { class: "secondaire", text: selectionLogement()
      ? "Aucun projet de référence ne donne les chambres de ses logements."
      : "Les typologies de logement ne concernent pas cette sélection." }));
    return;
  }
  const nLog = typos.reduce((s, t) => s + t.n, 0);
  const nProj = reference().filter((p) => (p.logements || []).length).length;
  titreTypo.textContent = `SUP par logement selon le nombre de chambres (${nProj} projet${nProj > 1 ? "s" : ""}, ${nLog} logements)`;

  const W = 900, G = 70, D = 230, L = 40, haut = 20 + typos.length * L;     // D : colonne de droite (médiane, effectifs)
  const max = Math.ceil(Math.max(...typos.map((t) => t.max)) / 20) * 20 + 20;
  const x = (v) => G + (v / max) * (W - G - D);
  const s = svg("svg", { viewBox: `0 0 ${W} ${haut + 24}`, role: "img", "aria-label": "SUP par logement selon le nombre de chambres" });
  for (let v = 0; v <= max; v += 20) {
    s.append(svg("line", { class: "axe", x1: x(v), x2: x(v), y1: 8, y2: haut }));
    s.append(svg("text", { class: "graduation", x: x(v), y: haut + 16, "text-anchor": "middle" }, `${v}`));
  }
  s.append(svg("text", { class: "graduation", x: x(max), y: haut + 16, dx: 18 }, "m²"));
  typos.forEach((t, i) => {
    const y = 24 + i * L;
    const g = svg("g", { class: "ligne-typo" + (t.projets < MIN_REFERENCE ? " grise" : "") });
    g.append(svg("text", { x: 0, y: y + 4 }, t.chambres === 0 ? "Studio" : `${t.chambres} ch.`));
    g.append(svg("line", { class: "moustache", x1: x(t.min), x2: x(t.max), y1: y, y2: y }));
    g.append(svg("line", { class: "moustache", x1: x(t.min), x2: x(t.min), y1: y - 6, y2: y + 6 }));
    g.append(svg("line", { class: "moustache", x1: x(t.max), x2: x(t.max), y1: y - 6, y2: y + 6 }));
    g.append(svg("rect", { class: "boite", x: x(t.q1), y: y - 9, width: Math.max(2, x(t.q3) - x(t.q1)), height: 18, rx: 2 }));
    g.append(svg("line", { class: "mediane", x1: x(t.mediane), x2: x(t.mediane), y1: y - 9, y2: y + 9 }));
    g.append(svg("text", { x: W - D + 12, y: y + 4 }, `${F0.format(t.mediane)} m²`));
    g.append(svg("text", { class: "secondaire", x: W - D + 64, y: y + 4 },
      `${t.n} logement${t.n > 1 ? "s" : ""}, ${t.projets} projet${t.projets > 1 ? "s" : ""}`));
    titre(g, `${t.chambres === 0 ? "Studio" : t.chambres + " chambre" + (t.chambres > 1 ? "s" : "")} : médiane ${F1.format(t.mediane)} m², ` +
      `quartiles ${F1.format(t.q1)} – ${F1.format(t.q3)} m², min ${F1.format(t.min)}, max ${F1.format(t.max)}`);
    s.append(g);
  });
  boites.replaceChildren(s);
}

// ------------------------------------------------------------------ Mon projet (saisie ou SIA Check)

const SURFACES = [["SP_HS", "SP hors-sol"], ["SP_SS", "SP sous-sol"], ["SUP_HS", "SUP hors-sol"], ["SD_HS", "SD hors-sol"],
                  ["SI", "SI"], ["SUS_HS", "SUS hors-sol"], ["SVN", "SVN"], ["FACADE", "Façade hors-sol"], ["VITRE", "Vitrages"], ["TOITURE", "Toitures"], ["VB", "VB (m³)"]];
const MIX = [["0", "Studios"], ["1", "1 chambre"], ["2", "2 chambres"], ["3", "3 chambres"], ["4", "4 ch. et plus"]];
const CHF_KPIS = new Set(["SUP/SP_HS", "SVN/SP_HS"]);
const CLE_SAISIE = "benchmark.monProjet";

function initSaisie() {
  const form = document.getElementById("saisie-form");
  const nombre = (name, label) => el("label", {}, label, el("input", { name, type: "number", min: "0", step: "any", inputmode: "decimal" }));
  document.getElementById("champs-surfaces").replaceChildren(...SURFACES.map(([k, l]) => nombre(k, l)));
  document.getElementById("champs-programme").replaceChildren(...MIX.map(([k, l]) => nombre(`mix${k}`, l)), nombre("ETAGES_HS", "Étages hors-sol"));
  for (const f of ["categorie", "intervention"]) {
    const valeurs = [...new Set(etat.data.projets.map((p) => p.infos[f]).filter(Boolean))].sort();
    form.elements[f].replaceChildren(el("option", { value: "", text: "Inconnue" }), ...valeurs.map((v) => el("option", { value: v, text: v })));
  }
  form.addEventListener("input", () => { if (etat.mienSource === "saisie") sauverSaisie(); majMien(); });
  form.addEventListener("submit", (e) => e.preventDefault());
  document.getElementById("saisie-effacer").addEventListener("click", () => {
    form.reset();
    etat.mienSource = "saisie";
    verrouiller(false);
    sauverSaisie();
    majMien();
  });
  document.getElementById("saisie-replier").addEventListener("click", () => replierSaisie(!form.hidden));
  try { remplirForm(JSON.parse(localStorage.getItem(CLE_SAISIE) || "null")); } catch { /* stockage indisponible */ }
  majMien();
}

function replierSaisie(replie) {
  document.getElementById("saisie-form").hidden = replie;
  const b = document.getElementById("saisie-replier");
  b.replaceChildren(icone(replie ? "deplier" : "replier"));
  b.title = replie ? "Déplier" : "Replier";
  b.setAttribute("aria-label", replie ? "Déplier la saisie" : "Replier la saisie");
  b.setAttribute("aria-expanded", String(!replie));
}

function lireSaisie() {
  const f = document.getElementById("saisie-form").elements;
  const num = (n) => { const v = f[n].value.trim(); return v === "" ? null : Number(v); };
  const s = { nom: f.nom.value.trim(), categorie: f.categorie.value, intervention: f.intervention.value,
              canton: f.canton.value.trim().toUpperCase(), valeurs: {}, mix: {}, ETAGES_HS: num("ETAGES_HS"), prix: num("prix") };
  for (const [k] of SURFACES) s.valeurs[k] = num(k);
  for (const [k] of MIX) s.mix[k] = num(`mix${k}`);
  return s;
}

function remplirForm(s) {
  if (!s) return;
  const f = document.getElementById("saisie-form").elements;
  const mettre = (n, v) => { if (f[n]) f[n].value = v ?? ""; };
  mettre("nom", s.nom); mettre("categorie", s.categorie); mettre("intervention", s.intervention); mettre("canton", s.canton);
  for (const [k] of SURFACES) mettre(k, s.valeurs?.[k]);
  for (const [k] of MIX) mettre(`mix${k}`, s.mix?.[k]);
  mettre("ETAGES_HS", s.ETAGES_HS); mettre("prix", s.prix);
}

function sauverSaisie() {
  try { localStorage.setItem(CLE_SAISIE, JSON.stringify(lireSaisie())); } catch { /* stockage indisponible : saisie non gardée */ }
}

/** Contrôles de vraisemblance : un champ faux est signalé et n'entre dans aucun ratio. */
function verifierSaisie(v) {
  const erreurs = {};
  for (const [k] of SURFACES) if (v[k] != null && (!Number.isFinite(v[k]) || v[k] < 0)) erreurs[k] = "Valeur négative ou invalide.";
  if (v.SP_HS != null && v.SUP_HS != null && v.SUP_HS > v.SP_HS) erreurs.SUP_HS = "La SUP dépasse la SP hors-sol.";
  if (v.FACADE != null && v.VITRE != null && v.VITRE > v.FACADE) erreurs.VITRE = "Les vitrages dépassent la façade.";
  const nettes = ["SUP_HS", "SD_HS", "SUS_HS"].reduce((s, k) => s + (v[k] || 0), 0);
  if (v.SP_HS != null && !erreurs.SUP_HS && nettes > v.SP_HS) erreurs.SP_HS = "Les surfaces nettes hors-sol dépassent la SP hors-sol.";
  return erreurs;
}

/** Totaux d'un projet saisi, aux clés du moteur (benchmark.py) : seuls les termes saisis existent. */
function projetSaisi(s) {
  const erreurs = verifierSaisie(s.valeurs);
  const t = {};
  for (const [k] of SURFACES) if (s.valeurs[k] != null && !erreurs[k]) t[k] = s.valeurs[k];
  if (t.SP_HS != null && t.SP_SS != null) t.SP = t.SP_HS + t.SP_SS;
  if (t.SUP_HS != null) t.SUP = t.SUP_HS;     // en faisabilité, la SUP est hors-sol
  if (t.VITRE > 0 && t.FACADE > t.VITRE) t.PLEINE = t.FACADE - t.VITRE;   // comme benchmark._enveloppe
  else delete t.VITRE;                                                   // vitrée seule : aucun ratio
  const mix = {};
  for (const [k] of MIX) if (s.mix[k] > 0) mix[k] = s.mix[k];
  const nb = Object.values(mix).reduce((a, b) => a + b, 0);
  if (nb > 0) t.LOG = nb;
  if (s.ETAGES_HS > 0) t.ETAGES_HS = s.ETAGES_HS;
  const features = {};
  for (const k of ["SP_HS", "LOG", "ETAGES_HS"]) if (t[k] > 0) features[k] = t[k];
  if (t.SP_SS != null && t.SP_HS > 0) features.PART_SS = t.SP_SS / t.SP_HS;
  if (nb > 0) features.PART_GRANDS = ((mix["3"] || 0) + (mix["4"] || 0)) / nb;
  const p = { id: MIEN, nom: s.nom || "Mon projet", fiable: false, controles: [], totaux: t, mix, features,
              infos: { categorie: s.categorie || null, intervention: s.intervention || null, canton: s.canton || null } };
  p.kpis = Object.fromEntries(etat.kpis.map((k) => [k.id, ratioDe(t, k)]));
  return { projet: p, erreurs };
}

function ratioDe(t, kpi) {
  const terme = (ks) => (ks.some((k) => t[k] == null) ? null : ks.reduce((s, k) => s + t[k], 0));
  const num = terme(kpi.num), den = terme(kpi.den);
  return num == null || !den ? null : { num, den, valeur: num / den };
}

function majMien() {
  const s = lireSaisie();
  etat.prix = s.prix > 0 ? s.prix : null;
  let erreurs = {};
  if (etat.mienSource === "saisie") ({ projet: etat.mien, erreurs } = projetSaisi(s));
  etat.mien.distances = distancesA(etat.mien.features);
  afficherErreurs(erreurs);
  const calculables = etat.kpis.filter((k) => etat.mien.kpis[k.id]).length;
  document.getElementById("saisie-bilan").textContent = calculables
    ? `${calculables} ratio${calculables > 1 ? "s" : ""} calculable${calculables > 1 ? "s" : ""} sur ${etat.kpis.length} · les champs vides laissent la ligne « donnée absente ».`
    : "Saisissez la SP hors-sol et le nombre de logements pour commencer.";
  if (estComparee(MIEN) && etat.data) { dessinerVolets(); dessinerRatios(); dessinerAnatomie(); }
}

function afficherErreurs(erreurs) {
  const form = document.getElementById("saisie-form");
  form.querySelectorAll(".erreur").forEach((e) => e.remove());
  for (const [k] of SURFACES) {
    const input = form.elements[k];
    input.setAttribute("aria-invalid", String(!!erreurs[k]));
    if (erreurs[k]) input.parentElement.append(el("span", { class: "erreur", text: erreurs[k] }));
  }
}

function verrouiller(oui) {
  const form = document.getElementById("saisie-form");
  for (const e of form.elements) {
    if (!e.name || e.name === "prix") continue;
    if (e.tagName === "SELECT") e.disabled = oui; else e.readOnly = oui;
  }
  document.getElementById("saisie-source").textContent = oui ? "Surfaces du projet ouvert dans SIA Check (corrections comprises)" : "";
  const effacer = document.getElementById("saisie-effacer");
  effacer.replaceChildren(icone(oui ? "reinit" : "effacer"));
  effacer.title = oui ? "Revenir à une saisie" : "Effacer la saisie";
  effacer.setAttribute("aria-label", effacer.title);
}

/** Projet ouvert dans SIA Check : calculé par le moteur (sia-check --benchmark-projet), affiché en lecture seule. */
function recevoirProjetSiaCheck(p) {
  if (!etat.data) return;
  etat.mienSource = "siacheck";
  etat.mien = { ...p, id: MIEN, fiable: false };
  const f = document.getElementById("saisie-form").elements, t = p.totaux || {};
  f.nom.value = p.nom || ""; f.canton.value = p.infos?.canton || "";
  for (const [k] of SURFACES) f[k].value = t[k] != null ? Math.round(t[k]) : "";
  for (const [k] of MIX) f[`mix${k}`].value = p.mix?.[k] ?? "";
  f.ETAGES_HS.value = t.ETAGES_HS ?? "";
  for (const n of ["categorie", "intervention"]) f[n].value = p.infos?.[n] || "";
  verrouiller(true);
  replierSaisie(true);
  majMien();
  if (!estComparee(MIEN)) basculerComparee(MIEN);
  else majComparees();
  document.getElementById("saisie").hidden = false;
  montrerVue("ratios");
}

// Similarité : même formule que benchmark.distance (écart moyen normalisé, au moins 2 caractéristiques communes,
// étendues mesurées sur toute la base). verifierDistances() la confronte au moteur à chaque chargement.
function echelles() {
  const out = {};
  for (const [f, kind] of Object.entries(etat.data.features)) {
    let v = etat.data.projets.map((p) => p.features?.[f]).filter((x) => x != null && (kind === "lin" || x > 0));
    if (kind === "log") v = v.map(Math.log);
    const lo = Math.min(...v), hi = Math.max(...v);
    out[f] = v.length > 1 && hi > lo ? hi - lo : 1;
  }
  return out;
}

function distance(fa, fb, e = echelles()) {
  const d = [];
  for (const [f, kind] of Object.entries(etat.data.features)) {
    if (fa?.[f] == null || fb?.[f] == null) continue;
    const x = kind === "log" ? Math.log(fa[f]) : fa[f], y = kind === "log" ? Math.log(fb[f]) : fb[f];
    d.push(Math.abs(x - y) / e[f]);
  }
  return d.length >= 2 ? d.reduce((a, b) => a + b, 0) / d.length : null;
}

function distancesA(features) {
  const e = echelles(), out = {};
  for (const q of etat.data.projets.filter((q) => q.fiable)) {
    const d = distance(features, q.features, e);
    if (d != null) out[q.id] = d;
  }
  return out;
}

/** Écart maximal entre les distances recalculées ici et celles du moteur (0 si les deux formules concordent). */
function verifierDistances() {
  const e = echelles();
  let max = 0;
  for (const p of etat.data.projets)
    for (const [id, d] of Object.entries(p.distances || {})) {
      const q = etat.projets.get(id), js = q && distance(p.features, q.features, e);
      if (js != null) max = Math.max(max, Math.abs(js - d));
    }
  return max;
}
window.verifierDistances = verifierDistances;

// ------------------------------------------------------------------ Programmer (programmation inverse, Évolution 3.3)

const CLE_PROGRAMME = "benchmark.programme";
// Légende SIA 416, comme dans l'application (report.py, SIA_COLORS)
const COULEURS_SIA = { SUP: "#D5003B", SUS: "#F0A900", SD: "#F2E900", SI: "#0C9DDA", SC: "#A3AAB6" };
/** Dernier programme calculé (hypothèses, lignes du tableau et parts de la barre) : repris tel quel par l'export Excel. */
const progEtat = { h: null, lignes: [], parts: [], n: 0 };

function initProgrammer() {
  const form = document.getElementById("prog-form");
  const nombre = (name, label, attrs = {}) =>
    el("label", {}, label, el("input", { name, type: "number", min: "0", step: "any", inputmode: "decimal", ...attrs }));
  document.getElementById("prog-mix").replaceChildren(...MIX.map(([k, l]) => nombre(`mix${k}`, `${l} (%)`, { max: "100" })),
    el("span", { id: "prog-mix-total", class: "total" }));
  form.addEventListener("submit", (e) => e.preventDefault());
  document.getElementById("prog-export").addEventListener("click", exporterExcel);
  form.addEventListener("input", () => {
    try { localStorage.setItem(CLE_PROGRAMME, JSON.stringify(Object.fromEntries(new FormData(form)))); } catch { /* stockage indisponible */ }
    dessinerProgramme();
  });
  try {
    const s = JSON.parse(localStorage.getItem(CLE_PROGRAMME) || "null");
    if (s) for (const [k, v] of Object.entries(s)) if (form.elements[k]) form.elements[k].value = v;
  } catch { /* stockage indisponible */ }
  dessinerProgramme();
}

function lireHypotheses() {
  const f = document.getElementById("prog-form").elements;
  const num = (n) => { const v = f[n].value.trim(); return v === "" ? null : Number(v); };
  const mix = {};
  for (const [k] of MIX) { const v = num(`mix${k}`); if (v > 0) mix[k] = v; }
  return { SP_HS: num("SP_HS"), mix: selectionLogement() ? mix : {}, prix: num("prix") };
}

/** Bas (1er quartile), central (médiane, comme les Tendances) et haut (3e quartile) d'un KPI sur la référence,
 *  multipliés par une base (V5_PLAN, partie 4). */
function fourchette(groupe, kpiId, base) {
  const kpi = etat.kpis.find((k) => k.id === kpiId);
  const c = combiner(groupe, kpi);
  if (!c.n || base == null) return null;
  const [bas, haut] = [c.q1 * base, c.q3 * base].sort((a, b) => a - b);
  return { bas, central: c.mediane * base, haut, n: c.n, kpi };
}

/** Surface moyenne d'un logement du mix visé, chaque typologie à sa médiane de SUP (onglet Typologies). */
function surfaceMoyenneMix(mix) {
  const typos = new Map(typologiesSelection().map((t) => [String(Math.min(t.chambres, 4)), t]));
  let parts = 0, somme = 0;
  for (const [k, part] of Object.entries(mix)) {
    const t = typos.get(k);
    if (!t) continue;
    parts += part;
    somme += part * t.mediane;
  }
  return parts ? somme / parts : null;
}

function dessinerProgramme() {
  const h = lireHypotheses();
  const logement = selectionLogement();
  for (const id of ["prog-mix-titre", "prog-mix"]) document.getElementById(id).hidden = !logement;
  const totalMix = Object.values(h.mix).reduce((a, b) => a + b, 0);
  const total = document.getElementById("prog-mix-total");
  total.textContent = totalMix ? `= ${F0.format(totalMix)} %` : "";
  total.classList.toggle("defavorable", totalMix > 0 && Math.abs(totalMix - 100) > 0.5);

  const resultat = document.getElementById("prog-resultat");
  const invite = document.getElementById("prog-invite");
  // la référence de Tendances, cochable ici aussi : une seule sélection pour tout le benchmark
  const groupe = reference();
  dessinerGroupeProgramme();
  progEtat.h = h; progEtat.lignes = []; progEtat.parts = []; progEtat.n = groupe.length;
  if (!(h.SP_HS > 0)) { resultat.hidden = true; invite.hidden = false; return; }
  invite.hidden = true;
  resultat.hidden = false;

  const fragile = document.getElementById("prog-fragile");
  fragile.hidden = groupe.length >= MIN_REFERENCE;
  fragile.textContent = groupe.length ? `Estimation fragile : ${groupe.length} projet${groupe.length > 1 ? "s" : ""}.`
                                      : "Aucun projet de référence coché : pas d'estimation.";
  if (!groupe.length) { document.getElementById("prog-barre").replaceChildren(); document.getElementById("prog-table").replaceChildren(); return; }

  const sup = fourchette(groupe, "SUP/SP_HS", h.SP_HS);
  const sd = fourchette(groupe, "SD/SP_HS", h.SP_HS);
  const sus = fourchette(groupe, "SUS_HS/SP_HS", h.SP_HS);
  dessinerBarre(h.SP_HS, sup, sd, sus);

  const lignes = [];
  const ligne = (label, f, unite, source, detail, sous) => lignes.push({ label, f, unite, source, detail, sous });
  ligne("SUP hors-sol", sup, "m²", sup && `SUP / SP hors-sol (n = ${sup.n})`);
  const svn = fourchette(groupe, "SVN/SP_HS", h.SP_HS);
  ligne("Surface de vente nette (SVN)", svn, "m²", svn && `SVN / SP hors-sol (n = ${svn.n})`);

  const moyenne = totalMix > 0 ? surfaceMoyenneMix(h.mix) : null;
  if (!logement) { /* pas de logements à estimer hors logement */ }
  else if (moyenne && sup) {
    const log = { bas: sup.bas / moyenne, central: sup.central / moyenne, haut: sup.haut / moyenne };
    const n = Math.round(log.central);
    const court = { 0: "studio", 1: "1 ch.", 2: "2 ch.", 3: "3 ch.", 4: "4 ch. et +" };
    const repartition = MIX.filter(([k]) => h.mix[k]).map(([k]) => `${Math.round((n * h.mix[k]) / totalMix)} × ${court[k]}`).join(" · ");
    ligne("Logements (mix visé)", log, "", `SUP ÷ ${F0.format(moyenne)} m², surface moyenne du mix (Typologies)`, repartition);
  } else {
    const r = fourchette(groupe, "SP_HS/LOG", 1);
    const log = r && { bas: h.SP_HS / r.haut, central: h.SP_HS / r.central, haut: h.SP_HS / r.bas };
    ligne("Logements", log, "", r && `SP hors-sol ÷ SP hors-sol par logement (n = ${r.n}) ; saisissez un mix pour l'affiner`);
  }
  const ss = sup && fourchette(groupe, "SP_SS/SUP", sup.central);
  ligne("SP sous-sol", ss, "m²", ss && `SP sous-sol / SUP (n = ${ss.n})`);
  const facade = fourchette(groupe, "FACADE/SP_HS", h.SP_HS);
  ligne("Façade", facade, "m²", facade && `Façade / SP hors-sol (n = ${facade.n})`);
  const vitree = facade && fourchette(groupe, "VITRE/FACADE", facade.central);
  if (vitree) {
    // la façade pleine suit la part vitrée en sens inverse : plus de vitrage, moins de plein
    ligne("dont vitrée", vitree, "m²", `Part vitrée (n = ${vitree.n})`, null, true);
    ligne("dont pleine", { bas: facade.central - vitree.haut, central: facade.central - vitree.central, haut: facade.central - vitree.bas },
          "m²", "façade − vitrée", null, true);
  }
  if (h.prix > 0 && svn)
    ligne("Chiffre d'affaires (SVN × prix)", { bas: svn.bas * h.prix, central: svn.central * h.prix, haut: svn.haut * h.prix },
          "CHF", `${F0.format(h.prix)} CHF / m² de SVN`);
  progEtat.lignes = lignes;
  dessinerTableProgramme(lignes);
}

/** Les projets fiables du pré-filtre, cochés s'ils sont dans la référence : même état que le volet des Tendances. */
function dessinerGroupeProgramme() {
  const fiables = fiablesSelection(), n = reference().length;
  document.getElementById("prog-groupe-titre").textContent =
    `Projets de référence : ${n} sur ${fiables.length} fiable${fiables.length > 1 ? "s" : ""} (${libelleSelection()}), les mêmes que dans Tendances`;
  document.getElementById("prog-groupe").replaceChildren(...fiables.map((p) => {
    const cb = el("input", { type: "checkbox", "aria-label": `Projet de référence : ${nomProjet(p)}` });
    cb.checked = !etat.exclus.has(p.id);
    cb.addEventListener("change", () => { cb.checked ? etat.exclus.delete(p.id) : etat.exclus.add(p.id); majReference(); });
    return el("li", {}, el("label", {}, cb, el("span", { class: "mono", text: p.id }), el("span", { class: "nom", text: p.nom })));
  }));
}

/** La SP hors-sol découpée en SUP, SD, SUS et le reste (construction, installations), à l'estimation centrale. */
function dessinerBarre(sp, sup, sd, sus) {
  const parts = [["SUP", "SUP", sup], ["SD", "SD", sd], ["SUS", "SUS hors-sol", sus]]
    .filter(([, , f]) => f).map(([code, label, f]) => ({ code, label, m2: f.central }));
  const reste = Math.max(0, sp - parts.reduce((s, x) => s + x.m2, 0));
  parts.push({ code: "reste", label: "Construction, installations et autres", m2: reste });
  progEtat.parts = parts;
  const pct = (m2) => `${F0.format((m2 / sp) * 100)} %`;
  document.getElementById("prog-titre-barre").textContent = `Où vont les ${F0.format(sp)} m² de SP hors-sol (estimation centrale)`;
  const barre = el("div", { class: "barre", role: "img", "aria-label": parts.map((x) => `${x.label} ${F0.format(x.m2)} m²`).join(", ") },
    ...parts.filter((x) => x.m2 > 0).map((x) => el("span", { class: `segment ${x.code === "reste" ? "reste" : ""}`,
      style: `flex-grow:${x.m2};${COULEURS_SIA[x.code] ? `background:${COULEURS_SIA[x.code]}` : ""}`,
      title: `${x.label} : ${F0.format(x.m2)} m² (${pct(x.m2)})` })));
  const legende = el("ul", { class: "legende" }, ...parts.map((x) => el("li", {},
    el("i", { class: x.code === "reste" ? "reste" : "", style: COULEURS_SIA[x.code] ? `background:${COULEURS_SIA[x.code]}` : "" }),
    `${x.label} `, el("b", { text: `${F0.format(x.m2)} m²` }), ` (${pct(x.m2)})`)));
  document.getElementById("prog-barre").replaceChildren(barre, legende);
}

function dessinerTableProgramme(lignes) {
  const fmt = (v, unite) => unite === "CHF" ? `≈ ${F1.format(v / 1e6)} M` : unite === "m²" ? `${F0.format(v)} m²` : F0.format(v);
  const tete = el("tr", {}, ...["", "Bas (P25)", "Central (médiane)", "Haut (P75)", "D'après"].map((t) => el("th", { scope: "col", text: t })));
  const corps = lignes.map(({ label, f, unite, source, detail, sous }) => {
    if (!f) return el("tr", {}, el("td", { text: label }), el("td", { colspan: "4", class: "absent", text: "Pas de donnée dans les projets de référence" }));
    const nom = el("td", { text: label, class: sous ? "sous" : "" });
    if (detail) nom.append(el("span", { class: "detail", text: `dont ${detail}` }));
    return el("tr", {}, nom, el("td", { text: fmt(f.bas, unite) }), el("td", { class: "central", text: fmt(f.central, unite) + (unite === "CHF" ? " CHF" : "") }),
      el("td", { text: fmt(f.haut, unite) }), el("td", { class: "source", text: source || "" }));
  });
  document.getElementById("prog-table").replaceChildren(el("thead", {}, tete), el("tbody", {}, ...corps));
}

// ------------------------------------------------------------------ export Excel (V5_PLAN, partie 4)

/** KPI de la sélection dans l'ordre de l'écran (groupes, puis familles), chacun avec son groupe. */
function kpisOrdonnes() {
  const kpis = kpisSelection(), connues = GROUPES.flatMap((g) => g.familles);
  const autres = [...new Set(kpis.map((k) => k.famille))].filter((f) => !connues.includes(f)).map((f) => ({ titre: f, definition: "", familles: [f] }));
  return [...GROUPES, ...autres].flatMap((g) => g.familles.flatMap((f) => kpis.filter((k) => k.famille === f).map((kpi) => ({ kpi, groupe: g, famille: f }))));
}

/** Charte HRS du classeur, et rien d'autre : orange de marque (bandeau de titre, sections, maquettes comparées), bleu
 *  foncé (en-têtes de tableau), bleus clairs (médiane, sections, bon côté), rouge-orange pâle (mauvais côté), gris. */
const XL = { noir: "000000", gris: "808080", clair: "BFBFBF", filet: "D9D9D9", blanc: "FFFFFF",
             orange: "FF6600", accent: "FF4A2E", bleu: "001A82", mediane: "C3DAFC", section: "DBE9FD", bande: "F4F8FE",
             bon: "001A82", bonFond: "DBE9FD", mauvais: "D62929", mauvaisFond: "FFE1DB", neutre: "000000", neutreFond: "EDEDED" };
const XL_POLICE = "Sofia Pro";
const XL_SOCIETE = "HRS Real Estate AG";
/** Parts de la barre « Où vont les m² » : la surface utile principale à l'orange, puis bleu foncé, bleu clair et gris. */
const XL_PARTS = { SUP: XL.orange, SD: XL.bleu, SUS: XL.mediane, reste: XL.clair };
/** Bandeau de section : bleu clair, texte bleu foncé, barre orange à gauche. */
const XL_SECTION = { fond: XL.section, couleur: XL.bleu, gras: true, taille: 11, v: "center", retrait: 1 };
const XL_BARRE = { bordure: { gauche: `thick:${XL.orange}` } };

/** Format d'affichage d'un KPI : l'unité est dans la cellule (% à une décimale, m² entiers, m et rapports à deux décimales). */
const formatKpi = (kpi) => ({ "%": "0.0%", "m²": '#,##0" m²"', m: '0.00" m"' })[kpi.unite] || "0.00";
/** Écart à la médiane, dans l'unité du KPI (pt = point de pourcentage) : ▲ au-dessus, ▼ en dessous, = à la médiane. */
function formatEcart(kpi) {
  const n = ({ "%": '0.0" pt"', "m²": '#,##0" m²"', m: '0.00" m"' })[kpi.unite] || "0.00";
  return `"▲ +"${n};"▼ −"${n};"="`;
}
/** L'écart arrondi comme il s'affiche (un écart infime se lit « = »), en points pour un KPI en %. */
function ecartXl(kpi, d) {
  const pas = kpi.unite === "%" ? 1000 : kpi.unite === "m²" ? 1 : 100;
  return Math.round(d * pas) / (kpi.unite === "%" ? 10 : pas);
}
/** Place d'une valeur par rapport à la fourchette P25–P75 de la référence : -1 sous, 0 dedans, 1 au-dessus. */
const placeXl = (c, v) => (v < c.q1 ? -1 : v > c.q3 ? 1 : 0);
/** Un écart ou une place de signe `signe` selon le sens du KPI : « bon », « mauvais », « neutre » (KPI sans sens), ou rien. */
const jugementXl = (kpi, signe) => (!signe ? null : !kpi.sens ? "neutre" : signe * kpi.sens > 0 ? "bon" : "mauvais");
/** ID d'un MDP : nombre dans Excel quand il en est un (pas d'avertissement « nombre stocké sous forme de texte »). */
const idCellule = (id) => (/^\d+$/.test(String(id)) ? Number(id) : String(id));
/** Nombre de lignes d'un texte qui revient à la ligne dans `largeur` caractères de colonne (estimation prudente). */
const lignesXl = (texte, largeur, taille = 10) =>
  String(texte).split("\n").reduce((n, t) => n + Math.max(1, Math.ceil((t.length * taille) / (largeur * 11))), 0);
/** Intitulé d'une maquette comparée. Sans ★ : la police de la charte ne l'a pas, Excel changerait de police pour tout l'intitulé. */
const nomCompare = (m) => (m.id !== MIEN ? `${m.p.id} · ${m.p.nom}` : m.p.nom && m.p.nom !== "Mon projet" ? `Mon projet · ${m.p.nom}` : "Mon projet");

/** Une feuille en construction : lignes ajoutées une à une, bandeaux fusionnés. `ct` colonnes (130 caractères au
 *  plus) portent les textes longs : titre, lecture, légende. */
function feuilleXl(nom, largeurs) {
  const f = { nom, largeurs, lignes: [], fusions: [], onglet: XL.orange }, nc = largeurs.length;
  let ct = 0, lt = 0;
  while (ct < nc && lt < 130) lt += largeurs[ct++];
  const ligne = (c, h) => f.lignes.push(h ? { c, h } : c) - 1;
  const fusion = (l1, c1, l2, c2) => { if (l2 > l1 || c2 > c1) f.fusions.push([l1, c1, l2, c2]); };
  /** Ligne dont le texte s'étend de c1 à c2 ; le style (fond, filets) court sur toute la largeur de la feuille,
   *  `premier` s'ajoute à la seule cellule du texte (barre à gauche). */
  const bandeau = (v, s, h, c1 = 0, c2 = ct - 1, premier = {}) => {
    const l = ligne(largeurs.map((_, k) => (k === c1 ? { v, s: { ...s, ...premier } } : { s })), h);
    fusion(l, c1, l, c2);
    return l;
  };
  /** Hauteur d'un texte qui revient à la ligne dans le bandeau. */
  const hauteur = (v, taille = 10) => 6 + Math.ceil(taille * 1.35 * lignesXl(Array.isArray(v) ? v.map((m) => m.t).join("") : v, lt, taille));
  return { f, nc, ct, ligne, fusion, bandeau, hauteur };
}

/** En-tête d'une feuille : bandeau de titre orange, comme une diapositive de titre (filet rouge-orange dessous), ce
 *  que la feuille montre et comment la lire, contexte de l'export. */
function enteteXl(x, titre, lecture, contexte) {
  x.bandeau(titre, { gras: true, taille: 17, couleur: XL.blanc, fond: XL.orange, v: "center", retrait: 1, bordure: { bas: `thick:${XL.accent}` } }, 40);
  x.ligne([], 8);
  x.bandeau(lecture, { couleur: XL.noir, v: "center", retour: true, retrait: 1 }, x.hauteur(lecture));
  x.bandeau(contexte, { v: "center", retrait: 1 }, 20);
  x.ligne([], 10);
}

/** Légende en pied de feuille : un titre, puis une ligne par point (texte enrichi). */
function legendeXl(x, points) {
  x.ligne([], 14);
  x.bandeau("Comment lire cette feuille", { gras: true, taille: 11, couleur: XL.bleu, bordure: { bas: `medium:${XL.orange}` }, v: "center", retrait: 1 }, 20);
  for (const p of points) x.bandeau(p, { couleur: XL.noir, v: "center", retour: true, retrait: 1 }, x.hauteur(p, 9));
}
/** Morceaux de texte enrichi des légendes : `g` en gras, `t` courant. */
const RT = { g: (t, couleur = XL.noir) => ({ t, gras: true, couleur, taille: 9 }), t: (t) => ({ t, couleur: XL.noir, taille: 9 }) };

/** Le classeur de l'écran : KPI (référence et maquettes comparées hors référence), projets de référence, détail par
 *  projet et, si une SP est saisie dans Programmer, le programme attendu. Une seule valeur centrale : la médiane,
 *  celle de Tendances et de Programmer ; la fourchette va du 1er au 3e quartile. */
function classeurBenchmark() {
  const ref = reference(), fiables = fiablesSelection(), kpis = kpisOrdonnes();
  const idsRef = new Set(ref.map((p) => p.id));
  // les maquettes comparées déjà dans la référence ne sont pas répétées : elles sont repérées dans les listes de projets
  const cmp = comparees(), hors = cmp.filter((m) => !idsRef.has(m.p.id)), dedans = new Map(cmp.filter((m) => idsRef.has(m.p.id)).map((m) => [m.p.id, m]));
  const stats = new Map(kpis.map(({ kpi }) => [kpi.id, combiner(ref, kpi)]));
  const date = new Date().toLocaleString("fr-CH", { dateStyle: "long", timeStyle: "short" });
  const pl = (n, mot) => `${n} ${mot}${n > 1 ? "s" : ""}`;
  const contexte = [
    { t: "Pré-filtre  ", couleur: XL.gris }, { t: libelleSelection(), gras: true, couleur: XL.bleu },
    { t: "        Référence  ", couleur: XL.gris }, { t: `${pl(ref.length, "projet")} sur ${pl(fiables.length, "fiable")}`, gras: true, couleur: XL.bleu },
    { t: "        Exporté le  ", couleur: XL.gris }, { t: date, gras: true, couleur: XL.bleu },
  ];
  const impression = (titres, papier) => ({ titres, papier, pied: `${XL_SOCIETE} · Benchmark des surfaces SIA 416 · ${libelleSelection()} · ${date}` });
  // tableaux : en-tête en aplat bleu foncé, texte blanc ; lignes séparées par un filet fin gris clair
  const tete = (v, s) => ({ v, s: { gras: true, taille: 9, couleur: XL.blanc, fond: XL.bleu, h: "center", v: "center", retour: true, ...s } });
  const teteMediane = { fond: XL.mediane, couleur: XL.bleu };
  const filet = { v: "center", bordure: { bas: XL.filet } }, droite = { h: "right", retrait: 1 };
  const absent = { v: "—", s: { ...filet, h: "center", couleur: XL.clair } };
  const gauche = { gauche: XL.mediane };     // filet vertical entre deux blocs de colonnes
  const blancG = { bordure: { gauche: XL.blanc } };     // le même, dans un en-tête
  /** Nom d'un projet de référence, précédé d'une pastille orange s'il est aussi comparé à l'écran. */
  const nomRef = (p) => (dedans.has(p.id) ? [{ t: "● ", gras: true, couleur: XL.orange }, { t: p.nom, gras: true, couleur: XL.noir }] : p.nom);
  const pastilles = dedans.size ? [[RT.g("● ", XL.orange), RT.g("Pastille : "), RT.t("projet de référence qui est aussi une maquette comparée à l'écran.")]] : [];
  /** Une valeur hors de la fourchette P25–P75 d'un ratio qui a un sens : aplat bleu clair du bon côté, rouge-orange
   *  pâle du mauvais. Un ratio sans bon ni mauvais sens n'est pas marqué : la moitié du tableau serait colorée pour rien. */
  const horsFourchette = (kpi, v) => {
    const c = stats.get(kpi.id), j = c.n >= MIN_REFERENCE && kpi.sens ? jugementXl(kpi, placeXl(c, v)) : null;
    return j ? { gras: true, couleur: XL[j], fond: XL[`${j}Fond`] } : {};
  };
  const legendeCouleurs = [RT.g("Bleu", XL.bon), RT.t(" : du bon côté selon le sens de lecture. "), RT.g("Rouge", XL.mauvais), RT.t(" : du mauvais côté. "),
    RT.g("Gris"), RT.t(" : ratio sans bon ni mauvais sens (un choix de projet).")];

  // 1. KPI : un ratio par ligne, rangé par groupe ; la référence, puis trois colonnes par maquette comparée hors référence
  const k = feuilleXl("KPI", [31, 52, 16, 8, 11, 11, 11, ...hors.flatMap(() => [12, 17, 22])]);
  enteteXl(k, "Benchmark des surfaces SIA 416 — ratios de la référence",
    "Un ratio par ligne. La médiane est la valeur du projet type : la moitié des projets de référence est au-dessus, l'autre en dessous. "
    + "La fourchette P25–P75 encadre la moitié centrale des projets."
    + (hors.length ? " À droite, chaque maquette comparée : sa valeur, son écart à la médiane et sa place par rapport à la fourchette." : ""), contexte);
  // sur-titre d'un bloc de colonnes : bleu foncé pour la référence, orange pour chaque maquette comparée
  const sur = { taille: 10, bordure: { gauche: XL.blanc, bas: XL.blanc } }, surCmp = { ...sur, fond: XL.orange };
  const k1 = k.ligne([tete("Ratio", { h: "left", retrait: 1 }), tete("En clair, pour le projet type", { h: "left" }), tete("Sens de lecture"),
    tete(`Projets de référence (${ref.length})`, sur), tete(null, sur), tete(null, sur), tete(null, sur),
    ...hors.flatMap((m) => [tete(nomCompare(m), surCmp), tete(null, surCmp), tete(null, surCmp)])], 24);
  const k2 = k.ligne([tete(null), tete(null), tete(null), tete("Projets (n)", blancG), tete("Bas (P25)"), tete("Médiane", teteMediane), tete("Haut (P75)"),
    ...hors.flatMap(() => [tete("Valeur", blancG), tete("Écart à la médiane"), tete("Place dans la fourchette")])], 28);
  for (const c of [0, 1, 2]) k.fusion(k1, c, k2, c);
  k.fusion(k1, 3, k1, 6);
  hors.forEach((_, i) => k.fusion(k1, 7 + 3 * i, k1, 9 + 3 * i));
  const SENS_XL = { 1: "Plus haut = mieux", "-1": "Plus bas = mieux", 0: "Ni bon ni mauvais : choix de projet" };
  let groupe = null, famille = null;
  for (const { kpi, groupe: g, famille: f } of kpis) {
    // groupes : un même bandeau de section pour tous ; familles : un sous-titre bleu
    if (g !== groupe)
      k.bandeau([{ t: g.titre, gras: true, taille: 11, couleur: XL.bleu }, { t: g.definition ? `     ${g.definition}` : "", taille: 9, couleur: XL.bleu }],
        XL_SECTION, 24, 0, k.nc - 1, XL_BARRE);
    if (g.familles.length > 1 && (g !== groupe || f !== famille))
      k.bandeau(f, { gras: true, taille: 9, couleur: XL.bleu, v: "bottom", retrait: 1, bordure: { bas: XL.mediane } }, 20, 0, k.nc - 1);
    groupe = g; famille = f;
    const c = stats.get(kpi.id), nombre = { ...filet, ...droite, format: formatKpi(kpi) }, [phrase, court] = PHRASES[kpi.id] || [];
    const clair = phrase && c.n ? phrase.replace("{v}", enClair(kpi, c.mediane)) : "";
    const lignes = Math.max(lignesXl(court || kpi.label, 30) + (court ? lignesXl(kpi.label, 30, 8) : 0),
      (clair ? lignesXl(clair, 52) : 0) + (kpi.note ? lignesXl(kpi.note, 52, 8) : 0), lignesXl(SENS_XL[kpi.sens] || SENS_XL[0], 16, 9));
    k.ligne([
      { v: [{ t: court || kpi.label, gras: true, couleur: XL.noir }, { t: court ? `\n${kpi.label}` : "", taille: 8, couleur: XL.gris }], s: { ...filet, retour: true, retrait: 1 } },
      { v: [{ t: clair, couleur: XL.noir }, { t: kpi.note ? `${clair ? "\n" : ""}${kpi.note}` : "", taille: 8, couleur: XL.gris }], s: { ...filet, retour: true } },
      { v: SENS_XL[kpi.sens] || SENS_XL[0], s: { ...filet, h: "center", retour: true, taille: 9, couleur: kpi.sens ? XL.noir : XL.gris } },
      { v: c.n || 0, s: { ...filet, h: "center", couleur: XL.gris, bordure: { ...filet.bordure, ...gauche } } },
      c.n ? { v: c.q1, s: nombre } : absent,
      c.n ? { v: c.mediane, s: { ...nombre, gras: true, couleur: XL.bleu, fond: XL.mediane } } : { ...absent, s: { ...absent.s, fond: XL.mediane } },
      c.n ? { v: c.q3, s: nombre } : absent,
      ...hors.flatMap((m) => {
        const v = m.p.kpis?.[kpi.id]?.valeur, bord = { bordure: { ...filet.bordure, ...gauche } };
        if (v == null) return [{ ...absent, s: { ...absent.s, ...bord } }, { s: filet }, { s: filet }];
        const valeurM = { v, s: { ...nombre, gras: true, ...bord } };
        if (!c.n) return [valeurM, { s: filet }, { s: filet }];
        const e = ecartXl(kpi, v - c.mediane), place = placeXl(c, v), j = jugementXl(kpi, place);
        return [valeurM,
          { v: e, s: { ...filet, ...droite, format: formatEcart(kpi), couleur: XL[jugementXl(kpi, Math.sign(e))] || XL.gris } },
          { v: place > 0 ? "▲ Au-dessus du P75" : place < 0 ? "▼ Sous le P25" : "Dans la fourchette",
            s: { ...filet, h: "center", taille: 9, ...(j ? { gras: true, couleur: XL[j], fond: XL[`${j}Fond`] } : { couleur: XL.gris }) } }];
      })], Math.max(30, 8 + 12.5 * lignes));
  }
  legendeXl(k, [
    [RT.g("Médiane : "), RT.t("la valeur centrale de la référence, celle des onglets Tendances et Programmer. "), RT.g("Fourchette (P25 à P75) : "),
     RT.t("un quart des projets est sous le P25, un quart au-dessus du P75. Avec peu de projets, la fourchette reste indicative.")],
    [RT.g("Sens de lecture : "), RT.t("dit de quel côté de la médiane un projet fait mieux. « Choix de projet » : le ratio décrit le projet sans le juger.")],
    ...(hors.length ? [
      [RT.g("Écart à la médiane : "), RT.t("valeur de la maquette moins la médiane, dans l'unité du ratio (pt = point de pourcentage). ▲ au-dessus de la médiane, ▼ en dessous. "),
       ...legendeCouleurs],
      [RT.g("Place dans la fourchette : "), RT.t("la maquette est-elle dans la moitié centrale des projets de référence ? Hors fourchette, la case est colorée : bleu clair du bon côté, rouge pâle du mauvais, gris sans jugement.")]] : []),
    ...(dedans.size ? [[RT.g("Maquettes comparées déjà dans la référence : "),
      RT.t(`${[...dedans.values()].map((m) => `${m.p.id} ${m.p.nom}`).join(", ")}. Leurs valeurs pèsent dans la médiane ; elles se lisent dans la feuille « Détail par projet ».`)]] : []),
  ]);
  Object.assign(k.f, { figer: { lignes: k2 + 1, colonnes: 1 }, impression: impression([k1, k2]) });

  // 2. Projets de référence : identité et surfaces principales, total et médiane en pied
  const SURFACES_REF = [["SP", "SP (m²)"], ["SP_HS", "SP hors-sol (m²)"], ["SP_SS", "SP sous-sol (m²)"], ["SUP", "SUP (m²)"]];
  const r = feuilleXl("Projets de référence", [8, 30, 40, 23, 26, 8, 18, 26, 8, 12, 12, 12, 12, 11, 9, 11]);
  enteteXl(r, "Projets de référence",
    "Les projets dont sont tirées la médiane et la fourchette de chaque ratio : les projets fiables du pré-filtre, cochés à l'écran. "
    + "Les flèches de l'en-tête trient et filtrent la liste.", contexte);
  const rTete = r.ligne([tete("ID"), ...["Nom", "Typologie", "Intervention", "Forme"].map((t) => tete(t, { h: "left" })), tete("Canton"), tete("Commune", { h: "left" }),
    tete("Adresse", { h: "left" }), tete("Phase SIA"), ...SURFACES_REF.map(([, t]) => tete(t)), tete("Logements"), tete("Étages hors-sol"), tete("Maquette 3D")], 32);
  ref.forEach((p, i) => {
    const base = { ...filet, ...(i % 2 ? { fond: XL.bande } : {}) };
    const centre = { ...base, h: "center" }, nombre = { ...base, ...droite, format: "#,##0" };
    const texte = (v) => ({ v: v || "", s: { ...base, retour: true } });
    const lignes = Math.max(...[[p.nom, 30], [p.infos?.categorie, 40], [p.infos?.intervention, 23], [p.infos?.forme, 26], [p.infos?.commune, 18], [p.infos?.adresse, 26]].map(([t, l]) => lignesXl(t || "", l)));
    r.ligne([{ v: idCellule(p.id), s: { ...centre, couleur: XL.gris } }, { v: nomRef(p), s: { ...base, gras: true, couleur: XL.noir, retour: true } },
      texte(p.infos?.categorie), texte(p.infos?.intervention), texte(p.infos?.forme), { v: p.infos?.canton || "", s: centre }, texte(p.infos?.commune), texte(p.infos?.adresse),
      { v: p.infos?.phase ?? "", s: centre }, ...SURFACES_REF.map(([c]) => ({ v: p.totaux?.[c], s: nombre })),
      { v: p.infos?.logements || null, s: nombre }, { v: p.totaux?.ETAGES_HS, s: centre },
      { v: p.maquette ? "oui" : "—", s: { ...centre, couleur: p.maquette ? XL.noir : XL.clair } }], 7 + 13.5 * lignes);
  });
  const rFin = r.f.lignes.length - 1;
  const colonneRef = (lire) => ref.map(lire).filter((v) => v != null && Number.isFinite(v)).sort((a, b) => a - b);
  const mesures = [...SURFACES_REF.map(([c]) => colonneRef((p) => p.totaux?.[c])), colonneRef((p) => p.infos?.logements || null), colonneRef((p) => p.totaux?.ETAGES_HS)];
  const pied = (titre, calcul, s) => r.ligne([{ s }, { v: titre, s: { ...s, gras: true } }, ...Array.from({ length: 7 }, () => ({ s })),
    ...mesures.map((v, i) => ({ v: v.length ? calcul(v, i) : null, s: { ...s, gras: true, format: "#,##0", ...(i === 5 ? { h: "center" } : droite) } })), { s }], 20);
  if (ref.length) {
    pied(`Total des ${pl(ref.length, "projet")}`, (v, i) => (i === 5 ? null : v.reduce((a, b) => a + b, 0)), { v: "center", couleur: XL.bleu, fond: XL.section, bordure: { haut: XL.bleu } });
    pied("Médiane", (v) => quantile(v, 0.5), { v: "center", couleur: XL.bleu, fond: XL.mediane });
  }
  legendeXl(r, [
    [RT.g("Projet fiable : "), RT.t("maquette dont les surfaces passent les contrôles du benchmark (surfaces brutes et nettes, cohérence, informations du projet).")],
    [RT.g("SP : "), RT.t("surface de plancher (SIA 416), hors-sol et sous-sol. "), RT.g("SUP : "), RT.t("surface utile principale. "),
     RT.g("Total et médiane : "), RT.t("sur les projets listés, sans tenir compte d'un filtre posé dans Excel.")],
    ...pastilles]);
  Object.assign(r.f, { figer: { lignes: rTete + 1, colonnes: 2 }, impression: impression([rTete, rTete]), ...(ref.length ? { filtre: [rTete, 0, rFin, r.nc - 1] } : {}) });

  // 3. Détail par projet : un projet par ligne, les ratios en colonnes sous leur groupe ; médiane et fourchette en pied
  const d = feuilleXl("Détail par projet", [8, 30, ...kpis.map(() => 13)]);
  enteteXl(d, "Détail par projet — la valeur de chaque ratio",
    "Un projet par ligne, un ratio par colonne. En pied, la médiane et la fourchette P25–P75 de la référence servent de repère. "
    + "Une valeur colorée sort de cette fourchette : en bleu du bon côté, en rouge du mauvais." + (hors.length ? " Les maquettes comparées hors référence suivent, à part." : ""), contexte);
  const debut = (i) => i === 0 || kpis[i].groupe !== kpis[i - 1].groupe;     // première colonne d'un groupe : filet à gauche
  const bordG = (i) => (debut(i) ? gauche : {});
  const blancD = (i) => (debut(i) ? blancG : {});
  const d1 = d.ligne([tete("ID"), tete("Projet", { h: "left" }),
    ...kpis.map(({ groupe: g }, i) => tete(debut(i) ? g.titre : null, { taille: 10, bordure: { bas: XL.blanc, ...blancD(i).bordure } }))], 22);
  const d2 = d.ligne([tete(null), tete(null), ...kpis.map(({ kpi }, i) => tete(PHRASES[kpi.id]?.[1] || kpi.label, blancD(i)))], 44);
  const SENS_COURT = { 1: "▲ mieux", "-1": "▼ mieux", 0: "choix de projet" };
  // sous-en-tête : le sens de lecture, en bleu clair
  const d3 = d.ligne([tete(null), tete(null), ...kpis.map(({ kpi }, i) =>
    tete(SENS_COURT[kpi.sens] || SENS_COURT[0], { gras: false, taille: 8, couleur: XL.bleu, fond: XL.section, ...blancD(i) }))], 16);
  for (const c of [0, 1]) d.fusion(d1, c, d3, c);
  kpis.forEach((_, i) => { if (debut(i)) { let j = i; while (j + 1 < kpis.length && !debut(j + 1)) j++; d.fusion(d1, 2 + i, d1, 2 + j); } });
  const valeurs = (p) => kpis.map(({ kpi }, i) => {
    const v = p.kpis?.[kpi.id]?.valeur, bordure = { ...filet.bordure, ...bordG(i) };
    return v == null ? { ...absent, s: { ...absent.s, bordure } } : { v, s: { v: "center", ...droite, format: formatKpi(kpi), ...horsFourchette(kpi, v), bordure } };
  });
  for (const p of ref)
    d.ligne([{ v: idCellule(p.id), s: { ...filet, h: "center", couleur: XL.gris } }, { v: nomRef(p), s: { ...filet, gras: true, couleur: XL.noir } }, ...valeurs(p)], 19);
  const repere = (titre, lire, s, format) => d.ligne([{ s }, { v: titre, s }, ...kpis.map(({ kpi }, i) => {
    const c = stats.get(kpi.id), st = { ...s, bordure: { ...s.bordure, ...bordG(i) } };
    return c.n ? { v: lire(c), s: { ...st, ...droite, format: format || formatKpi(kpi) } } : { v: "—", s: { ...st, h: "center", couleur: XL.clair } };
  })], 19);
  if (ref.length) {
    repere("Médiane de la référence", (c) => c.mediane, { v: "center", gras: true, couleur: XL.bleu, fond: XL.mediane, bordure: { haut: XL.bleu } });
    repere("Bas de la fourchette (P25)", (c) => c.q1, { v: "center", couleur: XL.noir, fond: XL.bande, bordure: { bas: XL.filet } });
    repere("Haut de la fourchette (P75)", (c) => c.q3, { v: "center", couleur: XL.noir, fond: XL.bande, bordure: { bas: XL.filet } });
    repere("Projets avec la donnée (n)", (c) => c.n, { v: "center", couleur: XL.gris, fond: XL.bande, bordure: { bas: XL.mediane } }, "0");
  }
  if (hors.length) {
    d.ligne([], 12);
    // même orange que les en-têtes des maquettes comparées de la feuille KPI
    d.bandeau("Maquettes comparées hors référence", { gras: true, taille: 10, couleur: XL.blanc, fond: XL.orange, v: "center", retrait: 1 }, 22, 0, d.nc - 1);
    for (const m of hors)
      d.ligne([{ v: m.id === MIEN ? "★" : idCellule(m.p.id), s: { ...filet, h: "center", couleur: XL.gris } },
        { v: m.id === MIEN ? m.p.nom || "Mon projet" : m.p.nom, s: { ...filet, gras: true, couleur: XL.noir } }, ...valeurs(m.p)], 19);
  }
  legendeXl(d, [
    [RT.g("Valeur colorée : "), RT.t("hors de la fourchette P25–P75 de la référence. "), RT.g("Bleu", XL.bon), RT.t(" : du bon côté selon le sens de lecture. "),
     RT.g("Rouge", XL.mauvais), RT.t(" : du mauvais côté. Les ratios sans bon ni mauvais sens (choix de projet) ne sont pas marqués.")],
    [RT.g("▲ mieux / ▼ mieux : "), RT.t("sens de lecture du ratio (plus haut ou plus bas = mieux). "), RT.g("— : "), RT.t("donnée absente de la maquette, le ratio n'est pas calculable. "),
     RT.t("L'intitulé complet de chaque ratio est dans la feuille « KPI ».")],
    ...pastilles]);
  Object.assign(d.f, { figer: { lignes: d3 + 1, colonnes: 2 }, impression: impression([d1, d3], 8) });

  const feuilles = [k.f, r.f, d.f];

  // 4. Programme attendu : seulement si une SP hors-sol est saisie dans Programmer, tel que son tableau
  const h = progEtat.h;
  if (h?.SP_HS > 0 && progEtat.lignes.length) {
    const p = feuilleXl("Programme attendu", [42, 18, 20, 18, 64]);
    enteteXl(p, "Programme attendu",
      "Ce que les projets de référence laissent attendre d'un projet de la surface saisie. Central : la médiane de la référence. "
      + "Bas et haut : la fourchette P25–P75. La dernière colonne dit de quel ratio vient chaque ligne.", contexte);
    const carte = (titre, v, format) => {
      const l = p.ligne([{ v: titre, s: { ...filet, couleur: XL.gris, retrait: 1 } }, { v, s: { ...filet, gras: true, couleur: XL.noir, h: "left", format } }, { s: filet }, { s: filet }, { s: filet }], 19);
      p.fusion(l, 1, l, 4);
    };
    p.bandeau("Hypothèses saisies", XL_SECTION, 22, 0, p.ct - 1, XL_BARRE);
    carte("SP hors-sol", h.SP_HS, '#,##0" m²"');
    const mix = MIX.filter(([c]) => h.mix[c]).map(([c, l]) => `${l} ${F0.format(h.mix[c])} %`).join(" · ");
    carte("Mix de logements visé", mix || "non saisi");
    carte("Prix de vente", h.prix > 0 ? h.prix : "non saisi", '#,##0" CHF / m² de SVN"');
    carte("Référence", `${pl(progEtat.n, "projet")} (${libelleSelection()})`);
    if (progEtat.n < MIN_REFERENCE)
      p.bandeau(`Estimation fragile : ${pl(progEtat.n, "projet")} de référence seulement.`, { gras: true, couleur: XL.mauvais, fond: XL.mauvaisFond, v: "center", retrait: 1 }, 22);
    p.ligne([], 14);
    const pTete = p.ligne([tete("Poste", { h: "left", retrait: 1 }), tete("Bas (P25)", droite), tete("Central (médiane)", { ...droite, ...teteMediane }),
      tete("Haut (P75)", droite), tete("D'après", { h: "left", retrait: 1 })], 24);
    const FORMATS = { "m²": '#,##0" m²"', CHF: '0.0,," M CHF"' };     // le chiffre d'affaires en millions, comme à l'écran
    for (const { label, f, unite, source, detail, sous } of progEtat.lignes) {
      const nom = { v: [{ t: label, gras: !sous, couleur: XL.noir }, { t: detail ? `\ndont ${detail}` : "", taille: 8, couleur: XL.gris }],
                    s: { ...filet, retour: true, retrait: sous ? 3 : 1 } };
      if (!f) {
        const s = { ...filet, couleur: XL.gris };
        const l = p.ligne([nom, { v: "Pas de donnée dans les projets de référence", s: { ...s, retrait: 1 } }, { s }, { s }, { s }], 21);
        p.fusion(l, 1, l, 4);
        continue;
      }
      const nombre = { ...filet, ...droite, format: FORMATS[unite] || "#,##0", couleur: XL.noir };
      const origine = { ...filet, taille: 9, couleur: XL.gris, retour: true, retrait: 1 };
      p.ligne([nom, { v: f.bas, s: nombre }, { v: f.central, s: { ...nombre, gras: true, couleur: XL.bleu, fond: XL.mediane } }, { v: f.haut, s: nombre },
        // le prix en nombre : son séparateur de milliers suit Excel, comme les montants de la ligne
        unite === "CHF" ? { v: h.prix, s: { ...origine, h: "left", format: '#,##0" CHF / m² de SVN"' } } : { v: source || "", s: origine }], detail ? 32 : 21);
    }
    if (progEtat.parts.length) {     // la barre de l'écran : où va la SP hors-sol, à l'estimation centrale
      p.ligne([], 14);
      // un nombre et son format, pas un texte : le séparateur de milliers suit les réglages d'Excel, comme le reste de la feuille
      p.bandeau(h.SP_HS, { ...XL_SECTION, h: "left", format: '"Où vont les "#,##0" m² de SP hors-sol (estimation centrale)"' }, 22, 0, p.ct - 1, XL_BARRE);
      for (const { code, label, m2 } of progEtat.parts) {
        const part = m2 / h.SP_HS;
        const l = p.ligne([{ v: label, s: { ...filet, couleur: XL.noir, retrait: 1 } }, { v: m2, s: { ...filet, ...droite, format: FORMATS["m²"] } }, { v: part, s: { ...filet, ...droite, format: "0%", gras: true } },
          { v: "█".repeat(Math.round(part * 60)), s: { ...filet, couleur: XL_PARTS[code] || XL_PARTS.reste, taille: 11 } }, { s: filet }], 19);
        p.fusion(l, 3, l, 4);
      }
    }
    legendeXl(p, [
      [RT.g("Central : "), RT.t("la surface de plancher saisie multipliée par la médiane du ratio dans les projets de référence. "),
       RT.g("Bas et haut : "), RT.t("la même surface multipliée par le P25 et le P75 du ratio : la moitié centrale des projets tombe entre les deux.")],
      [RT.g("Ordres de grandeur : "), RT.t("ces chiffres situent un projet en amont des études ; ils ne remplacent ni un avant-projet ni un métré.")]]);
    p.f.impression = impression([pTete, pTete]);
    feuilles.push(p.f);
  }
  return feuilles;
}

function exporterExcel() {
  const blob = classeurXlsx(classeurBenchmark(), { police: XL_POLICE });
  const jour = new Date().toISOString().slice(0, 10);
  const a = el("a", { href: URL.createObjectURL(blob), download: `Benchmark_SIA416_${jour}.xlsx` });
  document.body.append(a);
  a.click();     // dans SIA Check, l'application demande où enregistrer (MainWindow.Dashboard.cs, DownloadStarting)
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 60000);
}

// ------------------------------------------------------------------ onglets et démarrage

const VUES = ["ratios", "programmer", "base", "typologies"];

function montrerVue(nom) {
  for (const v of VUES) {
    const tab = document.getElementById(`tab-${v}`);
    tab.setAttribute("aria-selected", String(v === nom));
    tab.tabIndex = v === nom ? 0 : -1;
    document.getElementById(`vue-${v}`).hidden = v !== nom;
  }
}

function brancherOnglets() {
  VUES.forEach((v, i) => {
    const tab = document.getElementById(`tab-${v}`);
    tab.addEventListener("click", () => montrerVue(v));
    tab.addEventListener("keydown", (e) => {
      const pas = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!pas) return;
      const suivant = VUES[(i + pas + VUES.length) % VUES.length];
      montrerVue(suivant);
      document.getElementById(`tab-${suivant}`).focus();
    });
  });
}

function afficherEtat(message) {
  const p = document.getElementById("etat");
  p.textContent = message;
  p.hidden = false;
  for (const v of VUES) document.getElementById(`vue-${v}`).hidden = true;
}

function demarrer(data) {
  if (!data || !Array.isArray(data.projets) || !data.projets.length) {
    afficherEtat("La base n'a pas encore été lue, ou elle ne contient aucun MDP. Revenez à l'accueil et relisez la base.");
    return;
  }
  etat.data = data;
  etat.kpis = data.kpis;
  etat.projets = new Map(data.projets.map((p) => [String(p.id), p]));
  document.getElementById("etat").hidden = true;
  initVolets();
  brancher3D();
  brancherOutilsCarte();
  initSelection();
  remplirEcartes();
  initSaisie();
  initProgrammer();
  const ecart = verifierDistances();
  if (ecart > 0.002) console.warn(`Distances de la page et du moteur différentes (écart max ${ecart}) : formules à réaligner.`);
  dessinerBase();
  dessinerTypologies();
  // un projet demandé (SIA Check, lien) est ajouté aux maquettes comparées
  const demande = PARAMS.get("projet");
  if ((demande === MIEN || etat.projets.has(demande)) && !estComparee(demande)) basculerComparee(demande);
  document.getElementById("saisie").hidden = !estComparee(MIEN);
  dessinerVolets();
  dessinerRatios();
  dessinerAnatomie();
  montrerVue("ratios");
}

function charger() {
  poserIcones();
  if (PARAMS.get("theme")) document.documentElement.dataset.theme = PARAMS.get("theme");
  brancherOnglets();
  const hote = window.chrome && window.chrome.webview;
  if (hote) {   // dans SIA Check : l'application répond à « pret » par le contenu de benchmark.json
    hote.addEventListener("message", (e) => {
      const m = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
      if (m && m.monProjet) recevoirProjetSiaCheck(m.monProjet);
      else demarrer(m);
    });
    hote.postMessage("pret");
    return;
  }
  fetch(PARAMS.get("data") || "benchmark.json", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    // une erreur de la page reste dans la console : seule l'absence de la base donne ce message
    .then(demarrer, () => afficherEtat("La base n'a pas encore été lue (benchmark.json introuvable)."));
}

charger();
