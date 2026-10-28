"""Extérieurs, toitures et enveloppe d'un niveau (V4_PLAN §3.1, phase 22), au modèle Treegram (relevé L'Orée).

- **SEU, SED, SEI** : une surface élémentaire par espace extérieur de la maquette (balcon, loggia, terrasse,
  coursive), avec son logement. Aire déclarée, à défaut l'emprise.
- **Contour SEP** : un « plancher externe » dessiné (Myonaz, La Bâtie) n'est pas une surface élémentaire ; il
  entre dans la SEP du niveau, comme chez Treegram où la SEP n'existe qu'en total.
- **SPT** (toitures, code Treegram) : ce que la SP du niveau inférieur laisse à découvert, posé sur le niveau
  du dessus (Treegram : toiture d'attique sur l'attique, toiture du dernier étage sur le niveau « Toiture »,
  créé s'il manque), moins les extérieurs dessinés (une terrasse accessible est une SEU). Au-dessus d'un
  sous-sol, ce n'est pas une toiture mais une dalle sur sous-sol : des abords (SA, SIA 416 §1.2), hors SEP,
  gardés dans `Level.slab` pour le rapport. Treegram L'Orée la laisse dans la SEP du rez (A1, R3) ; le MDP de
  La Bâtie ne la compte pas (SEP du rez 49,8 m², dalle 1 081 m²).
- **SEP** du niveau : union des extérieurs, des contours et des toitures (Treegram compte les SPT dans la SEP ;
  la Fiabilisation les en retire, rules.COUNTED_IN).
- **Ouvertures de façade** : fenêtres et portes posées sur le contour de la SP (à `FACADE_REACH_M` près). Une
  ouverture que la maquette dit intérieure (`IsExternal` faux, Pset_WindowCommon / Pset_DoorCommon) n'en est
  jamais, même près du contour ; une ouverture dite extérieure en est une. Aire : grand côté de l'emprise × hauteur
  du maillage.
- **SFN** (façade) : périmètre de la SP × hauteur d'étage ; réservations = toutes les ouvertures de façade. Le
  maillage de la façade est percé de ces ouvertures (une baie vitrée se voit comme un trou dans la SFN).
- **SRV** (vitrages extérieurs) : les fenêtres de façade, et les portes de façade vitrées (nom ou type :
  `envelope.glazed_doors`). Une porte d'entrée pleine, une porte de garage restent des réservations sans vitrage.
  Les vitrages intérieurs (cloisons vitrées, fenêtres intérieures) ne comptent pas. Treegram L'Orée : SRV ≈
  réservations, il ne distinguait pas les portes pleines.
- Dimensions des totaux SP, SEP et SPT : hauteur d'étage, périmètre, DeltaX / DeltaY (rectangle minimal).
"""

from __future__ import annotations

import shapely
from shapely.geometry.base import BaseGeometry

import re

from shapely.geometry import box

from ..geom import Mesh
from .classify import EXTERIEUR, Decision, norm
from .ingest import Storey
from .interiors import Level, Room, area_of
from .plans import Plan

SLIVER_M = 0.25        # ouverture morphologique : bandes plus fines (tranches de murs, débords) ignorées
MIN_ROOF_M2 = 2.0      # morceau de toiture plus petit : ignoré
FACADE_REACH_M = 0.6   # ouverture à moins de cette distance du contour de la SP : en façade
DEFAULT_HEIGHT_M = 3.0  # hauteur d'un niveau sans niveau au-dessus (Treegram L'Orée : niveaux « Toiture »)


def _clean(g: BaseGeometry | None) -> BaseGeometry | None:
    if g is None or g.is_empty:
        return None
    g = g.buffer(-SLIVER_M, join_style="mitre").buffer(SLIVER_M, join_style="mitre")
    parts = [p for p in getattr(g, "geoms", [g]) if p.area >= MIN_ROOF_M2]
    return shapely.union_all(parts) if parts else None


def dims(g: BaseGeometry | None) -> dict:
    """Périmètre, DeltaX (grand côté) et DeltaY du rectangle minimal ; zéros sans géométrie, comme Treegram."""
    if g is None or g.is_empty:
        return {"Perimeter": 0.0, "DeltaX": 0.0, "DeltaY": 0.0}
    r = g.minimum_rotated_rectangle
    xs = list(r.exterior.coords) if hasattr(r, "exterior") else []
    sides = sorted({round(((xs[i + 1][0] - xs[i][0]) ** 2 + (xs[i + 1][1] - xs[i][1]) ** 2) ** 0.5, 3)
                    for i in range(min(2, len(xs) - 1))}, reverse=True) if xs else [0.0]
    return {"Perimeter": round(g.length, 3), "DeltaX": sides[0], "DeltaY": sides[-1] if len(sides) > 1 else sides[0]}


