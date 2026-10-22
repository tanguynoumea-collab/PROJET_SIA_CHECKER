"""Tableau MDP HRS (« MDP-<id>-<projet>.xlsx ») rempli depuis le `.tgm`.

Le gabarit est un MDP existant ou vierge : ses tableaux de données sont vidés puis remplis, le reste
(listes déroulantes, feuille « Listes formulaire », documents) est conservé (xlsx_tables).

| Feuille                    | Tableau            | Source                                                   |
|----------------------------|--------------------|----------------------------------------------------------|
| SurfacesBrutesVolumeSIA416 | SurfacesSIA4168    | SP / SEP par niveau (treegram.brutes), m³ = m² × h brute |
| SurfacesNettesSIA416       | SurfacesSIA41610   | surfaces élémentaires SIA (treegram.nettes)              |
| SurfacesUSPI               | SurfacesSIA41611   | SNH, SH, SBH, SE = SVN − SH, SVN, SVB par lot            |
| ListeLogements             | Logements          | lots USPI : bâtiment, niveau, nombre de chambres         |
| SurfacesEnveloppe          | SurfacesSIA416     | façade (SFN) et toiture (SPT) par niveau                 |
| InfosBatiment              | Tableau3           | étages hors-sol / sous-sol, dimensions (SP)              |
| InfosProjet                | InfosProjet        | comptages : bâtiments, étages, logements, chambres       |

Ce que le `.tgm` ne donne pas reste vide : affectation, typologies, nombre de pièces, champs
administratifs. Le tableau croisé de la feuille SurfacesEnveloppe n'est pas recalculé.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd

from . import reader, rules, treegram
from .config import Config
from .xlsx_tables import Formula, TemplateError, Workbook  # noqa: F401 (TemplateError réexportée)

DEFAULT_TEMPLATE = Path(__file__).parent / "templates" / "MDP-gabarit.xlsx"
PROJECT_ID = "InfosProjet!$C$2"
# Libellés de la liste « Categorie USPI » du gabarit (feuille Listes formulaire, colonne BD), fautes comprises.
USPI_LABELS = {"SNH": "Surface nette habitabe", "SH": "Surface habitable", "SBH": "Surface brute habitable",
               "SE": "Surface externe", "SVN": "Surface de Vente Nette", "SVB": "Surface de VenteBrute"}
FACADE, ROOF = "Facade global", "Surface de toiture"
ABOVE, BELOW, OTHER = "Hors-sol", "Sous-sol", "Divers"


def _blank(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def _decoupage(wb: Workbook) -> dict[str, str]:
    """Niveau -> découpage, d'après la table HsSs du gabarit."""
    if "HsSs" not in wb.tables:
        return {}
    return {r["Niveau"]: r["Decoupage"] for r in wb.table_rows("HsSs") if r["Niveau"] and r["Decoupage"]}


def _level_kind(level: str, table: dict[str, str]) -> str:
    if level in table:
        return table[level]
    if level[:1] == "S" and level[1:].isdigit():
        return BELOW
    if level[:1] == "N" and level[1:].isdigit():
        return ABOVE
    return OTHER


def _ordered(df: pd.DataFrame, cfg: Config, *extra: str) -> pd.DataFrame:
    return (df.assign(_rank=df.level.map(lambda lv: rules.level_rank(lv, cfg)))
              .sort_values(["building", "_rank", *extra], kind="stable").drop(columns="_rank"))


def _nodes(result: rules.Result, code: str) -> pd.DataFrame:
    s = result.surfaces
    return s[(s.kind == "node") & (s.code == code)]


def _project_levels(result: rules.Result, kinds: dict[str, str]) -> pd.DataFrame:
    """(bâtiment, niveau, découpage) des niveaux qui ont une SP non nulle."""
    sp = _nodes(result, "SP")
    sp = sp[sp.area.fillna(0) > 0]
    return sp.assign(kind=sp.level.map(lambda lv: _level_kind(lv, kinds)))[["building", "level", "kind", "area", "dx", "dy"]]


def _lots(result: rules.Result) -> pd.DataFrame:
    """Une ligne par lot : bâtiment, niveau, chambres et aires USPI (SH = SHA)."""
    s = result.surfaces
    s = s[(s.kind == "leaf") & s.lot.notna() & s.code.isin(["SNH", "SH", "SBH", "SVN", "SVB"])]
    if s.empty:
        return pd.DataFrame(columns=["building", "level", "lot", "bedrooms", *USPI_LABELS])
    areas = s.pivot_table(index=["building", "level", "lot"], columns="code", values="area", aggfunc="sum")
    beds = s[s.code == "SNH"].groupby(["building", "level", "lot"]).bedrooms.max()
    lots = areas.join(beds).reset_index()
    for c in USPI_LABELS:
        if c not in lots:
            lots[c] = float("nan")
    lots["SE"] = lots["SVN"] - lots["SH"]
    return lots


