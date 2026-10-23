"""Sujets : points d'attention regroupés par cause, avec une correction de base proposée par sujet.

Entrée : le document visionneuse (viewer.build) — points, surfaces et maillages. Sortie :

    {"subjects": [{"id", "titre", "cause", "action", "explication", "points": [clés de points],
                   "m2", "corrections": [entrées de journal, statut « proposée »]}]}

`action` : « corriger » (corrections proposées), « aucune » (rien à faire : surface de construction
implicite, agrégats), « à vérifier » (pas de correction automatique). Les corrections suivent le format
de corrections.py ; la revue IA (phase 4) et l'utilisateur les acceptent, les modifient ou les rejettent.

Causes reconnues (L'Orée, revue IA du 22.10.2026) :
- toitures : SEP d'un niveau Toiture ou au-dessus du dernier plancher (A2), ou part de SEP recouverte
  par la toiture Treegram (SPT) sur un attique ; une toiture non accessible n'est ni SP ni SEP
  (SIA 416 §3) -> `exclure` la SEP du niveau, ou la seule part de toiture ;
- abords : SEP non classée du niveau du terrain (A1), dalle au contact du terrain -> `découper` vers SA
  (SIA 416 §1.2) ; le tracé pré-calculé est la SEP hors plancher du niveau et hors SEU/SED ;
- sc-implicite : résidu R1 (SC) ou R3 (SEC) compatible avec la surface de construction, que Treegram ne crée
  pas -> aucune action ;
- agrégats : contrôles sommés par bâtiment ou sur le projet (niveau « * ») -> suivent leurs niveaux.
Les autres points sont regroupés par règle et catégorie, à vérifier.

La géométrie (shapely, comme preuves.py) donne les aires et les tracés ; sans elle, les aires viennent
des bilans de niveau et les découpes n'ont pas de tracé.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from . import rules
from .rules import _m2
from .config import Config

ABORDS, TOITURES, SC_IMPLICITE, AGREGATS = "abords", "toitures", "sc-implicite", "agregats"
TITLES = {
    TOITURES: "Toitures comptées en SEP",
    ABORDS: "SEP du niveau du terrain : abords SA",
    SC_IMPLICITE: "Surface de construction implicite",
    AGREGATS: "Agrégats par bâtiment et projet",
}
WHY = {
    TOITURES: "Une toiture non accessible n'est ni de la SP ni de la SEP (SIA 416 §3) ; Treegram la classe déjà en "
              "SPT. Les toitures-jardins et terrasses accessibles restent en SEU : à vérifier sur les plans.",
    ABORDS: "Une surface externe au contact direct du terrain relève des abords SA, y compris une dalle sur sous-sol "
            "aménagée (SIA 416 §1.2, §3). Les terrasses déjà classées SEU/SED restent en SEP.",
    SC_IMPLICITE: "Résidu compatible avec la surface de construction, intérieure (SC : murs, cloisons) ou externe "
                  "(SEC : garde-corps, murets des balcons et terrasses), que Treegram ne crée pas : il la considère déduite.",
    AGREGATS: "Sommes des contrôles de niveau : se corrigent avec les sujets de leurs niveaux.",
}
EXTERNAL_CLASSIFIED = ["SEU", "SED", "SEI"]


# --------------------------------------------------------------------------- géométrie

class _Geometry:
    """Emprises par (bâtiment, niveau) et code ; vide si shapely ou les maillages manquent."""

    def __init__(self, doc: dict):
        self.ok = False
        self.leaf: dict = defaultdict(lambda: defaultdict(list))
        self.node: dict = defaultdict(lambda: defaultdict(list))
        try:
            from shapely import union_all
            from .preuves import polygon_of
        except ImportError:
            return
        self._union_all = union_all
        for s in doc["surfaces"]:
            if s.get("mesh") and (g := polygon_of(s["mesh"])) is not None:
                code = s["code"] or s["category"]
                (self.node if s["kind"] == "node" else self.leaf)[(s["building"], s["level"])][code].append(g)
                self.ok = True

    def union(self, key, codes):
        """Surfaces élémentaires des codes ; à défaut de détail (SP, SEP), le total de niveau."""
        parts = []
        for c in codes:
            parts += self.leaf[key].get(c, []) or self.node[key].get(c, [])
        return self._union_all(parts) if parts else None

    def minus(self, geom, key, codes):
        other = self.union(key, codes)
        return geom if geom is None or other is None else geom.difference(other)


def _geojson(geom) -> dict | None:
    if geom is None or geom.is_empty:
        return None
    from shapely.geometry import mapping

    def rnd(x):
        if isinstance(x, (tuple, list)) and x and isinstance(x[0], (int, float)):
            return [round(float(v), 3) for v in x[:2]]
        return [rnd(v) for v in x]

    m = mapping(geom)
    if m["type"] not in ("Polygon", "MultiPolygon"):   # collection : garder les seules parties surfaciques
        polys = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            return None
        from shapely import union_all
        m = mapping(union_all(polys))
    return {"type": m["type"], "coordinates": rnd(m["coordinates"])}


def _trace(geom, z: float | None) -> dict | None:
    """Tracé triangulé pour la 3D de la visionneuse : {"z", "v": [x, y, …], "i": [a, b, c, …]}."""
    if geom is None or geom.is_empty or z is None:
        return None
    from shapely import constrained_delaunay_triangles
    polys = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type in ("Polygon", "MultiPolygon")]
    v: list[float] = []
    idx: list[int] = []
    index: dict[tuple, int] = {}
    for poly in polys:
        for tri in constrained_delaunay_triangles(poly).geoms:
            for x, y in list(tri.exterior.coords)[:3]:
                key = (round(x, 3), round(y, 3))
                if key not in index:
                    index[key] = len(index)
                    v.extend(key)
                idx.append(index[key])
    return {"z": round(z, 3), "v": v, "i": idx} if idx else None


def _top_z(surface: dict | None) -> float | None:
    """Altitude du dessus d'une surface (maillage du cache VWR)."""
    m = (surface or {}).get("mesh")
    return max(m["v"][2::3]) if m and m.get("v") else None