def roof_levels(levels: list[Level]) -> list[Level]:
    """Niveau « Toiture » ajouté au-dessus du dernier niveau occupé d'un bâtiment qui n'en a pas."""
    out = []
    for b in dict.fromkeys(lv.plan.storey.building for lv in levels):
        own = [lv for lv in levels if lv.plan.storey.building == b]
        occupied = [lv for lv in own if lv.sp is not None]
        if not occupied:
            continue
        top = max(occupied, key=lambda lv: lv.z)
        if any(lv.z > top.z for lv in own):
            continue
        st = top.plan.storey
        roof = Storey(f"toiture:{b}", "Toiture", b, top.z + (top.height or st.height or DEFAULT_HEIGHT_M), None,
                      st.rank + 1)
        out.append(Level(Plan(roof)))
    return out


def vertical_mesh(segments: list[tuple[tuple[float, float], tuple[float, float], float, float]]) -> Mesh | None:
    """Panneaux verticaux : un quadrilatère (deux triangles) par segment en plan, de z0 à z1."""
    v, i = [], []
    for (x0, y0), (x1, y1), z0, z1 in segments:
        if z1 <= z0 or (x0, y0) == (x1, y1):
            continue
        k = len(v) // 3
        v += [x0, y0, z0, x1, y1, z0, x1, y1, z1, x0, y0, z1]
        i += [k, k + 1, k + 2, k, k + 2, k + 3]
    return Mesh(v, i) if i else None


def _rings(g: BaseGeometry):
    for p in getattr(g, "geoms", [g]):
        if hasattr(p, "exterior"):
            yield p.exterior
            yield from p.interiors


GLAZED_DOORS = r"(vitr|fenetre|verre|glass|baie|coulissant|porte fenetre|\bpf\b)"


def _external(it) -> bool | None:
    """IsExternal de la maquette (Pset_WindowCommon, Pset_DoorCommon), None s'il n'est pas renseigné."""
    v = next((v for k, v in (it.props or {}).items() if k.endswith(".IsExternal")), None)
    return v if isinstance(v, bool) else None


def _openings(level: Level, sp: BaseGeometry, glazed_doors: str = GLAZED_DOORS, band: tuple[float, float] | None = None
              ) -> tuple[float, float, list, list]:
    """(réservations m², vitrages m², panneaux des réservations, panneaux des vitrages) de la façade du niveau.
    `band` (z0, z1) : hauteur d'étage ; une ouverture n'y compte que pour sa part comprise (allège sous le sol fini,
    fenêtre à cheval sur deux étages), comme la façade brute qui n'a que cette hauteur."""
    edge = sp.boundary
    glazed = re.compile(glazed_doors)
    resa = glass = 0.0
    holes, panes = [], []
    for p in level.plan.of("IfcWindow", "IfcDoor"):
        it = p.item
        if p.shape is None or it.z_min is None or it.z_max is None:
            continue
        external = _external(it)
        if external is False or (external is None and p.shape.distance(edge) > FACADE_REACH_M):
            continue   # intérieure (dit la maquette), ou loin de la façade
        if external is True and p.shape.distance(edge) > 2 * FACADE_REACH_M:
            continue   # dite extérieure mais hors du contour de ce niveau (cour, autre bâtiment)
        r = p.shape.minimum_rotated_rectangle
        c = list(r.exterior.coords) if hasattr(r, "exterior") else []
        if len(c) < 3:
            continue
        a, b, d = c[0], c[1], c[3] if len(c) > 3 else c[2]
        side = max(((a, b), (a, d)), key=lambda s: (s[1][0] - s[0][0]) ** 2 + (s[1][1] - s[0][1]) ** 2)
        width = ((side[1][0] - side[0][0]) ** 2 + (side[1][1] - side[0][1]) ** 2) ** 0.5
        zl, zh = (max(it.z_min, band[0]), min(it.z_max, band[1])) if band else (it.z_min, it.z_max)
        if zh - zl <= 0.01:
            continue
        m2 = width * (zh - zl)
        panel = (side[0], side[1], zl, zh)
        resa += m2
        holes.append(panel)
        if it.ifc_class.startswith("IfcWindow") or glazed.search(norm(f"{it.name} {it.type_name} {it.long_name}")):
            glass += m2
            panes.append(panel)
    return resa, glass, holes, panes


