"""Moteur de génération : maquette IFC -> projet `.siagen.json` au modèle Treegram (V4_PLAN §3).

    ingest -> plans -> audit d'entrée -> classify -> interiors -> assemble -> <projet>/<projet>.siagen.json

Le dossier du projet généré s'ouvre dans la Fiabilisation comme un dossier Treegram. Il contient aussi
`generation/rapport.json` : chaque espace de la maquette, sa nature, son code, son sous-type, la source et la
confiance de la décision, les sources en désaccord ; la SP de chaque niveau et sa méthode ; l'audit d'entrée.
C'est la liste de travail de l'analyse IA (phase 24) et des ajustements manuels (phase 25).
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .. import __version__, siagen
from . import assemble, audit, classify, exteriors, ingest, interiors, plans

FORMAT, VERSION = "sia-check-generation", 1
SURE = 0.8   # en dessous : décision à confirmer (IA ou manuel)


class GenerationBlocked(RuntimeError):
    def __init__(self, issues: list[audit.Issue]):
        super().__init__("; ".join(i.message for i in issues if i.severity == "bloquant"))
        self.issues = issues


@dataclass
class Generated:
    folder: Path
    siagen: Path
    report: Path
    data: dict


def _r(x, nd=3):
    return None if x is None else round(x, nd)


def report(model: ingest.Model, pl: list[plans.Plan], issues, decisions: dict, levels: list[interiors.Level],
           project: str, codes: dict[str, str] | None = None) -> dict:
    codes = codes or {}
    placed = {p.item.gid: p for plan in pl for p in plan.spaces}
    counted = {r.placed.item.gid: r.area for lv in levels for r in lv.rooms + lv.exteriors}
    spaces = []
    for s in model.spaces:
        d = decisions[s.gid]
        st = model.storey(s.storey)
        spaces.append({
            "gid": s.gid, "name": s.name, "long_name": s.long_name, "building": s.building,
            "storey": st.name if st else None, "level": codes.get(s.storey), "lot": s.lot, "in_lot": d.in_lot,
            "nature": d.nature, "code": d.code, "type": d.type, "source": d.source,
            "confidence": round(d.confidence, 2), "reason": d.reason, "conflicts": d.conflicts,
            "area": _r(counted.get(s.gid)), "area_plan": _r(placed[s.gid].area if s.gid in placed else None),
            "area_declared": _r(audit.declared_area(s)),
        })
    lv_out = []
    for lv in levels:
        if lv.empty:
            continue
        totals = Counter()
        for r in lv.rooms + lv.exteriors:
            totals[r.decision.code] += r.area
        lv_out.append({"building": lv.plan.storey.building, "storey": lv.plan.storey.name,
                       "level": codes.get(lv.plan.storey.gid),
                       "sp_m2": _r(lv.sp_area, 2), "sp_method": lv.sp_method, "rooms": len(lv.rooms),
                       "exteriors": len(lv.exteriors), "sep_m2": _r(lv.sep.area if lv.sep is not None else 0.0, 2),
                       "spt_m2": _r(lv.spt.area if lv.spt is not None else 0.0, 2),
                       "slab_m2": _r(lv.slab.area if lv.slab is not None else 0.0, 2), "envelope": lv.envelope,
                       "totals": {k: _r(v, 2) for k, v in sorted(totals.items())}})
    pieces = [x for x in spaces if x["nature"] == classify.PIECE]
    return {
        "format": FORMAT, "version": VERSION, "tool": f"sia-check {__version__}",
        "date": dt.datetime.now().isoformat(timespec="seconds"), "project": project, "source": model.path,
        "counts": {
            "spaces": len(spaces), "natures": dict(Counter(x["nature"] for x in spaces)),
            "pieces": len(pieces), "sources": dict(Counter(x["source"] or "aucune" for x in pieces)),
            "unclassified": sum(1 for x in pieces if x["source"] is None),
            "conflicts": sum(1 for x in pieces if x["conflicts"]),
            "to_confirm": sum(1 for x in pieces if x["confidence"] < SURE),
        },
        "levels": lv_out,
        "audit": [asdict(i) for i in issues],
        "spaces": spaces,
    }


def generate(ifc: Path, cfg_generation: dict, out_dir: Path, project: str | None = None) -> Generated:
    ifc = Path(ifc)
    model = ingest.load(ifc, cfg_generation)
    pl = plans.build(model)
    issues = audit.run(model, pl, cfg_generation)
    if audit.blocking(issues):
        raise GenerationBlocked(issues)
    decisions = classify.classify(model, pl, cfg_generation)
    levels = interiors.build(pl, decisions, cfg_generation)
    levels += exteriors.roof_levels(levels)
    storeys = [lv.plan.storey for lv in levels]
    occupied = {lv.plan.storey.gid for lv in levels if lv.rooms}
    codes = assemble.level_codes(storeys, occupied, cfg_generation)
    exteriors.build(levels, decisions, {g for g, c in codes.items() if c.startswith("S")}, cfg_generation)
    project = project or assemble.clean(ifc.stem)
    folder = Path(out_dir) / project
    els = assemble.elements(levels, codes)
    # maillages en repère local : en float32, les coordonnées nationales les arrondiraient au quart de mètre
    path = siagen.write(els, folder / f"{project}{siagen.SUFFIX}", project, source=str(ifc), origin=siagen.local_origin(els))
    data = report(model, pl, issues, decisions, levels, project, codes)
    rep = folder / "generation" / "rapport.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return Generated(folder, path, rep, data)


def summary(data: dict) -> str:
    c = data["counts"]
    lines = [f"{data['project']} : {c['spaces']} espaces, dont {c['pieces']} pièces · "
             + " · ".join(f"{k} {v}" for k, v in c["natures"].items() if k != classify.PIECE)]
    lines.append("Sources du classement : " + " · ".join(f"{k} {v}" for k, v in sorted(c["sources"].items())))
    lines.append(f"Non classées {c['unclassified']} · sources en désaccord {c['conflicts']} · à confirmer {c['to_confirm']}")
    cols = assemble.INTERIOR_NODES[:-1] + ["SEU", "SED"]
    lines.append(f"\n  {'bâtiment':<10}{'niveau':<24}{'SP':>10}  " + "".join(f"{k:>9}" for k in cols)
                 + f"{'SEP':>9}{'SPT':>9}{'façade':>9}{'vitr.':>8}  méthode SP")
    for lv in data["levels"]:
        t, env = lv["totals"], lv["envelope"]
        name = f"{lv['level'] or '?'} ({lv['storey']})"
        lines.append(f"  {lv['building'][:9]:<10}{name[:23]:<24}{lv['sp_m2']:>10.2f}  "
                     + "".join(f"{t.get(k, 0):>9.2f}" for k in cols)
                     + f"{lv['sep_m2']:>9.2f}{lv['spt_m2']:>9.2f}{env.get('GrossArea', 0):>9.1f}{env.get('SRV', 0):>8.1f}"
                     + f"  {lv['sp_method']}")
    doubt = [x for x in data["spaces"] if x["nature"] in (classify.PIECE, classify.EXTERIEUR) and x["confidence"] < SURE]
    if doubt:
        lines.append("\nÀ confirmer (confiance la plus basse d'abord) :")
        for x in sorted(doubt, key=lambda x: x["confidence"])[:15]:
            label = " / ".join(v for v in (x["name"], x["long_name"]) if v)
            lines.append(f"  {x['confidence']:.2f}  {x['storey'] or '?':<10}{label[:40]:<42}{x['code']:<10}"
                         f"{(x['type'] or ''):<28}{x['reason'][:70]}")
        if len(doubt) > 15:
            lines.append(f"  … et {len(doubt) - 15} autres (generation/rapport.json)")
    return "\n".join(lines)
