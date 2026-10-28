"""Extérieurs, toitures et enveloppe d'un niveau (V4_PLAN §3.1, phase 22), au modèle Treegram (relevé L'Orée).

- **SEU, SED, SEI** : une surface élémentaire par espace extérieur de la maquette (balcon, loggia, terrasse,
  coursive), avec son logement. Aire déclarée, à défaut l'emprise.
- **Contour SEP** : un « plancher externe » dessiné (Myonaz, La Bâtie) n'est pas une surface élémentaire ; il
  entre dans la SEP du niveau, comme chez Treegram où la SEP n'existe qu'en total.
- **SPT** (toitures, code Treegram) : ce que la SP du niveau inférieur laisse à découvert, posé sur le niveau
  du dessus (Treegram : toiture d'attique sur l'attique, toiture du dernier étage sur le niveau « Toiture »,
  créé s'il manque), moins les extérieurs dessinés (une terrasse accessible est une SEU). Au-dessus d'un
  sous-sol, ce n'est pas une toiture mais une dalle sur sous-sol : elle reste dans la SEP du niveau, sans
  catégorie (Treegram L'Orée : abords du rez, signalés par A1).
- **SEP** du niveau : union des extérieurs, des contours, des dalles sur sous-sol et des toitures (Treegram
  compte les SPT dans la SEP ; la Fiabilisation les en retire, rules.COUNTED_IN).
- **SFN** (façade) : périmètre de la SP × hauteur d'étage ; réservations = fenêtres et portes de la façade
  (largeur de l'emprise × hauteur du maillage) ; **SRV** (vitrages) = ces mêmes ouvertures, comme chez Treegram.
- Dimensions des totaux SP, SEP et SPT : hauteur d'étage, périmètre, DeltaX / DeltaY (rectangle minimal).
"""

from __future__ import annotations

import shapely
from shapely.geometry.base import BaseGeometry

from .classify import EXTERIEUR, Decision
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
        top = max(occupied, key=lambda lv: lv.plan.storey.elevation)
        if any(lv.plan.storey.elevation > top.plan.storey.elevation for lv in own):
            continue
        st = top.plan.storey
        roof = Storey(f"toiture:{b}", "Toiture", b, st.elevation + (st.height or DEFAULT_HEIGHT_M), None, st.rank + 1)
        out.append(Level(Plan(roof)))
    return out


def _openings(level: Level, sp: BaseGeometry) -> tuple[float, float]:
    """(réservations, vitrages) en m² : fenêtres et portes posées sur le contour de la SP."""
    edge = sp.boundary
    resa = glass = 0.0
    for p in level.plan.of("IfcWindow", "IfcDoor"):
        it = p.item
        if p.shape is None or it.z_min is None or it.z_max is None or p.shape.distance(edge) > FACADE_REACH_M:
            continue
        r = p.shape.minimum_rotated_rectangle
        c = list(r.exterior.coords) if hasattr(r, "exterior") else []
        width = max((((c[i + 1][0] - c[i][0]) ** 2 + (c[i + 1][1] - c[i][1]) ** 2) ** 0.5 for i in range(len(c) - 1)),
                    default=0.0)
        resa += width * (it.z_max - it.z_min)
    # Treegram : vitrages ≈ réservations (L'Orée E09 N03 : SRV 246,2 m², réservations 244,4 m²) ; portes-fenêtres
    # et portes vitrées comprises
    glass = resa
    return resa, glass


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
        own = sorted((lv for lv in levels if lv.plan.storey.building == b), key=lambda lv: lv.plan.storey.elevation)
        for below, lv in zip(own, own[1:]):
            if below.sp is None:
                continue
            covered = [g for g in (lv.sp, lv.sep) if g is not None]
            free = _clean(below.sp.difference(shapely.union_all(covered)) if covered else below.sp)
            if free is None:
                continue
            if below.plan.storey.gid in below_ground:
                lv.sep = shapely.union_all([g for g in (lv.sep, free) if g is not None])   # dalle sur sous-sol
            else:
                lv.spt = free
                lv.sep = shapely.union_all([g for g in (lv.sep, free) if g is not None])

    for lv in levels:
        st = lv.plan.storey
        h = st.height or DEFAULT_HEIGHT_M
        if lv.sp is None:
            lv.envelope = {"GrossArea": 0.0, "NetArea": 0.0, "ReservationsArea": 0.0, "Perimeter": 0.0,
                           "GrossHeight": round(h, 3), "SRV": 0.0}
            continue
        perimeter = lv.sp.length
        resa, glass = _openings(lv, lv.sp)
        gross = perimeter * h
        lv.envelope = {"GrossArea": round(gross, 2), "NetArea": round(max(gross - resa, 0.0), 2),
                       "ReservationsArea": round(resa, 2), "Perimeter": round(perimeter, 2),
                       "GrossHeight": round(h, 3), "SRV": round(glass, 2)}
