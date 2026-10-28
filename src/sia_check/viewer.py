"""Export JSON pour SIA Check Viewer (application WPF) : surfaces + maillages + points d'attention liés.

Contrat (version 1) :
{
  "format": "sia-check-viewer", "version": 1,
  "project", "date", "sources", "exit_code", "counts", "tolerance",
  "cache": {"files", "newest", "oldest", "source_modified", "stale", "errors"},
  "custom_rules": [{"id", "title", "parent", "adds", "description"}],
  "ratios": [{"building", "id", "family", "label", "value", "unit", "ref_min", "ref_max", "status",
              "num_m2", "den_m2", "note"}],
  "categories": [{"code", "family", "status", "color", "hatched", "name", "ref", "definition", "custom_rule"}],
  "surfaces":   [{"id", "building", "level", "category", "code", "kind", "status" (checked | ignored | unknown |
                  excluded : retirée par une correction), "area",
                  "room_type", "lot", "mesh": {"v": [x, y, z, …], "i": [a, b, c, …]} | null}],
  "levels":     [{"building", "level", "rank", "values": {code: m², dont SFN, SFN_NETTE, SFN_RESERVATIONS, SRV ; cages d'escalier :
                  SUP_ETAGE, LOGEMENTS, CAGES, SUP_CAGES, LOG_CAGES (ratios.stairs)}, "r1": {"diff", "verdict"} | null,
                  "r3": {…} | null, "alerts": [règles],
                  "before": {"values", "r1", "r3"} | null}],   (avec corrections : bilan sans elles)
  "issues":     [{"key", "rule", "verdict", "building", "level", "lot", "category", "expected",
                  "obtained", "diff_m2", "diff_pct", "message", "title", "hint", "surface_ids": [...]}],
  "subjects":   [{"id", "titre", "cause", "action", "explication", "points": [key], "m2",
                  "corrections": [entrées de journal]}]   (ajoutés par la CLI, sujets.py),
  "corrections_log": [{"id", "op", "sujet", "origine", "statut", "application", "surfaces", "m2", "raison"}]
                  (avec --corrections, corrections.py), "review": {…} | null (avec --revue, sujets.apply_review)
}
`key` est stable d'une analyse à l'autre : la visionneuse y accroche statut et commentaire.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd

from . import __version__, ratios, report, rules
from .config import Config
from .geom import Cache

FORMAT_VERSION = 1
COORD_DIGITS = 3


def _num(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), 3) if isinstance(v, float) else v


def _text(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)


def issue_key(r) -> str:
    return "|".join(str(x) for x in (r["rule"], r["building"], r["level"], _text(r["lot"]) or "", r["category"]))


def ratios_records(result: rules.Result) -> list[dict]:
    """Ratios informatifs (ratios.py) ; building « * » = projet entier."""
    if result.ratios is None:
        return []
    return [{k: (_num(v) if isinstance(v, float) else v) for k, v in r.items()}
            for r in result.ratios.to_dict("records")]


def custom_rules(cfg: Config) -> list[dict]:
    """Écarts assumés à la SIA 416 actifs pour cette analyse (config.yaml > custom_rules)."""
    return [{"id": r.id, "title": r.title, "parent": r.parent, "adds": list(r.adds), "description": r.description}
            for r in cfg.custom_rules]


def _subtree(code: str, cfg: Config) -> set[str]:
    out = {code}
    for k in cfg.children(code):
        out |= _subtree(k, cfg)
    return out


def _concerned(r: pd.Series, surf: pd.DataFrame, unknown: pd.DataFrame, cfg: Config) -> list[str]:
    """Surfaces à montrer pour un point d'attention."""
    if r["rule"] == "A3":
        u = unknown[unknown.category.replace("", "(vide)") == r["category"]]
        return u.id.dropna().astype(str).tolist()
    s = surf
    if r["building"] != rules.ALL:
        s = s[s.building == r["building"]]
    if r["level"] != rules.ALL:
        s = s[s.level == r["level"]]
    if _text(r["lot"]):
        return s[s.lot == r["lot"]].id.astype(str).tolist()
    # R5 porte sur SU, mais c'est le plancher entier qu'il faut regarder (SIA 416 §2.1.1).
    root = rules.SP if r["rule"] == "R5" else r["category"]
    if root not in cfg.categories:
        return []
    # SEP non classée, au terrain ou en toiture : c'est la SEP qui est en cause, pas ses parties déjà classées
    # (SEU, SED) qu'on prendrait sinon pour une partie du problème.
    codes = {rules.SEP} if root == rules.SEP and r["rule"] in ("R3", "A1", "A2") else _subtree(root, cfg)
    return s[s.code.isin(codes)].id.astype(str).tolist()


