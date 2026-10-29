"""Exports au gabarit Excel Treegram, régénérés depuis le `.tgm`.

Treegram exporte deux classeurs, une ligne par objet, clé « ID TGM » :
- <projet>-SurfacesNettes.xlsx : surfaces élémentaires (une par local) ;
- <projet>-SurfacesBrutes.xlsx : SP et SEP de chaque niveau.

Les colonnes, leur ordre et leurs valeurs fixes reprennent ceux de Treegram (L'Orée, export du
22.10.2026). Les nettes comprennent toutes les feuilles de l'arbre SIA 416 et les codes ajoutés par
une règle personnalisée (SUT sous P1) : l'export Treegram omet SED et SUT, celui-ci les garde.
Les codes ignorés (SPT…) et USPI n'y figurent pas, comme chez Treegram. Les abords SA créés par une
découpe (corrections.py) sont exportés comme les autres surfaces : en brutes s'ils viennent d'un total de
niveau, en nettes s'ils viennent d'une surface élémentaire.

Excel de correction (`write_corrections`) : les mêmes deux feuilles, une ligne par surface du `.tgm` et par
surface créée, avec la catégorie et l'aire corrigées, la correction appliquée et son explication.
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


def _roots(cfg: Config) -> list[str]:
    """Racines SIA décomposées (SP, SEP, ST), dans l'ordre de la config."""
    return [c for c, d in cfg.categories.items()
            if d.get("family") == "sia" and d.get("parent") is None and d.get("children")]


def gross_codes(cfg: Config) -> list[str]:
    """Codes exportés en brutes, une ligne par niveau : les racines, puis les abords SA (découpes d'un total)."""
    roots = _roots(cfg)
    return roots + [c for c in ("SA",) if c in cfg.categories and c not in roots]


CONSTRUCTION = {"SC", "SCP", "SCN", "SEC", "SECP", "SECN"}


def net_codes(cfg: Config) -> set[str]:
    """Codes SIA 416 sous les racines (SUP, SD, SEU…), plus les codes rattachés par une règle personnalisée.

    Seules les surfaces élémentaires sont exportées : un code intermédiaire (SU, SC…) n'y figure que si la
    source le porte sur une surface élémentaire.
    """
    sia = {c for c, d in cfg.categories.items() if d.get("family") == "sia" and not d.get("alias_of")}
    # construction modélisée par le moteur IFC (V4.1) : ni Treegram ni les MDP n'en ont, elle reste au bilan
    return (sia - set(_roots(cfg)) - CONSTRUCTION) | {c for r in cfg.custom_rules for c in r.adds}


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
    s = rules.net_of_roofs(result.surfaces)   # SEP sans les toitures SPT que Treegram y compte
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


# --------------------------------------------------------------------------- Excel de correction

# Correction de règle, sans entrée au journal : la SEP Treegram perd les toitures SPT (rules.net_of_roofs).
ROOFS = "toitures SPT"
CORRECTION_COLUMNS = ["Catégorie corrigée", "Aire corrigée", "Exclue", "Affectation", "Correction", "Explication"]


