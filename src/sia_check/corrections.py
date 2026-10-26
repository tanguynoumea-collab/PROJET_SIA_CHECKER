"""Corrections de surfaces : journal JSON, application au DataFrame des surfaces, avant / après.

Une correction est une opération sur des surfaces lues ; le `.tgm` n'est jamais modifié. Le journal
(un par projet) est écrit par la visionneuse ou par la revue IA :

    {"version": 1, "projet": "L OREE", "corrections": [
      {"id": "c1", "op": "exclure", "cible": {"selection": {"category": "SEP", "level": "Toiture"}},
       "sujet": "S2", "origine": "ia", "statut": "acceptée",
       "explication": "Toiture non accessible : ni SP ni SEP (SIA 416 §3).", "auteur": "…", "date": "2026-10-22"},
      {"id": "c2", "op": "découper", "cible": {"ids": ["B03_N00_SEP#total"]}, "vers": "SA", "aire": 1943.2,
       "polygone": [[x, y], …], …}
    ]}

Opérations (`op`) :
    reclasser  catégorie des cibles -> `vers`
    exclure    cibles retirées des sommes et des exports SIA (motif dans `explication`)
               avec `aire` : une seule cible, seule cette part est retirée (ex. toit d'attique) ;
               `polygone` (tracé) facultatif
    découper   une seule cible : `aire` m² passent dans une nouvelle surface de catégorie `vers`, même
               bâtiment, même niveau ; `polygone` (tracé) facultatif. Quand `vers` est une sous-catégorie
               de la cible (SEP -> SEU, SP -> SUS), l'aire est classée sans quitter la cible : le total
               garde son aire, la part non classée devient une sous-catégorie (config requise). La nouvelle
               surface est élémentaire si `vers` en a déjà au niveau (sinon elle serait masquée par elles),
               sinon de la même sorte que la cible
    ajuster    aire des cibles fixée à `aire`
    remodeler  une seule cible : nouvelle emprise `polygone` (dessinée dans la visionneuse), aire `aire` ; `vers`
               facultatif change aussi la catégorie (NC : non comptabilisée). La surface prend la géométrie du tracé
               (`geometrie`). Refusé sur un total de niveau Treegram dont les pièces sont livrées (sans effet)
    créer      nouvelle surface `vers` sur le niveau `niveau` ({building, level}), d'aire `aire`, de géométrie
               `polygone` à l'altitude `z` (facultatifs) ; pas de `cible`. Élémentaire si `vers` en a déjà au
               niveau (son total suit), sinon total de niveau
    affecter   colonne `affectation` (tableau MDP) fixée à `affectation`
    renseigner champs du tableau MDP sans surface (`champs` : {colonne: valeur}), pour les lots ou les
               bâtiments visés par `selection` (`bedrooms`, `building`) : typologies, forme (propositions.py)

Propositions refusées : une correction `affecter` ou `renseigner` au statut « rejetée » écrit « Inconnu »
(V2_PLAN §5.3 : la proposition se prend, ou l'on répond « Inconnu »).

Cible (`cible`) : `ids` (identifiants de surface), `tgm_ids` (ID TGM), ou `selection` : critères sur
`building`, `level`, `category`, `kind`, `room_type`, `lot`, `bedrooms` ; une valeur ou une liste, « * » ou absent
= tous ; `avec_lot` : true / false (surface d'appartement ou non).

Seules les corrections `statut` = « acceptée » sont appliquées, dans l'ordre du journal. Une correction
inapplicable (cible introuvable, champ manquant) est rapportée, jamais appliquée à moitié.

Tracés : une découpe ou une exclusion partielle peut porter son `polygone` (GeoJSON, dessiné dans la visionneuse
ou pré-calculé par sujets.py). Quand la géométrie des surfaces est connue (`geometry`), l'aire est recalculée à
l'application selon la règle de la visionneuse : polygone ∩ surface visée, moins les SEU / SED / SEI du niveau
pour une SEP. Au-delà de la tolérance, l'aire recalculée remplace celle du journal, et le journal le signale.

Totaux de niveau : les surfaces élémentaires font foi quand il y en a (rules.level_totals). Quand une
correction déplace l'aire d'une surface élémentaire, le total Treegram de sa catégorie est décalé
d'autant ; sinon un total devenu orphelin reprendrait la main sur une catégorie vidée.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import rules
from .config import Config

OPS = ("reclasser", "exclure", "découper", "ajuster", "remodeler", "créer", "affecter", "renseigner")
REJECTED = "rejetée"
UNKNOWN = "Inconnu"
ACCEPTED = "acceptée"
SELECT_FIELDS = ("building", "level", "category", "kind", "room_type", "lot", "bedrooms", "avec_lot")
APPLIED, NOT_FOUND, REFUSED, SKIPPED = "appliquée", "cible introuvable", "refusée", "non acceptée"


class JournalError(ValueError):
    pass


@dataclass
class Applied:
    surfaces: pd.DataFrame   # toutes les surfaces, exclues comprises ; colonnes de suivi ci-dessous
    log: pd.DataFrame        # une ligne par correction du journal
    infos: list[dict] = field(default_factory=list)   # « renseigner » : [{"selection", "champs"}] pour le MDP

    @property
    def kept(self) -> pd.DataFrame:
        """Surfaces vues par les règles et les exports (sans les exclues)."""
        return self.surfaces[~self.surfaces["excluded"]].drop(columns=TRACK_COLUMNS)


TRACK_COLUMNS = ["excluded", "corrections", "original_category", "original_area"]
# Géométrie dessinée d'une surface remodelée ou créée : {"polygone": GeoJSON, "z": altitude} ; la visionneuse la
# triangule à la place du maillage du cache VWR (viewer.build).
GEOMETRY_COLUMN = "geometrie"
# Parts retirées de l'emprise d'une surface par une découpe ou une exclusion partielle tracées : [GeoJSON, …].
# La visionneuse les soustrait du maillage (viewer.build) ; la part découpée porte sa géométrie (`dans` = surface
# d'origine, pour la découper à son emprise).
CUTS_COLUMN = "retraits"


# --------------------------------------------------------------------------- journal

def load(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        raise JournalError(f"journal de corrections illisible : {path} ({ex})") from ex
    return validate(data)


def validate(data: dict) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("corrections"), list):
        raise JournalError("journal de corrections : liste « corrections » attendue")
    ids = [c.get("id") for c in data["corrections"] if isinstance(c, dict)]
    if len(ids) != len(data["corrections"]) or any(not i for i in ids):
        raise JournalError("journal de corrections : chaque correction est un objet avec un « id »")
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise JournalError(f"journal de corrections : identifiants en double {sorted(dup)}")
    return data


def write(data: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validate(data), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- application

def _problem(c: dict) -> str | None:
    """Raison de refus d'une correction acceptée, None si elle est complète."""
    op = c.get("op")
    if op not in OPS:
        return f"opération inconnue « {op} »"
    if op == "créer":
        niveau = c.get("niveau")
        if not isinstance(niveau, dict) or not niveau.get("building") or not niveau.get("level"):
            return "« niveau » attendu pour créer ({building, level})"
    else:
        cible = c.get("cible")
        if not isinstance(cible, dict) or not ({"ids", "tgm_ids", "selection"} & set(cible)):
            return "cible manquante (ids, tgm_ids ou selection)"
    if op in ("reclasser", "découper", "créer") and not c.get("vers"):
        return f"« vers » manquant pour {op}"
    if op == "remodeler" and not isinstance(c.get("polygone"), dict):
        return "« polygone » attendu pour remodeler (nouvelle emprise)"
    if op in ("découper", "ajuster", "remodeler", "créer") or (op == "exclure" and c.get("aire") is not None):
        a = c.get("aire")
        if not isinstance(a, (int, float)) or isinstance(a, bool) or a < 0:
            return f"« aire » positive attendue pour {op}"
    if op == "renseigner" and not isinstance(c.get("champs"), dict):
        return "« champs » attendu pour renseigner ({colonne: valeur})"
    if op == "affecter" and not c.get("affectation"):
        return "« affectation » manquante"
    return None


