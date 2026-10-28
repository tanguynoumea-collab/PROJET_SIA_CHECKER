"""Surfaces intérieures d'un niveau : pièces classées et SP (V4_PLAN §3.1, phase 21).

**SP** (SIA 416 §2, surface de plancher, contour extérieur des murs) :
1. les espaces « surface de plancher » du niveau, s'il y en a (nature `plancher`) : leur union, plus les pièces
   qui en sortent avec leurs murs (locaux oubliés par l'architecte), moins les extérieurs dessinés à l'intérieur
   (loggia comptée par erreur : SEP au sens de SIA 416 §3) ;
2. sinon le contour des pièces, des murs, des murs-rideaux et des poteaux du niveau, joints fermés (fermeture
   morphologique de `sp.close_m`) et vides intérieurs de moins de `sp.min_hole_m2` bouchés (gaines, joints).
   Les vides plus grands (cours, patios) restent hors SP.

**Altitude d'un niveau** (`Level.z`) : le sol de la plupart des pièces (altitude de base des IfcSpace la plus
fréquente, pondérée par l'aire), à défaut celle du niveau IFC, souvent décalée (Myonaz 2 S01 : niveau à 612,04,
pièces à 611,40 ; Afiro S01 : 1,9 m sous ses pièces). Toutes les surfaces du niveau y sont posées, comme chez
Treegram : une fosse ou un escalier qui descend ne décale pas sa surface. Hauteur d'étage = écart au niveau
suivant du bâtiment.

**Aire d'une pièce** : son emprise en plan (`sp.area_source: plan`, SIA 416 §0.4), ou l'aire déclarée par les
quantités IFC (`declared`), à défaut l'emprise. Les pièces sans emprise en plan ne sont pas comptées.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from .audit import declared_area
from .classify import EXTERIEUR, PIECE, PLANCHER, Decision
from .plans import Placed, Plan

ENVELOPE_CLASSES = ("IfcWall", "IfcCurtainWall", "IfcColumn")
INSIDE = 0.8        # part d'un extérieur dans la surface de plancher au-delà de laquelle il en est retiré
OUTSIDE_M2 = 0.5    # part d'une pièce hors de la surface de plancher dessinée au-delà de laquelle elle y est ajoutée
WALL_REACH = 0.5    # murs pris autour de ces pièces (m)
OUTSIDE_EXCLUDED = {"SI"}   # installations hors du contour dessiné : gardées en SI, hors SP


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
    # phase 22 (exteriors.py) : surfaces extérieures, contour SEP, toitures SPT, façade et vitrages
    exteriors: list[Room] = field(default_factory=list)
    sep: BaseGeometry | None = None
    spt: BaseGeometry | None = None
    slab: BaseGeometry | None = None   # dalle sur sous-sol, à découvert : abords, hors SEP
    envelope: dict = field(default_factory=dict)
    facade: object = None     # geom.Mesh vertical de la façade (SFN)
    glazing: object = None    # geom.Mesh des ouvertures de façade (SRV)
    floor_z: float | None = None   # sol des pièces ; None : altitude du niveau IFC
    height: float | None = None    # jusqu'au niveau suivant du bâtiment ; None : hauteur IFC

    @property
    def z(self) -> float:
        return self.floor_z if self.floor_z is not None else self.plan.storey.elevation

    @property
    def sp_area(self) -> float:
        return self.sp.area if self.sp is not None else 0.0

    @property
    def empty(self) -> bool:
        return not self.rooms and not self.exteriors and self.sp is None and self.sep is None and self.spt is None


def _fill_holes(g: BaseGeometry, min_hole: float) -> BaseGeometry:
    def fix(p: Polygon) -> Polygon:
        return Polygon(p.exterior, [r for r in p.interiors if Polygon(r).area >= min_hole])
    if isinstance(g, Polygon):
        return fix(g)
    return shapely.union_all([fix(p) for p in getattr(g, "geoms", []) if isinstance(p, Polygon)])


def _contour(parts: list, walls: list, close: float, min_hole: float) -> BaseGeometry:
    g = shapely.union_all(parts + walls)
    if close > 0:
        g = g.buffer(close, join_style="mitre").buffer(-close, join_style="mitre")
    return _fill_holes(g.buffer(0), min_hole)


def surface_de_plancher(plan: Plan, decisions: dict[str, Decision], close: float, min_hole: float) -> tuple[BaseGeometry | None, str]:
    planchers = [p.shape for p in plan.spaces if p.shape is not None and decisions[p.item.gid].nature == PLANCHER]
    pieces = [p.shape for p in plan.spaces if p.shape is not None and decisions[p.item.gid].nature == PIECE]
    walls = [p.shape for p in plan.of(*ENVELOPE_CLASSES) if p.shape is not None]
    if planchers:
        g, why = shapely.union_all(planchers), f"{len(planchers)} espace(s) « surface de plancher »"
        # locaux que la surface dessinée oublie (La Bâtie, rez : poussettes, buanderie) : ajoutés avec leurs murs,
        # comme dans le MDP ; pas les installations hors du bâtiment (Myonaz 2 : bassin de rétention, SI hors SP)
        outside = [p.shape for p in plan.spaces if p.shape is not None and decisions[p.item.gid].nature == PIECE
                   and decisions[p.item.gid].code not in OUTSIDE_EXCLUDED and p.shape.difference(g).area > OUTSIDE_M2]
        if outside:
            near = shapely.union_all(outside).buffer(WALL_REACH)
            extra = _contour(outside, [w.intersection(near) for w in walls if w.intersects(near)], close, min_hole)
            before = g.area
            g = shapely.union_all([g, extra]).buffer(0)
            why += f", plus {g.area - before:.2f} m² de {len(outside)} pièce(s) hors de ce contour"
        # seuls les extérieurs dessinés dans la surface de plancher (loggia oubliée par l'architecte) en sortent ;
        # un balcon qui la touche de quelques centimètres la laisse intacte (Myonaz : SP du MDP = espace dessiné)
        ext = [p.shape for p in plan.spaces if p.shape is not None and decisions[p.item.gid].nature == EXTERIEUR
               and p.shape.intersection(g).area >= INSIDE * p.shape.area]
        cut = g.intersection(shapely.union_all(ext)).area if ext else 0.0
        if cut > 0.01:
            g = g.difference(shapely.union_all(ext))
            why += f", moins {cut:.2f} m² d'extérieurs"
        return g, why
    if not pieces:
        return None, "aucune pièce"
    return _contour(pieces, walls, close, min_hole), f"contour de {len(pieces)} pièces et {len(walls)} murs ou poteaux"


def build(plans: list[Plan], decisions: dict[str, Decision], cfg_generation: dict | None = None) -> list[Level]:
    sp_cfg = (cfg_generation or {}).get("sp") or {}
    close, min_hole = float(sp_cfg.get("close_m", 0.3)), float(sp_cfg.get("min_hole_m2", 4.0))
    declared = sp_cfg.get("area_source", "plan") == "declared"
    out = []
    for plan in plans:   # un niveau par plan, même vide : les toitures (phase 22) se posent sur les niveaux sans pièce
        lv = Level(plan)
        for p in plan.spaces:
            d = decisions[p.item.gid]
            if d.nature != PIECE or p.shape is None:
                continue
            lv.rooms.append(Room(p, d, area_of(p, declared)))
        lv.sp, lv.sp_method = surface_de_plancher(plan, decisions, close, min_hole)
        lv.floor_z = floor_z(lv)
        out.append(lv)
    heights(out)
    return out


def floor_z(lv: Level) -> float | None:
    """Altitude de base la plus fréquente des pièces du niveau, pondérée par l'aire (au centimètre)."""
    weight = Counter()
    for r in lv.rooms:
        if r.placed.item.z_min is not None:
            weight[round(r.placed.item.z_min, 2)] += r.placed.area
    return weight.most_common(1)[0][0] if weight else None


def heights(levels: list[Level]) -> None:
    """Hauteur d'étage de chaque niveau : écart d'altitude au niveau suivant du même bâtiment."""
    for b in dict.fromkeys(lv.plan.storey.building for lv in levels):
        own = sorted((lv for lv in levels if lv.plan.storey.building == b), key=lambda lv: lv.z)
        for lv, up in zip(own, own[1:]):
            if up.z - lv.z > 0.5:
                lv.height = round(up.z - lv.z, 4)


def area_of(p: Placed, declared: bool) -> float:
    return (declared_area(p.item) if declared else None) or p.area
