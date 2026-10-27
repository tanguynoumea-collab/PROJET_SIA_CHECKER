// Dashboard du benchmark (docs/DESIGN_PLAN.md, Évolution 3.1 ; docs/V3_PLAN.md §4).
// Données : benchmark.json de `sia-check --benchmark`. Dans SIA Check, l'application les transmet par WebView2
// (window.chrome.webview) ; sur un serveur, la page les lit à côté d'elle (?data=… pour un autre chemin).
// Le moteur fait foi pour les totaux, la fiabilité et les distances ; la page ne refait que les ratios combinés
// (Σ numérateurs / Σ dénominateurs) du groupe que l'utilisateur coche.
"use strict";

const PARAMS = new URLSearchParams(location.search);
const MIN_REFERENCE = 3;     // en dessous, la référence est fragile (V3_PLAN §4.4)
const TAILLE_GROUPE = 5;
const SVG = "http://www.w3.org/2000/svg";

const etat = { data: null, projets: new Map(), kpis: [], projetId: null, coches: new Set(), filtres: { categorie: true, intervention: true }, tri: null };

// ------------------------------------------------------------------ formats

const nf = (d) => new Intl.NumberFormat("fr-CH", { minimumFractionDigits: d, maximumFractionDigits: d });
const F0 = nf(0), F1 = nf(1), F2 = nf(2);

function valeur(kpi, v) {
  if (v == null) return "—";
  if (kpi.unite === "%") return `${F1.format(v * 100)} %`;
  if (kpi.unite === "m") return `${F2.format(v)} m`;
  return `${F0.format(v)} ${kpi.unite}`;
}

