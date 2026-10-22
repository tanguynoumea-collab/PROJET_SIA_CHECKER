"""Source Treegram (`.tgm` ou `.ifc`) -> DataFrame normalisé des surfaces.

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

Seul ce module touche à IfcOpenShell et au format `.tgm`.
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path

import pandas as pd

from . import tgm
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
        if ext == ".tgm":
            df = read_tgm(path, cfg)
        elif ext == ".ifc":
            df = read_ifc(path, cfg)
        else:
            raise ReadError(f"extension non prise en charge : {ext} (attendu .tgm ou .ifc)")
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
    """Surfaces SIA d'un projet Treegram.

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
    area_p = src.get("area_property", "Area")
    type_p = src.get("room_type_property", "Type")
    lot_p = src.get("lot_property", "ApartmentByTgm")
    name_re = re.compile(src.get("name_pattern", r"^(?P<building>[^_]+)_(?P<level>[^_]+)_"))
    lot_re = re.compile(src["lot_pattern"]) if src.get("lot_pattern") else None
    extra = EXTRA_COLUMNS | (src.get("extra_properties") or {})

    uncategorized = src.get("uncategorized_nodes") or {}
    bags = [g for g in tgm.scan(path.read_bytes())
            if cat_p in g.props or uncategorized.get(g.name) in g.props]
    if not any(cat_p in g.props for g in bags):
        raise ReadError(f"aucun élément portant la propriété « {cat_p} » : surfaces SIA non créées dans ce projet ?")

    rows, block, block_codes, block_loc = [], -1, set(), {}
    for g in bags:
        code = str(g.props.get(cat_p, g.name)).strip()
        m = name_re.match(g.name)
        row = {"category": code, "area": g.props.get(area_p), "room_type": g.props.get(type_p),
               "element_id": g.element_id, "tgm_id": g.tgm_id} | {c: g.props.get(p) for c, p in extra.items()}
        if m is None:
            if block < 0 or code in block_codes:
                block, block_codes = block + 1, set()
            block_codes.add(code)
            rows.append(row | {"kind": "node", "_block": block})
            continue
        block_loc.setdefault(block, (m["building"], m["level"]))
        lot = g.props.get(lot_p)
        if lot_re and (lm := lot_re.match(g.name)):
            lot = lm["lot"]
        rows.append(row | {"kind": "leaf", "id": g.name, "building": m["building"], "level": m["level"], "lot": lot})

    orphans = 0
    for row in rows:
        if row["kind"] != "node":
            continue
        loc = block_loc.get(row.pop("_block"))
        if loc is None:
            orphans += 1
            continue
        row["building"], row["level"] = loc
        row["id"] = f"{loc[0]}_{loc[1]}_{row['category']}#total"
    if orphans:
        log.warning("%d totaux de niveau sans surface élémentaire pour situer leur niveau : ignorés", orphans)
    rows = [r for r in rows if r.get("building") is not None]
    return _frame(rows, path)


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