def _target(df: pd.DataFrame, cible: dict) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    if "ids" in cible:
        mask &= df["id"].astype(str).isin([str(i) for i in cible["ids"]])
    if "tgm_ids" in cible:
        mask &= df["tgm_id"].isin(cible["tgm_ids"]) if "tgm_id" in df else False
    for field, want in (cible.get("selection") or {}).items():
        if field not in SELECT_FIELDS:
            raise JournalError(f"critère de sélection inconnu « {field} » (attendu : {', '.join(SELECT_FIELDS)})")
        if field == "avec_lot":
            mask &= df["lot"].notna() if want else df["lot"].isna()
            continue
        if want in (None, "*") or field not in df:
            continue
        values = [want] if isinstance(want, (str, int, float)) else list(want)
        if field == "bedrooms":   # numérique dans le DataFrame : comparer les nombres
            mask &= pd.to_numeric(df[field], errors="coerce").isin([float(v) for v in values])
        else:
            mask &= df[field].astype(str).isin([str(v) for v in values])
    return mask & ~df["excluded"]


def _shift_node(df: pd.DataFrame, building, level, category, delta: float) -> None:
    """Décale le total de niveau d'une catégorie (s'il existe) quand une surface élémentaire bouge."""
    if not delta:
        return
    m = (df.kind == "node") & (df.building == building) & (df.level == level) & (df.category == category) & ~df.excluded
    df.loc[m, "area"] = df.loc[m, "area"].fillna(0) + delta


