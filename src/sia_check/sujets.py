"""Sujets : points d'attention regroupés par cause, avec une correction de base proposée par sujet.

Entrée : le document visionneuse (viewer.build) — points, surfaces et maillages. Sortie :

    {"subjects": [{"id", "titre", "cause", "action", "explication", "points": [clés de points],
                   "m2", "corrections": [entrées de journal, statut « proposée »]}]}

`action` : « corriger » (corrections proposées), « aucune » (rien à faire : surface de construction
implicite, agrégats), « à vérifier » (pas de correction automatique). Les corrections suivent le format
de corrections.py ; la revue IA (phase 4) et l'utilisateur les acceptent, les modifient ou les rejettent.

Causes reconnues (L'Orée, revue IA du 22.10.2026) :
- toitures : SEP d'un niveau Toiture ou au-dessus du dernier plancher (A2), une fois retirées les toitures
  que Treegram classe en SPT (rules.COUNTED_IN) ; une toiture non accessible n'est ni SP ni SEP
  (SIA 416 §3) -> `exclure` la SEP du niveau, ou sa part hors terrasses classées ;
- abords : SEP non classée du niveau du terrain (A1), dalle au contact du terrain -> `découper` vers SA
  (SIA 416 §1.2) ; le tracé pré-calculé est la SEP hors plancher du niveau et hors SEU/SED ;
- sc-implicite : résidu R1 (SC) ou R3 (SEC) compatible avec la surface de construction, que Treegram ne crée
  pas -> aucune action ; depuis le 27.10.2026 ce résidu n'est plus un point d'attention (rules.implicit_construction) :
  le sujet ne se forme plus que sur des documents anciens ;
- agrégats : contrôles sommés par bâtiment ou sur le projet (niveau « * ») que les niveaux ne détaillent pas
  (les autres ne sont plus des points : rules.covered_aggregates) ;
- non classé : résidu R3 (SEP) ou R1 (SP) d'un niveau, hors toitures et abords -> `découper` la part non classée
  vers une sous-catégorie (SEU, SUS…, choisie dans la visionneuse) : une correction par niveau, la cible garde
  son aire (corrections.py), le résidu disparaît.
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
# Résidus d'un total racine : destination proposée par défaut (balcons non créés ; locaux sans type) et
# sous-catégories qui composent déjà le total, retirées du tracé.
UNCLASSIFIED = {
    "SEP": ("SEU", EXTERNAL_CLASSIFIED + ["SEC", "SECP", "SECN"]),
    "SP": ("SUS", ["SUP", "SUS", "SUT", "SD", "SI", "SC", "SCP", "SCN"]),
}
UNCLASSIFIED_WHY = {
    "SEP": "Choisir pour chaque niveau ce qu'est la SEP non classée : balcons ou terrasses (SEU), coursives (SED), "
           "installations (SEI), garde-corps et murets (SEC) ; au contact du terrain, abords (SA) ; toiture non "
           "accessible : exclure (SIA 416 §3).",
    "SP": "Choisir pour chaque niveau ce qu'est la SP non classée : utile (SUP, SUS), dégagement (SD), installations "
          "(SI) ou construction (SC, murs et cloisons) ; ajuster l'aire si seule une part est en cause (SIA 416 §2).",
}


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

    # Les toits d'attique classés SPT sont déjà retirés de la SEP (rules.COUNTED_IN) : seul A2 désigne une toiture.
    roofs = set(a2)
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

    # Corrections de base. Une part tracée en plusieurs morceaux d'un seul tenant donne une correction par morceau :
    # chacun se confirme ou change de catégorie indépendamment (trois morceaux de SEP au RDC : SA, SA et SEU…).
    def split(subject_id, base, region, z, why, aire_without_geometry):
        pieces = _pieces(region)
        if not pieces:
            _propose(subjects[subject_id], {**base, "aire": round(max(aire_without_geometry, 0), 2), "polygone": None,
                                            "trace": None, "explication": why(aire_without_geometry, "")}, 0)
            return
        for k, piece in enumerate(pieces, 1):
            c = {**base, "aire": round(piece.area, 2), "polygone": _geojson(piece), "trace": _trace(piece, z),
                 "explication": why(piece.area, f" (morceau {k} sur {len(pieces)})" if len(pieces) > 1 else "")}
            if len(pieces) > 1:
                c.update(id=f"{base['id']}-{k}", morceau=f"{k}/{len(pieces)}", groupe=base["id"])
            _propose(subjects[subject_id], c, 0)

    for key in sorted(roofs, key=lambda k: (k[0], rules.level_rank(k[1], cfg) or 0)):
        sep_id = _node_id(nodes, key, "SEP")
        if sep_id is None:
            continue
        b, lvl = key
        classified = sum(val(key, c) for c in EXTERNAL_CLASSIFIED)
        base = {"id": f"{TOITURES}-{b}-{lvl}", "op": "exclure", "cible": {"ids": [sep_id]}}
        z = _top_z(by_id.get(sep_id))
        roof = [c for c, host in rules.COUNTED_IN.items() if host == "SEP"]
        if classified <= tol and val(key, "SEP") >= node_area.get((b, lvl, "SEP"), 0) - tol:
            _propose(subjects[TOITURES], {**base, "explication": f"{b} {lvl} : niveau de toiture sans plancher ni "
                                                                 f"terrasse classée, SEP entière exclue."},
                     val(key, "SEP"))
        else:   # SEP hors terrasses classées et hors toitures déjà en SPT (retirées de la SEP)
            region = geo.minus(geo.union(key, ["SEP"]), key, EXTERNAL_CLASSIFIED + roof) if geo.ok else None
            split(TOITURES, base, region, z, lambda a, m: f"{b} {lvl}{m} : {_m2(a)} m² de SEP hors terrasses classées "
                  f"et toitures SPT ({_m2(classified)} m² de SEU/SED gardés).", val(key, "SEP") - classified)

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
        split(ABORDS, {"id": f"{ABORDS}-{b}-{lvl}", "op": "découper", "cible": {"ids": [sep_id]}, "vers": "SA"},
              region, _top_z(by_id.get(sep_id)),
              lambda a, m: f"{b} {lvl}{m} : {_m2(a)} m² de SEP hors plancher et hors SEU/SED, au contact du terrain.", aire)

    # Part non classée des SEP et SP de niveau : une découpe vers une sous-catégorie par morceau.
    for i in issues:
        key = (i["building"], i["level"])
        code = i["category"]
        if i["rule"] not in ("R1", "R3") or i["verdict"] != "ERREUR" or code not in UNCLASSIFIED                 or i["level"] == rules.ALL or (code == "SEP" and (key in roofs or key in grounds)):
            continue
        node_id = _node_id(nodes, key, code)
        diff = float(i.get("diff_m2") or 0)
        if node_id is None or diff <= tol:
            continue
        b, lvl = key
        to, classified = UNCLASSIFIED[code]
        region = geo.minus(geo.union(key, [code]), key, classified) if geo.ok else None
        sid = f"{i['rule']}-{code}"
        subjects[sid].update(action="corriger", explication=UNCLASSIFIED_WHY[code])
        split(sid, {"id": f"non-classe-{b}-{lvl}-{code}", "op": "découper", "cible": {"ids": [node_id]}, "vers": to},
              region, _top_z(by_id.get(node_id)),
              lambda a, m: f"{b} {lvl}{m} : {_m2(a)} m² de {code} sans sous-catégorie, classés en {to} par défaut ; "
                           f"choisir la bonne catégorie.", diff)

    order = [TOITURES, ABORDS, SC_IMPLICITE, AGREGATS]
    out = sorted(subjects.values(), key=lambda s: (order.index(s["id"]) if s["id"] in order else len(order), s["id"]))
    for s in out:
        s["m2"] = round(s["m2"], 2)
        if s["action"] == "corriger" and not s["corrections"]:
            s["action"] = "à vérifier"
    return {"version": 1, "geometry": geo.ok, "subjects": out}


# Miettes de tracé (artefacts le long des murs, 0,2 m de large sur L'Orée) : rejoignent le plus grand morceau.
MIN_PIECE = 1.0         # m²
MIN_PIECE_WIDTH = 0.8   # m : largeur moyenne 2 × aire / périmètre


def _pieces(region) -> list:
    """Morceaux d'un seul tenant d'une part tracée, du plus grand au plus petit ; vide sans géométrie."""
    if region is None or region.is_empty:
        return []
    from shapely import get_parts, union_all
    parts = sorted((g for g in get_parts(region) if g.geom_type in ("Polygon", "MultiPolygon") and g.area > 0),
                   key=lambda g: -g.area)
    def crumb(g):
        return g.area < MIN_PIECE or 2 * g.area / g.length < MIN_PIECE_WIDTH

    big = [g for g in parts if not crumb(g)]
    if not big:
        return [union_all(parts)] if parts else []
    crumbs = [g for g in parts if crumb(g)]
    if crumbs:
        big[0] = union_all([big[0], *crumbs])
    return big


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
    - Un sujet de base dont l'IA a repris toutes les propositions lui cède aussi ses points ; un sujet IA sans
      point ni correction n'est pas gardé.
    - Une proposition de base décidée par l'IA passe dans son sujet, `origine` « ia » ; `par_defaut`
      s'applique aux propositions des sujets `base` que les décisions ne citent pas.
    - « rejeter » garde la correction au statut « rejetée », pour la traçabilité ; « modifier » change
      les seuls champs donnés (`EDITABLE`) et retire un tracé devenu faux (`a_retracer`) ;
      « ajouter » crée une correction complète.
    - Une décision qui cite un niveau découpé en morceaux (`groupe`, ex. « abords-E09-N00 ») vaut pour chacun de ses
      morceaux ; une aire modifiée n'a alors plus de sens et la décision est écartée.
    - Une décision inapplicable (id inconnu, correction incomplète, cible absente) est écartée et listée
      dans `revue.problemes` ; le reste de la revue s'applique.
    Les corrections restent « proposée » : l'utilisateur les accepte.
    """
    from . import corrections   # évite l'import circulaire au chargement

    proposals = {c["id"]: (s["id"], c) for s in base["subjects"] for c in s["corrections"]}
    groups: dict[str, list[str]] = defaultdict(list)
    for _, c in proposals.values():
        if c.get("groupe"):
            groups[c["groupe"]].append(c["id"])
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
        decisions = []
        for d in spec.get("decisions") or []:
            pieces = groups.get(d.get("id")) if d.get("id") not in proposals and d.get("decision") != "ajouter" else None
            if not pieces:
                decisions.append(d)
            elif "aire" in d:
                problem(sid, d.get("id"), "aire modifiée sur un niveau découpé en morceaux")
            else:
                decisions += [{**d, "id": pid} for pid in pieces]
        for d in decisions:
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
    taken = {c["id"]: s["id"] for s in out_ai for c in s["corrections"]}   # proposition de base -> sujet IA
    remaining = []
    for s in base["subjects"]:
        rest = dict(s, points=[], corrections=[c for c in s["corrections"] if c["id"] not in used], m2=0.0)
        # Sujet de base dont l'IA a repris toutes les propositions : ses points suivent (sinon un doublon « corriger »
        # sans correction resterait), dans le sujet IA qui en a pris le plus.
        heir = None
        if s["corrections"] and not rest["corrections"]:
            owners = [taken[c["id"]] for c in s["corrections"] if c["id"] in taken]
            heir = max(set(owners), key=owners.count) if owners else None
        for key in s["points"]:
            ai = (verdicts.get(key) or {}).get("sujet")
            (by_ai[ai] if ai in by_ai else by_ai[heir] if heir else rest)["points"].append(key)
        if rest["points"] or rest["corrections"]:
            remaining.append(rest)
    # Sujet IA sans point ni correction (ses points ne sont plus des points d'attention : construction implicite,
    # agrégats détaillés par les niveaux) : rien à montrer
    out_ai = [s for s in out_ai if s["points"] or s["corrections"]]
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
