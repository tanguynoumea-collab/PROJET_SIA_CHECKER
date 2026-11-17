// Visionneuse 3D des maquettes de la base (docs/V5_PLAN.md, partie 2), chargée à la première ouverture.
// Lit une maquette MAQ-<id>.json.gz écrite par SIA Check (Services/WebModel.cs) et la montre comme la visionneuse de
// l'application : une couleur par catégorie SIA, la SP en dalle plus sombre sous les pièces, les contours de chaque
// surface, calques, bâtiments, niveau, éclatement. three.js est livré dans vendor/ : aucun accès réseau.
import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";

const SP_DESCENTE = 0.04;   // m : dessus de la SP sous celui des pièces (joints visibles), comme SceneController
const SP_TEINTE = 0.72;     // SP plus foncée que sa couleur de légende
const CONTOUR_TEINTE = 0.58;
const EXTERNE_GARDE = 0.45; // surfaces externes ou non contrôlées : part de la couleur gardée (reste = blanc)
const GROUPES = ["Intérieur", "Extérieur", "Enveloppe", "USPI · Maison", "Codes inconnus"];
const TOUS = "";

let v = null;   // la visionneuse : renderer, scène, caméra, contrôles (créés une fois, réutilisés d'une maquette à l'autre)
let m = null;   // la maquette affichée et son état (calques, bâtiments, niveau, éclatement)
let jeton = 0;  // ouverture en cours : une ouverture plus récente annule le chargement d'une plus ancienne

/** Lit une maquette : JSON compressé en gzip (ou déjà décompressé par le serveur). */
async function lire(url) {
  let r;
  try {
    r = await fetch(url, { cache: "no-store" });
  } catch {
    throw new Error("fichier de la maquette inaccessible (dossier de la base hors d'atteinte, ou maquette non servie)");
  }
  if (!r.ok) throw new Error(r.status === 404 ? "maquette introuvable dans la base" : `erreur ${r.status}`);
  const brut = new Uint8Array(await r.arrayBuffer());
  const gzip = brut[0] === 0x1f && brut[1] === 0x8b;
  const texte = gzip ? await new Response(new Blob([brut]).stream().pipeThrough(new DecompressionStream("gzip"))).text()
                     : new TextDecoder().decode(brut);
  const d = JSON.parse(texte);
  if (d.format !== "sia-check-maquette" || d.version !== 1) throw new Error("format de maquette inconnu");
  return d;
}

const teinte = (c, f) => new THREE.Color(c).multiplyScalar(f);
const pale = (c, garde) => new THREE.Color(c).lerp(new THREE.Color(1, 1, 1), 1 - garde);

function initialiser(conteneur) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.domElement.className = "v3-canvas";
  conteneur.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  scene.add(new THREE.AmbientLight(0xffffff, 1.9));
  const soleil = new THREE.DirectionalLight(0xffffff, 1.4);
  soleil.position.set(0.6, -1, 1.6);
  scene.add(soleil);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
  camera.up.set(0, 0, 1);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.screenSpacePanning = true;
  controls.enableZoom = false;
  const dessiner = () => renderer.render(scene, camera);
  controls.addEventListener("change", dessiner);
  new ResizeObserver(() => {
    const w = conteneur.clientWidth, h = conteneur.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    dessiner();
  }).observe(conteneur);

  // Molette : elle fait défiler la page, sauf après un clic dans la vue (jusqu'à ce que la souris en sorte) ou avec Ctrl
  let actif = false;
  const aide = conteneur.querySelector(".v3-aide");
  const marquer = () => { conteneur.classList.toggle("actif", actif); };
  renderer.domElement.addEventListener("pointerdown", () => { actif = true; controls.enableZoom = true; marquer(); });
  renderer.domElement.addEventListener("pointerleave", () => { actif = false; controls.enableZoom = false; marquer(); });
  conteneur.addEventListener("wheel", (e) => { controls.enableZoom = actif || e.ctrlKey; }, { capture: true, passive: true });
  if (aide) aide.textContent = "Clic dans la vue, puis molette pour zoomer (ou Ctrl + molette) · clic droit : déplacer";

  // Sélection d'une surface au clic (sans glisser) : sa fiche en bas à gauche
  const rayon = new THREE.Raycaster();
  let depart = null;
  renderer.domElement.addEventListener("pointerdown", (e) => { depart = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", (e) => {
    if (!depart || Math.hypot(e.clientX - depart[0], e.clientY - depart[1]) > 4 || e.button !== 0) return;
    const r = renderer.domElement.getBoundingClientRect();
    rayon.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
    const visibles = m ? m.meshes.filter((x) => x.visible && x.parent.visible) : [];
    const touche = rayon.intersectObjects(visibles, false)[0];
    choisir(touche ? surfaceDe(touche.object.userData.lot, touche.faceIndex) : null);
  });
  v = { renderer, scene, camera, controls, dessiner, conteneur };
}

