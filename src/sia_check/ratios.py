"""Ratios informatifs du développement immobilier (SIA 416, USPI 2014), par projet et par bâtiment.

Définitions dans config.yaml > ratios. Valeurs calculées sur les totaux de niveau du moteur
(rules.level_totals : le détail fait foi), avec la valeur « effective » de chaque code (propre
aire, sinon somme de ses enfants — règles personnalisées comprises, ex. P1 : SU = SUP + SUS + SUT).

Codes USPI (famille « uspi ») : uniquement la somme des lots (surfaces élémentaires). Les totaux de
niveau USPI de Treegram ne s'additionnent pas comme les lots (sur L'Orée, le total « SNH » des
sous-sols contient de la SUS) et fausseraient SH/SNH ou SNH/SP.

Jetons spéciaux :
    SC    surface de construction ; Treegram ne la fournit pas, elle vaut alors SP − SN
    LOTS  nombre de lots USPI distincts (surfaces SNH élémentaires portant un lot)

Les repères (`ref`) sont indicatifs : un ratio hors repère n'est pas une erreur du contrôle,
c'est une question posée à la revue IA et à l'utilisateur.
"""

from __future__ import annotations

import math

import pandas as pd

from .config import Config

RATIO_COLUMNS = ["building", "id", "family", "label", "value", "unit", "ref_min", "ref_max", "status",
                 "num_m2", "den_m2", "note"]
ALL = "*"


def _status(value: float | None, ref: list | None) -> str:
    if value is None or not ref:
        return "info" if value is not None else "n/a"
    lo, hi = ref
    return "bas" if value < lo else "haut" if value > hi else "ok"


def _is_uspi(code: str, cfg: Config) -> bool:
    return cfg.categories.get(code, {}).get("family") == "uspi"


def _level_value(code: str, row: pd.Series, cfg: Config) -> tuple[float, bool]:
    """Valeur effective d'un code SIA sur un niveau ; SC absente = SP − SN."""
    from .rules import _effective   # import local : rules importe ce module

    if code == "SC" and not _effective(row, "SC", cfg)[1]:
        sp, has_sp = _effective(row, "SP", cfg)
        sn, has_sn = _effective(row, "SN", cfg)
        return (sp - sn, True) if has_sp and has_sn else (0.0, False)
    return _effective(row, code, cfg)


def _operand(codes: list[str], levels: pd.DataFrame, lot_row: pd.Series, lots: int, cfg: Config) -> float | None:
    """Somme des codes sur la portée. Codes SIA : valeur effective niveau par niveau, puis somme
    (sommer d'abord laisserait un nœud SU d'un niveau masquer les feuilles d'un autre)."""
    total, present = 0.0, False
    for code in codes:
        if _is_uspi(code, cfg):
            v = lot_row.get(code)
            if v is not None and not pd.isna(v):
                total += float(v)
                present = True
        elif code == "LOTS":
            total += lots
            present = present or lots > 0
        else:
            for _, row in levels.iterrows():
                v, p = _level_value(code, row, cfg)
                total += v
                present = present or p
    return total if present else None


def compute(totals: pd.DataFrame, surf: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Une ligne par (portée, ratio) : portée = « * » (projet) puis chaque bâtiment."""
    from .rules import level_rank, level_totals   # import local : rules importe ce module

    rows = []
    if totals.empty or not cfg.ratios:
        return pd.DataFrame(rows, columns=RATIO_COLUMNS)
    lot_surf = surf[(surf["kind"] == "leaf") & surf["lot"].notna()] if "lot" in surf else surf.iloc[0:0]
    lot_totals = level_totals(lot_surf) if not lot_surf.empty else pd.DataFrame(index=totals.index)
    lots_src = surf[(surf["code"] == "SNH") & (surf["kind"] == "leaf") & surf["lot"].notna()] \
        if "lot" in surf else surf.iloc[0:0]
    above = [(b, l) for b, l in totals.index if (level_rank(l, cfg) is None or level_rank(l, cfg) >= 0)]
    scopes = [ALL] + sorted(totals.index.get_level_values("building").unique())

    for scope in scopes:
        for r in cfg.ratios:
            idx = list(totals.index) if r.get("levels", "all") == "all" else above
            if scope != ALL:
                idx = [k for k in idx if k[0] == scope]
            if not idx:
                continue
            levels = totals.loc[idx]
            lot_row = lot_totals.reindex(idx).sum(min_count=1)
            lots_scope = lots_src if scope == ALL else lots_src[lots_src["building"] == scope]
            lots = int(lots_scope["lot"].nunique())
            num = _operand(r.get("num", []), levels, lot_row, lots, cfg)
            den = _operand(r.get("den", []), levels, lot_row, lots, cfg)
            value = num / den if num is not None and den else None
            if value is not None and not math.isfinite(value):
                value = None
            ref = r.get("ref")
            rows.append({
                "building": scope, "id": r["id"], "family": r.get("family", ""), "label": r.get("label", r["id"]),
                "value": value, "unit": r.get("unit", "ratio"),
                "ref_min": ref[0] if ref else None, "ref_max": ref[1] if ref else None,
                "status": _status(value, ref), "num_m2": num, "den_m2": den, "note": r.get("note", ""),
            })
    return pd.DataFrame(rows, columns=RATIO_COLUMNS)
