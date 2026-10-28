"""Audit d'entrée et inventaire d'une maquette architecte (V4_PLAN §7, phase 20).

Avant toute génération, la maquette est passée en revue : ce qui manque ou se contredit est listé, avec les
espaces en cause. Un point « bloquant » interdit la génération (pas d'espaces, pas de niveaux) ; une « alerte »
la laisse faire mais fragilise le résultat ; une « info » décrit la maquette.

| Code | Gravité | Constat |
|---|---|---|
| G1 | bloquant | aucun IfcSpace |
| G2 | bloquant | aucun niveau (IfcBuildingStorey) |
| G3 | alerte | espaces sans niveau, ni par la structure spatiale ni par l'altitude |
| G4 | alerte | espaces rattachés à un niveau par leur seule altitude (hors structure spatiale) |
| G5 | alerte | espaces sans emprise en plan (géométrie absente ou verticale) |
| G6 | alerte | aire déclarée (quantités IFC) différente de l'aire en plan |
| G7 | alerte | plancher de l'espace loin de l'altitude de son niveau |
| G8 | alerte | éléments sans géométrie lisible, par classe |
| G9 | info | niveaux sans espace |
| G10 | info | espaces sans logement (propriété config.yaml > generation.lot vide ou absente) |

L'inventaire (`--inventaire`) écrit le tout en JSON : bâtiments, niveaux, espaces avec leurs propriétés (les
preuves de l'analyse IA, phase 24), éléments par classe, points d'audit.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import __version__
from .ingest import Item, Model
from .plans import Plan

FORMAT, VERSION = "sia-check-inventaire", 1
SEVERITIES = ("bloquant", "alerte", "info")
DECLARED_AREA = ("NetFloorArea", "GrossFloorArea")


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    gids: list[str] = field(default_factory=list)


def declared_area(item: Item) -> float | None:
    """Aire déclarée d'un espace : NetFloorArea des quantités (Qto_SpaceBaseQuantities, BaseQuantities…), sinon
    GrossFloorArea."""
    for q in DECLARED_AREA:
        for k, v in item.props.items():
            if k.endswith("." + q) and isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                return float(v)
    return None


def _names(items: list[Item], n: int = 5) -> str:
    shown = ", ".join(i.long_name or i.name or i.gid for i in items[:n])
    return shown + (f"… (+{len(items) - n})" if len(items) > n else "")


def run(model: Model, plans: list[Plan], gen_cfg: dict | None = None) -> list[Issue]:
    a = (gen_cfg or {}).get("audit") or {}
    rel, abs_m2, gap = float(a.get("area_rel", 0.02)), float(a.get("area_abs", 0.5)), float(a.get("storey_gap_m", 1.0))
    out: list[Issue] = []
    if not model.spaces:
        out.append(Issue("G1", "bloquant", "La maquette ne contient aucun IfcSpace : rien à classer."))
    if not model.storeys:
        out.append(Issue("G2", "bloquant", "La maquette ne contient aucun niveau (IfcBuildingStorey)."))

    def add(code, severity, items, message):
        if items:
            out.append(Issue(code, severity, f"{len(items)} {message} : {_names(items)}", [i.gid for i in items]))

    add("G3", "alerte", [s for s in model.spaces if s.storey is None], "espaces sans niveau")
    add("G4", "alerte", [s for s in model.spaces if s.storey_by == "altitude"],
        "espaces hors de la structure spatiale, rattachés à leur niveau par l'altitude")
    placed = {p.item.gid: p for plan in plans for p in plan.spaces}
    add("G5", "alerte", [s for s in model.spaces if s.storey is not None and (s.gid not in placed or placed[s.gid].shape is None)],
        "espaces sans emprise en plan")
    off = []
    for s in model.spaces:
        p, d = placed.get(s.gid), declared_area(s)
        if p is not None and p.shape is not None and d is not None:
            diff = abs(p.area - d)
            if diff > abs_m2 and diff > rel * d:
                off.append(s)
    add("G6", "alerte", off, f"espaces dont l'aire déclarée s'écarte de l'aire en plan (plus de {rel:.0%} et {abs_m2} m²)")
    add("G7", "alerte", [s for s in model.spaces if s.z_min is not None and (st := model.storey(s.storey)) is not None
                         and abs(s.z_min - st.elevation) > gap],
        f"espaces dont le plancher est à plus de {gap} m de l'altitude de leur niveau")
    for e in model.errors:
        out.append(Issue("G8", "alerte", e))
    empty = [p.storey for p in plans if not p.spaces]
    if empty:
        out.append(Issue("G9", "info", f"{len(empty)} niveaux sans espace : " + ", ".join(f"{s.building} {s.name}" for s in empty),
                         [s.gid for s in empty]))
    if (gen_cfg or {}).get("lot"):
        add("G10", "info", [s for s in model.spaces if s.lot is None], "espaces sans logement")
    return out


def blocking(issues: list[Issue]) -> bool:
    return any(i.severity == "bloquant" for i in issues)


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(x, nd)


def inventory(model: Model, plans: list[Plan], issues: list[Issue]) -> dict:
    buildings = []
    for b in model.buildings:
        levels = []
        for plan in (p for p in plans if p.storey.building == b):
            st = plan.storey
            levels.append({
                "gid": st.gid, "name": st.name, "rank": st.rank, "elevation": _r(st.elevation), "height": _r(st.height),
                "spaces": len(plan.spaces), "spaces_m2": _r(sum(p.area for p in plan.spaces), 2),
                "lots": len({p.item.lot for p in plan.spaces if p.item.lot}),
                "elements": dict(sorted(Counter(p.item.ifc_class for p in plan.elements).items())),
            })
        buildings.append({"name": b, "storeys": levels})
    placed = {p.item.gid: p for plan in plans for p in plan.spaces}
    spaces = [{
        "gid": s.gid, "name": s.name, "long_name": s.long_name, "predefined": s.predefined, "building": s.building,
        "storey": (model.storey(s.storey).name if model.storey(s.storey) else None), "storey_by": s.storey_by,
        "lot": s.lot, "area_plan": _r(placed[s.gid].area if s.gid in placed else None, 3),
        "area_declared": _r(declared_area(s), 3), "z_min": s.z_min, "z_max": s.z_max, "props": s.props,
    } for s in model.spaces]
    counts = Counter(i.severity for i in issues)
    return {
        "format": FORMAT, "version": VERSION, "tool": f"sia-check {__version__}",
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "source": model.path, "schema": model.schema, "project": model.project, "seconds": model.seconds,
        "counts": {"buildings": len(model.buildings), "storeys": len(model.storeys), "spaces": len(model.spaces),
                   "elements": dict(sorted(Counter(e.ifc_class for e in model.elements).items())),
                   "issues": {s: counts.get(s, 0) for s in SEVERITIES}},
        "blocking": blocking(issues),
        "buildings": buildings,
        "issues": [asdict(i) for i in issues],
        "spaces": spaces,
    }


def write(inv: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inv, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return path


def summary(inv: dict) -> str:
    """Résumé console : un bloc par bâtiment, une ligne par niveau, puis les points d'audit."""
    lines = [f"{inv['project'] or Path(inv['source']).stem} · {inv['schema']} · {inv['counts']['buildings']} bâtiment(s), "
             f"{inv['counts']['storeys']} niveaux, {inv['counts']['spaces']} espaces · {inv['seconds']} s"]
    for b in inv["buildings"]:
        lines.append(f"\nBâtiment {b['name']}")
        lines.append(f"  {'niveau':<20}{'alt. m':>9}{'haut. m':>8}{'espaces':>9}{'m² en plan':>12}{'logements':>11}  éléments")
        for s in reversed(b["storeys"]):
            el = " ".join(f"{k.removeprefix('Ifc')} {v}" for k, v in s["elements"].items())
            h = "" if s["height"] is None else f"{s['height']:.2f}"
            lines.append(f"  {s['name'][:19]:<20}{s['elevation']:>9.2f}{h:>8}{s['spaces']:>9}{s['spaces_m2']:>12.2f}"
                         f"{s['lots']:>11}  {el}")
    lines.append("")
    for i in inv["issues"]:
        lines.append(f"{i['code']:<4} {i['severity']:<9} {i['message']}")
    c = inv["counts"]["issues"]
    lines.append(("BLOQUANT : génération impossible · " if inv["blocking"] else "")
                 + " · ".join(f"{s} {c[s]}" for s in SEVERITIES))
    return "\n".join(lines)
