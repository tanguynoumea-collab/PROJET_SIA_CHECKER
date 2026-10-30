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
  La Bâtie ne la compte pas (SEP du rez 49,8 m², dalle 1 081 m²). Sous une toiture en pente, la SPT est sa surface
  développée, drapée sur la couverture (roofs.py, décision du 29.10.2026) ; la SEP la compte de même.
- **SEP** du niveau : union des extérieurs, des contours et des toitures (Treegram compte les SPT dans la SEP ;
  la Fiabilisation les en retire, rules.COUNTED_IN).
- **Ouvertures de façade** : fenêtres, portes et percements sans menuiserie (baies libres, ouvertures de parking :
  IfcOpeningElement d'un mur, d'un bardage ou d'un mur-rideau) posés sur le contour de la SP (à `FACADE_REACH_M` près).
  Largeur : côté de l'emprise parallèle à la façade (un percement est souvent plus profond que large). Une
  ouverture que la maquette dit intérieure (`IsExternal` faux, Pset_WindowCommon / Pset_DoorCommon) n'en est
  jamais, même près du contour ; une ouverture dite extérieure en est une. Aire : grand côté de l'emprise × hauteur
  du maillage.
- **SFN** (façade) : périmètre de la SP × hauteur d'étage ; réservations = toutes les ouvertures de façade. Le
  maillage de la façade est percé de ces ouvertures (une baie vitrée se voit comme un trou dans la SFN). Sous une
  toiture, la façade s'arrête à la sous-face de ses pans principaux (roofs.py) : plus basse aux rives (murets), en
  pointe dans les pignons là où aucun niveau ne la recouvre (Myonaz 2 N03). Une lucarne ne la fait pas monter : le
  pan est prolongé sous elle, et ses fenêtres, au-dessus de la rive pour plus de moitié, sont des fenêtres de toit.
- **Fenêtres de toit** (velux, inclinées de plus de 15° sur la verticale, ou au-dessus de la façade sous la
  toiture pour plus de moitié : fenêtres des lucarnes) : ni réservations ni façade, mais des vitrages SRV du dernier
  niveau sous elles, à leur aire vraie et dans leur plan. Une fenêtre à cheval sur la rive compte en façade pour sa
  part sous la rive.
- **SRV** (vitrages extérieurs) : les fenêtres de façade, et les portes de façade vitrées (nom ou type :
  `envelope.glazed_doors`). Une porte d'entrée pleine, une porte de garage restent des réservations sans vitrage.
  Les vitrages intérieurs (cloisons vitrées, fenêtres intérieures) ne comptent pas. Treegram L'Orée : SRV ≈
  réservations, il ne distinguait pas les portes pleines.
- Dimensions des totaux SP, SEP et SPT : hauteur d'étage, périmètre, DeltaX / DeltaY (rectangle minimal).
"""

from __future__ import annotations

import math
import re

import numpy as np
import shapely
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from ..geom import Mesh
from .classify import EXTERIEUR, Decision, norm
from .ingest import Storey
from .interiors import NOT_OPENINGS, Level, Room, area_of
from .plans import Placed, Plan
from .roofs import ROOF_DROP_M, ROOF_GLASS_SHARE, ROOF_WINDOW_DEG, SLOPED_NZ, ROOF_WINDOW_REACH_M, Roofs, is_roof, quads_mesh, window_panel

SLIVER_M = 0.25        # ouverture morphologique : bandes plus fines (tranches de murs, débords) ignorées
MIN_ROOF_M2 = 2.0      # morceau de toiture plus petit : ignoré
FACADE_REACH_M = 0.6   # ouverture à moins de cette distance du contour de la SP : en façade
DUPLICATE_M = 0.6      # deux ouvertures plus proches qui se recouvrent vues de face : la même baie percée deux fois
DEFAULT_HEIGHT_M = 3.0  # hauteur d'un niveau sans niveau au-dessus (Treegram L'Orée : niveaux « Toiture »)
SAMPLE_M = 0.5          # pas des points du haut de la façade sous une toiture
MIN_WALL_M = 0.3        # couverture plus basse au-dessus du sol : ignorée (toiture d'un niveau inférieur)
GABLE_MAX_M = 8.0       # pignon plus haut au-dessus de la hauteur d'étage : ignoré


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
# NOT_OPENINGS (interiors) : « portes » qui n'en sont pas, garde-corps de rampe en IfcDoor (CGA L04) ; ni réservation,
# ni vitrage, ni baie dans la SP


def _external(it) -> bool | None:
    """IsExternal de la maquette (Pset_WindowCommon, Pset_DoorCommon), None s'il n'est pas renseigné."""
    v = next((v for k, v in (it.props or {}).items() if k.endswith(".IsExternal")), None)   # dont Hôte.IsExternal
    return v if isinstance(v, bool) else None


def _openings(level: Level, sp: BaseGeometry, glazed_doors: str = GLAZED_DOORS, band: tuple[float, float] | None = None,
              not_openings: str = NOT_OPENINGS, extra: list[Placed] = (), skip: set[str] = frozenset(),
              top=None) -> tuple[float, float, list, list, set[str]]:
    """(réservations m², vitrages m², panneaux des réservations, panneaux des vitrages, gid retenus) de la façade du
    niveau. `band` (z0, z1) : hauteur d'étage ; une ouverture n'y compte que pour sa part comprise (allège sous le sol
    fini, fenêtre à cheval sur deux étages), comme la façade brute qui n'a que cette hauteur ; `top` (points -> z) :
    haut de la façade sous une toiture. `extra` : ouvertures d'un autre niveau (lucarnes rangées dans la toiture) ;
    `skip` : fenêtres de toit. Sous une toiture, une ouverture est rognée au haut de la façade ; au-dessus pour plus
    de moitié (lucarne), elle n'est pas en façade."""
    edge = sp.boundary
    glazed = re.compile(glazed_doors)
    fake = re.compile(not_openings)
    found = []   # (aire, panneau, vitrée, emprise, gid) avant dédoublonnage
    for p in list(level.plan.of("IfcWindow", "IfcDoor", "IfcOpeningElement")) + list(extra):
        it = p.item
        if p.shape is None or it.z_min is None or it.z_max is None or it.gid in skip \
                or fake.search(norm(f"{it.name} {it.type_name}")):
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
        side = _along(edge, p.shape, ((a, b), (a, d)))
        width = ((side[1][0] - side[0][0]) ** 2 + (side[1][1] - side[0][1]) ** 2) ** 0.5
        zl, zh = (max(it.z_min, band[0]), min(it.z_max, band[1])) if band else (it.z_min, it.z_max)
        if top is not None and band:   # haut de la façade sous la toiture : rive (plus bas), pignon (plus haut)
            c = p.shape.centroid
            wall = float(top([(c.x, c.y)])[0])
            if wall < band[1] - 0.01 and min(it.z_max, wall) - zl < 0.5 * (it.z_max - zl):
                continue   # lucarne : au-dessus de la rive pour plus de moitié, fenêtre de toit
            if float(np.max(top([side[0], side[1]]))) > band[1] + 0.01:
                zh = it.z_max   # pignon sur sa largeur : jusqu'en haut de l'ouverture, rognée ensuite à la pente (_facade)
        if zh - zl <= 0.01:
            continue
        is_glass = it.ifc_class.startswith("IfcWindow") or not it.ifc_class.startswith("IfcOpeningElement") \
            and glazed.search(norm(f"{it.name} {it.type_name} {it.long_name}")) is not None
        found.append((width * (zh - zl), (side[0], side[1], zl, zh), is_glass, p.shape, it.gid))
    # Une même baie percée deux fois (bardage et mur derrière, CGA L04) : une seule réservation, la plus grande ;
    # vitrée si l'une des deux l'est (la fenêtre posée dans le percement du mur)
    found.sort(key=lambda f: -f[0])

    def span(panel):   # étendue le long de la façade (abscisse curviligne sur le contour de la SP)
        (ax, ay), (bx, by) = panel[0], panel[1]
        u = sorted((edge.project(shapely.Point(ax, ay)), edge.project(shapely.Point(bx, by))))
        return u[0], u[1]

    def twins(k, panel, shape) -> bool:
        """Même baie : vues de face, elles se recouvrent sur plus de la moitié de la plus petite, à la même hauteur."""
        if k[3].distance(shape) > DUPLICATE_M:
            return False
        # parallèles : deux fenêtres d'angle, sur deux façades perpendiculaires, sont deux baies
        (p0, p1), (q0, q1) = k[1][:2], panel[:2]
        ux, uy, vx, vy = p1[0] - p0[0], p1[1] - p0[1], q1[0] - q0[0], q1[1] - q0[1]
        norms = ((ux * ux + uy * uy) * (vx * vx + vy * vy)) ** 0.5
        if norms <= 0 or abs(ux * vx + uy * vy) / norms < 0.9:
            return False
        (a0, a1), (b0, b1) = span(k[1]), span(panel)
        width = min(a1 - a0, b1 - b0)
        height = min(k[1][3] - k[1][2], panel[3] - panel[2])
        return width > 0 and min(a1, b1) - max(a0, b0) > 0.5 * width \
            and min(k[1][3], panel[3]) - max(k[1][2], panel[2]) > 0.5 * height

    kept = []
    for m2, panel, is_glass, shape, gid in found:
        twin = next((k for k in kept if twins(k, panel, shape)), None)
        if twin is None:
            kept.append([m2, panel, is_glass, shape])
        elif is_glass:
            twin[2] = True
    resa = sum(k[0] for k in kept)
    glass = sum(k[0] for k in kept if k[2])
    return resa, glass, [k[1] for k in kept], [k[1] for k in kept if k[2]], {f[4] for f in found}


def _along(edge: BaseGeometry, shape: BaseGeometry, sides) -> tuple:
    """Côté du rectangle de l'ouverture le plus parallèle à la façade voisine ; à défaut de façade, le plus long."""
    def length(s):
        return ((s[1][0] - s[0][0]) ** 2 + (s[1][1] - s[0][1]) ** 2) ** 0.5
    try:
        at = edge.project(shape.centroid)
        p, q = edge.interpolate(max(at - 0.05, 0.0)), edge.interpolate(at + 0.05)
        fx, fy = q.x - p.x, q.y - p.y
        fl = (fx * fx + fy * fy) ** 0.5
    except (AttributeError, ValueError):
        fl = 0.0
    if fl < 1e-9:
        return max(sides, key=length)
    return max(sides, key=lambda s: abs((s[1][0] - s[0][0]) * fx + (s[1][1] - s[0][1]) * fy) / (fl * max(length(s), 1e-9)))


def facade_mesh(sp: BaseGeometry, z0: float, z1: float, holes: list, top=None) -> Mesh | None:
    """Façade du niveau : un panneau vertical par côté de la SP, percé des ouvertures qui s'y projettent. `top`
    (points -> z) : haut de la façade sous une toiture, échantillonné tous les `SAMPLE_M` ; à défaut z1."""
    return _facade(sp, z0, z1, holes, top)[0]


def _facade(sp: BaseGeometry, z0: float, z1: float, holes: list, top=None,
            panes: list = ()) -> tuple[Mesh | None, float, dict, Mesh | None]:
    """(maillage, aire brute, part de chaque ouverture dans la façade, maillage des vitrages `panes`) : voir
    facade_mesh. Sous une toiture, une ouverture est rognée au contour de la façade, côté par côté : une
    porte-fenêtre de pignon dont le linteau suit la pente ne dépasse pas du toit, et ne compte que sa part dans la
    façade (`part` : aire rognée / aire du rectangle, sur le côté le plus proche)."""
    v, idx, gross = [], [], 0.0
    gv, gi = [], []
    glass = {tuple(map(tuple, (q[0], q[1]))) + (q[2], q[3]) for q in panes}
    best: dict = {}   # ouverture -> (distance au côté, part rognée, polygone rogné, origine et direction du côté)
    for ring in _rings(sp):
        pts = list(ring.coords)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            if length < 1e-6:
                continue
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            if top is None:
                wall = box(0.0, z0, length, z1)
            else:
                us = np.linspace(0.0, length, max(2, math.ceil(length / SAMPLE_M) + 1))
                zs = top([(x0 + ux * u, y0 + uy * u) for u in us])
                wall = shapely.Polygon([(0.0, z0), (length, z0)] + list(zip(us[::-1], zs[::-1]))).buffer(0)
            cut = []
            for hole in holes:
                (ax, ay), (bx, by), zl, zh = hole
                # distance au côté (normale) et position le long du côté, pour les deux bouts de l'ouverture
                ua, ub = (ax - x0) * ux + (ay - y0) * uy, (bx - x0) * ux + (by - y0) * uy
                da, db = abs((ax - x0) * uy - (ay - y0) * ux), abs((bx - x0) * uy - (by - y0) * ux)
                if max(da, db) > 2 * FACADE_REACH_M or max(ua, ub) < 0 or min(ua, ub) > length:   # emprise à 0,6 m, axe un peu plus loin
                    continue
                rect = box(max(min(ua, ub), 0.0), zl, min(max(ua, ub), length), zh)
                cut.append(rect)
                key = tuple(map(tuple, (hole[0], hole[1]))) + (zl, zh)
                if rect.area > 1e-9 and (key not in best or max(da, db) < best[key][0]):
                    kept = rect.intersection(wall)
                    best[key] = (max(da, db), kept.area / rect.area, kept, (x0, y0, ux, uy))
            gross += wall.area
            face = wall.difference(shapely.union_all(cut)) if cut else wall
            if face.is_empty:
                continue
            for t in getattr(shapely.constrained_delaunay_triangles(face), "geoms", []):
                if t.area <= 1e-9 or not face.covers(t.representative_point()):
                    continue
                for u, z in list(t.exterior.coords)[:3]:
                    idx.append(len(v) // 3)
                    v += [x0 + ux * u, y0 + uy * u, z]
    for key, (_, _, kept, (x0, y0, ux, uy)) in best.items():   # vitrages rognés au contour de la façade
        if key not in glass or kept.is_empty:
            continue
        for t in getattr(shapely.constrained_delaunay_triangles(kept), "geoms", []):
            if t.area <= 1e-9 or not kept.covers(t.representative_point()):
                continue
            for u, z in list(t.exterior.coords)[:3]:
                gi.append(len(gv) // 3)
                gv += [x0 + ux * u, y0 + uy * u, z]
    part = {key: b[1] for key, b in best.items()}
    loose = vertical_mesh([q for q in panes if tuple(map(tuple, (q[0], q[1]))) + (q[2], q[3]) not in best])
    return (Mesh(v, idx) if idx else None), gross, part, _merge([Mesh(gv, gi) if gi else None, loose])


def _top(roofs: Roofs | None, z0: float, z1: float, above: BaseGeometry | None, sp: BaseGeometry | None = None,
         last: bool = False):
    """Haut de la façade d'un niveau en des points de son contour, là où aucun niveau ne le recouvre : la
    couverture en pente (pans principaux, la surface de la SPT) si elle est plus basse que l'étage (rive) ; au
    dernier niveau occupé (`last`), si elle est plus haute (pignon) ; sinon z1. Façade et toiture se rejoignent sans
    jour. Une toiture posée sur les murets sans déborder (Myonaz 2), une lucarne qui perce le pan : le plan du pan le
    plus proche y est prolongé (roofs.py, `EXTEND_M`) ; une toiture plate ne touche pas la façade."""
    if not roofs:
        return None
    near = above.buffer(FACADE_REACH_M) if above is not None else None

    def top(pts):
        pts = np.asarray(pts, float).reshape(-1, 2)
        free = np.array([near is None or not near.covers(shapely.Point(x, y)) for x, y in pts], dtype=bool)
        out = np.full(len(pts), z1)
        if not free.any():
            return out
        zt = roofs.top_z(pts, z0, extend=True, sloped=True)
        eave = free & ~np.isnan(zt) & (zt > z0 + MIN_WALL_M) & (zt < z1)
        out[eave] = zt[eave]
        if last:
            gable = free & ~eave & ~np.isnan(zt) & (zt > z1) & (zt < z1 + GABLE_MAX_M)
            out[gable] = zt[gable]
        return out
    return top


def _merge(meshes) -> Mesh | None:
    v, i = [], []
    for m in meshes:
        if m is None:
            continue
        k = len(v) // 3
        v += list(m.vertices)
        i += [k + j for j in m.indices]
    return Mesh(v, i) if i else None


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
            if d.code == "SEP":   # hors de la SP : un contour dessiné sur une pièce intérieure ne la compte pas deux fois
                contours.append(p.shape.difference(lv.sp) if lv.sp is not None else p.shape)
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

    roofs = {b: Roofs([p for lv in levels if lv.plan.storey.building == b for p in lv.plan.elements if is_roof(p)])
             for b in dict.fromkeys(lv.plan.storey.building for lv in levels)}
    for lv in levels:
        if lv.spt is None:
            continue
        r = roofs[lv.plan.storey.building]
        # seulement les toitures du niveau : une marquise du rez sous la toiture du dernier étage n'en est pas
        lv.spt_parts = [(part, r.developed(part, lv.z - ROOF_DROP_M) if r else part.area, r.drape(part, lv.z) if r else None)
                        for part in getattr(lv.spt, "geoms", [lv.spt])]

    env_cfg = (cfg_generation or {}).get("envelope") or {}
    windows = {}   # gid -> (Placed, inclinaison, aire, quadrilatère) des fenêtres du bâtiment
    for lv in levels:
        for p in lv.plan.of("IfcWindow"):
            if p.item.mesh is not None and (w := window_panel(p.item.mesh)) is not None:
                windows[p.item.gid] = (p, *w)
    # fenêtre de toit dans son ébrasement (joues verticales plus grandes que la vitre) : la vitre est parallèle au pan
    for g, (p, *_w) in list(windows.items()):
        r = roofs.get(p.item.building)
        if _w[0] <= ROOF_WINDOW_DEG and _under_roof(r, p) and (n := r.normal_at(tuple(p.shape.centroid.coords[0]))) is not None                 and n[2] < SLOPED_NZ and (w := window_panel(p.item.mesh, n)) is not None and w[1] >= ROOF_GLASS_SHARE * _w[1]:
            windows[g] = (p, *w)
    tilted = {g for g, w in windows.items() if w[1] > ROOF_WINDOW_DEG and _under_roof(roofs.get(w[0].item.building), w[0])}
    taken: set[str] = set()
    for b in dict.fromkeys(lv.plan.storey.building for lv in levels):
        own = sorted((lv for lv in levels if lv.plan.storey.building == b), key=lambda lv: lv.z)
        # ouvertures d'un niveau sans SP (toiture) : comptées dans la façade du niveau dont elles percent la hauteur
        loose = [p for lv in own if lv.sp is None for p in lv.plan.of("IfcWindow", "IfcDoor", "IfcOpeningElement")]
        top_level = max((lv for lv in own if lv.sp is not None), key=lambda lv: lv.z, default=None)
        tops = {}   # niveau -> haut de sa façade sous la toiture (fenêtres de toit des lucarnes)
        for k, lv in enumerate(own):
            h = lv.height or lv.plan.storey.height or DEFAULT_HEIGHT_M
            if lv.sp is None:
                lv.envelope = {"GrossArea": 0.0, "NetArea": 0.0, "ReservationsArea": 0.0, "Perimeter": 0.0,
                               "GrossHeight": round(h, 3), "SRV": 0.0}
                continue
            above = next((u.sp for u in own[k + 1:] if u.sp is not None), None)
            top = _top(roofs[b], lv.z, lv.z + h, above, lv.sp, last=lv is top_level)
            tops[id(lv)] = top
            resa, glass, holes, panes, used = _openings(
                lv, lv.sp, env_cfg.get("glazed_doors") or GLAZED_DOORS, (lv.z, lv.z + h),
                env_cfg.get("not_openings") or NOT_OPENINGS, extra=loose, skip=tilted, top=top)
            taken |= used
            lv.facade, gross, part, lv.glazing = _facade(lv.sp, lv.z, lv.z + h, holes, top, panes)
            if top is not None:   # ouvertures rognées au contour de la façade (linteau en pente, pignon)
                def m2(q):
                    return ((q[1][0] - q[0][0]) ** 2 + (q[1][1] - q[0][1]) ** 2) ** 0.5 * (q[3] - q[2])                         * part.get(tuple(map(tuple, (q[0], q[1]))) + (q[2], q[3]), 1.0)
                resa, glass = sum(m2(q) for q in holes), sum(m2(q) for q in panes)
            # sous une toiture en pente, la façade n'est plus périmètre × hauteur d'étage : la SFN porte sa hauteur
            # moyenne (contrôle E3 de la Fiabilisation), les totaux SP, SEP et SPT la hauteur d'étage
            mean = gross / lv.sp.length if top is not None and lv.sp.length > 0 else h
            lv.envelope = {"GrossArea": round(gross, 2), "NetArea": round(max(gross - resa, 0.0), 2),
                           "ReservationsArea": round(resa, 2), "Perimeter": round(lv.sp.length, 2),
                           "GrossHeight": round(mean, 3), "StoreyHeight": round(h, 3), "SRV": round(glass, 2)}
        holes = _roof_windows(own, roofs[b], windows, tilted, taken, tops)
        # la SPT est percée au droit des fenêtres de toit (comme la façade de ses ouvertures) ; son aire reste brute
        if holes and roofs[b]:
            cut = shapely.union_all([shapely.Polygon([q[:2] for q in quad]).buffer(0) for quad in holes])
            for lv in own:
                if lv.spt_parts:
                    lv.spt_parts = [(part, dev, roofs[b].drape(part.difference(cut), lv.z) if mesh is not None else None)
                                    for part, dev, mesh in lv.spt_parts]


def _under_roof(roofs: Roofs | None, p: Placed) -> bool:
    """Fenêtre juste sous la couverture ; loin dessous (fenêtre inclinée d'un niveau inférieur, saut-de-loup), non.
    La couverture est lue autour de la fenêtre : une lucarne perce la toiture, il n'y en a pas au droit de sa vitre."""
    if not roofs or p.item.z_max is None:
        return False
    ring = p.shape.buffer(1.0).exterior if hasattr(p.shape.buffer(1.0), "exterior") else p.shape.envelope.exterior
    pts = [p.shape.centroid] + [ring.interpolate(d) for d in np.arange(0.0, ring.length, SAMPLE_M)]
    z = roofs.top_z([(q.x, q.y) for q in pts])
    return not np.isnan(z).all() and p.item.z_max >= np.nanmin(z) - ROOF_WINDOW_REACH_M


def _laid(roofs: Roofs, p: Placed, area: float, quad: list) -> list | None:
    """Vitre verticale d'une lucarne couchée dans le pan sous elle, à la même aire : même largeur, le long de la
    pente. La lucarne (pans secondaires) n'est pas dans la toiture simplifiée : debout, la vitre en dépasserait."""
    c = p.shape.centroid
    n = roofs.normal_at((c.x, c.y))
    z = roofs.top_z([(c.x, c.y)], extend=True)[0]
    if n is None or np.isnan(z):
        return None
    q = np.asarray(quad, float)
    width = float(np.linalg.norm(q[1] - q[0]))
    if width <= 1e-6:
        return None
    u = np.array([q[1][0] - q[0][0], q[1][1] - q[0][1], 0.0])
    u = u - n * (u @ n)               # largeur de la vitre, dans le pan
    u /= np.linalg.norm(u)
    v = np.cross(n, u)                # le long de la pente
    length = area / width
    o = np.array([c.x, c.y, z])
    return [(o + u * su * width / 2 + v * sv * length / 2).tolist() for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def _roof_windows(own: list[Level], roofs: Roofs, windows: dict, tilted: set[str], taken: set[str],
                  tops: dict | None = None) -> list:
    """Fenêtres de toit du bâtiment : inclinées, ou hors façade sous la toiture et au-dessus de la façade (de
    l'étage, ou de la rive pour plus de moitié : lucarne). Vitrages SRV du dernier niveau occupé sous elles, à leur
    aire vraie et dans leur plan. Renvoie leurs quadrilatères (trous de la SPT)."""
    if not roofs:
        return []
    quads = []
    cover = shapely.union_all([r.shape for r in roofs.parts])
    gids = {p.item.gid for lv in own for p in lv.plan.of("IfcWindow")}
    for g in gids:
        p, tilt, area, quad = windows.get(g, (None, 0, 0, None))
        if p is None or g in taken or _external(p.item) is False or not p.shape.intersects(cover) \
                or not _under_roof(roofs, p):
            continue
        host = next((lv for lv in reversed(own) if lv.sp is not None and lv.z <= p.item.z_min + 0.01), None)
        if host is None:
            continue
        h = host.height or host.plan.storey.height or DEFAULT_HEIGHT_M
        wall = host.z + h
        if (top := (tops or {}).get(id(host))) is not None:   # sous la toiture : la rive, plus basse que l'étage
            c = p.shape.centroid
            wall = min(wall, float(top([(c.x, c.y)])[0]))
        if g not in tilted and 0.5 * (p.item.z_min + p.item.z_max) < wall - 0.01:
            continue   # verticale sous le haut de la façade, hors façade : fenêtre intérieure
        if g not in tilted and (laid := _laid(roofs, p, area, quad)) is not None:
            quad = laid   # fenêtre de lucarne : la lucarne n'est pas dans la toiture simplifiée, la vitre y est couchée
        # posée à fleur de la couverture (la SPT percée à son droit) : ni au-dessus, ni en dessous
        zs = roofs.top_z([q[:2] for q in quad], extend=True)
        quad = [[q[0], q[1], float(z) if not np.isnan(z) else q[2]] for q, z in zip(quad, zs)]
        host.glazing = _merge([host.glazing, quads_mesh([quad])])
        quads.append(quad)
        host.envelope["SRV"] = round(host.envelope.get("SRV", 0.0) + area, 2)
        host.envelope["RoofWindowsArea"] = round(host.envelope.get("RoofWindowsArea", 0.0) + area, 2)
    return quads