/** Indice de la surface d'un triangle d'un lot (table « t » : premier triangle de chaque surface, croissante). */
function surfaceDe(lot, triangle) {
  let lo = 0, hi = lot.t.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (lot.t[mid] <= triangle) lo = mid; else hi = mid - 1; }
  return lot.s[lo];
}

function choisir(indice) {
  const info = v.conteneur.querySelector(".v3-info");
  if (indice == null || !m) { info.hidden = true; return; }
  const s = m.d.surfaces[indice], cat = m.cats.get(s.code);
  const m2 = s.m2 != null ? `${new Intl.NumberFormat("fr-CH", { maximumFractionDigits: 1 }).format(s.m2)} m²` : "";
  info.replaceChildren(...[
    ["b", cat?.titre || s.code], ["span", [s.nom, s.lot ? `lot ${s.lot}` : ""].filter(Boolean).join(" · ")],
    ["span", `${s.b} · ${s.l}${m2 ? " · " + m2 : ""}`]].filter(([, t]) => t).map(([tag, t]) => {
      const e = document.createElement(tag); e.textContent = t; return e;
    }));
  info.hidden = false;
}

/** Contours d'une surface : les arêtes qui n'appartiennent qu'à un de ses triangles. */
function contours(pos, idx, de, a, sortie) {
  const vues = new Map();
  for (let t = de; t < a; t++)
    for (let k = 0; k < 3; k++) {
      const p = idx[3 * t + k], q = idx[3 * t + ((k + 1) % 3)];
      const cle = p < q ? `${p},${q}` : `${q},${p}`;
      vues.set(cle, (vues.get(cle) || 0) + 1);
    }
  for (const [cle, n] of vues) {
    if (n !== 1) continue;
    const [p, q] = cle.split(",").map(Number);
    sortie.push(pos[3 * p], pos[3 * p + 1], pos[3 * p + 2], pos[3 * q], pos[3 * q + 1], pos[3 * q + 2]);
  }
}

function vider() {
  if (!m) return;
  for (const g of m.niveaux.values()) {
    v.scene.remove(g.groupe);
    g.groupe.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
  }
  m = null;
}