def _dims(result: rules.Result) -> dict[str, list[float]]:
    """ID TGM d'un total de niveau -> [largeur, longueur] (DeltaX / DeltaY, nuls exclus)."""
    s = result.surfaces
    if not {"tgm_id", "dx", "dy"} <= set(s.columns):
        return {}
    s = s[(s.kind == "node") & s.tgm_id.notna()]
    return {r.tgm_id: sorted(round(float(v), 3) for v in (r.dx, r.dy) if not pd.isna(v) and v)
            for r in s.itertuples(index=False)}


def brutes_records(result, cfg, kinds, pid) -> list[dict]:
    dims, out = _dims(result), []
    for r in treegram.brutes(result, cfg).to_dict("records"):
        d = dims.get(r["ID TGM"], [])
        m2, h = _blank(r["Area"]), _blank(r["GrossHeight"])
        out.append({
            "ID Projet": Formula(PROJECT_ID, pid), "Categorie SIA416": r["Catégorie SIA"],
            "Partie d'Ouvrage": r["BuildingByTgm"], "Etage": r["StoreyByTgm"],
            "Decoupage": _level_kind(r["StoreyByTgm"], kinds),
            "Largeur globale": d[0] if len(d) == 2 else None, "Longueur globale": d[-1] if d else None,
            "Perimètre": _blank(r["Perimeter"]), "Hauteur brute (m)": h, "m2": m2,
            "m3": Formula("SurfacesSIA4168[[#This Row],[m2]]*SurfacesSIA4168[[#This Row],[Hauteur brute (m)]]",
                          m2 * h if m2 is not None and h is not None else None),
        })
    return out


def nettes_records(result, cfg, pid) -> list[dict]:
    return [{"ID Projet": Formula(PROJECT_ID, pid), "Categorie SIA416": r["Catégorie SIA"],
             "Partie d'Ouvrage": r["BuildingByTgm"], "Affectation": None, "Etage": r["StoreyByTgm"],
             "Appartement_Unite": _blank(r["ApartmentByTgm"]), "Nºlocal": _blank(r["ID TGM"]),
             "Nom du local": _blank(r["Type"]), "m2": _blank(r["Area"])}
            for r in treegram.nettes(result, cfg).to_dict("records")]


def uspi_records(lots: pd.DataFrame, cfg, pid) -> list[dict]:
    out = []
    for r in _ordered(lots, cfg, "lot").to_dict("records"):
        for code, label in USPI_LABELS.items():
            if not pd.isna(r[code]):
                out.append({"ID Projet": Formula(PROJECT_ID, pid), "Categorie USPI": label,
                            "Appartement_Unite": r["lot"], "m2": round(float(r[code]), 3)})
    return out


def logements_records(lots: pd.DataFrame, cfg, pid) -> list[dict]:
    return [{"ID Projet": Formula(PROJECT_ID, pid), "Partie d'Ouvrage": r["building"], "Etage": r["level"],
             "Appartement_Unite": r["lot"], "Nbr de chambres": None if pd.isna(r["bedrooms"]) else int(r["bedrooms"])}
            for r in _ordered(lots, cfg, "lot").to_dict("records")]


def enveloppe_records(result, cfg, pid) -> list[dict]:
    rows = []
    for r in _nodes(result, "SFN").to_dict("records"):
        rows.append({"building": r["building"], "level": r["level"], "_k": 0, "part": FACADE,
                     "len": _blank(r.get("perimeter")), "h": _blank(r.get("gross_height")),
                     "brute": _blank(r.get("gross_area")), "nette": _blank(r.get("net_area")),
                     "vitree": _blank(r.get("reservations_area"))})
    spt = _nodes(result, "SPT")
    for r in spt[spt.area.fillna(0) > 0].to_dict("records"):
        rows.append({"building": r["building"], "level": r["level"], "_k": 1, "part": ROOF, "len": None, "h": None,
                     "brute": round(r["area"], 3), "nette": round(r["area"], 3), "vitree": None})
    if not rows:
        return []
    df = _ordered(pd.DataFrame(rows), cfg, "_k")
    return [{"ID Projet": Formula(PROJECT_ID, pid), "Partie de l'enveloppe": r["part"], "Partie d'Ouvrage": r["building"],
             "Etage": r["level"], "Longueur (m)": r["len"], "Hauteur (m)": r["h"], "Surface Brutte": r["brute"],
             "Surface nette (m2)": r["nette"], "Surface vitrée": r["vitree"]} for r in df.to_dict("records")]


