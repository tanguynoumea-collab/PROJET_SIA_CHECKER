"""Remplissage des tableaux Excel d'un classeur gabarit, sans toucher au reste du classeur.

openpyxl réécrit tout le classeur et perd ce qu'il ne connaît pas : validations de données au format
Excel 2010 (`x14:dataValidation`, les listes déroulantes du MDP), tableaux croisés, parties SharePoint.
Ce module travaille donc directement dans le paquet zip : seules les feuilles et les tableaux remplis
sont réécrits, et dans ces feuilles seules les cellules des colonnes du tableau ; tout le reste est
recopié octet pour octet.

Pour un tableau rempli :
- les lignes de données sont remplacées (la ligne de totaux suit la dernière ligne) ;
- chaque cellule reprend le style de la première ligne de données du gabarit ;
- une colonne calculée reçoit sa formule (`calculatedColumnFormula`), avec la valeur en cache si elle
  est fournie ; une formule de colonne cassée (`#REF!`) est retirée du tableau ;
- les filtres actifs sont levés et les lignes masquées par eux réaffichées.

Les formules sont recalculées à l'ouverture (`fullCalcOnLoad`) et la chaîne de calcul est supprimée
(Excel la reconstruit).
"""

from __future__ import annotations

import math
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
ROW_RE = re.compile(r'<row\b([^>]*?)(?:/>|>(.*?)</row>)', re.S)
CELL_RE = re.compile(r'<c\b[^>]*?\br="([A-Z]+)(\d+)"[^>]*?(?:/>|>.*?</c>)', re.S)
ATTR_RE = re.compile(r'\s([\w:]+)="([^"]*)"')
SHEETDATA_RE = re.compile(r'<sheetData\s*/>|<sheetData>(.*?)</sheetData>', re.S)
CALC_CHAIN = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/calcChain"


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class Formula:
    """Formule à écrire telle quelle, avec sa valeur en cache facultative."""
    text: str
    cached: object = None


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def col_letters(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _split_ref(ref: str) -> tuple[int, int, int, int]:
    m = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", ref)
    if not m:
        raise TemplateError(f"plage de tableau illisible : {ref}")
    return col_index(m[1]), int(m[2]), col_index(m[3]), int(m[4])


@dataclass
class Table:
    name: str
    part: str            # chemin du tableau dans le zip
    sheet_part: str      # chemin de la feuille
    columns: list[str]
    formulas: dict[str, str]   # colonne -> formule de colonne calculée (valide)
    first_col: int
    header_row: int
    last_row: int
    totals: int


@dataclass
class Row:
    attrs: str
    cells: dict[int, str] = field(default_factory=dict)   # colonne -> XML de la cellule


def _attrs(s: str) -> dict[str, str]:
    return dict(ATTR_RE.findall(" " + s))


def _cell_style(xml: str) -> str | None:
    m = re.match(r'<c\b[^>]*?\ss="(\d+)"', xml)
    return m[1] if m else None


def _value_xml(ref: str, value, style: str | None) -> str | None:
    s = f' s="{style}"' if style else ""
    if isinstance(value, Formula):
        f = f"<f>{escape(value.text)}</f>"
        c = value.cached
        if isinstance(c, bool) or c is None or (isinstance(c, float) and math.isnan(c)):
            return f'<c r="{ref}"{s}>{f}</c>'
        if isinstance(c, (int, float)):
            return f'<c r="{ref}"{s}>{f}<v>{c!r}</v></c>'
        return f'<c r="{ref}"{s} t="str">{f}<v>{escape(str(c))}</v></c>'
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return f'<c r="{ref}"{s}/>' if style else None
    if isinstance(value, bool):
        return f'<c r="{ref}"{s} t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s}><v>{value!r}</v></c>'
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'


def _num(v) -> int | float:
    """Entier si la valeur l'est (les `numpy` deviennent des nombres Python)."""
    f = float(v)
    return int(f) if f.is_integer() and abs(f) < 2**53 else f


def _plain(value):
    if isinstance(value, Formula):
        return Formula(value.text, None if value.cached is None else _plain(value.cached))
    if value is None or isinstance(value, (str, bool)):
        return value
    try:
        return _num(value)
    except (TypeError, ValueError):
        return str(value)


class Workbook:
    """Classeur gabarit chargé en mémoire ; `fill_table` puis `save`."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as z:
            self.infos = z.infolist()
            self.parts = {i.filename: z.read(i.filename) for i in self.infos}
        self._strings = self._shared_strings()
        self.sheets = self._sheets()                 # nom -> chemin de la feuille
        self.tables = self._tables()                 # nom -> Table
        self._rows: dict[str, dict[int, Row]] = {}   # feuilles modifiées, analysées
        self._dirty_tables: dict[str, str] = {}

    # ------------------------------------------------------------------ lecture du paquet

    def _xml(self, part: str) -> ET.Element:
        return ET.fromstring(self.parts[part])

    def _rels(self, part: str) -> dict[str, tuple[str, str]]:
        d, f = posixpath.split(part)
        rels = posixpath.join(d, "_rels", f + ".rels")
        if rels not in self.parts:
            return {}
        out = {}
        for r in self._xml(rels).findall("pr:Relationship", NS):
            target = r.get("Target")
            # Cible absolue (« /xl/worksheets/sheet1.xml », classeurs écrits par openpyxl) : depuis la racine du paquet
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(d, target))
            out[r.get("Id")] = (r.get("Type"), path)
        return out

    def _shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self.parts:
            return []
        return ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
                for si in self._xml("xl/sharedStrings.xml").findall("m:si", NS)]

    def _sheets(self) -> dict[str, str]:
        rels = self._rels("xl/workbook.xml")
        return {s.get("name"): rels[s.get(f"{{{NS['r']}}}id")][1]
                for s in self._xml("xl/workbook.xml").find("m:sheets", NS)}

    def _tables(self) -> dict[str, Table]:
        out = {}
        for sheet_part in self.sheets.values():
            for typ, target in self._rels(sheet_part).values():
                if not typ.endswith("/table"):
                    continue
                t = self._xml(target)
                c0, r0, _, r1 = _split_ref(t.get("ref"))
                cols, formulas = [], {}
                for tc in t.find("m:tableColumns", NS):
                    cols.append(tc.get("name"))
                    f = tc.find("m:calculatedColumnFormula", NS)
                    if f is not None and f.text and "#REF!" not in f.text:
                        formulas[tc.get("name")] = f.text
                out[t.get("name")] = Table(t.get("name"), target, sheet_part, cols, formulas, c0,
                                           r0 + int(t.get("headerRowCount", "1")) - 1, r1,
                                           int(t.get("totalsRowCount", "0")))
        return out

    def _sheet_rows(self, sheet_part: str) -> dict[int, Row]:
        if sheet_part not in self._rows:
            text = self.parts[sheet_part].decode("utf-8")
            m = SHEETDATA_RE.search(text)
            rows = {}
            for rm in ROW_RE.finditer(m[1] or "" if m else ""):
                attrs = rm[1]
                n = int(_attrs(attrs)["r"])
                rows[n] = Row(attrs, {col_index(cm[1]): cm[0] for cm in CELL_RE.finditer(rm[2] or "")})
            self._rows[sheet_part] = rows
        return self._rows[sheet_part]

    # ------------------------------------------------------------------ lecture des cellules

    def cell_value(self, sheet: str, ref: str):
        """Valeur affichée d'une cellule (texte partagé résolu), None si vide."""
        m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
        row = self._sheet_rows(self.sheets[sheet]).get(int(m[2]))
        xml = row.cells.get(col_index(m[1])) if row else None
        if xml is None:
            return None
        t = re.match(r'<c\b[^>]*?\st="(\w+)"', xml)
        v = re.search(r"<v>(.*?)</v>", xml, re.S)
        if t and t[1] == "inlineStr":
            return "".join(re.findall(r"<t[^>]*>(.*?)</t>", xml, re.S))
        if v is None:
            return None
        if t and t[1] == "s":
            return self._strings[int(v[1])]
        if t and t[1] in ("str", "e"):
            return v[1]
        try:
            return _num(v[1])
        except ValueError:
            return v[1]

    def table_rows(self, name: str) -> list[dict]:
        """Lignes de données d'un tableau, valeurs affichées."""
        t = self.tables[name]
        sheet = next(k for k, v in self.sheets.items() if v == t.sheet_part)
        return [{c: self.cell_value(sheet, f"{col_letters(t.first_col + i)}{r}") for i, c in enumerate(t.columns)}
                for r in range(t.header_row + 1, t.last_row - t.totals + 1)]

    # ------------------------------------------------------------------ écriture

    def set_cell(self, sheet: str, ref: str, value) -> None:
        """Écrit une cellule existante ou nouvelle, en gardant son style."""
        m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
        rows = self._sheet_rows(self.sheets[sheet])
        row = rows.setdefault(int(m[2]), Row(f' r="{m[2]}"'))
        col = col_index(m[1])
        old = row.cells.get(col)
        xml = _value_xml(ref, _plain(value), _cell_style(old) if old else None)
        if xml is None:
            row.cells.pop(col, None)
        else:
            row.cells[col] = xml

    def fill_table(self, name: str, records: list[dict]) -> None:
        """Remplace les lignes de données du tableau `name` par `records` (clé = en-tête de colonne).

        Une colonne absente d'un enregistrement reçoit la formule de colonne calculée, s'il y en a une.
        """
        if name not in self.tables:
            raise TemplateError(f"tableau « {name} » absent du gabarit")
        t = self.tables[name]
        unknown = {k for r in records for k in r} - set(t.columns)
        if unknown:
            raise TemplateError(f"tableau {name} : colonnes inconnues {sorted(unknown)}")
        rows = self._sheet_rows(t.sheet_part)
        cols = range(t.first_col, t.first_col + len(t.columns))
        first = rows.get(t.header_row + 1)
        styles = {c: _cell_style(first.cells[c]) if first and c in first.cells else None for c in cols}
        totals = {r: {c: rows[r].cells[c] for c in cols if r in rows and c in rows[r].cells}
                  for r in range(t.last_row - t.totals + 1, t.last_row + 1)}
        for r in range(t.header_row + 1, t.last_row + 1):
            if r in rows:
                for c in cols:
                    rows[r].cells.pop(c, None)

        for i, rec in enumerate(records):
            n = t.header_row + 1 + i
            row = rows.setdefault(n, Row(f' r="{n}"'))
            for j, col_name in enumerate(t.columns):
                c = t.first_col + j
                value = rec[col_name] if col_name in rec else (
                    Formula(t.formulas[col_name]) if col_name in t.formulas else None)
                xml = _value_xml(f"{col_letters(c)}{n}", _plain(value), styles[c])
                if xml:
                    row.cells[c] = xml
        last = t.header_row + max(len(records), 1)   # un tableau garde au moins une ligne de données
        if not records:                               # ligne vide, styles gardés pour le prochain remplissage
            row = rows.setdefault(last, Row(f' r="{last}"'))
            for c in cols:
                if styles[c]:
                    row.cells[c] = f'<c r="{col_letters(c)}{last}" s="{styles[c]}"/>'
        for k, (old_r, cells) in enumerate(sorted(totals.items())):
            n = last + 1 + k
            row = rows.setdefault(n, Row(f' r="{n}"'))
            for c, xml in cells.items():
                row.cells[c] = re.sub(r'\br="[A-Z]+\d+"', f'r="{col_letters(c)}{n}"', xml, count=1)

        for n, row in rows.items():     # filtres levés : plus de lignes masquées dans la plage du tableau
            if t.header_row < n <= max(last + t.totals, t.last_row):
                row.attrs = re.sub(r'\s(hidden|spans)="[^"]*"', "", row.attrs)
        for n in [n for n, row in rows.items() if not row.cells and last + t.totals < n <= t.last_row
                  and 'customFormat="1"' not in row.attrs]:
            del rows[n]

        new_ref = f"{col_letters(t.first_col)}{t.header_row}:{col_letters(cols[-1])}{last + t.totals}"
        filter_ref = f"{col_letters(t.first_col)}{t.header_row}:{col_letters(cols[-1])}{last}"
        x = self.parts[t.part].decode("utf-8")
        x = re.sub(r'(<table\b[^>]*?\sref=")[^"]*"', rf'\g<1>{new_ref}"', x, count=1)
        x = re.sub(r'<autoFilter\b[^>]*?(/>|>.*?</autoFilter>)',
                   f'<autoFilter ref="{filter_ref}"/>', x, count=1, flags=re.S)
        x = re.sub(r"<calculatedColumnFormula>[^<]*#REF![^<]*</calculatedColumnFormula>", "", x)
        self.parts[t.part] = x.encode("utf-8")
        t.last_row = last + t.totals

    # ------------------------------------------------------------------ enregistrement

    def _render_sheet(self, part: str) -> bytes:
        text = self.parts[part].decode("utf-8")
        rows = self._rows[part]
        body = []
        max_r = max_c = 1
        for n in sorted(rows):
            row = rows[n]
            attrs = re.sub(r'\sr="\d+"', f' r="{n}"', row.attrs, count=1)
            cells = "".join(row.cells[c] for c in sorted(row.cells))
            body.append(f"<row{attrs}>{cells}</row>" if cells else f"<row{attrs}/>")
            if row.cells:
                max_r, max_c = max(max_r, n), max(max_c, max(row.cells))
        data = f"<sheetData>{''.join(body)}</sheetData>" if body else "<sheetData/>"
        text = SHEETDATA_RE.sub(lambda _: data, text, count=1)
        text = re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:{col_letters(max_c)}{max_r}"/>', text, count=1)
        return text.encode("utf-8")

    def save(self, path: str | Path, compact_strings: bool = False) -> Path:
        """Écrit le classeur. `compact_strings` retire de la table des chaînes partagées les textes que plus
        aucune cellule n'utilise (données d'un ancien projet, pour un gabarit vierge)."""
        path = Path(path)
        parts = dict(self.parts)
        for part in self._rows:
            parts[part] = self._render_sheet(part)
        if compact_strings and "xl/sharedStrings.xml" in parts:
            _compact_strings(parts)
        if self._rows:
            wb = parts["xl/workbook.xml"].decode("utf-8")
            if "fullCalcOnLoad" not in wb:
                wb = re.sub(r"<calcPr\b", '<calcPr fullCalcOnLoad="1"', wb, count=1)
            parts["xl/workbook.xml"] = wb.encode("utf-8")
            parts.pop("xl/calcChain.xml", None)
            rels = parts["xl/_rels/workbook.xml.rels"].decode("utf-8")
            parts["xl/_rels/workbook.xml.rels"] = re.sub(
                rf'<Relationship [^>]*Type="{re.escape(CALC_CHAIN)}"[^>]*/>', "", rels).encode("utf-8")
            ct = parts["[Content_Types].xml"].decode("utf-8")
            parts["[Content_Types].xml"] = re.sub(r'<Override [^>]*PartName="/xl/calcChain.xml"[^>]*/>', "", ct).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for info in self.infos:
                if info.filename in parts:
                    z.writestr(info, parts[info.filename], compress_type=zipfile.ZIP_DEFLATED)
        tmp.replace(path)
        return path


SST_CELL_RE = re.compile(r'(<c\b[^>]*?\st="s"[^>]*>)<v>(\d+)</v>')
SI_RE = re.compile(r"<si>.*?</si>|<si/>", re.S)


def _compact_strings(parts: dict[str, bytes]) -> None:
    """Renumérote les chaînes partagées dans l'ordre de première utilisation et retire les autres."""
    sheets = sorted(n for n in parts if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    sst = parts["xl/sharedStrings.xml"].decode("utf-8")
    items = SI_RE.findall(sst)
    mapping: dict[int, int] = {}
    for n in sheets:
        for m in SST_CELL_RE.finditer(parts[n].decode("utf-8")):
            mapping.setdefault(int(m[2]), len(mapping))
    for n in sheets:
        text = parts[n].decode("utf-8")
        parts[n] = SST_CELL_RE.sub(lambda m: f"{m[1]}<v>{mapping[int(m[2])]}</v>", text).encode("utf-8")
    kept = [items[i] for i in sorted(mapping, key=mapping.get)]
    head = re.match(r"(.*?<sst\b[^>]*>)", sst, re.S)[1]
    head = re.sub(r'\s(count|uniqueCount)="\d+"', "", head)
    head = head.replace("<sst", f'<sst count="{len(kept)}" uniqueCount="{len(kept)}"', 1)
    parts["xl/sharedStrings.xml"] = (head + "".join(kept) + "</sst>").encode("utf-8")
