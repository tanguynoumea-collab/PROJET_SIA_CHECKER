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
                    "diff_m2", "diff_pct", "verdict", "message", "hint"]

# Titre court d'un point, affiché en tête dans la visionneuse et les rapports.
RULE_TITLES = {
    "R0": "Terrain non sous-classifié",
    "R1": "Plancher non entièrement classé",
    "R2": "Surface utile incohérente",
    "R3": "Surface externe non classée",
    "R4": "Sous-catégories en excès ou sans parent",
    "R5": "Niveau sans surface utile",
    "A1": "Surface externe au niveau du terrain",
    "A2": "Surface externe sans plancher (toiture ?)",
    "A3": "Code de surface inconnu",
    "U1": "Lot USPI : SH < SNH",
    "U2": "Lot USPI : SBH < SH",
    "U3": "Lot USPI : SVB < SVN",
    "U4": "Lot USPI : SVB − SVN ≠ MEM",
}


def title_of(rule: str, verdict: str) -> str:
    if rule == "R1" and verdict == "INFO":
        return "Surface de construction implicite"
    return RULE_TITLES.get(rule, rule)
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
    ratios: pd.DataFrame | None = None   # ratios informatifs (ratios.py), par projet et bâtiment

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


def _row(building, level, rule, category, expected, obtained, verdict, message, lot=None, hint="") -> dict:
    """message = constat chiffré ; hint = ce qu'il faut vérifier (vide pour les contrôles OK)."""
    diff = expected - obtained
    return {"building": building, "level": level, "lot": lot, "rule": rule, "category": category,
            "expected": expected, "obtained": obtained, "diff_m2": diff, "diff_pct": _pct(diff, expected),
            "verdict": verdict, "message": message, "hint": hint}


def _breakdown(parts: dict[str, float]) -> str:
    """« SUP 457,41 + SUS 44,23 + SD 128,20 » : le détail que l'utilisateur va chercher dans Treegram."""
    return " + ".join(f"{k} {_m2(v)}" for k, v in parts.items()) or "aucune sous-catégorie"


# Ce qu'il faut vérifier, par (règle, catégorie). Les références renvoient à la SIA 416 (2003).
HINTS = {
    ("R1", "SP"): "Au-delà de la seule surface de construction (≈ 15 % aux étages courants), des espaces du niveau "
                  "ne sont pas classés : locaux sans type, codes maison hors de la chaîne SIA, pièces oubliées. "
                  "Comparer au même niveau des bâtiments voisins.",
    ("R1", "SN"): "La SN déclarée ne correspond pas à SU + SD + SI (SIA 416 §2.1) : vérifier le classement des pièces.",
    ("R2", "SU"): "La SU déclarée ne correspond pas à la somme de ses sous-catégories (SIA 416 §2.1.1, et règles "
                  "personnalisées éventuelles) : vérifier le classement des pièces.",
    ("R3", "SEP"): "Balcons ou terrasses non créés en SEU/SED, ou SEP qui ne devrait pas exister : surface en contact "
                   "avec le terrain (→ abords SA, SIA 416 §1.2) ou toiture non accessible (→ hors SEP, §3).",
    ("R3", "SEN"): "La SEN déclarée ne correspond pas à SEU + SED + SEI (SIA 416 §3.1).",
}
IMPLICIT_HINT = ("En général rien à faire : la surface de construction (murs, cloisons, piliers) n'est pas fournie par "
                 "Treegram et apparaît ici. Un écart nettement différent des niveaux comparables signale une pièce manquante.")


def _label(code: str, cfg: Config) -> str:
    return cfg.labels.get(code, {}).get("name", code)


def _custom_note(codes, cfg: Config) -> str:
    """« Règle personnalisée P1 (SU = SUP + SUS + SUT) appliquée. » quand un écart à la norme intervient."""
    ids = []
    for r in cfg.custom_rules:
        if (r.parent in codes or any(a in codes for a in r.adds)) and r.id not in ids:
            ids.append(r.id)
    rules = [r for r in cfg.custom_rules if r.id in ids]
    return "".join(f" Règle personnalisée {r.id} ({r.title}) appliquée." for r in rules)


def _judge(c: dict, cfg: Config) -> dict | None:
    """Verdict d'une sommation, avec mention des règles personnalisées qui y interviennent."""
    row = _judge_sum(c, cfg)
    if row is not None:
        row["message"] += _custom_note(set(c["parts"]) | {c["code"]}, cfg)
    return row