def _mark(df: pd.DataFrame, idx, cid: str) -> None:
    df.loc[idx, "corrections"] = [f"{c};{cid}" if c else cid for c in df.loc[idx, "corrections"]]


def _descends(cfg: Config | None, code: str, ancestor: str) -> bool:
    """`code` est-il une sous-catégorie (à tout degré) de `ancestor` ?"""
    if cfg is None or code not in cfg.categories or ancestor not in cfg.categories:
        return False
    code, ancestor = cfg.canonical(code), cfg.canonical(ancestor)
    seen = set()
    while code is not None and code not in seen:
        seen.add(code)
        code = cfg.categories.get(code, {}).get("parent")
        if code == ancestor:
            return True
    return False


def _geometry(c: dict) -> dict | None:
    return {"polygone": c["polygone"], "z": c.get("z")} if isinstance(c.get("polygone"), dict) else None


def _cut(df: pd.DataFrame, i, c: dict) -> None:
    """Tracé d'une découpe ou d'une exclusion partielle : retiré de l'emprise affichée de la surface d'origine."""
    if isinstance(c.get("polygone"), dict):
        df.at[i, CUTS_COLUMN] = [*(df.at[i, CUTS_COLUMN] or []), c["polygone"]]


def _create(df: pd.DataFrame, c: dict) -> tuple[pd.DataFrame, int, float]:
    """`créer` : nouvelle surface du niveau ; elle rejoint le détail de sa catégorie s'il existe."""
    b, lvl, code, aire = c["niveau"]["building"], c["niveau"]["level"], c["vers"], float(c["aire"])
    same = (df.building == b) & (df.level == lvl)
    if not same.any():
        raise _Refuse(f"niveau {b} {lvl} inconnu")
    leaves = same & (df.kind == "leaf") & (df.category == code) & ~df.excluded
    new = {col: None for col in df.columns}
    new.update(id=f"{b}_{lvl}_{code}#{c['id']}", building=b, level=lvl, category=code, area=aire,
               kind="leaf" if leaves.any() else "node", excluded=False, corrections=c["id"])
    if "elevation" in df:
        new["elevation"] = df.loc[same, "elevation"].dropna().iloc[0] if df.loc[same, "elevation"].notna().any() else None
    new[GEOMETRY_COLUMN] = _geometry(c)
    if new["kind"] == "leaf":
        _shift_node(df, b, lvl, code, aire)
    return pd.concat([df, pd.DataFrame([new])], ignore_index=True), 1, aire