def _mesh(meshes) -> dict | None:
    if not meshes:
        return None
    v, idx = [], []
    for m in meshes:
        base = len(v) // 3
        v.extend(round(x, COORD_DIGITS) for x in m.vertices)
        idx.extend(base + i for i in m.indices)
    return {"v": v, "i": idx}


def _flat_mesh(geom, z: float) -> dict | None:
    """Maillage à plat d'une géométrie shapely (tracé triangulé de sujets._trace, en 3D)."""
    from .sujets import _trace
    t = _trace(geom, z) if geom is not None and not geom.is_empty else None
    if t is None:
        return None
    xy = t["v"]
    return {"v": [c for k in range(0, len(xy), 2) for c in (xy[k], xy[k + 1], t["z"])], "i": t["i"]}


def _top(mesh: dict | None) -> float | None:
    return max(mesh["v"][2::3]) if mesh and mesh.get("v") else None


def _drawn_mesh(geometry, fallback_z: float | None, within=None) -> dict | None:
    """Maillage d'une surface remodelée, créée ou découpée (corrections.GEOMETRY_COLUMN) : son tracé triangulé, à plat,
    limité à l'emprise d'origine (`within`) pour une part découpée."""
    if not isinstance(geometry, dict) or not isinstance(geometry.get("polygone"), dict):
        return None
    try:
        from shapely.geometry import shape
    except ImportError:
        return None
    geom = shape(geometry["polygone"]).buffer(0)
    if within is not None:
        geom = geom.intersection(within)
    z = geometry.get("z")
    return _flat_mesh(geom, float(z if z is not None else fallback_z or 0.0))


def _cut_mesh(mesh: dict, cuts: list) -> dict | None:
    """Emprise d'une surface moins les parts découpées ou exclues par les corrections (corrections.CUTS_COLUMN)."""
    try:
        from shapely import union_all
        from shapely.geometry import shape
        from .preuves import polygon_of
    except ImportError:
        return mesh
    base = polygon_of(mesh)
    if base is None:
        return mesh
    rest = base.difference(union_all([shape(c).buffer(0) for c in cuts]))
    return _flat_mesh(rest, _top(mesh) or 0.0)


CACHE_MARGIN = dt.timedelta(minutes=10)


def _roof_footprints(shown: pd.DataFrame, detailed: set, footprint) -> dict[tuple, object]:
    """(bâtiment, niveau, total hôte) -> union des emprises des toitures que Treegram compte dans ce total."""
    try:
        from shapely import union_all
    except ImportError:
        return {}
    out: dict[tuple, list] = {}
    for r in shown[shown.category.isin(rules.COUNTED_IN.keys())].itertuples(index=False):
        if r.kind == "node" and (r.building, r.level, r.category) in detailed:
            continue   # total doublé par ses pièces : les pièces suffisent
        host = (r.building, r.level, rules.COUNTED_IN[r.category])
        if host in detailed:
            continue   # SEP détaillée : Treegram n'y compte pas la toiture
        g = footprint(str(r.id))
        if g is not None:
            out.setdefault(host, []).append(g)
    return {k: union_all(v) for k, v in out.items()}


# Demi-largeur des bandes gardées en 3D quand la toiture est retirée de la SEP : le contour de la SEP Treegram
# déborde celui de la SPT de quelques centimètres (bord de dalle, acrotère), ce qui laissait un cadre autour du toit.
ROOF_EDGE = 0.15


def _without(mesh: dict, region, edge: float = 0.0) -> dict | None:
    """Emprise d'une surface moins une région (shapely), sans les bandes plus étroites que 2 × `edge`."""
    from .preuves import polygon_of
    base = polygon_of(mesh)
    if base is None:
        return mesh
    rest = base.difference(region)
    if edge and not rest.is_empty:
        rest = rest.buffer(-edge, join_style="mitre").buffer(edge, join_style="mitre").intersection(rest)
    return None if rest.is_empty or rest.area < 1e-3 else _flat_mesh(rest, _top(mesh) or 0.0)


