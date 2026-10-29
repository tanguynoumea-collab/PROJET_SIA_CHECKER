"""Surfaces de construction modélisées depuis l'IFC : SC et SEC (V4.1, décision du 29.10.2026).

Treegram ne crée ni SC ni SEC : il les considère déduites, et la Fiabilisation les voit comme le résidu des règles
R1 (SP = SN + SC) et R3 (SEP = SEN + SEC), qui mêle alors la construction et les surfaces oubliées. Les modéliser
laisse au résidu les seules vraies zones de SP ou de SEP non classées.

**SC** (SIA 416 §2.2), dans la SP du niveau et hors des pièces :
- **SCP** (porteuse, §2.2.1) : murs porteurs (`Pset_WallCommon.LoadBearing` vrai) et poteaux ;
- **SCN** (non porteuse, §2.2.2) : murs non porteurs ou sans indication, murs-rideaux ;
- les baies des portes et fenêtres comptent avec le mur qu'elles percent ;
- les bandes de la SP plus étroites que `THIN_M` (jeu entre un espace Revit et son mur, enduits, cloisons non
  dessinées) sont de la construction : SCN avec les murs du niveau, **SC** (non modélisée) sur un niveau sans aucun
  mur dans la maquette (Afiro). Une feuille SC à côté de SCP / SCN masquerait leur somme (rules._effective).
Ce qui reste encore est la **SP non classée** : aucune surface ne la couvre, la plaque SP la montre en 3D.

**Aire déclarée** : les pièces comptent leur aire IFC (`sp.area_source: declared`, comme les MDP), plus petite que
leur emprise sous un rampant (Myonaz N03 : 18 et 28 m²), parfois plus grande. Cet écart est reporté sur l'aire de
la construction non porteuse (SCN, ou SC), comme dans les MDP où il tombe dans la SC implicite : le résidu R1 ne
garde ainsi que les zones non classées. Idem pour les extérieurs (SECN).

**SEC** (SIA 416 §3.2), dans la SEP du niveau (toitures SPT exclues) et hors des extérieurs : garde-corps pleins
et murets, **SECP** s'ils sont porteurs, sinon **SECN**, avec les bandes minces autour des extérieurs (dalle sous
le garde-corps, nez de dalle). Ce qui reste est la **SEP non classée**.
"""

from __future__ import annotations

import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

import hashlib
import re

from .classify import EXTERIEUR, PIECE, Decision, norm
from .ingest import Item
from .interiors import Level, Room, bays
from .plans import Placed

THIN_M = 0.6        # bande plus étroite : construction non modélisée (mur le plus épais, uspi.wall_max_m)
MIN_PART_M2 = 0.05  # morceau plus petit : ignoré (arrondis des contours)
MIN_GAP_M2 = 0.5    # zone non classée plus petite : non signalée
DEDUCED_M2 = 2.0    # zone non classée plus grande : un espace déduit, proposé à la classification
DEDUCED_CONFIDENCE = 0.5   # toujours à trancher (onglet Espaces, IA ou manuel)
GARAGE = re.compile(r"\b(garage|parking|portail)\b")
GRID_M = 0.001      # grille des opérations : sans elle, GEOS échoue sur des contours presque confondus (Myonaz 2)


def _poly(g: BaseGeometry) -> BaseGeometry:
    """Polygones seuls d'une géométrie rendue valide (make_valid laisse des segments, que la grille refuse)."""
    g = shapely.make_valid(g)
    parts = [p for p in shapely.get_parts(g) if p.geom_type in ("Polygon", "MultiPolygon")] if not g.is_empty else []
    return shapely.union_all(parts) if parts else Polygon()


def _u(geoms) -> BaseGeometry:
    return _poly(shapely.union_all([_poly(g) for g in geoms], grid_size=GRID_M))


def _i(a: BaseGeometry, b: BaseGeometry) -> BaseGeometry:
    return _poly(shapely.intersection(_poly(a), _poly(b), grid_size=GRID_M))


def _d(a: BaseGeometry, b: BaseGeometry) -> BaseGeometry:
    return _poly(shapely.difference(_poly(a), _poly(b), grid_size=GRID_M))