function ecartTexte(kpi, d) {
  const s = d > 0 ? "+" : d < 0 ? "−" : "±";
  const a = Math.abs(d);
  if (kpi.unite === "%") { const p = a * 100; return `${s}${F1.format(p)} pt${p >= 2 ? "s" : ""}`; }
  if (kpi.unite === "m") return `${s}${F2.format(a)} m`;
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

/** Les projets fiables les plus proches, filtres appliqués : une valeur inconnue n'écarte pas (comme le moteur). */
function candidats(ref) {
  const memes = (f) => !etat.filtres[f] || !ref.infos[f];
  return Object.entries(ref.distances || {})
    .map(([id, d]) => ({ p: etat.projets.get(id), d }))
    .filter(({ p }) => p && p.fiable && p.id !== ref.id)
    .filter(({ p }) => ["categorie", "intervention"].every((f) => memes(f) || !p.infos[f] || norm(p.infos[f]) === norm(ref.infos[f])))
    .sort((a, b) => a.d - b.d)
    .slice(0, TAILLE_GROUPE);
}

const norm = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase();

/** Domaine d'une règle : toutes les valeurs fiables de la base et celle du projet étudié, avec une marge. */
function domaine(kpi, extra) {
  const v = etat.data.projets.filter((p) => p.fiable && p.kpis[kpi.id]).map((p) => p.kpis[kpi.id].valeur);
  if (extra != null) v.push(extra);
  if (!v.length) return null;
  let lo = Math.min(...v), hi = Math.max(...v);
  const marge = (hi - lo) * 0.08 || Math.abs(hi) * 0.1 || 1;
  return [lo - marge, hi + marge];
}

// ------------------------------------------------------------------ Comparer

function remplirProjets() {
  const sel = document.getElementById("projet");
  const fiables = etat.data.projets.filter((p) => p.fiable), ecartes = etat.data.projets.filter((p) => !p.fiable);
  const groupe = (label, liste) => {
    const g = el("optgroup", { label });
    for (const p of liste) g.append(el("option", { value: p.id, text: nomProjet(p) }));
    return g;
  };
  sel.append(groupe("Fiables", fiables), groupe("Écartés (données incohérentes)", ecartes));
  sel.addEventListener("change", () => choisirProjet(sel.value));
}

function choisirProjet(id) {
  etat.projetId = id;
  document.getElementById("projet").value = id;
  etat.coches = new Set(candidats(etat.projets.get(id)).map((c) => c.p.id));
  dessinerComparer();
}

function dessinerComparer() {
  const ref = etat.projets.get(etat.projetId);
  const liste = candidats(ref);
  const groupe = liste.filter((c) => etat.coches.has(c.p.id)).map((c) => c.p);

  const bandeau = document.getElementById("bandeau-projet");
  bandeau.hidden = ref.fiable;
  bandeau.textContent = ref.fiable ? "" : "Données incohérentes : ce projet est écarté des références (SP et SN ne décrivent pas le même périmètre). " +
    "Ses ratios sont affichés pour mémoire.";

  const ul = document.getElementById("similaires");
  ul.replaceChildren(...liste.map(({ p, d }) => {
    const cb = el("input", { type: "checkbox", "aria-label": `Inclure ${nomProjet(p)} dans la référence` });
    cb.checked = etat.coches.has(p.id);
    cb.addEventListener("change", () => { cb.checked ? etat.coches.add(p.id) : etat.coches.delete(p.id); dessinerComparer(); });
    const pleins = Math.max(1, Math.round(5 * (1 - Math.min(d, 1))));
    const prox = el("span", { class: "proximite", title: `Distance ${F2.format(d)} (0 = identique)` },
      ...Array.from({ length: 5 }, (_, i) => el("i", { class: i < pleins ? "plein" : "" })));
    return el("li", {}, el("label", {}, cb, el("span", { class: "mono", text: p.id }), el("span", { class: "nom", text: p.nom, title: p.nom })), prox);
  }));

  const aucun = document.getElementById("aucun-similaire");
  aucun.hidden = liste.length > 0;
  if (!liste.length) {
    const filtre = etat.filtres.categorie || etat.filtres.intervention;
    aucun.replaceChildren(filtre ? "Aucun projet ne passe ces filtres." : "Aucun projet comparable : il manque au projet des caractéristiques (SP hors-sol, logements…).");
    if (filtre) {
      const b = el("button", { class: "lien", type: "button", text: "Retirer les filtres" });
      b.addEventListener("click", () => { etat.filtres.categorie = etat.filtres.intervention = false; syncFiltres(); choisirProjet(ref.id); });
      aucun.append(" ", b);
    }
  }

  document.getElementById("resume-reference").textContent = groupe.length
    ? `Référence : ${groupe.length} projet${groupe.length > 1 ? "s" : ""} similaire${groupe.length > 1 ? "s" : ""} · ratios combinés` +
      (groupe.length < MIN_REFERENCE ? " · référence fragile" : "")
    : "Aucune référence : cochez au moins un projet similaire.";

  const regles = document.getElementById("regles");
  regles.replaceChildren();
  for (const famille of [...new Set(etat.kpis.map((k) => k.famille))]) {
    const bloc = el("section", { class: "famille" }, el("h2", { text: famille }));
    for (const kpi of etat.kpis.filter((k) => k.famille === famille)) bloc.append(ligneKpi(kpi, ref, groupe));
    regles.append(bloc);
  }
}

function ligneKpi(kpi, ref, groupe) {
  const r = ref.kpis[kpi.id];
  const c = combiner(groupe, kpi);
  const libelle = el("div", { class: "libelle", text: kpi.label, title: kpi.note || kpi.label });
  if (!r) return el("div", { class: "kpi" }, libelle, el("div", { class: "absent", text: "Donnée absente du MDP" }), el("div"));

  const valeurs = el("div", { class: "valeurs" });
  valeurs.append("ce projet ", el("b", { text: valeur(kpi, r.valeur) }));
  if (c.n) valeurs.append(`   référence ${valeur(kpi, c.combine)} (n = ${c.n})`);
  libelle.append(el("br"), valeurs);

  const ecart = el("div", { class: "ecart" });
  if (c.n) {
    const d = r.valeur - c.combine;
    const neutre = kpi.sens === 0 || Math.abs(d) < (kpi.unite === "%" ? 0.0005 : 0.005);
    const favorable = !neutre && Math.sign(d) === kpi.sens;
    const glyphe = neutre ? "" : favorable ? "▲ " : "▼ ";
    ecart.append(el("span", { class: neutre ? "" : favorable ? "favorable" : "defavorable",
      title: neutre ? "Écart à la référence" : favorable ? "Favorable" : "Défavorable", text: glyphe + ecartTexte(kpi, d) }));
    if (kpi.objet && !neutre) {
      const m2 = d * r.den;     // l'écart rapporté à la surface du projet : ce qu'il gagne ou perd face à la référence
      ecart.append(el("span", { class: "m2", text: `${signe(m2)}${F0.format(Math.abs(m2))} m² ${kpi.objet}` }));
    }
  }
  return el("div", { class: "kpi" }, libelle, regle(kpi, r.valeur, c, ref), ecart);
}

/** La règle graduée : pairs en points neutres, quartiles en aplat, référence en trait, projet étudié en accent. */
function regle(kpi, v, c, ref) {
  // En HTML positionné (pourcentages) plutôt qu'en SVG étiré : les points restent ronds à toutes les largeurs.
  const dom = domaine(kpi, v);
  const x = (t) => `${((t - dom[0]) / (dom[1] - dom[0])) * 100}%`;
  const r = el("div", { class: "regle", role: "img",
    "aria-label": `${kpi.label} : ${valeur(kpi, v)}` + (c.n ? `, référence ${valeur(kpi, c.combine)}` : "") });
  r.append(el("span", { class: "axe" }));
  r.append(el("span", { class: "graduation debut", text: valeur(kpi, Math.max(dom[0], 0)) }));
  r.append(el("span", { class: "graduation fin", text: valeur(kpi, dom[1]) }));
  const marque = (classe, t, title, extra = {}) => el("span", { class: classe, title, style: `left:${x(t)};${extra.style || ""}` });
  if (c.n) {
    r.append(marque("quartiles", c.q1, `Quartiles : ${valeur(kpi, c.q1)} à ${valeur(kpi, c.q3)}`,
      { style: `width:calc(${x(c.q3)} - ${x(c.q1)})` }));
    for (const { p, v: pv } of c.valeurs) r.append(marque("pair", pv, `${nomProjet(p)} : ${valeur(kpi, pv)}`));
    r.append(marque("reference" + (c.n < MIN_REFERENCE ? " fragile" : ""), c.combine,
      `Référence (ratio combiné de ${c.n} projet${c.n > 1 ? "s" : ""}) : ${valeur(kpi, c.combine)}` + (c.n < MIN_REFERENCE ? " · fragile" : "")));
  }
  r.append(marque("etudie", v, `${nomProjet(ref)} : ${valeur(kpi, v)}`));
  return r;
}

function syncFiltres() {
  document.getElementById("filtre-categorie").checked = etat.filtres.categorie;
  document.getElementById("filtre-intervention").checked = etat.filtres.intervention;
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
  const base = etat.data.base;
  const colonnes = [{ id: "nom", label: "Projet" }, { id: "canton", label: "Canton" }, ...etat.kpis.map((k) => ({ id: k.id, label: k.id, kpi: k }))];
  const cle = (p, col) => col.id === "nom" ? Number(p.id) || p.id : col.id === "canton" ? (p.infos.canton || "") : p.kpis[col.id]?.valeur ?? -Infinity;
  let lignes = [...etat.data.projets].sort((a, b) => b.fiable - a.fiable || String(a.id).localeCompare(String(b.id), "fr", { numeric: true }));
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

  const ensemble = el("tr", { class: "ensemble" }, el("td", { text: "Ensemble des projets fiables" }), el("td"),
    ...etat.kpis.map((k) => el("td", { title: base[k.id]?.n ? `n = ${base[k.id].n}` : "", text: base[k.id]?.n ? `${valeur(k, base[k.id].combine)} (${base[k.id].n})` : "—" })));

  const corps = lignes.map((p) => {
    const tr = el("tr", { class: p.fiable ? "" : "ecarte", tabindex: "0", title: p.fiable ? "Comparer ce projet" : "Écarté des références : comparer pour mémoire" },
      el("td", {}, el("span", { class: "mono", text: p.id }), ` ${p.nom}${p.fiable ? "" : " (écarté)"}`),
      el("td", { class: "mono", text: p.infos.canton || "—" }),
      ...etat.kpis.map((k) => celluleBase(k, p, base[k.id])));
    const ouvrir = () => { montrerVue("comparer"); choisirProjet(p.id); };
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
  const typos = etat.data.typologies || [];
  const boites = document.getElementById("boites");
  const titreTypo = document.getElementById("titre-typologies");
  if (!typos.length) {
    titreTypo.textContent = "SUP par logement selon le nombre de chambres";
    boites.replaceChildren(el("p", { class: "secondaire", text: "Aucun MDP fiable ne donne les chambres de ses logements." }));
    return;
  }
  const nLog = typos.reduce((s, t) => s + t.n, 0);
  const nProj = new Set(etat.data.projets.filter((p) => p.fiable && Object.keys(p.mix || {}).length).map((p) => p.id)).size;
  titreTypo.textContent = `SUP par logement selon le nombre de chambres (${nProj} projets, ${nLog} logements)`;

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

// ------------------------------------------------------------------ onglets et démarrage

const VUES = ["comparer", "base", "typologies"];

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
  for (const f of ["categorie", "intervention"])
    document.getElementById(`filtre-${f}`).addEventListener("change", (e) => { etat.filtres[f] = e.target.checked; choisirProjet(etat.projetId); });
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
  remplirProjets();
  remplirEcartes();
  dessinerBase();
  dessinerTypologies();
  montrerVue("comparer");
  const premier = data.projets.find((p) => p.fiable) || data.projets[0];
  choisirProjet(String(PARAMS.get("projet") || premier.id));
}

function charger() {
  if (PARAMS.get("theme")) document.documentElement.dataset.theme = PARAMS.get("theme");
  brancherOnglets();
  const hote = window.chrome && window.chrome.webview;
  if (hote) {   // dans SIA Check : l'application répond à « pret » par le contenu de benchmark.json
    hote.addEventListener("message", (e) => demarrer(typeof e.data === "string" ? JSON.parse(e.data) : e.data));
    hote.postMessage("pret");
    return;
  }
  fetch(PARAMS.get("data") || "benchmark.json", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(demarrer)
    .catch(() => afficherEtat("La base n'a pas encore été lue (benchmark.json introuvable)."));
}

charger();
