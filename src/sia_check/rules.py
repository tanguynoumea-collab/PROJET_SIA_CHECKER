"""Invariants SIA 416 et alertes : fonctions pures sur le DataFrame de reader.py.

Ce module ne connaît ni IfcOpenShell ni le format .tgm : il ne voit que les colonnes
`building, level, category, area, kind, lot, elevation`.

Sorties : un DataFrame de résidus (RESIDUAL_COLUMNS), une ligne par contrôle effectué.
Verdicts, du moins au plus grave : OK, INFO, ALERTE, ERREUR.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import pandas as pd

from .config import Config

RESIDUAL_COLUMNS = ["building", "level", "lot", "rule", "category", "expected", "obtained",
                    "diff_m2", "diff_pct", "verdict", "message"]
VERDICTS = ["OK", "INFO", "ALERTE", "ERREUR"]
FAILING = {"ALERTE", "ERREUR"}
ALL = "*"  # niveau ou bâtiment agrégé

# Codes portés par les règles de niveau (SIA 416).
SP, SU, SEP = "SP", "SU", "SEP"          # §2, §2.1.1, §3
# Chaîne USPI 2014 p. 4 : SH = SNH + SCI ; SBH = SH + MEM ; SVB = SBH + SE ; SVN = SH + SE.
SNH, SH, SBH, SVN, SVB = "SNH", "SH", "SBH", "SVN", "SVB"


@dataclass
class Result:
    residuals: pd.DataFrame   # tous les contrôles, verdict compris
    surfaces: pd.DataFrame    # surfaces connues, avec `code` normalisé et `ignored`
    unknown: pd.DataFrame     # surfaces dont la catégorie n'est pas dans la config (A3)
    totals: pd.DataFrame      # aire par (bâtiment, niveau) × code

    @property
    def failing(self) -> pd.DataFrame:
        return self.residuals[self.residuals.verdict.isin(FAILING)]

    @property
    def exit_code(self) -> int:
        return 1 if len(self.failing) else 0


# --------------------------------------------------------------------------- préparation

def classify(df: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sépare surfaces connues / inconnues ; ajoute `code` (alias résolu) et `ignored`."""
    df = df.copy()
    df["category"] = df["category"].fillna("").astype(str).str.strip()
    known = df["category"].isin(cfg.categories.keys())
    unknown = df[~known].copy()
    surf = df[known].copy()
    surf["code"] = surf["category"].map(cfg.canonical)
    # astype(bool) : sur une sélection vide, map() rend un dtype objet que pandas prendrait pour des noms de colonnes.
    surf["ignored"] = surf["category"].map(lambda c: bool(cfg.categories[c].get("ignore"))).astype(bool)
    return surf, unknown


def level_totals(surf: pd.DataFrame, include_ignored: bool = False) -> pd.DataFrame:
    """Aire par (building, level) × code ; NaN = catégorie absente du niveau.

    Une catégorie peut être fournie deux fois par Treegram : surfaces élémentaires et
    total de niveau. Les surfaces élémentaires font foi quand il y en a (elles sont
    plus fines et le total n'est pas toujours recalculé après modification) ; le total
    de niveau n'est utilisé que pour les catégories sans détail (ex. SP, SEP).
    `include_ignored` sert aux synthèses : les règles ne voient jamais les codes ignorés.
    """
    s = surf if include_ignored else surf[~surf["ignored"]]
    if s.empty:
        return pd.DataFrame(index=pd.MultiIndex.from_tuples([], names=["building", "level"]))
    g = s.groupby(["building", "level", "code", "kind"])["area"].sum(min_count=1).unstack("kind")
    val = g["leaf"] if "leaf" in g else pd.Series(float("nan"), index=g.index)
    if "node" in g:
        val = val.where(val.notna(), g["node"])
    return val.unstack("code")