def _load_bearing(item) -> bool:
    v = next((v for k, v in (item.props or {}).items() if k.endswith(".LoadBearing")), None)
    return v is True


def _clean(g: BaseGeometry | None) -> BaseGeometry | None:
    if g is None or g.is_empty:
        return None
    parts = [p for p in getattr(g, "geoms", [g]) if isinstance(p, Polygon) and p.area >= MIN_PART_M2]
    return _u(parts) if parts else None


def _area(g: BaseGeometry | None) -> float:
    return g.area if g is not None else 0.0


def _gaps(g: BaseGeometry | None) -> BaseGeometry | None:
    parts = [p for p in getattr(g, "geoms", [g]) if g is not None and isinstance(p, Polygon) and p.area >= MIN_GAP_M2]
    return _u(parts) if parts else None


def interior(lv: Level) -> dict:
    """{SCP, SCN, SC, gaps} du niveau : géométries (ou None) ; gaps = SP non classée."""
    if lv.sp is None:
        return {}
    sp = lv.sp
    taken = _u([r.placed.shape for r in lv.rooms]) if lv.rooms else Polygon()
    walls = [p for p in lv.plan.of("IfcWall", "IfcCurtainWall") if p.shape is not None]
    bearing = [p.shape for p in walls if _load_bearing(p.item)] + \
              [p.shape for p in lv.plan.of("IfcColumn") if p.shape is not None]
    other = [p.shape for p in walls if not _load_bearing(p.item)]
    # baie : avec le mur qu'elle perce, le plus long contact l'emporte
    for bay in bays(lv.plan):
        touch_b = sum(_i(bay.buffer(0.05), w).area for w in bearing)
        touch_o = sum(_i(bay.buffer(0.05), w).area for w in other)
        (bearing if touch_b >= touch_o and touch_b > 0 else other).append(bay)
    out = {}
    for code, geoms in (("SCP", bearing), ("SCN", other)):
        g = _d(_i(_u(geoms), sp), taken) if geoms else None
        out[code] = _clean(g)
        if out[code] is not None:
            taken = _u([taken, out[code]])
    rest = _d(sp, taken)
    thick = _i(rest.buffer(-THIN_M / 2, join_style="mitre").buffer(THIN_M / 2, join_style="mitre"), rest)
    thin = _clean(_d(rest, thick))
    target = "SCN" if (out["SCP"] is not None or out["SCN"] is not None) else "SC"
    out[target] = _clean(_u([g for g in (out.get(target), thin) if g is not None])) \
        if (out.get(target) is not None or thin is not None) else None
    out["gaps"] = _gaps(thick)
    out["delta"] = (target, sum(r.placed.area - r.area for r in lv.rooms))
    return out


def exterior(lv: Level) -> dict:
    """{SECP, SECN, gaps} du niveau ; gaps = SEP non classée (toitures SPT exclues)."""
    if lv.sep is None:
        return {}
    region = _d(lv.sep, lv.spt) if lv.spt is not None else lv.sep
    taken = _u([r.placed.shape for r in lv.exteriors]) if lv.exteriors else Polygon()
    if lv.sp is not None:
        taken = _u([taken, lv.sp])
    out = {}
    elems = [p for p in lv.plan.of("IfcRailing", "IfcWall") if p.shape is not None]
    for code, geoms in (("SECP", [p.shape for p in elems if _load_bearing(p.item)]),
                        ("SECN", [p.shape for p in elems if not _load_bearing(p.item)])):
        g = _d(_i(_u(geoms), region), taken) if geoms else None
        out[code] = _clean(g)
        if out[code] is not None:
            taken = _u([taken, out[code]])
    # bandes minces autour des extérieurs (dalle sous le garde-corps, nez de dalle) : construction externe, SECN
    rest = _d(region, taken)
    thick = _i(rest.buffer(-THIN_M / 2, join_style="mitre").buffer(THIN_M / 2, join_style="mitre"), rest)
    thin = _clean(_d(rest, thick))
    if thin is not None:
        out["SECN"] = _clean(_u([g for g in (out["SECN"], thin) if g is not None]))
    out["gaps"] = _gaps(thick)
    out["delta"] = ("SECN", sum(r.placed.area - r.area for r in lv.exteriors))
    return out


