"""Source Treegram (`.tgm` ou `.ifc`) ou projet généré (`.siagen.json`, V4) -> DataFrame normalisé des surfaces.

Colonnes produites (SURFACE_COLUMNS) :
    id         identifiant stable (GlobalId IFC, nom d'élément Treegram)
    building   bâtiment
    level      niveau
    category   code brut lu dans la source (non normalisé : alias et inconnus traités dans rules.py)
    area       aire en m²
    kind       "leaf" = surface élémentaire, "node" = total par niveau fourni par Treegram
    room_type  sous-type (ex. PieceDeVie, Balcon) si la source le donne
    lot        identifiant de lot PPE si la source le donne
    elevation  altitude du niveau si la source la donne
    source     chemin du fichier lu
    element_id identifiant interne Treegram (.tgm) : clé de la géométrie du cache VWR
    tgm_id     « ID TGM » des exports Excel Treegram (H<conteneur>::H<élément>)
    perimeter, gross_height, dx, dy, bedrooms, gross_area, net_area, reservations_area
               propriétés Treegram reprises telles quelles (sources.tgm.extra_properties) ;
               vides pour l'IFC

Seul ce module touche à IfcOpenShell et au format `.tgm` ; le `.siagen.json` suit le contrat de siagen.py.
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path

import pandas as pd

from . import siagen, tgm
from .config import Config

log = logging.getLogger(__name__)

EXTRA_COLUMNS = {"perimeter": "Perimeter", "gross_height": "GrossHeight", "dx": "DeltaX", "dy": "DeltaY",
                 "bedrooms": "Bedrooms", "gross_area": "GrossArea", "net_area": "NetArea",
                 "reservations_area": "ReservationsArea"}
SURFACE_COLUMNS = ["id", "building", "level", "category", "area", "kind", "room_type", "lot", "elevation", "source",
                   "element_id", "tgm_id", *EXTRA_COLUMNS]


class ReadError(RuntimeError):
    pass


def read(path: str | Path, cfg: Config) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise ReadError(f"fichier introuvable : {path}")
    ext = path.suffix.lower()
    try:
        if siagen.is_siagen(path):
            df = read_siagen(path, cfg)
        elif ext == ".tgm":
            df = read_tgm(path, cfg)
        elif ext == ".ifc":
            df = read_ifc(path, cfg)
        else:
            raise ReadError(f"extension non prise en charge : {ext} (attendu .tgm, .siagen.json ou .ifc)")
    except ReadError:
        raise
    except Exception as ex:  # noqa: BLE001 — toute erreur de lecture devient un code de sortie 2
        raise ReadError(f"lecture impossible de {path} : {ex}") from ex
    for r in df.itertuples():
        log.debug("surface %s | %s | %s | %s | %.3f m² | %s", r.building, r.level, r.category, r.kind, r.area, r.id)
    log.info("%s : %d surfaces lues (%d élémentaires, %d totaux de niveau)",
             path.name, len(df), (df.kind == "leaf").sum(), (df.kind == "node").sum())
    return df


def _frame(rows: list[dict], path: Path) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=SURFACE_COLUMNS)
    df["source"] = str(path)
    for c in ["area", *EXTRA_COLUMNS]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# --------------------------------------------------------------------------- .tgm

def read_tgm(path: Path, cfg: Config) -> pd.DataFrame:
    return _frame(_rows(tgm_elements(path, cfg), cfg), path)


def tgm_elements(path: Path, cfg: Config) -> list[siagen.Element]:
    """Surfaces SIA d'un projet Treegram, au modèle du contrat `.siagen` (bâtiment et niveau explicites).

    Totaux sans propriété de catégorie : sources.tgm.uncategorized_nodes associe un nom d'élément à une propriété
    qui l'identifie (SFN : NetArea, pour la façade du niveau, qui ouvre chaque bloc de niveau) ; le nom sert de code.

    Deux sortes d'éléments portent la propriété de catégorie (docs/ifc-schema.md §2.2) :
    - surfaces élémentaires : bâtiment et niveau lus dans le préfixe du nom ;
    - totaux de niveau (« nœuds »), nommés par le seul code : aucun lien explicite vers leur niveau.
      Ils sont groupés en blocs (un bloc = un niveau, chaque code au plus une fois) et un bloc
      prend le niveau de la première surface élémentaire qui suit son premier nœud.
      Les éléments modifiés après coup sont ajoutés en fin de fichier ; ils restent rattachés
      par leur nom, jamais par leur position.
    """
    src = cfg.sources.get("tgm") or {}
    cat_p = src.get("category_property", "Catégorie SIA")
    name_re = re.compile(src.get("name_pattern", r"^(?P<building>[^_]+)_(?P<level>[^_]+)_"))

    uncategorized = src.get("uncategorized_nodes") or {}
    following = src.get("following_nodes") or {}
    bags, prev = [], None
    for g in tgm.scan(path.read_bytes()):
        if cat_p in g.props or uncategorized.get(g.name) in g.props:
            bags.append(g)
        elif (prev is not None and following.get(g.name) == prev.name
              and uncategorized.get(prev.name) in prev.props):     # ex. SRV juste après la SFN de son niveau
            bags.append(g)
        prev = g
    if not any(cat_p in g.props for g in bags):
        raise ReadError(f"aucun élément portant la propriété « {cat_p} » : surfaces SIA non créées dans ce projet ?")

    located, block, block_codes, block_loc = [], -1, set(), {}
    for g in bags:
        code = str(g.props.get(cat_p, g.name)).strip()
        m = name_re.match(g.name)
        if m is None:
            if block < 0 or code in block_codes:
                block, block_codes = block + 1, set()
            block_codes.add(code)
            located.append((g, "node", block))
            continue
        block_loc.setdefault(block, (m["building"], m["level"]))
        located.append((g, "leaf", (m["building"], m["level"])))

    elements, orphans = [], 0
    for g, kind, where in located:
        loc = block_loc.get(where) if kind == "node" else where
        if loc is None:
            orphans += 1
            continue
        elements.append(siagen.Element(g.name, kind, loc[0], loc[1], g.props, g.element_id, g.container_id))
    if orphans:
        log.warning("%d totaux de niveau sans surface élémentaire pour situer leur niveau : ignorés", orphans)
    return elements


def read_siagen(path: Path, cfg: Config) -> pd.DataFrame:
    """Projet `.siagen.json` (moteur de génération V4) : mêmes surfaces et mêmes colonnes qu'un `.tgm`."""
    try:
        _, elements = siagen.load(path)
    except siagen.FormatError as ex:
        raise ReadError(f"{path.name} : {ex}") from ex
    cat_p = (cfg.sources.get("tgm") or {}).get("category_property", "Catégorie SIA")
    if not any(cat_p in e.props for e in elements):
        raise ReadError(f"{path.name} : aucun élément portant la propriété « {cat_p} »")
    return _frame(_rows(elements, cfg), path)


