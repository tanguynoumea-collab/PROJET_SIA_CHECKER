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
const MIEN = "mien";

const etat = { data: null, projets: new Map(), kpis: [], projetId: null, coches: new Set(), filtres: { categorie: true, intervention: true }, tri: null,
                mien: null, mienSource: "saisie", prix: null, groupeCle: "" };

/** Un projet de la base, ou « Mon projet » (id « mien »). */
const projet = (id) => (id === MIEN ? etat.mien : etat.projets.get(id));

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
  sel.replaceChildren();
  const fiables = etat.data.projets.filter((p) => p.fiable), ecartes = etat.data.projets.filter((p) => !p.fiable);
  const groupe = (label, liste) => {
    const g = el("optgroup", { label });
    for (const p of liste) g.append(el("option", { value: p.id, text: nomProjet(p) }));
    return g;
  };
  const mien = el("optgroup", { label: "Mon projet" }, el("option", { value: MIEN, id: "option-mien", text: "★ Mon projet" }));
  sel.append(mien, groupe("Fiables", fiables), groupe("Écartés (données incohérentes)", ecartes));
  sel.addEventListener("change", () => choisirProjet(sel.value));
}

function choisirProjet(id) {
  etat.projetId = id;
  document.getElementById("projet").value = id;
  const ref = projet(id);
  etat.coches = new Set(candidats(ref).map((c) => c.p.id));
  etat.groupeCle = candidats(ref).map((c) => c.p.id).join();
  document.getElementById("saisie").hidden = id !== MIEN;
  dessinerComparer();
}

function dessinerComparer() {
  const ref = projet(etat.projetId);
  const liste = candidats(ref);
  const groupe = liste.filter((c) => etat.coches.has(c.p.id)).map((c) => c.p);

  const bandeau = document.getElementById("bandeau-projet");
  bandeau.hidden = ref.fiable || ref.id === MIEN;
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
    const comparable = Object.keys(ref.distances || {}).length > 0;
    const filtre = comparable && (etat.filtres.categorie || etat.filtres.intervention);
    aucun.replaceChildren(filtre ? "Aucun projet ne passe ces filtres."
      : ref.id === MIEN ? "Saisissez au moins la SP hors-sol et le nombre de logements pour trouver des projets similaires."
      : "Aucun projet comparable : il manque au projet des caractéristiques (SP hors-sol, logements…).");
    if (filtre) {
      const b = el("button", { class: "lien", type: "button", text: "Retirer les filtres" });
      b.addEventListener("click", () => { etat.filtres.categorie = etat.filtres.intervention = false; syncFiltres(); choisirProjet(ref.id); });
      aucun.append(" ", b);
    }
  }

  document.getElementById("resume-reference").textContent = groupe.length
    ? `Référence : ${groupe.length} projet${groupe.length > 1 ? "s" : ""} similaire${groupe.length > 1 ? "s" : ""} · ratios combinés` +
      (groupe.length < MIN_REFERENCE ? " · référence fragile" : "")
    : liste.length ? "Aucune référence : cochez au moins un projet similaire." : "Aucune référence : aucun projet similaire.";

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
  if (!r) return el("div", { class: "kpi" }, libelle, el("div", { class: "absent", text: ref.id === MIEN && etat.mienSource === "saisie" ? "Non saisi" : "Donnée absente du MDP" }), el("div"));

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
      // CHF : seulement pour les m² vendables (Rendement), au prix de vente saisi ; les pertes restent en m²
      if (CHF_KPIS.has(kpi.id) && etat.prix > 0) {
        const chf = Math.round((m2 * etat.prix) / 1000) * 1000;
        ecart.append(el("span", { class: "chf", title: `${F0.format(Math.abs(m2))} m² × ${F0.format(etat.prix)} CHF/m²`,
          text: `≈ ${signe(chf)}${F0.format(Math.abs(chf))} CHF` }));
      }
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

// ------------------------------------------------------------------ Mon projet (saisie ou SIA Check)

const SURFACES = [["SP_HS", "SP hors-sol"], ["SP_SS", "SP sous-sol"], ["SUP_HS", "SUP hors-sol"], ["SD_HS", "SD hors-sol"],
                  ["SI", "SI"], ["SUS_HS", "SUS hors-sol"], ["SVN", "SVN"], ["FACADE", "Façade"], ["VB", "VB (m³)"]];
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
  b.textContent = replie ? "Déplier" : "Replier";
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
  document.getElementById("option-mien").textContent = `★ Mon projet : ${etat.mien.nom}` + (etat.mienSource === "siacheck" ? " (SIA Check)" : "");
  if (etat.projetId === MIEN) {
    const liste = candidats(etat.mien).map((c) => c.p.id);
    if (liste.join() !== etat.groupeCle) { etat.groupeCle = liste.join(); etat.coches = new Set(liste); }
    dessinerComparer();
  }
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
  document.getElementById("saisie-effacer").textContent = oui ? "Revenir à une saisie" : "Effacer la saisie";
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
  montrerVue("comparer");
  choisirProjet(MIEN);
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
  initSaisie();
  const ecart = verifierDistances();
  if (ecart > 0.002) console.warn(`Distances de la page et du moteur différentes (écart max ${ecart}) : formules à réaligner.`);
  dessinerBase();
  dessinerTypologies();
  montrerVue("comparer");
  const premier = data.projets.find((p) => p.fiable) || data.projets[0];
  const demande = PARAMS.get("projet");
  choisirProjet(demande === MIEN || etat.projets.has(demande) ? demande : String(premier.id));
}

function charger() {
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
    .then(demarrer)
    .catch(() => afficherEtat("La base n'a pas encore été lue (benchmark.json introuvable)."));
}

charger();
