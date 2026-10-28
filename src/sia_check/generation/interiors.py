"""Surfaces intérieures d'un niveau : pièces classées et SP (V4_PLAN §3.1, phase 21).

**SP** (SIA 416 §2, surface de plancher, contour extérieur des murs) :
1. les espaces « surface de plancher » du niveau, s'il y en a (nature `plancher`) : leur union, moins les
   extérieurs du niveau (loggias, balcons : SEP au sens de SIA 416 §3, que les architectes y laissent souvent) ;
2. sinon le contour des pièces, des murs, des murs-rideaux et des poteaux du niveau, joints fermés (fermeture
   morphologique de `sp.close_m`) et vides intérieurs de moins de `sp.min_hole_m2` bouchés (gaines, joints).
   Les vides plus grands (cours, patios) restent hors SP.

**Aire d'une pièce** : son emprise en plan (`sp.area_source: plan`, SIA 416 §0.4), ou l'aire déclarée par les
quantités IFC (`declared`), à défaut l'emprise. Les pièces sans emprise en plan ne sont pas comptées.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from .audit import declared_area
from .classify import EXTERIEUR, PIECE, PLANCHER, Decision
from .plans import Placed, Plan

ENVELOPE_CLASSES = ("IfcWall", "IfcCurtainWall", "IfcColumn")


@dataclass
class Room:
    placed: Placed
    decision: Decision
    area: float


@dataclass
class Level:
    plan: Plan
    rooms: list[Room] = field(default_factory=list)
    sp: BaseGeometry | None = None
    sp_method: str = ""

    @property
    def sp_area(self) -> float:
        return self.sp.area if self.sp is not None else 0.0


def _fill_holes(g: BaseGeometry, min_hole: float) -> BaseGeometry:
    def fix(p: Polygon) -> Polygon:
        return Polygon(p.exterior, [r for r in p.interiors if Polygon(r).area >= min_hole])
    if isinstance(g, Polygon):
        return fix(g)
    return shapely.union_all([fix(p) for p in getattr(g, "geoms", []) if isinstance(p, Polygon)])


def surface_de_plancher(plan: Plan, decisions: dict[str, Decision], close: float, min_hole: float) -> tuple[BaseGeometry | None, str]:
    planchers = [p.shape for p in plan.spaces if p.shape is not None and decisions[p.item.gid].nature == PLANCHER]
    if planchers:
        g, why = shapely.union_all(planchers), f"{len(planchers)} espace(s) « surface de plancher »"
        ext = [p.shape for p in plan.spaces if p.shape is not None and decisions[p.item.gid].nature == EXTERIEUR]
        cut = g.intersection(shapely.union_all(ext)).area if ext else 0.0
        if cut > 0.01:
            g = g.difference(shapely.union_all(ext))
            why += f", moins {cut:.2f} m² d'extérieurs"
        return g, why
    parts = [p.shape for p in plan.spaces if p.shape is not None and decisions[p.item.gid].nature == PIECE]
    if not parts:
        return None, "aucune pièce"
    walls = [p.shape for p in plan.of(*ENVELOPE_CLASSES) if p.shape is not None]
    g = shapely.union_all(parts + walls)
    if close > 0:
        g = g.buffer(close, join_style="mitre").buffer(-close, join_style="mitre")
    g = _fill_holes(g.buffer(0), min_hole)
    return g, f"contour de {len(parts)} pièces et {len(walls)} murs ou poteaux"


def build(plans: list[Plan], decisions: dict[str, Decision], cfg_generation: dict | None = None) -> list[Level]:
    sp_cfg = (cfg_generation or {}).get("sp") or {}
    close, min_hole = float(sp_cfg.get("close_m", 0.3)), float(sp_cfg.get("min_hole_m2", 4.0))
    declared = sp_cfg.get("area_source", "plan") == "declared"
    out = []
    for plan in plans:
        lv = Level(plan)
        for p in plan.spaces:
            d = decisions[p.item.gid]
            if d.nature != PIECE or p.shape is None:
                continue
            area = (declared_area(p.item) if declared else None) or p.area
            lv.rooms.append(Room(p, d, area))
        lv.sp, lv.sp_method = surface_de_plancher(plan, decisions, close, min_hole)
        if lv.rooms or lv.sp is not None:
            out.append(lv)
    return out