def _levels(rep: report.Report, cfg: Config) -> list[dict]:
    out = []
    env = report.envelope_by_level(rep.result)
    st = ratios.stairs(rep.result.surfaces, rep.result.totals)
    for r in rep.levels.to_dict("records"):
        e = env.loc[(r["building"], r["level"])] if (r["building"], r["level"]) in env.index else {}
        cg = st.loc[(r["building"], r["level"])] if (r["building"], r["level"]) in st.index else {}
        def check(prefix):
            v = r.get(f"{prefix} verdict")
            return None if not isinstance(v, str) else {"diff": _num(r[f"{prefix} écart"]), "verdict": v}
        out.append({
            "building": r["building"], "level": r["level"], "rank": _num(rules.level_rank(r["level"], cfg)),
            "values": {c: _num(v) for c, v in [*((c, r[c]) for c in report.LEVEL_COLUMNS),
                                                 *((c, e[c]) for c in report.ENVELOPE_COLUMNS if c in e),
                                                 *((k, cg[k]) for k in ratios.STAIR_COLUMNS if k in cg)]
                       if _num(v) is not None},
            "r1": check("R1"), "r3": check("R3"),
            "alerts": [a for a in r["Alertes"].split(", ") if a],
        })
    return out


def build(result: rules.Result, cfg: Config, cache: Cache, project: str, sources: list[str],
          source_modified: dt.datetime | None = None, date: str | None = None,
          before: rules.Result | None = None, excluded: pd.DataFrame | None = None) -> dict:
    """`before` : contrôles sans les corrections (corrections.run) ; chaque niveau reçoit alors `before`.
    `excluded` : surfaces retirées par une correction, listées avec le statut « excluded » (hors calques,
    hors sommes) pour que la visionneuse puisse encore les montrer."""
    rep = report.build(result, cfg, project, sources, date)
    surf = result.surfaces
    parts = [surf.assign(status=surf.ignored.map({True: "ignored", False: "checked"})),
             result.unknown.assign(code=None, status="unknown")]
    if excluded is not None and len(excluded):
        parts.append(excluded.assign(code=excluded.category.map(lambda c: cfg.canonical(c) if c in cfg.categories else None),
                                     status="excluded"))
    all_surf = pd.concat(parts, ignore_index=True)

    categories = []
    listed = all_surf[all_surf.status != "excluded"]
    for code in report._category_order(cfg, set(listed.code.dropna()) | set(listed.category)):
        spec = cfg.categories.get(code)
        categories.append({
            "code": code,
            "family": (spec or {}).get("family"),
            "status": "unknown" if spec is None else "ignored" if spec.get("ignore") else "checked",
            "color": report.SIA_COLORS.get(code),
            "hatched": code in report.HATCHED,
            "name": cfg.labels.get(code, {}).get("name"),
            "ref": cfg.labels.get(code, {}).get("ref"),
            "definition": cfg.labels.get(code, {}).get("def"),
            "custom_rule": rule.id if (rule := cfg.custom_rule_of(code)) else None,
        })

    surfaces = []
    created = set()
    # Totaux de niveau Treegram dont les pièces sont livrées : même emprise que leur détail. Gardés pour les données
    # (le détail fait foi dans les sommes, rules.level_totals), sans maillage : ni doublon en 3D ni surface à cliquer.
    shown = all_surf[all_surf.status != "excluded"]
    detailed = set(zip(shown.building[shown.kind == "leaf"], shown.level[shown.kind == "leaf"],
                       shown.category[shown.kind == "leaf"]))
    redundant = set()
    # Maillages lus (cache VWR) : emprise d'origine des parts découpées.
    read_mesh = {}
    for r in all_surf.itertuples(index=False):
        eid = None if pd.isna(getattr(r, "element_id", None)) else int(r.element_id)
        read_mesh[str(r.id)] = _mesh(cache.meshes.get(eid)) if eid is not None else None

    def footprint(sid):
        try:
            from .preuves import polygon_of
        except ImportError:
            return None
        m = read_mesh.get(sid)
        return polygon_of(m) if m else None

    roofs = _roof_footprints(shown, detailed, footprint)

    for r in all_surf.itertuples(index=False):
        if pd.isna(getattr(r, "element_id", None)) and "#" in str(r.id) and not str(r.id).endswith("#total"):
            created.add(str(r.id))
        mesh = read_mesh[str(r.id)]
        drawn = getattr(r, "geometrie", None)
        cuts = getattr(r, "retraits", None)
        if isinstance(drawn, dict):   # emprise redessinée, surface créée ou part découpée : le tracé fait l'emprise
            parent = drawn.get("dans")
            mesh = _drawn_mesh(drawn, _top(mesh) or _top(read_mesh.get(parent)),
                               footprint(parent) if parent else None) or mesh
        elif r.kind == "node" and (r.building, r.level, r.category) in detailed:
            mesh = None
            redundant.add(str(r.id))
        if isinstance(cuts, list) and cuts and mesh:
            mesh = _cut_mesh(mesh, cuts)
        area = r.area
        # Total SEP de Treegram qui compte les toitures SPT (rules.COUNTED_IN) : affiché et compté sans elles, comme
        # dans le bilan ; plus de maillage s'il n'en reste rien (toiture en double SEP + SPT).
        key = (r.building, r.level, r.category)
        if r.kind == "node" and r.status != "excluded" and key in roofs and str(r.id) not in redundant:
            net = result.totals[r.category].get((r.building, r.level)) if r.category in result.totals else None
            if net is not None and not pd.isna(net):
                area = net
            if mesh:
                mesh = _without(mesh, roofs[key], ROOF_EDGE) if area > cfg.abs_m2 else None
            if mesh is None:
                redundant.add(str(r.id))
        surfaces.append({
            "id": str(r.id), "building": _text(r.building), "level": _text(r.level),
            "category": r.category, "code": _text(r.code), "kind": r.kind, "status": r.status,
            "area": _num(area), "room_type": _text(r.room_type), "lot": _text(r.lot),
            "mesh": mesh,
        })

    levels = _levels(rep, cfg)
    if before is not None:
        old = {(lv["building"], lv["level"]): lv for lv in _levels(report.build(before, cfg, project, sources, date), cfg)}
        for lv in levels:
            b = old.get((lv["building"], lv["level"]))
            lv["before"] = None if b is None else {k: b[k] for k in ("values", "r1", "r3")}

    issues = []
    for _, r in rep.residuals.iterrows():
        issues.append({
            "key": issue_key(r), "rule": r["rule"], "verdict": r["verdict"],
            "building": r["building"], "level": r["level"], "lot": _text(r["lot"]), "category": r["category"],
            "expected": _num(r["expected"]), "obtained": _num(r["obtained"]),
            "diff_m2": _num(r["diff_m2"]), "diff_pct": _num(r["diff_pct"]), "message": r["message"],
            "title": rules.title_of(r["rule"], r["verdict"]), "hint": r["hint"] or None,
            "surface_ids": _concerned(r, surf, result.unknown, cfg),
        })

    # Le cache est écrit pendant l'action Treegram qui crée les surfaces, la base de l'action une fois finie (L'Orée :
    # 7 s plus tard) : une marge évite de le dire périmé à tort.
    stale = bool(source_modified and cache.newest and cache.newest < source_modified - CACHE_MARGIN)
    return {
        "format": "sia-check-viewer", "version": FORMAT_VERSION, "tool_version": __version__,
        "project": project, "date": rep.date, "sources": rep.sources,
        "exit_code": result.exit_code, "counts": rep.counts,
        "tolerance": {"abs_m2": cfg.abs_m2, "rel": cfg.rel},
        "custom_rules": custom_rules(cfg),
        "cache": {
            "files": cache.files,
            "newest": cache.newest.isoformat(timespec="seconds") if cache.newest else None,
            "oldest": cache.oldest.isoformat(timespec="seconds") if cache.oldest else None,
            "source_modified": source_modified.isoformat(timespec="seconds") if source_modified else None,
            "stale": stale,
            "errors": cache.errors,
            # Les surfaces créées par une correction (découpe vers SA) n'ont pas de maillage par nature.
            "surfaces_without_mesh": sum(1 for s in surfaces if s["mesh"] is None and (s["area"] or 0) > 0
                                         and s["id"] not in created and s["id"] not in redundant),
        },
        "categories": categories, "surfaces": surfaces, "levels": levels, "issues": issues,
        "ratios": ratios_records(result),
    }


def balance(result: rules.Result, cfg: Config, before: rules.Result | None = None) -> dict:
    """Bilan par niveau et ratios seuls (format du fichier visionneuse), pour l'aperçu en direct des corrections."""
    rep = report.build(result, cfg, "", [])
    levels = _levels(rep, cfg)
    if before is not None:
        old = {(lv["building"], lv["level"]): lv for lv in _levels(report.build(before, cfg, "", []), cfg)}
        for lv in levels:
            b = old.get((lv["building"], lv["level"]))
            lv["before"] = None if b is None else {k: b[k] for k in ("values", "r1", "r3")}
    return {"levels": levels, "ratios": ratios_records(result), "counts": rep.counts}


def write(doc: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path
