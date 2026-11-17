// Classeur Excel (.xlsx) écrit par la page, sans bibliothèque : l'export de Programmer (docs/V5_PLAN.md, partie 4)
// fonctionne dans SIA Check comme sur un serveur, sans réseau. SpreadsheetML (Office Open XML) : textes en ligne,
// nombres bruts avec un format d'affichage, styles décrits par cellule et mis en commun, archive ZIP sans compression.
"use strict";

/**
 * Le classeur en Blob.
 * feuilles : [{ nom, lignes, largeurs?, figer?, fusions?, filtre?, impression?, onglet? }]
 *   lignes     : [ligne…] ; ligne = [cellule…] ou { c: [cellule…], h: hauteur en points }
 *   cellule    : null, texte, nombre, ou { v, s } ; une cellule sans valeur mais stylée garde son fond et ses filets
 *   v          : texte, nombre, ou texte enrichi [{ t, gras?, italique?, taille?, couleur? }…]
 *   s (style)  : { gras, italique, taille, couleur, fond, format, h, v, retour, retrait, bordure }
 *                couleurs « RRGGBB » ; format = code Excel (« 0.0% ») ; h = left | center | right ; v = top | center | bottom ;
 *                bordure = { haut, bas, gauche, droite } : « RRGGBB » (filet fin) ou « style:RRGGBB » (medium, thick…)
 *   largeurs   : [largeur de colonne en caractères…]
 *   figer      : nombre de lignes figées, ou { lignes, colonnes }
 *   fusions    : [[l1, c1, l2, c2]…] et filtre : [l1, c1, l2, c2] (filtre automatique) — indices à partir de 0
 *   impression : { titres: [l1, l2] lignes répétées sur chaque page (indices à partir de 0), papier: 9 (A4) ou 8 (A3),
 *                  portrait?, pied? } — toujours ajustée à la largeur d'une page
 *   onglet     : couleur de l'onglet
 * options  : { police } — police de tout le classeur (Calibri par défaut ; Excel la remplace si le poste ne l'a pas)
 */