# --------------------------------------------------------------------------- sommations (R1–R4)

def _effective(row: pd.Series, code: str, cfg: Config) -> tuple[float, bool]:
    """Valeur d'une catégorie : sa propre aire si présente, sinon la somme de ses enfants."""
    v = row.get(code)
    if v is not None and not pd.isna(v):
        return float(v), True
    kids = [_effective(row, k, cfg) for k in cfg.children(code)]
    return sum(v for v, _ in kids), any(p for _, p in kids)


def _present(row: pd.Series, code: str, cfg: Config) -> dict[str, float]:
    """Codes réellement fournis qui composent la valeur de `code`, avec leur aire (pour les messages)."""
    v = row.get(code)
    if v is not None and not pd.isna(v):
        return {code: float(v)}
    return {c: a for k in cfg.children(code) for c, a in _present(row, k, cfg).items()}


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
                "parts": {c: a for k in cfg.children(code) for c, a in _present(row, k, cfg).items()},
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
            parts: dict[str, float] = {}
            for c in cs:
                for k, v in c["parts"].items():
                    parts[k] = parts.get(k, 0.0) + v
            out.append(_judge({
                "building": bld, "level": ALL, "code": code,
                "own": sum(c["own"] for c in cs),
                "obtained": sum(c["obtained"] for c in cs),
                "parts": parts,
                "missing_opt": set.intersection(*(c["missing_opt"] for c in cs)),
            }, cfg))
    return [r for r in out if r]