def _rows(elements: list[siagen.Element], cfg: Config) -> list[dict]:
    """Lignes du DataFrame normalisé, communes au `.tgm` et au `.siagen.json`."""
    src = cfg.sources.get("tgm") or {}
    cat_p = src.get("category_property", "Catégorie SIA")
    area_p = src.get("area_property", "Area")
    type_p = src.get("room_type_property", "Type")
    lot_p = src.get("lot_property", "ApartmentByTgm")
    lot_re = re.compile(src["lot_pattern"]) if src.get("lot_pattern") else None
    extra = EXTRA_COLUMNS | (src.get("extra_properties") or {})

    rows = []
    for e in elements:
        code = str(e.props.get(cat_p, e.name)).strip()
        # Totaux sans catégorie (façade SFN) : pas d'« Area », leur aire est la surface brute.
        area = e.props.get(area_p) if cat_p in e.props else e.props.get(area_p, e.props.get("GrossArea"))
        row = {"category": code, "area": area, "room_type": e.props.get(type_p), "kind": e.kind,
               "building": e.building, "level": e.level, "element_id": e.element_id, "tgm_id": e.tgm_id}
        row |= {c: e.props.get(p) for c, p in extra.items()}
        if e.kind == "node":
            row["id"] = f"{e.building}_{e.level}_{code}#total"
        else:
            lot = e.props.get(lot_p)
            if lot_re and (lm := lot_re.match(e.name)):
                lot = lm["lot"]
            row |= {"id": e.name, "lot": lot}
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- .ifc

def _ifc_value(entity, spec: dict | None, psets: dict):
    if not spec:
        return None
    if "attribute" in spec:
        return getattr(entity, spec["attribute"], None)
    return (psets.get(spec.get("pset")) or {}).get(spec.get("property"))


def read_ifc(path: Path, cfg: Config) -> pd.DataFrame:
    import ifcopenshell
    import ifcopenshell.util.element as uel

    src = cfg.sources.get("ifc") or {}
    f = ifcopenshell.open(str(path))
    log.info("%s : schéma %s", path.name, f.schema)

    def ancestor(el, cls: str):
        c = uel.get_container(el) or uel.get_aggregate(el)
        while c is not None and not c.is_a(cls):
            c = uel.get_aggregate(c)
        return c

    rows = []
    for cls in src.get("classes") or ["IfcSpace"]:
        try:
            entities = f.by_type(cls)
        except RuntimeError:  # classe absente du schéma
            continue
        for e in entities:
            psets = uel.get_psets(e)
            cat = _ifc_value(e, src.get("category"), psets)
            area = _ifc_value(e, src.get("area"), psets)
            st, bd = ancestor(e, "IfcBuildingStorey"), ancestor(e, "IfcBuilding")
            elev = getattr(st, "Elevation", None) if st else None
            rows.append({
                "id": e.GlobalId,
                "building": bd.Name if bd else None,
                "level": st.Name if st else None,
                "category": None if cat is None else str(cat).strip(),
                "area": area,
                "kind": "leaf",
                "lot": _ifc_value(e, src.get("lot"), psets),
                "elevation": elev if elev is not None and not math.isnan(elev) else None,
            })
    df = _frame(rows, path)
    missing = df["area"].isna().sum()
    if missing:
        log.warning("%d surfaces sans aire lisible (%s) : comptées 0 m²", missing, src.get("area"))
        df["area"] = df["area"].fillna(0.0)
    return df