def _apply_one(df: pd.DataFrame, c: dict, cfg: Config | None = None) -> tuple[pd.DataFrame, int, float]:
    """Applique une correction ; renvoie (surfaces, nombre de surfaces touchées, m² déplacés ou modifiés)."""
    op, cid = c["op"], c["id"]
    if op == "créer":
        return _create(df, c)
    idx = df.index[_target(df, c["cible"])]
    partial = op == "exclure" and c.get("aire") is not None
    if (op in ("découper", "remodeler") or partial) and len(idx) != 1:
        raise _Refuse(f"{op} d'une partie vise une seule surface ({len(idx)} trouvées)")
    if len(idx) == 0:
        return df, 0, 0.0
    moved = 0.0
    if partial:
        i = idx[0]
        r = df.loc[i]
        aire = float(c["aire"])
        if aire > float(r.area or 0) + 1e-6:
            raise _Refuse(f"aire exclue {aire:.2f} m² > aire de la surface {float(r.area or 0):.2f} m²")
        if r.kind == "leaf":
            _shift_node(df, r.building, r.level, r.category, -aire)
        df.loc[i, "area"] = float(r.area or 0) - aire
        _cut(df, i, c)
        moved = aire
    elif op == "reclasser":
        for i in idx:
            r = df.loc[i]
            if r.kind == "leaf" and r.category != c["vers"]:
                _shift_node(df, r.building, r.level, r.category, -(r.area or 0))
                _shift_node(df, r.building, r.level, c["vers"], r.area or 0)
            moved += float(r.area or 0)
        df.loc[idx, "category"] = c["vers"]
    elif op == "exclure":
        for i in idx:
            r = df.loc[i]
            if r.kind == "leaf":
                _shift_node(df, r.building, r.level, r.category, -(r.area or 0))
            moved += float(r.area or 0)
        df.loc[idx, "excluded"] = True
    elif op == "remodeler":
        i = idx[0]
        r = df.loc[i]
        if r.kind == "node" and ((df.kind == "leaf") & (df.building == r.building) & (df.level == r.level)
                                 & (df.category == r.category) & ~df.excluded).any():
            raise _Refuse(f"total de niveau Treegram {r.category} doublé par ses pièces (le détail fait foi) : "
                          f"modifiez les pièces")
        aire, to = float(c["aire"]), c.get("vers") or r.category
        if r.kind == "leaf":   # le total de niveau perd l'ancienne surface et gagne la nouvelle
            _shift_node(df, r.building, r.level, r.category, -float(r.area or 0))
            _shift_node(df, r.building, r.level, to, aire)
        moved = abs(aire - float(r.area or 0))
        df.loc[i, "area"] = aire
        df.loc[i, "category"] = to
        df.at[i, GEOMETRY_COLUMN] = _geometry(c)
    elif op == "ajuster":
        for i in idx:
            r = df.loc[i]
            delta = float(c["aire"]) - float(r.area or 0)
            if r.kind == "leaf":
                _shift_node(df, r.building, r.level, r.category, delta)
            moved += abs(delta)
        df.loc[idx, "area"] = float(c["aire"])
    elif op == "découper":
        i = idx[0]
        r = df.loc[i].copy()
        aire = float(c["aire"])
        if aire > float(r.area or 0) + 1e-6:
            raise _Refuse(f"aire découpée {aire:.2f} m² > aire de la surface {float(r.area or 0):.2f} m²")
        inside = _descends(cfg, c["vers"], r.category)   # classée dans la cible : la cible garde son aire
        if not inside:
            df.loc[i, "area"] = float(r.area or 0) - aire
        new = r.copy()
        new["id"] = f"{r['id']}#{cid}"
        new["category"], new["area"] = c["vers"], aire
        leaves = (df.kind == "leaf") & (df.building == r.building) & (df.level == r.level)             & (df.category == c["vers"]) & ~df.excluded
        new["kind"] = "leaf" if leaves.any() else r.kind
        for col in ("element_id", "tgm_id"):
            if col in new:
                new[col] = None
        new["original_category"], new["original_area"], new["corrections"] = None, None, cid
        new[CUTS_COLUMN] = None
        if (geo := _geometry(c)) is not None:
            new[GEOMETRY_COLUMN] = {**geo, "dans": str(r["id"])}
        _cut(df, i, c)
        if r.kind == "leaf" and not inside:   # l'aire quitte le total de niveau de la cible
            _shift_node(df, r.building, r.level, r.category, -aire)
        if new["kind"] == "leaf":   # et rejoint celui de sa nouvelle catégorie
            _shift_node(df, r.building, r.level, c["vers"], aire)
        df = pd.concat([df, pd.DataFrame([new.to_dict()])], ignore_index=True)
        moved = aire
    elif op == "affecter":
        df.loc[idx, "affectation"] = c["affectation"]
    elif op == "renseigner":   # rien sur les surfaces : les champs vont au MDP (Applied.infos)
        return df, len(idx), 0.0
    _mark(df, idx, cid)
    return df, len(idx), moved


