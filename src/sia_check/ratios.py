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
    CAGES, SUP_CAGES, LOG_CAGES
          cages d'escalier, SUP (+ SUT) et logements des étages de logements desservis (`stairs`), sommés sur la
          portée : SUP / cage et logements / cage sont des moyennes pondérées des étages

Les repères (`ref`) sont indicatifs : un ratio hors repère n'est pas une erreur du contrôle,
c'est une question posée à la revue IA et à l'utilisateur.

**Repères et typologie** (décision du 28.10.2026) : un repère ne vaut que pour un type de bâtiment. Ceux de
config.yaml viennent des projets de logement de la base ; ils valent pour les typologies `typologies` du ratio
(par défaut logement et logement mixte), `refs` en donne d'autres par typologie. Sans typologie (fiche projet,
`--typologie`), aucun repère n'est appliqué : le ratio garde sa valeur, son statut est « typologie ». Pour une
typologie sans repère (parking, activités…), le statut est « info ».
"""

from __future__ import annotations

import math
import re
import unicodedata

import pandas as pd

from .config import Config

RATIO_COLUMNS = ["building", "id", "family", "label", "value", "unit", "ref_min", "ref_max", "status",
                 "num_m2", "den_m2", "note"]
ALL = "*"


STAIR_TOKENS = ("CAGES", "SUP_CAGES", "LOG_CAGES")
STAIR_COLUMNS = ["SUP_ETAGE", "LOGEMENTS", *STAIR_TOKENS]


def is_stair(room_type) -> bool:
    """Sous-type d'une cage d'escalier : « Escalier », « Cage d'escalier », « Cages d'escaliers »…"""
    if not isinstance(room_type, str):
        return False
    k = unicodedata.normalize("NFKD", room_type).encode("ascii", "ignore").decode().lower()
    return re.search(r"escalier", k) is not None


def stairs(surf: pd.DataFrame, totals: pd.DataFrame) -> pd.DataFrame:
    """Cages d'escalier des étages de logements, par (bâtiment, niveau).

    Cage : surface élémentaire SD (dégagement commun) dont le sous-type est un escalier ; l'escalier intérieur d'un
    duplex (SUP) ou un escalier extérieur (SEU) n'en est pas une. Logements de l'étage : lots distincts des surfaces SUP / SUT élémentaires du niveau. Un étage de
    logements a de la SUP (+ SUT, totaux du moteur) et au moins un logement ; les autres (sous-sols techniques…) ne
    sont pas concernés. SUP_ETAGE et LOGEMENTS décrivent tous les étages de logements ; CAGES, SUP_CAGES et
    LOG_CAGES seulement ceux qui ont une cage (sinon pas de division possible).
    """
    out = pd.DataFrame(index=totals.index, columns=STAIR_COLUMNS, dtype=float)
    if totals.empty or not {"room_type", "lot", "kind"} <= set(surf.columns):
        return out
    leaves = surf[surf["kind"] == "leaf"]
    if "ignored" in leaves:
        leaves = leaves[~leaves["ignored"].astype(bool)]
    cages = leaves[leaves["room_type"].map(is_stair) & (leaves["code"] == "SD")].groupby(["building", "level"]).size()
    homes = leaves[leaves["lot"].notna() & leaves["code"].isin(["SUP", "SUT"])]         .groupby(["building", "level"])["lot"].nunique()
    sup = sum(totals[c].fillna(0) for c in ("SUP", "SUT") if c in totals)
    sup = sup if isinstance(sup, pd.Series) else pd.Series(0.0, index=totals.index)
    homes = homes.reindex(totals.index).fillna(0)
    cages = cages.reindex(totals.index).fillna(0)
    housing = (sup > 0) & (homes > 0)
    served = housing & (cages > 0)
    out["SUP_ETAGE"] = sup.where(housing)
    out["LOGEMENTS"] = homes.where(housing)
    out["CAGES"] = cages.where(housing)
    out["SUP_CAGES"] = sup.where(served)
    out["LOG_CAGES"] = homes.where(served)
    out.loc[housing & ~served, "CAGES"] = 0.0
    return out


HOUSING = ("logement", "mixte")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()


def typology_key(label: str | None) -> str | None:
    """Libellé de la liste du MDP (« Logement Mixte (>10% autres affectations) ») -> clé des repères."""
    t = _norm(label or "")
    if not t:
        return None
    for key, rx in (("mixte", r"logement mixte"), ("logement", r"^logement"), ("activites", r"activit"),
                    ("industriel", r"industri"), ("ecole", r"ecole"), ("hotel", r"hotel"), ("sport", r"sport"),
                    ("ems", r"\bems\b"), ("sante", r"sante"), ("commercial", r"centre commercial")):
        if re.search(rx, t):
            return key
    return "autre"


def reference(r: dict, key: str | None) -> list | None:
    """Repère d'un ratio pour une typologie : `refs[clé]`, sinon `ref` si la typologie en relève, sinon aucun."""
    if key is None:
        return None
    if key in (r.get("refs") or {}):
        return r["refs"][key]
    return r.get("ref") if key in (r.get("typologies") or HOUSING) else None