# --------------------------------------------------------------------------- regroupement

def _node_id(doc_index: dict, key, code) -> str | None:
    return doc_index.get((key[0], key[1], code))


def build(doc: dict, cfg: Config) -> dict:
    issues = doc["issues"]
    levels = {(lv["building"], lv["level"]): lv for lv in doc["levels"]}
    nodes = {(s["building"], s["level"], s["code"] or s["category"]): s["id"]
             for s in doc["surfaces"] if s["kind"] == "node"}
    node_area = {(s["building"], s["level"], s["code"] or s["category"]): s["area"] or 0
                 for s in doc["surfaces"] if s["kind"] == "node"}
    geo = _Geometry(doc)
    by_id = {s["id"]: s for s in doc["surfaces"]}
    tol = cfg.abs_m2

    def val(key, code) -> float:
        return float((levels.get(key) or {}).get("values", {}).get(code) or 0)

    a2 = {(i["building"], i["level"]) for i in issues if i["rule"] == "A2"}
    a1 = {(i["building"], i["level"]) for i in issues if i["rule"] == "A1"}
    r3 = {(i["building"], i["level"]) for i in issues if i["rule"] == "R3" and i["level"] != rules.ALL}

    # Part de toiture (SPT) dans la SEP des niveaux à plancher : attiques.
    roof_part: dict[tuple, object] = {}
    if geo.ok:
        for key in r3 - a2:
            sep = geo.union(key, ["SEP"])
            spt = geo.union(key, ["SPT"])
            if sep is None or spt is None:
                continue
            part = geo.minus(geo.minus(sep.intersection(spt), key, EXTERNAL_CLASSIFIED), key, ["SP"])
            if part.area > tol:
                roof_part[key] = part
    roofs = a2 | set(roof_part)
    grounds = a1 - roofs

    subjects: dict[str, dict] = {}

    def subject(sid: str, cause: str, action: str, title=None, why=None) -> dict:
        return subjects.setdefault(sid, {"id": sid, "titre": title or TITLES.get(sid, sid), "cause": cause,
                                         "action": action, "explication": why or WHY.get(sid, ""),
                                         "points": [], "m2": 0.0, "corrections": []})

    for i in issues:
        key = (i["building"], i["level"])
        if i["level"] == rules.ALL and i["rule"] != "A3":   # A3 : codes inconnus, listés au niveau « * »
            s = subject(AGREGATS, AGREGATS, "aucune")
        elif i["rule"] == "A2" or (i["rule"] == "R3" and key in roofs):
            s = subject(TOITURES, TOITURES, "corriger")
        elif i["rule"] == "A1" or (i["rule"] == "R3" and key in grounds):
            s = subject(ABORDS, ABORDS, "corriger")
        elif i["rule"] in ("R1", "R3") and i["verdict"] == "INFO":
            s = subject(SC_IMPLICITE, SC_IMPLICITE, "aucune")
        else:
            sid = f"{i['rule']}-{i['category']}"
            s = subject(sid, sid, "à vérifier", title=f"{rules.title_of(i['rule'], i['verdict'])} ({i['category']})",
                        why=i.get("hint") or "")
        s["points"].append(i["key"])

    # Corrections de base.
    for key in sorted(roofs, key=lambda k: (k[0], rules.level_rank(k[1], cfg) or 0)):
        sep_id = _node_id(nodes, key, "SEP")
        if sep_id is None:
            continue
        b, lvl = key
        classified = sum(val(key, c) for c in EXTERNAL_CLASSIFIED)
        c = {"id": f"{TOITURES}-{b}-{lvl}", "op": "exclure", "cible": {"ids": [sep_id]}}
        if key in roof_part:
            part = roof_part[key]
            c.update(aire=round(part.area, 2), polygone=_geojson(part), trace=_trace(part, _top_z(by_id.get(sep_id))),
                     explication=f"{b} {lvl} : {_m2(part.area)} m² de SEP sous la toiture Treegram (SPT), hors "
                                 f"terrasses classées SEU/SED.")
        elif classified <= tol:
            c["explication"] = f"{b} {lvl} : niveau de toiture sans plancher ni terrasse classée, SEP entière exclue."
        else:
            sep = node_area.get((b, lvl, "SEP"), 0)
            region = geo.minus(geo.union(key, ["SEP"]), key, EXTERNAL_CLASSIFIED) if geo.ok else None
            aire = region.area if region is not None else sep - classified
            c.update(aire=round(max(aire, 0), 2), polygone=_geojson(region),
                     trace=_trace(region, _top_z(by_id.get(sep_id))),
                     explication=f"{b} {lvl} : SEP hors terrasses classées ({_m2(classified)} m² de SEU/SED gardés).")
        _propose(subjects[TOITURES], c, node_area.get((b, lvl, "SEP"), 0))

    for key in sorted(grounds, key=lambda k: (k[0], rules.level_rank(k[1], cfg) or 0)):
        sep_id = _node_id(nodes, key, "SEP")
        if sep_id is None:
            continue
        b, lvl = key
        region = None
        if geo.ok and (sep := geo.union(key, ["SEP"])) is not None:
            region = geo.minus(geo.minus(sep, key, ["SP"]), key, EXTERNAL_CLASSIFIED)
            aire = region.area
        else:
            aire = node_area.get((b, lvl, "SEP"), 0) - sum(val(key, c) for c in EXTERNAL_CLASSIFIED)
        if aire <= tol:
            continue
        _propose(subjects[ABORDS], {
            "id": f"{ABORDS}-{b}-{lvl}", "op": "découper", "cible": {"ids": [sep_id]}, "vers": "SA",
            "aire": round(aire, 2), "polygone": _geojson(region), "trace": _trace(region, _top_z(by_id.get(sep_id))),
            "explication": f"{b} {lvl} : {_m2(aire)} m² de SEP hors plancher et hors SEU/SED, au contact du terrain.",
        }, aire)

    order = [TOITURES, ABORDS, SC_IMPLICITE, AGREGATS]
    out = sorted(subjects.values(), key=lambda s: (order.index(s["id"]) if s["id"] in order else len(order), s["id"]))
    for s in out:
        s["m2"] = round(s["m2"], 2)
        if s["action"] == "corriger" and not s["corrections"]:
            s["action"] = "à vérifier"
    return {"version": 1, "geometry": geo.ok, "subjects": out}