def _exceeds(diff: float, ref: float, cfg: Config) -> bool:
    """Écart signalé si la tolérance absolue ET la tolérance relative sont dépassées."""
    if abs(diff) <= cfg.abs_m2:
        return False
    return ref == 0 or abs(diff) / abs(ref) > cfg.rel


def _m2(v: float) -> str:
    """Aire au format suisse des messages : 15 091,48 (espace fine insécable, virgule décimale)."""
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def _pct1(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def _pct(diff: float, ref: float) -> float:
    return float("nan") if not ref else 100.0 * diff / ref


def _row(building, level, rule, category, expected, obtained, verdict, message, lot=None) -> dict:
    diff = expected - obtained
    return {"building": building, "level": level, "lot": lot, "rule": rule, "category": category,
            "expected": expected, "obtained": obtained, "diff_m2": diff, "diff_pct": _pct(diff, expected),
            "verdict": verdict, "message": message}


# --------------------------------------------------------------------------- sommations (R1–R4)

def _effective(row: pd.Series, code: str, cfg: Config) -> tuple[float, bool]:
    """Valeur d'une catégorie : sa propre aire si présente, sinon la somme de ses enfants."""
    v = row.get(code)
    if v is not None and not pd.isna(v):
        return float(v), True
    kids = [_effective(row, k, cfg) for k in cfg.children(code)]
    return sum(v for v, _ in kids), any(p for _, p in kids)


def _present(row: pd.Series, code: str, cfg: Config) -> list[str]:
    """Codes réellement fournis qui composent la valeur de `code` (pour les messages)."""
    v = row.get(code)
    if v is not None and not pd.isna(v):
        return [code]
    return [c for k in cfg.children(code) for c in _present(row, k, cfg)]


def sum_checks(totals: pd.DataFrame, cfg: Config) -> list[dict]:
    """Parent = Σ enfants pour chaque catégorie qui a des enfants (SIA 416 §1, §2, §3).

    Résidu > 0 : surface non sous-classifiée (R1/R3), ou « implicite » si seule une
    sous-catégorie `optional` manque (SC, §2.2) et que le résidu reste sous `implicit_max_rel`.
    Résidu < 0 : sous-catégories sans parent suffisant -> R4.
    Un parent racine absent alors que ses enfants existent -> R4.

    Une catégorie intermédiaire (SN, SU, SC…) fournie sans aucun détail n'est pas contrôlée :
    rien ne dit qu'elle devait être subdivisée. Une racine (SP, SEP, ST) l'est toujours.

    Les contrôles sont faits par niveau, puis agrégés par bâtiment (level = *) et au total
    (building = level = *) en sommant les paires (attendu, obtenu) des seuls niveaux où le
    parent existe : additionner les catégories elles-mêmes fausserait le résultat quand une
    catégorie intermédiaire (ex. SU) n'est fournie que sur une partie des niveaux. Les
    sous-catégories orphelines restent signalées en R4 au niveau.
    """
    parents = [c for c in cfg.categories if cfg.children(c)]
    checks = []
    for (bld, lvl), row in totals.iterrows():
        for code in parents:
            own = row.get(code)
            kids = [(k, *_effective(row, k, cfg)) for k in cfg.children(code)]
            has_own, has_kids = own is not None and not pd.isna(own), any(p for _, _, p in kids)
            is_root = cfg.categories[code].get("parent") is None
            if not has_kids and not (has_own and is_root):
                continue
            checks.append({
                "building": bld, "level": lvl, "code": code,
                "own": None if own is None or pd.isna(own) else float(own),
                "obtained": sum(v for _, v, _ in kids),
                "labels": [c for k in cfg.children(code) for c in _present(row, k, cfg)],
                "missing_opt": {k for k, _, p in kids if not p and cfg.categories[k].get("optional")},
            })
    out = [_judge(c, cfg) for c in checks]
    for scope in (["building"], []):
        groups: dict[tuple, list[dict]] = {}
        for c in checks:
            if c["own"] is None:
                continue
            groups.setdefault((c["building"] if scope else ALL, c["code"]), []).append(c)
        for (bld, code), cs in groups.items():
            out.append(_judge({
                "building": bld, "level": ALL, "code": code,
                "own": sum(c["own"] for c in cs),
                "obtained": sum(c["obtained"] for c in cs),
                "labels": list(dict.fromkeys(lab for c in cs for lab in c["labels"])),
                "missing_opt": set.intersection(*(c["missing_opt"] for c in cs)),
            }, cfg))
    return [r for r in out if r]


def _judge(c: dict, cfg: Config) -> dict | None:
    bld, lvl, code, own, obtained = c["building"], c["level"], c["code"], c["own"], c["obtained"]
    spec = cfg.categories[code]
    rule = spec.get("rule") or f"Σ{code}"
    labels = "+".join(c["labels"]) or "aucune sous-catégorie"
    if own is None:
        if spec.get("parent") is None and _exceeds(-obtained, 0, cfg):
            return _row(bld, lvl, "R4", code, 0.0, obtained, "ERREUR", f"{labels} sans {code} au même niveau")
        return None
    diff = own - obtained
    if not _exceeds(diff, own, cfg):
        return _row(bld, lvl, rule, code, own, obtained, "OK", f"{code} = {labels}")
    if diff < 0:
        return _row(bld, lvl, "R4", code, own, obtained, "ERREUR", f"{labels} dépasse {code} de {_m2(-diff)} m²")
    missing = sorted(c["missing_opt"])
    max_rel = max((cfg.categories[k].get("implicit_max_rel", 0) for k in missing), default=0)
    if missing and own and diff / own <= max_rel:
        return _row(bld, lvl, rule, code, own, obtained, "INFO",
                    f"{'+'.join(missing)} implicite : {_m2(diff)} m² ({_pct1(100 * diff / own)} %)")
    return _row(bld, lvl, rule, code, own, obtained, "ERREUR",
                f"{code} non sous-classifiée : {_m2(diff)} m² hors {labels}")


# --------------------------------------------------------------------------- niveaux (R5, A1, A2)

def _matches(name: str, patterns: list[str]) -> bool:
    return any(re.search(p, str(name)) for p in patterns)


def level_rank(name: str, cfg: Config) -> float | None:
    for o in cfg.order:
        m = re.search(o["pattern"], str(name))
        if m:
            n = int(m.group(1)) if m.groups() else 0
            return o.get("factor", 1) * n + o.get("offset", 0)
    return None


def _ranks(surf: pd.DataFrame, totals: pd.DataFrame, cfg: Config) -> dict[tuple, float | None]:
    elev = surf.dropna(subset=["elevation"]).groupby(["building", "level"])["elevation"].first() \
        if "elevation" in surf else pd.Series(dtype=float)
    return {k: (float(elev[k]) if k in elev.index else level_rank(k[1], cfg)) for k in totals.index}


def level_checks(totals: pd.DataFrame, surf: pd.DataFrame, cfg: Config) -> list[dict]:
    out = []
    ranks = _ranks(surf, totals, cfg)
    top_sp: dict[str, float] = {}
    for (bld, lvl), row in totals.iterrows():
        sp, _ = _effective(row, SP, cfg)
        r = ranks[(bld, lvl)]
        if sp > cfg.abs_m2 and r is not None:
            top_sp[bld] = max(top_sp.get(bld, -math.inf), r)

    for (bld, lvl), row in totals.iterrows():
        sp, _ = _effective(row, SP, cfg)
        su, _ = _effective(row, SU, cfg)
        sep, _ = _effective(row, SEP, cfg)

        # R5 — niveau avec plancher mais sans surface utile (SIA 416 §2.1.1).
        if sp > cfg.abs_m2 and su <= cfg.abs_m2 and not _matches(lvl, cfg.technical):
            out.append(_row(bld, lvl, "R5", SU, sp, su, "ALERTE",
                            f"SP {_m2(sp)} m² sans surface utile (SUP+SUS = {_m2(su)})"))

        if sep <= cfg.abs_m2:
            continue
        # A1 — SEP au niveau du terrain : candidate surface des abords SA (SIA 416 §3, renvoi §1.2).
        if _matches(lvl, cfg.ground):
            out.append(_row(bld, lvl, "A1", SEP, sep, 0.0, "ALERTE",
                            f"SEP {_m2(sep)} m² au niveau du terrain : candidate surface des abords SA"))
        # A2 — SEP sans plancher adjacent : candidate toiture non accessible, hors SEP (SIA 416 §3).
        r = ranks[(bld, lvl)]
        why = []
        if sp <= cfg.abs_m2:
            why.append("niveau sans SP")
        if r is not None and bld in top_sp and r > top_sp[bld]:
            why.append("au-dessus du dernier niveau avec SP")
        if why:
            out.append(_row(bld, lvl, "A2", SEP, sep, 0.0, "ALERTE",
                            f"SEP {_m2(sep)} m² ({', '.join(why)}) : candidate toiture non accessible"))
    return out


# --------------------------------------------------------------------------- USPI

def uspi_checks(surf: pd.DataFrame, cfg: Config) -> list[dict]:
    """Ordre de la chaîne USPI par lot (USPI 2014 p. 4) ; aucune pondération recalculée."""
    s = surf[(~surf["ignored"]) & surf["lot"].notna() & (surf["kind"] == "leaf")]
    s = s[s["code"].isin([SNH, SH, SBH, SVN, SVB])]
    if s.empty:
        return []
    out = []
    lots = s.groupby(["building", "level", "lot", "code"])["area"].sum().unstack("code")
    pairs = [("U1", SH, SNH), ("U2", SBH, SH), ("U3", SVB, SVN)]  # (règle, grand, petit)
    for (bld, lvl, lot), row in lots.iterrows():
        for rule, big, small in pairs:
            if pd.isna(row.get(big)) or pd.isna(row.get(small)):
                continue
            b, sm = float(row[big]), float(row[small])
            bad = sm - b > 0 and _exceeds(sm - b, b, cfg)
            out.append(_row(bld, lvl, rule, big, b, sm, "ALERTE" if bad else "OK",
                            f"{big} < {small}" if bad else f"{big} ≥ {small}", lot=lot))
        # U4 — SVB − SVN = MEM = SBH − SH (USPI p. 4, renvoi 6).
        if all(not pd.isna(row.get(c)) for c in (SVB, SVN, SBH, SH)):
            mem = float(row[SBH] - row[SH])
            got = float(row[SVB] - row[SVN])
            bad = _exceeds(mem - got, mem, cfg)
            out.append(_row(bld, lvl, "U4", "MEM", mem, got, "ALERTE" if bad else "OK",
                            f"SVB−SVN ({_m2(got)}) ≠ SBH−SH ({_m2(mem)})" if bad else "SVB−SVN = SBH−SH", lot=lot))
    return out


# --------------------------------------------------------------------------- codes inconnus (A3)

def unknown_checks(unknown: pd.DataFrame) -> list[dict]:
    out = []
    if unknown.empty:
        return out
    for code, g in unknown.groupby(unknown["category"].replace("", "(vide)")):
        out.append(_row(ALL, ALL, "A3", code, 0.0, float(g["area"].sum()), "ALERTE",
                        f"code inconnu de la config : {len(g)} surfaces exclues des sommes"))
    return out


# --------------------------------------------------------------------------- point d'entrée

def run(df: pd.DataFrame, cfg: Config) -> Result:
    surf, unknown = classify(df, cfg)
    totals = level_totals(surf)
    rows = sum_checks(totals, cfg)
    rows += level_checks(totals, surf, cfg)
    rows += uspi_checks(surf, cfg)
    rows += unknown_checks(unknown)
    res = pd.DataFrame(rows, columns=RESIDUAL_COLUMNS)
    return Result(residuals=res, surfaces=surf, unknown=unknown, totals=totals)