def _judge_sum(c: dict, cfg: Config) -> dict | None:
    bld, lvl, code, own, obtained = c["building"], c["level"], c["code"], c["own"], c["obtained"]
    spec = cfg.categories[code]
    rule = spec.get("rule") or f"Σ{code}"
    parts = _breakdown(c["parts"])
    if own is None:
        if spec.get("parent") is None and not spec.get("absent_ok") and _exceeds(-obtained, 0, cfg):
            return _row(bld, lvl, "R4", code, 0.0, obtained, "ERREUR",
                        f"{_m2(obtained)} m² classés ({parts}) sans aucune {code} au même niveau.",
                        hint=f"Créer la {code} du niveau dans Treegram, ou vérifier que ces surfaces ne sont pas "
                             f"rattachées au mauvais niveau.")
        return None
    diff = own - obtained
    if not _exceeds(diff, own, cfg):
        return _row(bld, lvl, rule, code, own, obtained, "OK", f"{code} {_m2(own)} = {parts}.")
    if diff < 0:
        return _row(bld, lvl, "R4", code, own, obtained, "ERREUR",
                    f"Les sous-catégories ({parts} = {_m2(obtained)} m²) dépassent la {code} ({_m2(own)} m²) "
                    f"de {_m2(-diff)} m².",
                    hint=f"Surface comptée deux fois (pièce classée dans deux catégories, ou rattachée à deux niveaux) "
                         f"ou {code} incomplète : comparer le contour de la {code} aux pièces du niveau.")
    missing = sorted(c["missing_opt"])
    max_rel = max((cfg.categories[k].get("implicit_max_rel", 0) for k in missing), default=0)
    pct = _pct1(100 * diff / own) if own else "–"
    if missing and own and diff / own <= max_rel:
        return _row(bld, lvl, rule, code, own, obtained, "INFO",
                    f"{_m2(diff)} m² de {code} non classés ({pct} %), compatibles avec la surface de construction "
                    f"({'+'.join(missing)}, non fournie). {code} {_m2(own)} ; classés {parts} = {_m2(obtained)}.",
                    hint=IMPLICIT_HINT)
    return _row(bld, lvl, rule, code, own, obtained, "ERREUR",
                f"{_m2(diff)} m² de {code} ({pct} %) ne sont rattachés à aucune sous-catégorie. "
                f"{_label(code, cfg)} {_m2(own)} m² ; classés {parts} = {_m2(obtained)} m².",
                hint=HINTS.get((rule, code), f"Vérifier le classement des surfaces de la {code}."))


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
                            f"Plancher de {_m2(sp)} m² sans aucune surface utile "
                            f"({' + '.join(cfg.children(SU))} = {_m2(su)} m²).{_custom_note({SU}, cfg)}",
                            hint="Niveau technique ? Le déclarer dans config.yaml (levels.technical). Sinon les pièces "
                                 "ne sont pas classées en surface utile : vérifier les locaux sans type et les codes "
                                 "maison hors de la chaîne SIA."))

        if sep <= cfg.abs_m2:
            continue
        # A1 — SEP au niveau du terrain : candidate surface des abords SA (SIA 416 §3, renvoi §1.2).
        if _matches(lvl, cfg.ground):
            out.append(_row(bld, lvl, "A1", SEP, sep, 0.0, "ALERTE",
                            f"{_m2(sep)} m² de SEP au niveau du terrain.",
                            hint="Une surface extérieure en contact direct avec le terrain (cours, dalles sur sous-sol, "
                                 "accès) relève des abords SA (SIA 416 §1.2) et sort de la SEP (§3). Ne garder en SEP "
                                 "que les terrasses privatives séparées des abords."))
        # A2 — SEP sans plancher adjacent : candidate toiture non accessible, hors SEP (SIA 416 §3).
        r = ranks[(bld, lvl)]
        why = []
        if sp <= cfg.abs_m2:
            why.append("niveau sans SP")
        if r is not None and bld in top_sp and r > top_sp[bld]:
            why.append("au-dessus du dernier niveau avec SP")
        if why:
            out.append(_row(bld, lvl, "A2", SEP, sep, 0.0, "ALERTE",
                            f"{_m2(sep)} m² de SEP ({', '.join(why)}).",
                            hint="Toiture non accessible : ni SP ni SEP (SIA 416 §3), à exclure. Si c'est une "
                                 "toiture-jardin ou une terrasse accessible, la classer en SEU."))
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
    # (règle, grand, petit, relation USPI qui impose l'ordre)
    pairs = [("U1", SH, SNH, "SH = SNH + SCI"), ("U2", SBH, SH, "SBH = SH + MEM"), ("U3", SVB, SVN, "SVB = SBH + SE ≥ SVN = SH + SE")]
    for (bld, lvl, lot), row in lots.iterrows():
        for rule, big, small, why in pairs:
            if pd.isna(row.get(big)) or pd.isna(row.get(small)):
                continue
            b, sm = float(row[big]), float(row[small])
            bad = sm - b > 0 and _exceeds(sm - b, b, cfg)
            msg = (f"{big} {_m2(b)} m² inférieure à {small} {_m2(sm)} m² pour ce lot." if bad
                   else f"{big} {_m2(b)} ≥ {small} {_m2(sm)}.")
            out.append(_row(bld, lvl, rule, big, b, sm, "ALERTE" if bad else "OK", msg, lot=lot,
                            hint=f"Impossible par construction ({why}, USPI 2014) : une des deux surfaces du lot "
                                 f"est mal calculée ou rattachée au mauvais lot." if bad else ""))
        # U4 — SVB − SVN = MEM = SBH − SH (USPI p. 4, renvoi 6).
        if all(not pd.isna(row.get(c)) for c in (SVB, SVN, SBH, SH)):
            mem = float(row[SBH] - row[SH])
            got = float(row[SVB] - row[SVN])
            bad = _exceeds(mem - got, mem, cfg)
            out.append(_row(bld, lvl, "U4", "MEM", mem, got, "ALERTE" if bad else "OK",
                            f"SVB − SVN = {_m2(got)} m² alors que SBH − SH = {_m2(mem)} m²." if bad
                            else "SVB − SVN = SBH − SH.", lot=lot,
                            hint="Les deux écarts doivent valoir MEM (murs extérieurs et mitoyens, USPI 2014) : "
                                 "surfaces externes pondérées différemment entre SVB et SVN ?" if bad else ""))
    return out


# --------------------------------------------------------------------------- codes inconnus (A3)

def unknown_checks(unknown: pd.DataFrame) -> list[dict]:
    out = []
    if unknown.empty:
        return out
    for code, g in unknown.groupby(unknown["category"].replace("", "(vide)")):
        out.append(_row(ALL, ALL, "A3", code, 0.0, float(g["area"].sum()), "ALERTE",
                        f"Code « {code} » inconnu : {len(g)} surfaces ({_m2(float(g['area'].sum()))} m²) exclues des sommes.",
                        hint="Ajouter le code dans config.yaml (categories et labels), ou demander sa signification "
                             "à Treegram."))
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
    from . import ratios   # import local : ratios s'appuie sur ce module
    return Result(residuals=res, surfaces=surf, unknown=unknown, totals=totals,
                  ratios=ratios.compute(totals, surf, cfg))