function classeurXlsx(feuilles, { police = "Calibri" } = {}) {
  const styles = tableStyles(police);
  const noms = feuilles.map((f) => nomFeuille(f.nom));
  const corps = feuilles.map((f) => feuilleXml(f, styles));     // avant styles.xml : les feuilles remplissent la table
  const fichiers = [
    ["[Content_Types].xml", xml(`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
${feuilles.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("\n")}
</Types>`)],
    ["_rels/.rels", xml(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`)],
    ["xl/workbook.xml", xml(`<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<bookViews><workbookView/></bookViews>
<sheets>${noms.map((n, i) => `<sheet name="${echapper(n)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("")}</sheets>${nomsDefinis(feuilles, noms)}
</workbook>`)],
    ["xl/_rels/workbook.xml.rels", xml(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
${feuilles.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("\n")}
<Relationship Id="rId${feuilles.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`)],
    ["xl/styles.xml", xml(styles.xml())],
    ...corps.map((c, i) => [`xl/worksheets/sheet${i + 1}.xml`, xml(c)]),
  ];
  return new Blob([zipSansCompression(fichiers)], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

const xml = (corps) => new TextEncoder().encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n${corps}`);
const echapper = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
  // caractères de contrôle interdits en XML 1.0 (hors tabulation et sauts de ligne)
  .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
/** Nom d'onglet Excel : 31 caractères au plus, sans : \ / ? * [ ]. */
const nomFeuille = (n) => String(n).replace(/[:\\/?*[\]]/g, " ").slice(0, 31);

/** Lettres de colonne : 0 → A, 26 → AA. */
function colonne(i) {
  let s = "";
  for (i += 1; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s;
  return s;
}
/** Plage « A1:C3 » d'indices à partir de 0 ; `abs` : références absolues ($A$1), pour les noms définis. */
function plage([l1, c1, l2, c2], abs = false) {
  const d = abs ? "$" : "";
  return `${d}${colonne(c1)}${d}${l1 + 1}:${d}${colonne(c2)}${d}${l2 + 1}`;
}

// ------------------------------------------------------------------ styles

const TAILLE = 10;

/** Police en XML : `balise` vaut « font » (styles.xml) ou « rPr » (texte enrichi, où le nom s'écrit rFont). */
function policeXml(p, balise, police) {
  return `<${balise}>${p.gras ? "<b/>" : ""}${p.italique ? "<i/>" : ""}<sz val="${p.taille || TAILLE}"/>`
    + `${p.couleur ? `<color rgb="FF${p.couleur}"/>` : ""}<${balise === "font" ? "name" : "rFont"} val="${echapper(police)}"/><family val="2"/></${balise}>`;
}

/** Table des styles du classeur : chaque style de cellule distinct reçoit un index (attribut s) ; ses polices, fonds,
 *  bordures et formats de nombre sont mis en commun. */
function tableStyles(police) {
  const registre = (...initial) => {
    const index = new Map(), items = [];
    const ajouter = (x) => { if (!index.has(x)) { index.set(x, items.length); items.push(x); } return index.get(x); };
    initial.forEach(ajouter);
    return { ajouter, items };
  };
  const fonts = registre(policeXml({}, "font", police));
  const fills = registre(`<fill><patternFill patternType="none"/></fill>`, `<fill><patternFill patternType="gray125"/></fill>`);   // imposés par Excel
  const borders = registre("<border><left/><right/><top/><bottom/><diagonal/></border>");
  const formats = registre();
  const xfs = registre(`<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>`);
  const connus = new Map();

  const cote = (nom, b) => {
    if (!b) return `<${nom}/>`;
    const [style, couleur] = b.includes(":") ? b.split(":") : ["thin", b];
    return `<${nom} style="${style}"><color rgb="FF${couleur}"/></${nom}>`;
  };
  function index(s) {
    const cle = JSON.stringify(s);
    if (connus.has(cle)) return connus.get(cle);
    const font = fonts.ajouter(policeXml(s, "font", police));
    const fill = s.fond ? fills.ajouter(`<fill><patternFill patternType="solid"><fgColor rgb="FF${s.fond}"/><bgColor indexed="64"/></patternFill></fill>`) : 0;
    const b = s.bordure;
    const border = b ? borders.ajouter(`<border>${cote("left", b.gauche)}${cote("right", b.droite)}${cote("top", b.haut)}${cote("bottom", b.bas)}<diagonal/></border>`) : 0;
    const fmt = s.format ? 164 + formats.ajouter(s.format) : 0;
    const aligne = [s.h && `horizontal="${s.h}"`, s.v && `vertical="${s.v}"`, s.retour && `wrapText="1"`, s.retrait && `indent="${s.retrait}"`].filter(Boolean);
    const xf = `<xf numFmtId="${fmt}" fontId="${font}" fillId="${fill}" borderId="${border}" xfId="0"`
      + `${fmt ? ` applyNumberFormat="1"` : ""}${font ? ` applyFont="1"` : ""}${fill ? ` applyFill="1"` : ""}${border ? ` applyBorder="1"` : ""}`
      + (aligne.length ? ` applyAlignment="1"><alignment ${aligne.join(" ")}/></xf>` : "/>");
    const i = xfs.ajouter(xf);
    connus.set(cle, i);
    return i;
  }
  const bloc = (nom, r) => `<${nom} count="${r.items.length}">${r.items.join("")}</${nom}>`;
  const xmlStyles = () => `<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">`
    + (formats.items.length ? `<numFmts count="${formats.items.length}">${formats.items.map((f, i) => `<numFmt numFmtId="${164 + i}" formatCode="${echapper(f)}"/>`).join("")}</numFmts>` : "")
    + bloc("fonts", fonts) + bloc("fills", fills) + bloc("borders", borders)
    + `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>` + bloc("cellXfs", xfs)
    + `<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;
  return { index, xml: xmlStyles, police };
}

// ------------------------------------------------------------------ feuilles

const texteXml = (t) => `<t xml:space="preserve">${echapper(t)}</t>`;

function celluleXml(c, ref, styles) {
  if (c == null || c === "") return "";
  const { v, s } = typeof c === "object" ? c : { v: c };
  const style = s ? ` s="${styles.index(s)}"` : "";
  if (Array.isArray(v)) {     // texte enrichi : chaque morceau porte sa police
    const morceaux = v.filter((m) => m && m.t != null && m.t !== "");
    if (morceaux.length) return `<c r="${ref}"${style} t="inlineStr"><is>${morceaux.map((m) => `<r>${policeXml(m, "rPr", styles.police)}${texteXml(m.t)}</r>`).join("")}</is></c>`;
  } else if (typeof v === "number" && Number.isFinite(v)) return `<c r="${ref}"${style}><v>${v}</v></c>`;
  else if (typeof v === "string" && v !== "") return `<c r="${ref}"${style} t="inlineStr"><is>${texteXml(v)}</is></c>`;
  return style ? `<c r="${ref}"${style}/>` : "";
}

function feuilleXml(f, styles) {
  const lignes = f.lignes.map((ligne, r) => {
    const { c, h } = Array.isArray(ligne) ? { c: ligne } : ligne;
    const cellules = c.map((x, k) => celluleXml(x, `${colonne(k)}${r + 1}`, styles)).join("");
    return `<row r="${r + 1}"${h ? ` ht="${h}" customHeight="1"` : ""}>${cellules}</row>`;
  }).join("");
  const imp = f.impression;
  const proprietes = f.onglet || imp ? `<sheetPr>${f.onglet ? `<tabColor rgb="FF${f.onglet}"/>` : ""}${imp ? `<pageSetUpPr fitToPage="1"/>` : ""}</sheetPr>` : "";
  const fl = typeof f.figer === "number" ? f.figer : f.figer?.lignes || 0, fc = f.figer?.colonnes || 0;
  const volet = fl || fc ? `<pane${fc ? ` xSplit="${fc}"` : ""}${fl ? ` ySplit="${fl}"` : ""} topLeftCell="${colonne(fc)}${fl + 1}" `
    + `activePane="${fl && fc ? "bottomRight" : fl ? "bottomLeft" : "topRight"}" state="frozen"/>` : "";
  const vue = `<sheetViews><sheetView showGridLines="0" workbookViewId="0">${volet}</sheetView></sheetViews>`;     // sans quadrillage : les filets suffisent
  const largeurs = f.largeurs?.length ? `<cols>${f.largeurs.map((l, i) => `<col min="${i + 1}" max="${i + 1}" width="${l}" customWidth="1"/>`).join("")}</cols>` : "";
  const filtre = f.filtre ? `<autoFilter ref="${plage(f.filtre)}"/>` : "";
  const fusions = f.fusions?.length ? `<mergeCells count="${f.fusions.length}">${f.fusions.map((m) => `<mergeCell ref="${plage(m)}"/>`).join("")}</mergeCells>` : "";
  // impression : paysage, ajustée à la largeur d'une page, autant de pages que nécessaire en hauteur
  const page = imp ? `<printOptions horizontalCentered="1"/><pageMargins left="0.4" right="0.4" top="0.45" bottom="0.6" header="0.3" footer="0.3"/>`
    + `<pageSetup paperSize="${imp.papier || 9}" orientation="${imp.portrait ? "portrait" : "landscape"}" fitToWidth="1" fitToHeight="0"/>`
    + `<headerFooter><oddFooter>${echapper(`&L&"${styles.police},Regular"&8${imp.pied || ""}&C&"${styles.police},Regular"&8&A&R&"${styles.police},Regular"&8Page &P / &N`)}</oddFooter></headerFooter>` : "";
  // l'ordre des éléments est imposé par le schéma
  return `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">${proprietes}${vue}<sheetFormatPr defaultRowHeight="13.5"/>${largeurs}`
    + `<sheetData>${lignes}</sheetData>${filtre}${fusions}${page}</worksheet>`;
}

/** Noms définis du classeur : plage du filtre automatique et lignes de titre répétées à l'impression. */
function nomsDefinis(feuilles, noms) {
  const cite = (n) => `'${echapper(n.replace(/'/g, "''"))}'`;
  const defs = feuilles.flatMap((f, i) => [
    f.filtre && `<definedName name="_xlnm._FilterDatabase" localSheetId="${i}" hidden="1">${cite(noms[i])}!${plage(f.filtre, true)}</definedName>`,
    f.impression?.titres && `<definedName name="_xlnm.Print_Titles" localSheetId="${i}">${cite(noms[i])}!$${f.impression.titres[0] + 1}:$${f.impression.titres[1] + 1}</definedName>`,
  ]).filter(Boolean);
  return defs.length ? `\n<definedNames>${defs.join("")}</definedNames>` : "";
}

// ------------------------------------------------------------------ ZIP (méthode 0, sans compression)

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
function crc32(octets) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < octets.length; i++) c = CRC_TABLE[(c ^ octets[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

function zipSansCompression(fichiers) {
  const enc = new TextEncoder(), parts = [], central = [];
  let decalage = 0;
  for (const [nom, donnees] of fichiers) {
    const n = enc.encode(nom), crc = crc32(donnees);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034B50, true); local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);   // UTF-8
    local.setUint16(8, 0, true); local.setUint32(14, crc, true);
    local.setUint32(18, donnees.length, true); local.setUint32(22, donnees.length, true); local.setUint16(26, n.length, true);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014B50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true);
    c.setUint32(16, crc, true); c.setUint32(20, donnees.length, true); c.setUint32(24, donnees.length, true);
    c.setUint16(28, n.length, true); c.setUint32(42, decalage, true);
    parts.push(new Uint8Array(local.buffer), n, donnees);
    central.push(new Uint8Array(c.buffer), n);
    decalage += 30 + n.length + donnees.length;
  }
  const tailleCentral = central.reduce((s, p) => s + p.length, 0);
  const fin = new DataView(new ArrayBuffer(22));
  fin.setUint32(0, 0x06054B50, true); fin.setUint16(8, fichiers.length, true); fin.setUint16(10, fichiers.length, true);
  fin.setUint32(12, tailleCentral, true); fin.setUint32(16, decalage, true);
  return new Blob([...parts, ...central, new Uint8Array(fin.buffer)]);
}