class _Refuse(Exception):
    pass


CLASSIFIED_EXTERNAL = ("SEU", "SED", "SEI")


def _traced_area(df: pd.DataFrame, c: dict, geometry) -> float | None:
    """Aire comptée du tracé d'une correction : polygone ∩ cible − sous-catégories externes classées du niveau ;
    pour une emprise redessinée ou une surface créée, l'aire du polygone lui-même."""
    if c.get("polygone") and c["op"] in ("remodeler", "créer"):
        try:
            from shapely.geometry import shape
        except ImportError:
            return None
        return float(shape(c["polygone"]).buffer(0).area)
    if geometry is None or not c.get("polygone") or c["op"] not in ("découper", "exclure"):
        return None
    try:
        from shapely.geometry import shape
        from shapely import union_all
    except ImportError:
        return None
    rows = df[_target(df, c["cible"])]
    if len(rows) != 1:
        return None
    src = geometry(rows.iloc[0])
    if src is None:
        return None
    region = shape(c["polygone"]).buffer(0).intersection(src)
    r = rows.iloc[0]
    if r.category == "SEP":
        same = df[(df.building == r.building) & (df.level == r.level) & (df.kind == "leaf")
                  & df.category.isin(CLASSIFIED_EXTERNAL) & ~df.excluded]
        parts = [g for g in (geometry(x) for _, x in same.iterrows()) if g is not None]
        if parts:
            region = region.difference(union_all(parts))
    return float(region.area)


def apply(df: pd.DataFrame, journal: dict, geometry=None, tolerance: tuple[float, float] = (0.5, 0.005),
          cfg: Config | None = None) -> Applied:
    """Applique les corrections acceptées du journal à une copie des surfaces lues (reader.read).

    `geometry(surface) -> polygone shapely | None` : géométrie en plan d'une surface, pour recalculer l'aire des
    corrections tracées ; `tolerance` : (m², relatif), comme config.yaml > tolerance ; `cfg` : hiérarchie des
    catégories, pour les découpes vers une sous-catégorie de la cible.
    """
    df = df.copy().reset_index(drop=True)
    df["excluded"] = False
    df["corrections"] = ""
    df["original_category"] = df["category"]
    df["original_area"] = df["area"]
    for col in (GEOMETRY_COLUMN, CUTS_COLUMN):
        if col not in df:
            df[col] = None
        df[col] = df[col].astype(object)
    if "affectation" not in df:
        df["affectation"] = None
    log, infos = [], []
    for c in journal.get("corrections", []):
        entry = {"id": c.get("id"), "op": c.get("op"), "sujet": c.get("sujet"), "origine": c.get("origine"),
                 "statut": c.get("statut"), "application": SKIPPED, "surfaces": 0, "m2": 0.0, "raison": ""}
        if c.get("statut") == REJECTED and c.get("op") in ("affecter", "renseigner") and not _problem(c):
            c = _unknown(c)   # proposition refusée : « Inconnu » au MDP
        if c.get("statut") in (ACCEPTED, UNKNOWN):
            reason = _problem(c)
            if reason:
                entry.update(application=REFUSED, raison=reason)
            else:
                try:
                    computed = _traced_area(df, c, geometry)
                    stated = float(c.get("aire") or 0)
                    if computed is not None and abs(computed - stated) > tolerance[0] \
                            and abs(computed - stated) > tolerance[1] * max(stated, computed):
                        c = {**c, "aire": round(computed, 2)}
                        entry["raison"] = f"aire recalculée depuis le tracé : {computed:.2f} m² au lieu de {stated:.2f}"
                    df, n, m2 = _apply_one(df, c, cfg)
                    if c["op"] == "renseigner":
                        infos.append({"selection": (c["cible"].get("selection") or {}), "champs": c["champs"]})
                    entry.update(application=APPLIED if n or c["op"] == "renseigner" else NOT_FOUND,
                                 surfaces=n, m2=round(m2, 3))
                    if c.get("statut") == UNKNOWN:
                        entry["raison"] = "proposition refusée : « Inconnu »"
                except _Refuse as ex:
                    entry.update(application=REFUSED, raison=str(ex))
        log.append(entry)
    df["area"] = pd.to_numeric(df["area"], errors="coerce")
    return Applied(df, pd.DataFrame(log, columns=["id", "op", "sujet", "origine", "statut", "application",
                                                  "surfaces", "m2", "raison"]), infos)


