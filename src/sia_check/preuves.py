"""Revue IA, étape 1 : preuves factuelles à partir du fichier visionneuse de sia-check.

Usage (une seule exécution du moteur, comme dans la visionneuse) :
    sia-check "<dossier projet>" -q --viewer-json analyse.json --preuves <projet>_<date>.preuves.json
ou, à partir d'un fichier visionneuse existant :
    python scripts/revue_ia_preuves.py analyse.json docs/revue-ia/<projet>_<date>.preuves.json

Les règles R1–R5 / A1–A3 disent OÙ la sommation ne boucle pas. Ce script rassemble ce qu'il
faut pour dire POURQUOI, avant la rédaction du rapport par l'IA (étape 2, voir
.claude/skills/revue-ia/SKILL.md) :

- bilan par niveau enrichi des codes maison (SUT hors logement, SPT toitures), en tenant compte des
  règles personnalisées : un code déjà compté par le moteur (ex. SUT sous P1) n'est pas recompté ;
- géométrie (projection en plan, aires en m²) :
    * surfaces intérieures hors de l'emprise SP de leur niveau,
    * recouvrements entre surfaces intérieures du même niveau (doublons, A4 du brief),
    * SEP décomposée : sous l'emprise SP du même niveau (double compte), au-dessus du niveau
      inférieur (terrasse ou toiture sur le bâtiment), au-dessus d'un sous-sol seul (dalle sur
      sous-sol), au-dessus de rien (terrain), et part recouverte par SPT ;
- totaux de niveau Treegram différents de la somme de leur détail.

Dépendance : shapely (extra `revue` ; embarquée dans le moteur de la visionneuse).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from shapely import Polygon, union_all
from shapely.geometry.base import BaseGeometry

INTERIOR = ["SUP", "SUS", "SD", "SI", "SUT"]
MIN_AREA = 0.5      # m² : en dessous, bruit de triangulation
NDIGITS = 2


def polygon_of(mesh: dict) -> BaseGeometry | None:
    v, idx = mesh["v"], mesh["i"]
    tris = []
    for t in range(0, len(idx) - 2, 3):
        pts = [(v[3 * k], v[3 * k + 1]) for k in idx[t:t + 3]]
        p = Polygon(pts)
        if p.area > 1e-6:
            tris.append(p)
    if not tris:
        return None
    g = union_all(tris).buffer(0)
    return g if not g.is_empty else None


def rank_of(level: str, ranks: dict) -> float:
    return ranks.get(level, 0)


def r(x: float) -> float:
    return round(float(x), NDIGITS)


def build(doc: dict) -> dict:
    """Preuves à partir du document visionneuse (contrat de viewer.py)."""
    levels = {(l["building"], l["level"]): l for l in doc["levels"]}
    ranks = {(l["building"], l["level"]): l.get("rank") or 0 for l in doc["levels"]}

    # Géométries par niveau : `geo` (surfaces élémentaires) et `geo_nodes` (totaux de niveau Treegram,
    # seule géométrie de SP et SEP). Ne jamais les mélanger : un total recouvre ses propres pièces.
    geo: dict[tuple, dict[str, list[tuple[str, BaseGeometry]]]] = defaultdict(lambda: defaultdict(list))
    geo_nodes: dict[tuple, dict[str, list[tuple[str, BaseGeometry]]]] = defaultdict(lambda: defaultdict(list))
    area_by: dict[tuple, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    nodes: dict[tuple, dict[str, float]] = defaultdict(dict)
    for s in doc["surfaces"]:
        key = (s["building"], s["level"])
        code = s["code"] or s["category"]
        if s["kind"] == "node":
            nodes[key][code] = s["area"] or 0
        else:
            area_by[key][code] += s["area"] or 0
        if s["mesh"] and (g := polygon_of(s["mesh"])) is not None:
            (geo_nodes if s["kind"] == "node" else geo)[key][code].append((s["id"], g))

    def union(key, codes) -> BaseGeometry | None:
        """Union des surfaces élémentaires des codes ; à défaut de détail (SP, SEP), le total de niveau."""
        parts = []
        for c in codes:
            parts += [g for _, g in geo[key].get(c, [])] or [g for _, g in geo_nodes[key].get(c, [])]
        return union_all(parts) if parts else None

    # SUT est-il déjà dans les sommes du moteur (règle personnalisée P1) ? Les fichiers antérieurs aux
    # règles personnalisées n'ont pas de statut : SUT y était ignoré.
    cat_status = {c["code"]: c for c in doc.get("categories", [])}
    sut_info = cat_status.get("SUT", {})
    sut_counted = sut_info.get("status") == "checked"

    out_levels, outside, overlaps, sep_split, uspi_totals = [], [], [], [], []
    for key in sorted(levels, key=lambda k: (k[0], rank_of(k, ranks))):
        b, lvl = key
        lv = levels[key]
        vals = lv["values"]
        sp = vals.get("SP", 0)
        r1 = (lv.get("r1") or {}).get("diff")
        sut, spt = area_by[key].get("SUT", 0), area_by[key].get("SPT", 0)
        out_levels.append({
            "building": b, "level": lvl, "rank": ranks[key], "SP": r(sp),
            **{c: r(vals.get(c, 0)) for c in ("SUP", "SUS", "SD", "SI", "SEP", "SEU", "SED")},
            "SUT": r(sut), "SUT_counted_by_engine": sut_counted,
            "SUT_custom_rule": sut_info.get("custom_rule"), "SPT_ignored": r(spt),
            "R1_residual": r(r1) if r1 is not None else None,
            "R1_pct": r(100 * r1 / sp) if r1 is not None and sp else None,
            # Résidu avec SUT compté : déjà le cas si le moteur l'a compté (P1), sinon on le retranche.
            "R1_residual_if_SUT_counted": r(r1 - (0 if sut_counted else sut)) if r1 is not None else None,
            "R1_pct_if_SUT_counted": (r(100 * (r1 - (0 if sut_counted else sut)) / sp)
                                      if r1 is not None and sp else None),
            "alerts": lv["alerts"],
        })

        # Total de niveau Treegram ≠ somme du détail (constaté sur la chaîne USPI : totaux > somme des lots).
        for code, total in nodes[key].items():
            detail = area_by[key].get(code)
            if detail and abs(total - detail) > MIN_AREA:
                uspi_totals.append({"building": b, "level": lvl, "code": code, "total_treegram": r(total),
                                    "sum_detail": r(detail), "diff": r(total - detail)})

        footprint = union(key, ["SP"])
        if footprint is None:
            continue
        # Surfaces intérieures hors de l'emprise SP du niveau.
        for code in INTERIOR:
            for sid, g in geo[key].get(code, []):
                out_area = g.difference(footprint).area
                if out_area > MIN_AREA:
                    outside.append({"building": b, "level": lvl, "code": code, "id": sid,
                                    "area_outside_SP": r(out_area), "surface_area": r(g.area)})
        # Recouvrements entre surfaces intérieures du même niveau.
        items = [(c, sid, g) for c in INTERIOR for sid, g in geo[key].get(c, [])]
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                ci, si, gi = items[i]
                cj, sj, gj = items[j]
                if not gi.envelope.intersects(gj.envelope):
                    continue
                a = gi.intersection(gj).area
                if a > MIN_AREA:
                    overlaps.append({"building": b, "level": lvl, "a": si, "a_code": ci, "b": sj, "b_code": cj,
                                     "overlap": r(a)})

    # Décomposition de la SEP de chaque niveau.
    for key in sorted(levels, key=lambda k: (k[0], rank_of(k, ranks))):
        b, lvl = key
        sep = union(key, ["SEP"])
        if sep is None or sep.area < MIN_AREA:
            continue
        same = union(key, ["SP"])
        below_keys = sorted((k for k in levels if k[0] == b and ranks[k] < ranks[key]), key=lambda k: ranks[k])
        below = below_keys[-1] if below_keys else None
        below_fp = union(below, ["SP"]) if below else None
        basements = [k for k in below_keys if str(k[1]).startswith("S")]
        basement_fp = union_all([g for k in basements if (g := union(k, ["SP"])) is not None]) if basements else None
        classified = union(key, ["SEU", "SED"])
        roof_code = union(key, ["SPT"])

        rest = sep
        on_same = sep.intersection(same).area if same is not None else 0
        rest = rest.difference(same) if same is not None else rest
        over_below = rest.intersection(below_fp).area if below_fp is not None else 0
        rest = rest.difference(below_fp) if below_fp is not None else rest
        over_basement = rest.intersection(basement_fp).area if basement_fp is not None else 0
        rest = rest.difference(basement_fp) if basement_fp is not None else rest
        sep_split.append({
            "building": b, "level": lvl, "SEP_geom": r(sep.area),
            "under_SP_same_level": r(on_same),
            "over_level_below": r(over_below), "level_below": below[1] if below else None,
            "over_basement_only": r(over_basement),
            "over_nothing": r(rest.area),
            "classified_SEU_SED": r(sep.intersection(classified).area) if classified is not None else 0,
            "covered_by_SPT": r(sep.intersection(roof_code).area) if roof_code is not None else 0,
        })

    ev = {
        "project": doc["project"], "analysis_date": doc["date"], "cache": doc["cache"],
        "counts": doc["counts"], "tolerance": doc["tolerance"],
        "levels": out_levels, "sep_decomposition": sep_split,
        "interior_outside_SP": outside, "interior_overlaps": overlaps,
        "level_total_vs_detail": uspi_totals,
        "issues": [{k: i[k] for k in ("key", "rule", "verdict", "building", "level", "lot", "category",
                                     "expected", "obtained", "diff_m2", "diff_pct", "title", "message")}
                   for i in doc["issues"]],
    }
    return ev


def summary(ev: dict) -> str:
    return (f"{len(ev['levels'])} niveaux, {len(ev['sep_decomposition'])} SEP décomposées, "
            f"{len(ev['interior_outside_SP'])} surfaces hors SP, {len(ev['interior_overlaps'])} recouvrements, "
            f"{len(ev['level_total_vs_detail'])} totaux ≠ détail")


def write(ev: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main(src: str, dst: str) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows cp1252
    ev = build(json.loads(Path(src).read_text(encoding="utf-8")))
    print(f"{summary(ev)} -> {write(ev, dst)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