def _propose(subject: dict, correction: dict, m2: float) -> None:
    """`m2` : surface en jeu (l'aire découpée ou exclue, sinon l'aire entière de la cible)."""
    m2 = round(float(correction.get("aire") or m2 or 0), 2)
    subject["corrections"].append({**correction, "m2": m2, "sujet": subject["id"], "origine": "règle",
                                   "statut": "proposée"})
    subject["m2"] += m2


# --------------------------------------------------------------------------- revue IA

DECISIONS = ("garder", "modifier", "rejeter", "ajouter")
EDITABLE = ("op", "cible", "vers", "aire", "affectation", "explication")
REJECTED = "rejetée"


def apply_review(base: dict, review: dict, surface_ids: set[str] | None = None) -> dict:
    """Sujets réorientés par la revue IA (fichier verdicts, bloc `sujets`).

    Format du bloc (voir .claude/skills/revue-ia/SKILL.md, étape 6) :

        "sujets": {"S1": {"titre", "certitude", "action": "corriger|aucune|à vérifier", "explication",
                          "base": ["abords"], "par_defaut": "garder|rejeter",
                          "decisions": [{"id", "decision": "garder|modifier|rejeter|ajouter", "explication",
                                         + champs modifiés ou correction complète pour « ajouter »}]}}

    - Les points dont le verdict IA cite un sujet S… passent dans ce sujet ; les autres restent dans leur
      sujet de base (faux positifs, agrégats…).
    - Une proposition de base décidée par l'IA passe dans son sujet, `origine` « ia » ; `par_defaut`
      s'applique aux propositions des sujets `base` que les décisions ne citent pas.
    - « rejeter » garde la correction au statut « rejetée », pour la traçabilité ; « modifier » change
      les seuls champs donnés (`EDITABLE`) et retire un tracé devenu faux (`a_retracer`) ;
      « ajouter » crée une correction complète.
    - Une décision inapplicable (id inconnu, correction incomplète, cible absente) est écartée et listée
      dans `revue.problemes` ; le reste de la revue s'applique.
    Les corrections restent « proposée » : l'utilisateur les accepte.
    """
    from . import corrections   # évite l'import circulaire au chargement

    proposals = {c["id"]: (s["id"], c) for s in base["subjects"] for c in s["corrections"]}
    used: set[str] = set()
    problems: list[dict] = []
    ai_subjects = review.get("sujets") or {}
    verdicts = review.get("points") or {}

    def problem(sid, did, why):
        problems.append({"sujet": sid, "id": did, "raison": why})

    def target_ok(c) -> bool:
        ids = (c.get("cible") or {}).get("ids")
        return surface_ids is None or not ids or all(str(i) in surface_ids for i in ids)

    out_ai = []
    for sid, spec in ai_subjects.items():
        decided: list[dict] = []
        for d in spec.get("decisions") or []:
            did, kind = d.get("id"), d.get("decision")
            if kind not in DECISIONS:
                problem(sid, did, f"décision inconnue « {kind} »")
                continue
            if kind == "ajouter":
                if not did or did in proposals or did in used:
                    problem(sid, did, "« ajouter » demande un id nouveau")
                    continue
                c = {k: v for k, v in d.items() if k != "decision"}
                why = corrections._problem(c)
                if why or not target_ok(c):
                    problem(sid, did, why or "cible inconnue")
                    continue
                decided.append({**c, "sujet": sid, "origine": "ia", "statut": "proposée", "revue": "ajoutée"})
                used.add(did)
                continue
            if did not in proposals:
                problem(sid, did, "proposition inconnue")
                continue
            if did in used:
                problem(sid, did, "proposition décidée deux fois")
                continue
            c = dict(proposals[did][1])
            if kind == "modifier":
                changes = {k: v for k, v in d.items() if k in EDITABLE}
                if "aire" in changes and c.get("polygone"):
                    c.pop("polygone")
                    c.pop("trace", None)
                    c["a_retracer"] = True
                c.update(changes)
                c["base"] = {k: proposals[did][1].get(k) for k in changes}
                why = corrections._problem(c)
                if why or not target_ok(c):
                    problem(sid, did, why or "cible inconnue")
                    continue
            elif d.get("explication"):
                c["explication"] = d["explication"]
            c.update(sujet=sid, origine="ia", revue=kind, statut=REJECTED if kind == "rejeter" else "proposée")
            decided.append(c)
            used.add(did)
        default = spec.get("par_defaut")
        if default in ("garder", "rejeter"):
            for bid in spec.get("base") or []:
                for c in next((s["corrections"] for s in base["subjects"] if s["id"] == bid), []):
                    if c["id"] not in used:
                        decided.append({**c, "sujet": sid, "origine": "ia", "revue": default,
                                        "statut": REJECTED if default == "rejeter" else "proposée"})
                        used.add(c["id"])
        elif default is not None:
            problem(sid, None, f"par_defaut « {default} » : garder ou rejeter attendu")
        out_ai.append({"id": sid, "titre": spec.get("titre") or sid, "cause": ",".join(spec.get("base") or []) or "ia",
                       "action": spec.get("action") or ("corriger" if decided else "à vérifier"),
                       "certitude": spec.get("certitude"), "explication": spec.get("explication") or "",
                       "origine": "ia", "points": [], "m2": 0.0, "corrections": decided})

    by_ai = {s["id"]: s for s in out_ai}
    remaining = []
    for s in base["subjects"]:
        rest = dict(s, points=[], corrections=[c for c in s["corrections"] if c["id"] not in used], m2=0.0)
        for key in s["points"]:
            ai = (verdicts.get(key) or {}).get("sujet")
            (by_ai[ai] if ai in by_ai else rest)["points"].append(key)
        if rest["points"] or rest["corrections"]:
            remaining.append(rest)
    for s in out_ai + remaining:
        s["m2"] = round(sum(float(c.get("aire") or c.get("m2") or 0)
                            for c in s["corrections"] if c.get("statut") != REJECTED), 2)
    unknown_points = sorted(set(verdicts) - {k for s in base["subjects"] for k in s["points"]})
    return {**base, "subjects": out_ai + remaining,
            "revue": {"date": review.get("revue_ia"), "modele": review.get("modele"),
                      "decisions": len(used), "problemes": problems, "points_inconnus": unknown_points}}


def load_review(path: str | Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        from .corrections import JournalError
        raise JournalError(f"revue IA illisible : {path} ({ex})") from ex


# --------------------------------------------------------------------------- journal

def journal(subjects: dict, project: str | None = None) -> dict:
    """Journal de corrections (corrections.py) reprenant toutes les corrections proposées.

    `sujets.write(sj | journal(sj))` donne un seul fichier : sujets pour la lecture, `corrections` pour
    `sia-check --corrections`, une fois les statuts passés à « acceptée »."""
    return {"version": 1, "projet": project,
            "corrections": [c for s in subjects["subjects"] for c in s["corrections"]]}


def summary(subjects: dict) -> str:
    """« toitures 22 corrections · abords 9 · … » pour le journal de la CLI."""
    return " · ".join(f"{s['id']} {len(s['points'])} pts" + (f", {len(s['corrections'])} corr." if s["corrections"] else "")
                      for s in subjects["subjects"])


def write(subjects: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(subjects, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
