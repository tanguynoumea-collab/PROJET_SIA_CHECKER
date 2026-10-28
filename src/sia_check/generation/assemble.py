"""Assemblage au modèle Treegram : surfaces générées -> éléments du contrat `.siagen.json` (V4_PLAN §3.2).

Reproduit ce que Treegram écrit dans le `.tgm` (relevé sur L'Orée, docs/ifc-schema.md §2.2) :

- une surface élémentaire par pièce, nommée `Bât_Niv_ShellByTgm-nn_SpaceByTgm-m_CODE`. La coque (`ShellByTgm`,
  deux chiffres) est le logement de la pièce, ou les parties communes du niveau ; la pièce est numérotée dans sa
  coque ;
- propriétés `Catégorie SIA`, `Area`, `Type`, et `ApartmentByTgm` (`Bât_Niv_Apart-nn`) pour une pièce de
  logement. `IfcGlobalId` garde le lien vers l'espace de la maquette ;
- un total par code et par niveau, dans l'ordre de Treegram, y compris à 0 m² ; la SP n'existe qu'en total.

Le bâtiment prend le nom de la maquette, sans `_` (séparateur des noms Treegram). Le niveau prend le code
Treegram (N00, N01…, S01…, Toiture ; config.yaml > generation.levels), dont dépendent le rang des niveaux, le
rez (A1) et les étages du MDP. Sans rez reconnu, il garde le nom de la maquette. Les maillages sont les
emprises en plan, triangulées à l'altitude du plancher.
"""

from __future__ import annotations

import re

import shapely
from shapely.geometry.base import BaseGeometry

from ..geom import Mesh
from ..siagen import Element
from .ingest import Storey
from .interiors import Level

CATEGORY = "Catégorie SIA"
NODE_ORDER = ["SFN", "SRV", "SUP", "SUS", "SD", "SED", "SI", "SUT", "SEU", "SNH", "SHA", "SBH", "SVN", "SVB",
              "SP", "SEP", "SPT"]
INTERIOR_NODES = ["SUP", "SUS", "SD", "SI", "SUT", "SP"]   # phase 21 : extérieurs, USPI et enveloppe à venir
CONTAINER_ID = 1


def clean(name: str) -> str:
    """Nom de bâtiment ou de niveau utilisable dans un nom Treegram (pas de `_`, pas d'espace)."""
    return re.sub(r"[-_\s]+", "-", str(name).strip()).strip("-") or "X"


def level_codes(storeys: list[Storey], occupied: set[str], cfg_generation: dict | None = None) -> dict[str, str]:
    """Code Treegram de chaque niveau (gid -> code), bâtiment par bâtiment."""
    lv = (cfg_generation or {}).get("levels") or {}
    ground = [re.compile(p) for p in lv.get("ground") or []]
    roof = re.compile(lv["roof"]) if lv.get("roof") else None
    out = {}
    for b in dict.fromkeys(s.building for s in storeys):
        levels = sorted((s for s in storeys if s.building == b), key=lambda s: s.elevation)
        rez = next((s for rx in ground for s in levels if rx.search(s.name)), None)
        if rez is None:
            out |= {s.gid: clean(s.name) for s in levels}
            continue
        g = levels.index(rez)
        top = max((k for k, s in enumerate(levels) if s.gid in occupied), default=len(levels) - 1)
        for k, s in enumerate(levels):
            if k > top and roof and roof.search(s.name):
                out[s.gid] = "Toiture"
            else:
                out[s.gid] = f"N{k - g:02d}" if k >= g else f"S{g - k:02d}"
    return out


def mesh_of(g: BaseGeometry | None, z: float) -> Mesh | None:
    """Triangulation contrainte d'une emprise en plan, posée à l'altitude z."""
    if g is None or g.is_empty:
        return None
    tris = shapely.constrained_delaunay_triangles(g)
    v, i = [], []
    for t in getattr(tris, "geoms", []):
        if t.area <= 0 or not g.covers(t.representative_point()):
            continue
        for x, y in list(t.exterior.coords)[:3]:
            i.append(len(v) // 3)
            v += [float(x), float(y), float(z)]
    return Mesh(v, i) if i else None


def elements(levels: list[Level], codes: dict[str, str] | None = None) -> list[Element]:
    out: list[Element] = []
    next_id = 1
    codes = codes or {}

    def add(name, kind, b, lv, props, mesh=None):
        nonlocal next_id
        out.append(Element(name, kind, b, lv, props, next_id, CONTAINER_ID, [mesh] if mesh else []))
        next_id += 1

    for level in levels:
        st = level.plan.storey
        b, lv = clean(st.building), codes.get(st.gid) or clean(st.name)
        lots = sorted({r.placed.item.lot for r in level.rooms if r.decision.in_lot})
        apart = {lot: f"{b}_{lv}_Apart-{k:02d}" for k, lot in enumerate(lots, 1)}
        shells = {lot: k for k, lot in enumerate(lots, 1)}
        common_shell = len(lots) + 1
        totals = {code: 0.0 for code in INTERIOR_NODES}
        totals["SP"] = level.sp_area
        leaves, counter = [], {}
        for r in sorted(level.rooms, key=lambda r: (r.placed.item.lot or "~", r.placed.item.name or "", r.placed.item.gid)):
            d, item = r.decision, r.placed.item
            shell = shells.get(item.lot) if d.in_lot else common_shell
            counter[shell] = counter.get(shell, 0) + 1
            props = {CATEGORY: d.code, "Area": round(r.area, 3)}
            if d.type:
                props["Type"] = d.type
            if d.in_lot:
                props["ApartmentByTgm"] = apart[item.lot]
            props["IfcGlobalId"] = item.gid
            name = f"{b}_{lv}_ShellByTgm-{shell:02d}_SpaceByTgm-{counter[shell]}_{d.code}"
            leaves.append((name, props, mesh_of(r.placed.shape, item.z_min if item.z_min is not None else st.elevation)))
            if d.code in totals:
                totals[d.code] += r.area
        for code in (c for c in NODE_ORDER if c in INTERIOR_NODES):
            mesh = mesh_of(level.sp, st.elevation) if code == "SP" else None
            add(code, "node", b, lv, {CATEGORY: code, "Area": round(totals[code], 3)}, mesh)
        for name, props, mesh in leaves:
            add(name, "leaf", b, lv, props, mesh)
    return out