def facade_mesh(sp: BaseGeometry, z0: float, z1: float, holes: list) -> Mesh | None:
    """Façade du niveau : un panneau vertical par côté de la SP, percé des ouvertures qui s'y projettent."""
    v, idx = [], []
    for ring in _rings(sp):
        pts = list(ring.coords)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            if length < 1e-6:
                continue
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            wall = box(0.0, z0, length, z1)
            cut = []
            for (ax, ay), (bx, by), zl, zh in holes:
                # distance au côté (normale) et position le long du côté, pour les deux bouts de l'ouverture
                ua, ub = (ax - x0) * ux + (ay - y0) * uy, (bx - x0) * ux + (by - y0) * uy
                da, db = abs((ax - x0) * uy - (ay - y0) * ux), abs((bx - x0) * uy - (by - y0) * ux)
                if max(da, db) > 2 * FACADE_REACH_M or max(ua, ub) < 0 or min(ua, ub) > length:   # emprise à 0,6 m, axe un peu plus loin
                    continue
                cut.append(box(min(ua, ub), zl, max(ua, ub), zh))
            face = wall.difference(shapely.union_all(cut)) if cut else wall
            if face.is_empty:
                continue
            for t in getattr(shapely.constrained_delaunay_triangles(face), "geoms", []):
                if t.area <= 1e-9 or not face.covers(t.representative_point()):
                    continue
                for u, z in list(t.exterior.coords)[:3]:
                    idx.append(len(v) // 3)
                    v += [x0 + ux * u, y0 + uy * u, z]
    return Mesh(v, idx) if idx else None


def build(levels: list[Level], decisions: dict[str, Decision], below_ground: set[str],
          cfg_generation: dict | None = None) -> None:
    """Complète chaque niveau (en place). `below_ground` : gid des niveaux sous le rez (codes S…)."""
    declared = ((cfg_generation or {}).get("sp") or {}).get("area_source", "plan") == "declared"
    for lv in levels:
        contours = []
        for p in lv.plan.spaces:
            d = decisions[p.item.gid]
            if d.nature != EXTERIEUR or p.shape is None:
                continue
            if d.code == "SEP":
                contours.append(p.shape)
            else:
                lv.exteriors.append(Room(p, d, area_of(p, declared)))
        lv.sep = shapely.union_all(contours + [r.placed.shape for r in lv.exteriors]) if (contours or lv.exteriors) else None

    for b in dict.fromkeys(lv.plan.storey.building for lv in levels):
        own = sorted((lv for lv in levels if lv.plan.storey.building == b), key=lambda lv: lv.z)
        for below, lv in zip(own, own[1:]):
            if below.sp is None:
                continue
            covered = [g for g in (lv.sp, lv.sep) if g is not None]
            free = _clean(below.sp.difference(shapely.union_all(covered)) if covered else below.sp)
            if free is None:
                continue
            if below.plan.storey.gid in below_ground:
                lv.slab = free   # dalle sur sous-sol : abords (SA), hors SEP
            else:
                lv.spt = free
                lv.sep = shapely.union_all([g for g in (lv.sep, free) if g is not None])

    for lv in levels:
        st = lv.plan.storey
        h = lv.height or st.height or DEFAULT_HEIGHT_M
        if lv.sp is None:
            lv.envelope = {"GrossArea": 0.0, "NetArea": 0.0, "ReservationsArea": 0.0, "Perimeter": 0.0,
                           "GrossHeight": round(h, 3), "SRV": 0.0}
            continue
        perimeter = lv.sp.length
        env_cfg = (cfg_generation or {}).get("envelope") or {}
        resa, glass, holes, panes = _openings(lv, lv.sp, env_cfg.get("glazed_doors") or GLAZED_DOORS, (lv.z, lv.z + h))
        lv.facade = facade_mesh(lv.sp, lv.z, lv.z + h, holes)
        lv.glazing = vertical_mesh(panes)
        gross = perimeter * h
        lv.envelope = {"GrossArea": round(gross, 2), "NetArea": round(max(gross - resa, 0.0), 2),
                       "ReservationsArea": round(resa, 2), "Perimeter": round(perimeter, 2),
                       "GrossHeight": round(h, 3), "SRV": round(glass, 2)}