function construire(d) {
  const u = d.unite || 0.01;
  const cats = new Map(d.categories.map((c) => [c.code, c]));
  const niveaux = new Map(), meshes = [];
  const rangs = new Map(d.niveaux.map((n) => [`${n.b}|${n.l}`, n.rang]));
  // ordre des niveaux par bâtiment : l'éclatement les écarte d'autant
  for (const b of new Set(d.niveaux.map((n) => n.b)))
    d.niveaux.filter((n) => n.b === b).sort((x, y) => x.rang - y.rang)
      .forEach((n, k) => niveaux.set(`${n.b}|${n.l}`, { b: n.b, l: n.l, ordre: k, groupe: new THREE.Group() }));
  for (const lot of d.lots) {
    const cle = `${lot.b}|${lot.l}`;
    if (!niveaux.has(cle)) niveaux.set(cle, { b: lot.b, l: lot.l, ordre: 0, groupe: new THREE.Group() });
    const cat = cats.get(lot.code) || { couleur: "#6B7280", hachure: true };
    const sp = lot.code === "SP" || lot.code === "SEP";
    const pos = new Float32Array(lot.v.length);
    for (let k = 0; k < lot.v.length; k += 3) {
      pos[k] = lot.v[k] * u; pos[k + 1] = lot.v[k + 1] * u; pos[k + 2] = lot.v[k + 2] * u - (sp ? SP_DESCENTE : 0);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setIndex(lot.i);
    geo.computeVertexNormals();
    const couleur = sp ? teinte(cat.couleur, SP_TEINTE) : cat.hachure ? pale(cat.couleur, EXTERNE_GARDE) : new THREE.Color(cat.couleur);
    const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color: couleur, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: sp ? 2 : 1, polygonOffsetUnits: sp ? 2 : 1 }));
    mesh.userData = { lot, code: lot.code };
    const traits = [];
    const nTri = lot.i.length / 3;
    lot.t.forEach((de, k) => contours(pos, lot.i, de, k + 1 < lot.t.length ? lot.t[k + 1] : nTri, traits));
    const lignes = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(traits, 3)),
      new THREE.LineBasicMaterial({ color: teinte(cat.couleur, CONTOUR_TEINTE) }));
    lignes.userData = { code: lot.code };
    const n = niveaux.get(cle);
    n.groupe.add(mesh, lignes);
    meshes.push(mesh);
  }
  for (const n of niveaux.values()) v.scene.add(n.groupe);
  const boite = new THREE.Box3();
  for (const x of meshes) { x.geometry.computeBoundingBox(); boite.union(x.geometry.boundingBox); }
  const batiments = [...new Set(d.niveaux.map((n) => n.b))].sort();
  const nomsNiveaux = [...new Set(d.niveaux.slice().sort((x, y) => x.rang - y.rang).map((n) => n.l))];
  return { d, cats, niveaux, meshes, boite, rangs,
           visibles: new Set(d.categories.filter((c) => c.visible).map((c) => c.code)),
           batiments: new Set(batiments), listeBatiments: batiments, nomsNiveaux, niveau: TOUS, eclatement: 0 };
}

function appliquer() {
  if (!m) return;
  for (const n of m.niveaux.values()) {
    n.groupe.visible = m.batiments.has(n.b) && (m.niveau === TOUS || n.l === m.niveau);
    n.groupe.position.z = n.ordre * m.eclatement;
    for (const o of n.groupe.children) o.visible = m.visibles.has(o.userData.code);
  }
  v.dessiner();
}

/** Cadre la maquette : vue de dessus ou vue 3D en plongée depuis le sud-est. */
export function cadrer(vue = "3d") {
  if (!m) return;
  // ce qui est montré, éclatement compris ; rien de visible : toute la maquette
  const boite = new THREE.Box3();
  for (const n of m.niveaux.values()) if (n.groupe.visible) boite.expandByObject(n.groupe);
  if (boite.isEmpty()) boite.copy(m.boite);
  if (boite.isEmpty()) return;
  const centre = boite.getCenter(new THREE.Vector3()), taille = boite.getSize(new THREE.Vector3());
  const r = Math.max(taille.x, taille.y, taille.z, 10) * 0.7;
  const d = r / Math.tan((v.camera.fov * Math.PI) / 360);
  const dir = vue === "dessus" ? new THREE.Vector3(0, -0.001, 1) : new THREE.Vector3(0.55, -0.85, 0.75);
  v.camera.position.copy(centre).addScaledVector(dir.normalize(), d);
  v.camera.near = Math.max(0.05, d / 500); v.camera.far = d * 10;
  v.camera.updateProjectionMatrix();
  v.controls.target.copy(centre);
  v.controls.update();
  v.dessiner();
}