def build(levels: list[Level]) -> None:
    """Complète chaque niveau (en place) : `Level.construction` = {code: (géométrie, aire)}, l'aire comprenant
    l'écart entre emprise et aire déclarée des pièces ; `Level.unclassified` = SP et SEP non classées."""
    for lv in levels:
        inner, outer = interior(lv), exterior(lv)
        lv.construction, lv.unclassified = {}, {"SP": inner.get("gaps"), "SEP": outer.get("gaps")}
        for part in (inner, outer):
            if not part:
                continue
            target, delta = part["delta"]
            for code, g in part.items():
                if code in ("gaps", "delta") or g is None:
                    continue
                lv.construction[code] = (g, g.area + (delta if code == target else 0.0))
            if target not in lv.construction and abs(delta) > 0:
                lv.construction[target] = (None, delta)   # écart sans géométrie : l'aire seule, pour le bilan
            lv.construction[f"ecart_{target}"] = (None, delta)


def _gid(lv: Level, g: BaseGeometry, kind: str) -> str:
    """Identifiant stable d'un espace déduit : niveau, nature et centre arrondi au demi-mètre."""
    c = g.centroid
    key = f"{lv.plan.storey.gid}|{kind}|{round(c.x * 2) / 2}|{round(c.y * 2) / 2}"
    return "deduit-" + hashlib.sha1(key.encode()).hexdigest()[:16]


def deduce(levels: list[Level], decisions: dict, apply=None) -> list[Item]:
    """Zones non classées de plus de `DEDUCED_M2` -> espaces déduits, à trancher (décision du 29.10.2026, Myonaz 1 :
    local fermé de 32 m² sans IfcSpace). SP : une SUS, Parking si une porte de garage la dessert, sinon LocauxCommuns ;
    SEP : une SEU Terrasse. `apply(decisions)` applique le journal (une décision manuelle ou IA sur l'espace déduit
    vaut aux générations suivantes : son identifiant ne dépend que de sa position). Renvoie les nouveaux items."""
    items = []
    for lv in levels:
        st = lv.plan.storey
        for kind, gaps in (lv.unclassified or {}).items():
            for g in getattr(gaps, "geoms", [gaps]) if gaps is not None else []:
                if g.area < DEDUCED_M2:
                    continue
                gid = _gid(lv, g, kind)
                if kind == "SP":
                    doors = [p for p in lv.plan.of("IfcDoor") if p.shape is not None and p.shape.distance(g) < 0.5]
                    garage = any(GARAGE.search(norm(f"{p.item.name} {p.item.type_name}")) for p in doors)
                    nature, code, typ = PIECE, "SUS", "Parking" if garage else "LocauxCommuns"
                    why = "porte de garage" if garage else "aucun indice"
                else:
                    nature, code, typ, why = EXTERIEUR, "SEU", "Terrasse", "aucun indice"
                item = Item(gid, "IfcSpace", "Zone sans espace", st.building, st.gid, storey_by="aucun",
                            long_name=f"Zone sans espace ({kind}, {g.area:.1f} m²)")
                decisions[gid] = Decision(gid, nature, code, typ, "construction", DEDUCED_CONFIDENCE,
                                          f"zone de {kind} qu'aucun espace de la maquette ne couvre : espace déduit "
                                          f"({why}), à confirmer")
                items.append((lv, item, g))
    if apply is not None:
        apply(decisions)
    for lv, item, g in items:
        d = decisions[item.gid]
        room = Room(Placed(item, g), d, g.area)
        (lv.rooms if d.nature == PIECE else lv.exteriors).append(room)
    return [it for _, it, _ in items]


def summary(lv: Level) -> dict:
    """Aires pour le rapport de génération : construction par code (écart d'aire déclarée compris), écart reporté,
    SP et SEP non classées."""
    out = {k: round(a, 2) for k, (_, a) in sorted(lv.construction.items())}
    for k, g in lv.unclassified.items():
        out[f"{k}_non_classee"] = round(_area(g), 2)
    return out
