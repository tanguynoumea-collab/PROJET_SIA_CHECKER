"""Chaîne USPI par logement (V4_PLAN §3.1, phase 23), au modèle Treegram (relevé sur L'Orée, 314 logements).

Treegram écrit, pour chaque logement d'un niveau, cinq surfaces élémentaires `Bât_Niv_Apart-nn_CODE`, avec
`ApartmentByTgm` et, sur la SNH, `Bedrooms` :

- **SNH** = somme des SUP du logement (L'Orée : égalité au millième sur les 314 logements) ; maillage : ces SUP ;
- **SHA** = SNH + cloisons entre ces SUP (L'Orée : SHA / SNH ≈ 1,02) : le contour intérieur du logement dessiné
  dans la maquette s'il y en a un (espace de nature logement portant le lot, Myonaz : « LOG », catégorie
  « Surface utile principal » ; le MDP l'appelle SVN), sinon les SUP fermées sur l'épaisseur des cloisons
  (`partition_m`), sans les gaines et autres locaux non SUP ;
- **SBH** = SHA + murs extérieurs et mitoyens (L'Orée : SBH / SHA ≈ 1,16, un seul contour) : le contour brut du
  logement dessiné s'il y en a un (espace « surface de plancher » portant le lot, La Bâtie : « 3P », « 4P »),
  sinon le logement étendu dans ses murs jusqu'à `wall_max_m`, en même temps que les logements et les locaux
  communs voisins, qui se partagent ainsi les mitoyens. Un contour brut de tout le niveau (Myonaz : « SBH »,
  `sbh_contour`) borne cette croissance à la place de la SP ;
- **SVN** = SHA + SEU du logement, **SVB** = SBH + SEU (L'Orée : écart égal aux SEU au centième) ;
- **Bedrooms** = nombre de pièces de type Chambre.

Totaux de niveau : SNH = SUP + SUS du niveau, logement ou non (L'Orée : SNH du sous-sol = SUS) ; SHA, SBH, SVN
et SVB = somme des logements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from .classify import Decision, norm
from .interiors import Level, area_of

CODES = ("SNH", "SHA", "SBH", "SVN", "SVB")
GROSS, INNER = "plancher", "logement"      # natures des contours dessinés : brut (SBH), intérieur (SHA)


@dataclass
class Lot:
    key: str
    areas: dict[str, float] = field(default_factory=dict)        # code -> m²
    shapes: dict[str, BaseGeometry] = field(default_factory=dict)
    bedrooms: int = 0
    sbh_source: str = ""                                          # « contour dessiné » | « murs partagés »


def _union(shapes) -> BaseGeometry | None:
    shapes = [s for s in shapes if s is not None and not s.is_empty]
    return shapely.union_all(shapes) if shapes else None


def _area(g: BaseGeometry | None) -> float:
    return g.area if g is not None else 0.0


GRID_M = 0.001   # opérations sur une grille au millimètre : GEOS échoue sinon sur les bandes de murs très fines
EMPTY = Polygon()


def _poly(g: BaseGeometry | None) -> BaseGeometry:
    """Surfaces seules, valides, sur la grille : les opérations sur des bandes fines rendent aussi des lignes."""
    if g is None or g.is_empty:
        return EMPTY
    g = shapely.make_valid(g)
    parts = [x for x in getattr(g, "geoms", [g]) if isinstance(x, (Polygon, MultiPolygon))]
    if not parts:
        return EMPTY
    g = shapely.set_precision(shapely.union_all(parts), GRID_M)
    parts = [x for x in getattr(g, "geoms", [g]) if isinstance(x, (Polygon, MultiPolygon)) and x.area > 1e-6]
    return shapely.union_all(parts) if parts else EMPTY


def _and(a, b):
    return _poly(shapely.intersection(_poly(a), _poly(b), grid_size=GRID_M))


def _minus(a, b):
    return _poly(shapely.difference(_poly(a), _poly(b), grid_size=GRID_M))


def _grow(regions: dict[str, BaseGeometry], limit: BaseGeometry, reach: float, step: float) -> dict[str, BaseGeometry]:
    """Croissance simultanée des régions par pas de `step` jusqu'à `reach`, dans `limit` et sans empiéter sur les
    autres : un mur entre deux régions est partagé à mi-épaisseur, un mur de façade revient à sa seule voisine."""
    limit = _poly(limit)
    keys = list(regions)
    out = [_and(regions[k], limit) for k in keys]
    for _ in range(max(1, round(reach / step))):
        tree = shapely.STRtree(out)
        grown = []
        for n, g in enumerate(out):
            ring = _and(g.buffer(step, join_style="mitre"), limit)
            near = [out[j] for j in tree.query(ring) if j != n and not out[j].is_empty]
            grown.append(_minus(ring, shapely.union_all(near, grid_size=GRID_M)) if near else ring)
        # une bande atteinte au même pas par deux régions n'est à aucune des deux (pas de surface comptée deux fois)
        tree = shapely.STRtree(grown)
        cut = [[] for _ in grown]
        for a in range(len(grown)):
            for b in tree.query(grown[a]):
                if b > a:
                    both = _and(grown[a], grown[b])
                    if not both.is_empty:
                        cut[a].append(both)
                        cut[b].append(both)
        grown = [_minus(g, shapely.union_all(c, grid_size=GRID_M)) if c else g for g, c in zip(grown, cut)]
        out = [_poly(shapely.union(o, g, grid_size=GRID_M)) for o, g in zip(out, grown)]
    return {k: (g if not g.is_empty else None) for k, g in zip(keys, out)}


def _text(it) -> str:
    return " ".join(norm(str(v)) for v in (it.name, it.long_name, *(it.props or {}).values()) if v)


def build(level: Level, decisions: dict[str, Decision], cfg_generation: dict | None = None) -> list[Lot]:
    """Logements du niveau, triés par lot (même ordre que les `Apart-nn` de l'assemblage)."""
    cfg = (cfg_generation or {}).get("uspi") or {}
    sbh_rx = re.compile(cfg["sbh_contour"]) if cfg.get("sbh_contour") else None
    partition = float(cfg.get("partition_m", 0.2))
    reach, step = float(cfg.get("wall_max_m", 0.6)), float(cfg.get("step_m", 0.05))
    # un logement a des SUP : un lot de caves au sous-sol (La Bâtie : « LUP ») n'a pas de chaîne USPI
    keys = sorted({r.placed.item.lot for r in level.rooms if r.decision.in_lot and r.decision.code == "SUP"})
    if not keys:
        return []
    lots = {k: Lot(k) for k in keys}
    rooms = {k: [r for r in level.rooms if r.decision.in_lot and r.placed.item.lot == k] for k in keys}

    declared = ((cfg_generation or {}).get("sp") or {}).get("area_source", "plan") == "declared"

    def drawn(nature: str) -> tuple[dict[str, BaseGeometry | None], dict[str, float]]:
        """Contours de cette nature par lot, et leur aire comme pour une pièce (déclarée : Myonaz N03, combles)."""
        own = {k: [p for p in level.plan.spaces if p.shape is not None and p.item.lot == k
                   and decisions[p.item.gid].nature == nature] for k in keys}
        return ({k: _union(p.shape for p in v) for k, v in own.items()},
                {k: sum(area_of(p, declared) for p in v) for k, v in own.items()})

    (inner, inner_m2), (gross, gross_m2) = drawn(INNER), drawn(GROSS)
    whole = _union(p.shape for p in level.plan.spaces if p.shape is not None and sbh_rx is not None
                   and decisions[p.item.gid].nature in (GROSS, INNER) and sbh_rx.search(_text(p.item)))
    for k, lot in lots.items():
        sup = [r for r in rooms[k] if r.decision.code == "SUP"]
        lot.areas["SNH"] = sum(r.area for r in sup)
        lot.bedrooms = sum(1 for r in rooms[k] if r.decision.type == "Chambre")
        snh = _union(r.placed.shape for r in sup)
        lot.shapes["SNH"] = snh
        if inner[k] is not None:
            lot.shapes["SHA"] = inner[k]
            lot.areas["SHA"] = max(lot.areas["SNH"], inner_m2[k])
        elif snh is not None:
            r = partition / 2
            closed = snh.buffer(r, join_style="mitre").buffer(-r, join_style="mitre")
            not_sup = _union(x.placed.shape for x in level.rooms if x.decision.code != "SUP")
            sha = _union([closed.difference(not_sup) if not_sup is not None else closed, snh])
            if level.sp is not None:
                sha = _union([sha.intersection(level.sp), snh])
            lot.shapes["SHA"] = sha
            lot.areas["SHA"] = lot.areas["SNH"] + max(0.0, _area(sha) - _area(snh))
        else:
            lot.areas["SHA"] = lot.areas["SNH"]

    # SBH : contour brut dessiné du logement, sinon croissance dans les murs avec les voisins
    todo = [k for k in keys if gross[k] is None]
    grown = {}
    limit = whole if whole is not None else level.sp
    if todo and limit is not None:
        regions = {k: _union(r.placed.shape for r in rooms[k]) for k in keys}
        regions = {k: g for k, g in regions.items() if g is not None}
        commons = [r for r in level.rooms if not r.decision.in_lot]
        regions |= {f"~{n}": r.placed.shape for n, r in enumerate(commons)}
        grown = _grow(regions, limit, reach, step)
    for k, lot in lots.items():
        if gross[k] is not None:
            sbh, lot.sbh_source = gross[k], "contour du logement"
        else:
            sbh = grown.get(k)
            lot.sbh_source = "contour du niveau, murs partagés" if whole is not None else "murs partagés"
        lot.shapes["SBH"] = sbh
        lot.areas["SBH"] = max(gross_m2[k] if gross[k] is not None else _area(sbh), lot.areas["SHA"])
        seu = [x for x in level.exteriors if x.decision.in_lot and x.placed.item.lot == k and x.decision.code == "SEU"]
        se, se_shape = sum(x.area for x in seu), _union(x.placed.shape for x in seu)
        lot.areas["SVN"] = lot.areas["SHA"] + se
        lot.areas["SVB"] = lot.areas["SBH"] + se
        lot.shapes["SVN"] = _union([lot.shapes.get("SHA"), se_shape])
        lot.shapes["SVB"] = _union([sbh, se_shape])
    return [lots[k] for k in keys]