/** Panneau de droite : calques par groupe, bâtiments, niveau, éclatement (comme l'onglet Calques de l'application). */
function panneau(racine) {
  const el = (tag, attrs = {}, ...enfants) => {
    const e = document.createElement(tag);
    for (const [k, val] of Object.entries(attrs)) k === "text" ? (e.textContent = val) : k === "class" ? (e.className = val) : e.setAttribute(k, val);
    e.append(...enfants.filter((x) => x != null));
    return e;
  };
  const f = new Intl.NumberFormat("fr-CH", { maximumFractionDigits: 0 });
  const blocs = [];
  for (const g of [...GROUPES, ...new Set(m.d.categories.map((c) => c.groupe).filter((x) => !GROUPES.includes(x)))]) {
    const cats = m.d.categories.filter((c) => c.groupe === g);
    if (!cats.length) continue;
    blocs.push(el("h3", { text: g }), el("ul", { class: "v3-calques" }, ...cats.map((c) => {
      const cb = el("input", { type: "checkbox", "aria-label": c.titre });
      cb.checked = m.visibles.has(c.code);
      cb.addEventListener("change", () => { cb.checked ? m.visibles.add(c.code) : m.visibles.delete(c.code); appliquer(); });
      const pastille = el("i", { class: `v3-pastille${c.hachure ? " hachure" : ""}`, style: `--c:${c.couleur}` });
      return el("li", {}, el("label", { title: c.definition ? `${c.titre}\n${c.definition}` : c.titre }, cb, pastille,
        el("span", { class: "mono", text: c.code }), el("span", { class: "secondaire", text: `${f.format(c.m2)} m²` })));
    })));
  }
  if (m.listeBatiments.length > 1) {
    blocs.push(el("h3", { text: "Bâtiments" }), el("div", { class: "v3-puces" }, ...m.listeBatiments.map((b) => {
      const cb = el("input", { type: "checkbox", "aria-label": `Bâtiment ${b}` });
      cb.checked = m.batiments.has(b);
      cb.addEventListener("change", () => { cb.checked ? m.batiments.add(b) : m.batiments.delete(b); appliquer(); });
      return el("label", { class: "v3-puce" }, cb, el("span", { class: "mono", text: b }));
    })));
  }
  const niveau = el("select", { "aria-label": "Niveau affiché" }, el("option", { value: TOUS, text: "Tous les niveaux" }),
    ...m.nomsNiveaux.map((l) => el("option", { value: l, text: l })));
  niveau.value = m.niveau;
  niveau.addEventListener("change", () => { m.niveau = niveau.value; appliquer(); });
  const eclat = el("input", { type: "range", min: "0", max: "12", step: "0.5", "aria-label": "Éclatement des niveaux" });
  eclat.value = String(m.eclatement);
  eclat.addEventListener("input", () => { m.eclatement = Number(eclat.value); appliquer(); });
  blocs.push(el("h3", { text: "Niveaux" }), el("div", { class: "v3-niveaux" }, niveau,
    el("label", { class: "v3-eclat", title: "Écarte les niveaux les uns des autres" }, el("span", { class: "secondaire", text: "Éclater" }), eclat)));
  racine.replaceChildren(...blocs);
}

/**
 * Montre une maquette dans `conteneur` (la zone de la scène) ; `calques` reçoit le panneau des calques.
 * Rend une promesse résolue quand la maquette est affichée, rejetée si elle ne peut pas l'être.
 */
export async function afficher(url, conteneur, calques) {
  if (!v || v.conteneur !== conteneur) initialiser(conteneur);
  const moi = ++jeton;
  const d = await lire(url);
  if (moi !== jeton) return false;      // une autre maquette a été demandée entre-temps
  vider();
  choisir(null);
  m = construire(d);
  panneau(calques);
  appliquer();
  cadrer("3d");
  return true;
}

/** Libère la maquette affichée (fermeture de la vue). */
export function fermer() {
  jeton++;
  if (v) { vider(); v.dessiner(); }
}
