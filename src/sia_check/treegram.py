"""Exports au gabarit Excel Treegram, régénérés depuis le `.tgm`.

Treegram exporte deux classeurs, une ligne par objet, clé « ID TGM » :
- <projet>-SurfacesNettes.xlsx : surfaces élémentaires (une par local) ;
- <projet>-SurfacesBrutes.xlsx : SP et SEP de chaque niveau.

Les colonnes, leur ordre et leurs valeurs fixes reprennent ceux de Treegram (L'Orée, export du
22.10.2026). Les nettes comprennent toutes les feuilles de l'arbre SIA 416 et les codes ajoutés par
une règle personnalisée (SUT sous P1) : l'export Treegram omet SED et SUT, celui-ci les garde.
Les codes ignorés (SPT…) et USPI n'y figurent pas, comme chez Treegram.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import rules
from .config import Config

NETTES_COLUMNS = ["ID TGM", "Object.Name", "Object.Type", "ApartmentByTgm", "Area", "BuildingByTgm",
                  "Catégorie SIA", "object.name2", "object.type3", "StoreyByTgm", "Type"]
BRUTES_COLUMNS = ["ID TGM", "Object.Name", "Object.Type", "Area", "BuildingByTgm", "Catégorie SIA",
                  "GrossHeight", "object.name2", "object.type3", "Perimeter", "StoreyByTgm"]
NETTES_TYPE, BRUTES_TYPE = "SiaSurfaceBySpace", "SiaSurface"
DECIMALS = {"Area": 3, "Perimeter": 3, "GrossHeight": 2}


def gross_codes(cfg: Config) -> list[str]:
    """Racines SIA décomposées (SP, SEP…), dans l'ordre de la config : une ligne par niveau."""
    return [c for c, d in cfg.categories.items()
            if d.get("family") == "sia" and d.get("parent") is None and d.get("children")]


def net_codes(cfg: Config) -> set[str]:
    """Codes SIA 416 sous les racines (SUP, SD, SEU…), plus les codes rattachés par une règle personnalisée.

    Seules les surfaces élémentaires sont exportées : un code intermédiaire (SU, SC…) n'y figure que si la
    source le porte sur une surface élémentaire.
    """
    sia = {c for c, d in cfg.categories.items() if d.get("family") == "sia" and not d.get("alias_of")}
    return (sia - set(gross_codes(cfg))) | {c for r in cfg.custom_rules for c in r.adds}


def _sorted(df: pd.DataFrame, order: list[str]) -> pd.DataFrame:
    rank = {c: i for i, c in enumerate(order)}
    eid = df["element_id"] if "element_id" in df else pd.Series(float("nan"), index=df.index)
    return (df.assign(_r=df["code"].map(rank), _e=pd.to_numeric(eid, errors="coerce"))
              .sort_values(["_r", "building", "_e"], kind="stable").drop(columns=["_r", "_e"]))


def _rounded(out: pd.DataFrame) -> pd.DataFrame:
    for col, n in DECIMALS.items():
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(n)
    return out


def nettes(result: rules.Result, cfg: Config) -> pd.DataFrame:
    s = result.surfaces
    s = s[(s.kind == "leaf") & ~s.ignored & s.code.isin(net_codes(cfg))]
    s = _sorted(s, sorted(net_codes(cfg)))
    out = pd.DataFrame({
        "ID TGM": s.get("tgm_id"), "Object.Name": s["id"], "Object.Type": NETTES_TYPE,
        "ApartmentByTgm": s["lot"], "Area": s["area"], "BuildingByTgm": s["building"],
        "Catégorie SIA": s["category"], "object.name2": s["id"], "object.type3": NETTES_TYPE,
        "StoreyByTgm": s["level"], "Type": s["room_type"],
    }, columns=NETTES_COLUMNS)
    return _rounded(out).reset_index(drop=True)


def brutes(result: rules.Result, cfg: Config) -> pd.DataFrame:
    s = result.surfaces
    codes = gross_codes(cfg)
    s = _sorted(s[(s.kind == "node") & s.code.isin(codes)], codes)
    out = pd.DataFrame({
        "ID TGM": s.get("tgm_id"), "Object.Name": s["category"], "Object.Type": BRUTES_TYPE, "Area": s["area"],
        "BuildingByTgm": s["building"], "Catégorie SIA": s["category"], "GrossHeight": s.get("gross_height"),
        "object.name2": s["category"], "object.type3": BRUTES_TYPE, "Perimeter": s.get("perimeter"),
        "StoreyByTgm": s["level"],
    }, columns=BRUTES_COLUMNS)
    return _rounded(out).reset_index(drop=True)


def write(result: rules.Result, cfg: Config, out_dir: str | Path, stem: str) -> list[Path]:
    """Écrit <stem>-SurfacesNettes.xlsx et <stem>-SurfacesBrutes.xlsx ; renvoie les chemins."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for sheet, df in (("SurfacesNettes", nettes(result, cfg)), ("SurfacesBrutes", brutes(result, cfg))):
        path = out_dir / f"{stem}-{sheet}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            df.to_excel(xw, sheet_name=sheet, index=False)
        paths.append(path)
    return paths