def suggest(surf: pd.DataFrame) -> tuple[str, str] | None:
    """Typologie proposée d'après les surfaces élémentaires (libellé de la liste du MDP, raison), ou None."""
    if surf.empty or "kind" not in surf:
        return None
    leaves = surf[surf["kind"] == "leaf"]
    if "ignored" in leaves:
        leaves = leaves[~leaves["ignored"].astype(bool)]
    m2 = leaves.groupby("code")["area"].sum()
    sup, sus, sut = (float(m2.get(c, 0.0)) for c in ("SUP", "SUS", "SUT"))
    su = sup + sus + sut
    if su <= 0:
        return None
    parking = float(leaves[(leaves["code"] == "SUS") & (leaves.get("room_type") == "Parking")]["area"].sum()) \
        if "room_type" in leaves else 0.0
    lots = leaves[leaves["code"].isin(["SUP", "SUT"]) & leaves["lot"].notna()]["lot"].nunique() if "lot" in leaves else 0
    pct = lambda v: f"{100 * v / su:.0f} %"   # noqa: E731
    if lots and sup / max(sup + sut, 1e-9) >= 0.9:
        return "Logement (100-90% SU)", f"{lots} logements, SUP {pct(sup)} de la SU"
    if lots:
        return "Logement Mixte (>10% autres affectations)", f"{lots} logements, SUT {pct(sut)} de la SU"
    if parking >= 0.5 * su:
        return "Autre", f"parking : {pct(parking)} de la SU"
    if sut >= 0.5 * su:
        return "Activités (Bureaux, Artisanat, Commerce)", f"aucun logement, SUT {pct(sut)} de la SU"
    return "Autre", f"aucun logement (SUP {pct(sup)}, SUS {pct(sus)}, SUT {pct(sut)} de la SU)"


def _status(value: float | None, ref: list | None, key: str | None = "logement") -> str:
    if value is None:
        return "n/a"
    if key is None:
        return "typologie"
    if not ref:
        return "info"
    lo, hi = ref
    return "bas" if value < lo else "haut" if value > hi else "ok"


def _is_uspi(code: str, cfg: Config) -> bool:
    return cfg.categories.get(code, {}).get("family") == "uspi"


def _level_value(code: str, row: pd.Series, cfg: Config) -> tuple[float, bool]:
    """Valeur effective d'un code SIA sur un niveau ; SC absente = SP − SN."""
    from .rules import _effective   # import local : rules importe ce module

    if code in STAIR_TOKENS:   # étages de logements desservis seulement (stairs) : CAGES n'y vaut jamais 0
        v = row.get(code)
        ok = v is not None and not pd.isna(v) and (code != "CAGES" or not pd.isna(row.get("SUP_CAGES")))
        return (float(v), True) if ok else (0.0, False)
    if code == "PLEINE":     # façade pleine = façade brute − vitrages (V3_PLAN §10)
        sfn, srv = row.get("SFN"), row.get("SRV")
        if sfn is None or pd.isna(sfn):
            return 0.0, False
        return float(sfn) - (0.0 if srv is None or pd.isna(srv) else float(srv)), True
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
    # Enveloppe : façades, vitrages et toitures, ignorés par les règles de sommation, rejoignent les totaux des seuls
    # ratios (coefficient de forme : SP hors-sol / façades + toitures)
    env = surf[surf["code"].isin(["SFN", "SRV", "SPT"]) & (surf["kind"] == "node")]
    if not env.empty:
        totals = totals.join(env.groupby(["building", "level", "code"])["area"].sum().unstack("code"), how="left")
    totals = totals.join(stairs(surf, totals), how="left")
    above = [(b, l) for b, l in totals.index if (level_rank(l, cfg) is None or level_rank(l, cfg) >= 0)]
    key = typology_key(cfg.typologie)
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
            ref = reference(r, key)
            status = _status(value, ref, key)
            if not (r.get("ref") or r.get("refs")) and status == "typologie":
                status = "info"          # ratio sans repère, quelle que soit la typologie (SNH / lot…)
            elif status == "info" and (r.get("ref") or r.get("refs")):
                status = "sans repère"   # repère établi pour d'autres typologies (logement)
            rows.append({
                "building": scope, "id": r["id"], "family": r.get("family", ""), "label": r.get("label", r["id"]),
                "value": value, "unit": r.get("unit", "ratio"),
                "ref_min": ref[0] if ref else None, "ref_max": ref[1] if ref else None,
                "status": status, "num_m2": num, "den_m2": den, "note": r.get("note", ""),
            })
    return pd.DataFrame(rows, columns=RATIO_COLUMNS)