def corrections_frames(applied, journal: dict, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(nettes, brutes, journal) : gabarit Treegram tel que lu dans le `.tgm`, plus l'état corrigé de chaque surface."""
    entries = {c.get("id"): c for c in journal.get("corrections", [])}
    s = applied.surfaces.copy()
    canon = lambda c: cfg.canonical(c) if isinstance(c, str) and c in cfg.categories else None  # noqa: E731
    # Aire corrigée : SEP sans les toitures SPT que Treegram y compte (rules.net_of_roofs), comme le bilan.
    net_area = rules.net_of_roofs(s.assign(code=s.category.map(canon)))["area"]
    roofed = (s.kind == "node") & ~s.excluded & ((net_area - s.area).abs() > 1e-9)
    s["area"] = net_area
    s.loc[roofed, "corrections"] = [f"{c};{ROOFS}" if c else ROOFS for c in s.loc[roofed, "corrections"]]
    s["code"] = s.original_category.map(canon).fillna(s.category.map(canon))
    s = s[s.code.notna()]

    def describe(ids: str) -> tuple[str, str]:
        parts, why = [], []
        for cid in [i for i in str(ids or "").split(";") if i]:
            if cid == ROOFS:
                parts.append(ROOFS)
                why.append("Toitures classées SPT retirées de la SEP du niveau, qui les comptait (SIA 416 §3 : une "
                           "toiture non accessible n'est ni SP ni SEP).")
                continue
            c = entries.get(cid, {})
            to = f" → {c['vers']}" if c.get("vers") else f" : {c['affectation']}" if c.get("affectation") else ""
            parts.append(f"{cid} ({c.get('op', '?')}{to})")
            if c.get("explication"):
                why.append(c["explication"])
        return " ; ".join(parts), " ".join(why)

    def frame(rows: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
        created = rows.original_category.isna()
        desc = [describe(i) for i in rows.corrections]
        extra = pd.DataFrame({
            "Catégorie corrigée": rows.category.where(~rows.excluded, ""),
            "Aire corrigée": rows.area.where(~rows.excluded, 0.0).round(3),
            "Exclue": rows.excluded.map({True: "oui", False: ""}),
            "Affectation": rows.get("affectation"),
            "Correction": [d[0] for d in desc],
            "Explication": [d[1] for d in desc],
        }, index=rows.index)
        base = base.copy()
        base.index = rows.index
        base.loc[created, ["Area", "Catégorie SIA"]] = [None, ""]   # surface créée : rien dans le .tgm
        return pd.concat([base, extra], axis=1).reset_index(drop=True)

    net = s[(s.kind == "leaf") & s.code.isin(net_codes(cfg))]
    net = _sorted(net, sorted(net_codes(cfg)))
    net_base = pd.DataFrame({
        "ID TGM": net.get("tgm_id"), "Object.Name": net["id"], "Object.Type": NETTES_TYPE, "ApartmentByTgm": net["lot"],
        "Area": net["original_area"], "BuildingByTgm": net["building"], "Catégorie SIA": net["original_category"],
        "object.name2": net["id"], "object.type3": NETTES_TYPE, "StoreyByTgm": net["level"], "Type": net["room_type"],
    }, columns=NETTES_COLUMNS)
    codes = gross_codes(cfg)
    gross = _sorted(s[(s.kind == "node") & s.code.isin(codes)], codes)
    gross_base = pd.DataFrame({
        "ID TGM": gross.get("tgm_id"), "Object.Name": gross["original_category"].fillna(gross["category"]),
        "Object.Type": BRUTES_TYPE, "Area": gross["original_area"], "BuildingByTgm": gross["building"],
        "Catégorie SIA": gross["original_category"], "GrossHeight": gross.get("gross_height"),
        "object.name2": gross["original_category"].fillna(gross["category"]), "object.type3": BRUTES_TYPE,
        "Perimeter": gross.get("perimeter"), "StoreyByTgm": gross["level"],
    }, columns=BRUTES_COLUMNS)
    log = applied.log.assign(explication=applied.log.id.map(lambda i: entries.get(i, {}).get("explication", "")))
    return _rounded(frame(net, net_base)), _rounded(frame(gross, gross_base)), log


def write_corrections(applied, journal: dict, cfg: Config, path: str | Path) -> Path:
    """Excel de correction : SurfacesNettes et SurfacesBrutes au gabarit Treegram, colonnes de correction en plus,
    et la feuille Journal (chaque correction, son statut, son application et son explication)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nets, gross, log = corrections_frames(applied, journal, cfg)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        nets.to_excel(xw, sheet_name="SurfacesNettes", index=False)
        gross.to_excel(xw, sheet_name="SurfacesBrutes", index=False)
        log.to_excel(xw, sheet_name="Journal", index=False)
        for ws in xw.book.worksheets:   # en-têtes figés et filtrables, colonnes de correction repérables
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
    return path