def batiments_records(levels: pd.DataFrame, pid) -> list[dict]:
    out = []
    for bld, g in levels.groupby("building", sort=True):
        above = g[g.kind == ABOVE]
        ref = (above if len(above) else g).sort_values("area").iloc[-1]   # plus grand niveau courant
        dims = sorted(v for v in (ref.dx, ref.dy) if not pd.isna(v) and v)
        out.append({"ID Projet": Formula(PROJECT_ID, pid), "Partie d'Ouvrage": bld,
                    "Nbr d'étages hors-sol": len(above), "Nbr d'étages sous-sol": int((g.kind == BELOW).sum()),
                    "Largeur du bâtiment (m)": round(dims[0], 2) if len(dims) == 2 else None,
                    "Longueur  du bâtiment": round(dims[-1], 2) if dims else None})
    return out


def projet_values(levels: pd.DataFrame, lots: pd.DataFrame) -> dict[str, object]:
    per_bld = levels.groupby("building").kind
    beds = lots.bedrooms.dropna().astype(int) if len(lots) else pd.Series(dtype=int)
    values = {
        "Nbr de bâtiments (lots)": int(levels.building.nunique()),
        "Nbr d'étages hors-sol": int(per_bld.apply(lambda k: (k == ABOVE).sum()).max()) if len(levels) else None,
        "Nbr d'étages sous-sol": int(per_bld.apply(lambda k: (k == BELOW).sum()).max()) if len(levels) else None,
        "Nbr total de logements": int(len(lots)),
        "Nbr logements type-Studio": int((beds == 0).sum()),
        "Nbr de chambres": int(beds.sum()),
    }
    for n in range(1, 6):
        values[f"Nbr logements type-{n} chambre{'s' if n > 1 else ''}"] = int((beds == n).sum())
    return values


def build(result: rules.Result, cfg: Config, template: str | Path, project_id=None, project_name=None) -> Workbook:
    wb = Workbook(template)
    missing = [c for c in ["tgm_id", *reader.EXTRA_COLUMNS] if c not in result.surfaces]
    if missing:   # source sans propriétés Treegram (IFC) : colonnes vides
        result = dataclasses.replace(result, surfaces=result.surfaces.assign(**{c: None for c in missing}))
    info = {r["Description"]: i for i, r in enumerate(wb.table_rows("InfosProjet"))} if "InfosProjet" in wb.tables else {}
    info_row = lambda desc: wb.tables["InfosProjet"].header_row + 1 + info[desc]  # noqa: E731
    if project_id is not None and "ID projet" in info:
        wb.set_cell("InfosProjet", f"C{info_row('ID projet')}", project_id)
    pid = wb.cell_value("InfosProjet", f"C{info_row('ID projet')}") if "ID projet" in info else project_id
    if project_name and "Nom Projet HRS" in info and not wb.cell_value("InfosProjet", f"C{info_row('Nom Projet HRS')}"):
        wb.set_cell("InfosProjet", f"C{info_row('Nom Projet HRS')}", project_name)

    kinds = _decoupage(wb)
    levels, lots = _project_levels(result, kinds), _lots(result)
    wb.fill_table("SurfacesSIA4168", brutes_records(result, cfg, kinds, pid))
    wb.fill_table("SurfacesSIA41610", nettes_records(result, cfg, pid))
    wb.fill_table("SurfacesSIA41611", uspi_records(lots, cfg, pid))
    wb.fill_table("Logements", logements_records(lots, cfg, pid))
    wb.fill_table("SurfacesSIA416", enveloppe_records(result, cfg, pid))
    wb.fill_table("Tableau3", batiments_records(levels, pid))
    for desc, value in projet_values(levels, lots).items():
        if desc in info:
            wb.set_cell("InfosProjet", f"C{info_row(desc)}", value)
    return wb


def write(result: rules.Result, cfg: Config, path: str | Path, template: str | Path | None = None,
          project_id=None, project_name=None) -> Path:
    return build(result, cfg, template or DEFAULT_TEMPLATE, project_id, project_name).save(path)