def _unknown(c: dict) -> dict:
    """Proposition refusée : mêmes cibles, valeurs « Inconnu » (statut interne UNKNOWN, appliqué)."""
    if c["op"] == "affecter":
        return {**c, "affectation": UNKNOWN, "statut": UNKNOWN}
    return {**c, "champs": {k: UNKNOWN for k in c["champs"]}, "statut": UNKNOWN}


# --------------------------------------------------------------------------- avant / après

KEY = ["building", "level", "lot", "rule", "category"]


def compare(before: rules.Result, after: rules.Result) -> pd.DataFrame:
    """Contrôles avant et après corrections, hors contrôles OK des deux côtés ; écart absolu décroissant."""
    cols = KEY + ["verdict", "diff_m2", "message"]
    b = before.residuals[cols].copy()
    a = after.residuals[cols].copy()
    for d in (a, b):
        d["lot"] = d["lot"].fillna("")
    m = b.merge(a, on=KEY, how="outer", suffixes=("_avant", "_apres"))
    m[["verdict_avant", "verdict_apres"]] = m[["verdict_avant", "verdict_apres"]].fillna("absent")
    m = m[~((m.verdict_avant.isin(["OK", "absent"])) & (m.verdict_apres.isin(["OK", "absent"])))]
    m["change"] = m.apply(_change, axis=1)
    return m.assign(_k=m.diff_m2_avant.abs().fillna(0)).sort_values("_k", ascending=False).drop(columns="_k")


def _change(r) -> str:
    before, after = r.verdict_avant, r.verdict_apres
    if after in ("OK", "absent"):
        return "résolu"
    if before in ("OK", "absent"):
        return "nouveau"
    if before != after:
        return f"{before} → {after}"
    d0, d1 = abs(r.diff_m2_avant or 0), abs(r.diff_m2_apres or 0)
    return "réduit" if d1 < d0 - 0.005 else "accru" if d1 > d0 + 0.005 else "inchangé"


def counts(result: rules.Result) -> dict[str, int]:
    return result.residuals.verdict.value_counts().reindex(rules.VERDICTS, fill_value=0).to_dict()


def summary(applied: Applied, before: rules.Result, after: rules.Result) -> dict:
    cmp = compare(before, after)
    return {
        "corrections": applied.log.to_dict("records"),
        "verdicts_avant": counts(before), "verdicts_apres": counts(after),
        "changements": cmp["change"].value_counts().to_dict(),
        "controles": json.loads(cmp.to_json(orient="records", force_ascii=False)),
    }


def write_summary(applied: Applied, before: rules.Result, after: rules.Result, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary(applied, before, after), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def run(df: pd.DataFrame, journal: dict, cfg: Config, geometry=None) -> tuple[Applied, rules.Result, rules.Result]:
    """(corrections appliquées, contrôles avant, contrôles après)."""
    applied = apply(df, journal, geometry, (cfg.abs_m2, cfg.rel), cfg)
    return applied, rules.run(df, cfg), rules.run(applied.kept, cfg)
