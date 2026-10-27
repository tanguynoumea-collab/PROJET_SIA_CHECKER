"""Tableau MDP HRS (« MDP-<id>-<projet>.xlsx ») rempli depuis le `.tgm`.

Le gabarit est un MDP existant ou vierge : ses tableaux de données sont vidés puis remplis, le reste
(listes déroulantes, feuille « Listes formulaire », documents) est conservé (xlsx_tables).

| Feuille                    | Tableau            | Source                                                   |
|----------------------------|--------------------|----------------------------------------------------------|
| SurfacesBrutesVolumeSIA416 | SurfacesSIA4168    | SP / SEP / SA par niveau, m³ = m² × h brute (hors SA)     |
| SurfacesNettesSIA416       | SurfacesSIA41610   | surfaces élémentaires SIA (treegram.nettes)              |
| SurfacesUSPI               | SurfacesSIA41611   | SNH, SH, SBH, SE = SVN − SH, SVN, SVB par lot            |
| ListeLogements             | Logements          | lots USPI : bâtiment, niveau, nombre de chambres         |
| SurfacesEnveloppe          | SurfacesSIA416     | façade (SFN) et toiture (SPT) par niveau                 |
| InfosBatiment              | Tableau3           | étages hors-sol / sous-sol, dimensions (SP)              |
| InfosProjet                | InfosProjet        | comptages : bâtiments, étages, logements, chambres       |

Affectation, typologies, nombre de pièces et forme des bâtiments : propositions acceptées dans la
visionneuse (propositions.py, corrections « affecter » et « renseigner »), « Inconnu » si elles sont
refusées, vides sinon. Les champs administratifs restent vides. Le tableau croisé de la feuille
SurfacesEnveloppe n'est pas recalculé.

Pour Power BI : pas de ligne brute à 0 m², étages aux codes du gabarit (`mdp.etages`, Toiture -> TOI),
nombre de chambres vide quand Treegram écrit −1.
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
    beds = beds.where(beds >= 0)   # Treegram écrit −1 quand les chambres ne sont pas renseignées : vide
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


def _etage(level, cfg: Config):
    """Niveau Treegram -> code d'étage de la liste du gabarit (`config.yaml > mdp.etages`, ex. Toiture -> TOI)."""
    return (cfg.mdp.get("etages") or {}).get(level, level) if level is not None else None


def brutes_records(result, cfg, kinds, pid) -> list[dict]:
    """Une ligne par total de niveau non nul. Les abords (SA) n'ont pas de volume : hauteur et m³ vides."""
    dims, out = _dims(result), []
    for r in treegram.brutes(result, cfg).to_dict("records"):
        d = dims.get(r["ID TGM"], [])
        m2, h = _blank(r["Area"]), _blank(r["GrossHeight"])
        if not m2 and r["Catégorie SIA"] == "SP":   # SP de toiture à 0 m² : pas un étage
            continue
        cat, etage = r["Catégorie SIA"], _etage(r["StoreyByTgm"], cfg)
        if cat == "SA":
            h = None
        out.append({
            "ID Projet": Formula(PROJECT_ID, pid), "Categorie SIA416": cat,
            "Partie d'Ouvrage": r["BuildingByTgm"], "Etage": etage,
            "Decoupage": _level_kind(etage, kinds),
            "Largeur globale": d[0] if len(d) == 2 else None, "Longueur globale": d[-1] if d else None,
            "Perimètre": _blank(r["Perimeter"]), "Hauteur brute (m)": h, "m2": m2,
            "m3": None if h is None else
            Formula("SurfacesSIA4168[[#This Row],[m2]]*SurfacesSIA4168[[#This Row],[Hauteur brute (m)]]", m2 * h),
        })
    return out


def nettes_records(result, cfg, pid) -> list[dict]:
    s = result.surfaces   # affectation : correction « affecter » (corrections.py)
    aff = dict(zip(s["id"].astype(str), s["affectation"])) if "affectation" in s else {}
    return [{"ID Projet": Formula(PROJECT_ID, pid), "Categorie SIA416": r["Catégorie SIA"],
             "Partie d'Ouvrage": r["BuildingByTgm"], "Affectation": _blank(aff.get(str(r["Object.Name"]))),
             "Etage": _etage(r["StoreyByTgm"], cfg),
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


def _champs(infos: list[dict], columns, **key) -> dict:
    """Champs « renseigner » dont la sélection correspond à la ligne (bedrooms, building), limités au tableau."""
    out = {}
    for info in infos or []:
        sel = info["selection"]
        if all(_matches(sel.get(k), v) for k, v in key.items() if k in sel) and any(k in sel for k in key):
            out.update({c: v for c, v in info["champs"].items() if c in columns})
    return out


def _matches(want, value) -> bool:
    values = want if isinstance(want, list) else [want]
    try:
        return any(float(w) == float(value) for w in values)
    except (TypeError, ValueError):
        return any(str(w) == str(value) for w in values)


def logements_records(lots: pd.DataFrame, cfg, pid, infos=None, columns=()) -> list[dict]:
    out = []
    for r in _ordered(lots, cfg, "lot").to_dict("records"):
        beds = None if pd.isna(r["bedrooms"]) else int(r["bedrooms"])
        out.append({"ID Projet": Formula(PROJECT_ID, pid), "Partie d'Ouvrage": r["building"], "Etage": _etage(r["level"], cfg),
                    "Appartement_Unite": r["lot"], "Nbr de chambres": beds,
                    **_champs(infos, columns, bedrooms=beds, building=r["building"])})
    return out


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
             "Etage": _etage(r["level"], cfg), "Longueur (m)": r["len"], "Hauteur (m)": r["h"], "Surface Brutte": r["brute"],
             "Surface nette (m2)": r["nette"], "Surface vitrée": r["vitree"]} for r in df.to_dict("records")]


def batiments_records(levels: pd.DataFrame, pid, infos=None, columns=()) -> list[dict]:
    out = []
    for bld, g in levels.groupby("building", sort=True):
        above = g[g.kind == ABOVE]
        ref = (above if len(above) else g).sort_values("area").iloc[-1]   # plus grand niveau courant
        dims = sorted(v for v in (ref.dx, ref.dy) if not pd.isna(v) and v)
        out.append({"ID Projet": Formula(PROJECT_ID, pid), "Partie d'Ouvrage": bld,
                    "Nbr d'étages hors-sol": len(above), "Nbr d'étages sous-sol": int((g.kind == BELOW).sum()),
                    "Largeur du bâtiment (m)": round(dims[0], 2) if len(dims) == 2 else None,
                    "Longueur  du bâtiment": round(dims[-1], 2) if dims else None,
                    **_champs(infos, columns, building=bld)})
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


# Identité d'un projet (fiche « Identité du projet » de la visionneuse) : descriptions de la feuille InfosProjet
IDENTITE = ("ID projet", "Nom Projet HRS", "Canton", "Commune", "Categorie d'Ouvrage", "Type d'intervention",
            "Phase du projet")
# Colonnes de la feuille « Listes formulaire » qui alimentent les listes déroulantes de la fiche
LISTES = {"Categorie d'Ouvrage": "Categorie d'Ouvrage", "Canton": "Cantons", "Type d'intervention": "Type Intervention",
          "Phase du projet": "Phase du projet"}


def _ligne_info(wb: Workbook, desc: str) -> int | None:
    """Ligne de `desc` dans InfosProjet : par le tableau du gabarit, sinon en lisant la colonne B (anciens MDP)."""
    if "InfosProjet" in wb.tables:
        rows = [r["Description"] for r in wb.table_rows("InfosProjet")]
        if desc in rows:
            return wb.tables["InfosProjet"].header_row + 1 + rows.index(desc)
    if "InfosProjet" not in wb.sheets:
        return None
    cle = desc.strip().lower()
    for r in range(1, 120):
        v = wb.cell_value("InfosProjet", f"B{r}")
        if v is not None and str(v).strip().lower() == cle:
            return r
    return None


def _valeur_identite(desc: str, v):
    """ID et phase en nombre quand ils le sont (jointure Power BI, listes du gabarit)."""
    if isinstance(v, str) and desc in ("ID projet", "Phase du projet") and v.strip().isdigit():
        return int(v.strip())
    return v.strip() if isinstance(v, str) else v


def set_identite(wb: Workbook, identite: dict) -> None:
    """Écrit les champs d'identité renseignés dans InfosProjet ; une valeur vide n'efface rien."""
    for desc, v in identite.items():
        if desc not in IDENTITE or v is None or (isinstance(v, str) and not v.strip()):
            continue
        r = _ligne_info(wb, desc)
        if r is not None:
            wb.set_cell("InfosProjet", f"C{r}", _valeur_identite(desc, v))


def ecrire_identite(path: str | Path, identite: dict) -> Path:
    """L'identité écrite dans un MDP existant, le reste du classeur intact (listes, mises en forme, tableaux)."""
    wb = Workbook(path)
    set_identite(wb, identite)
    return wb.save(path)


def listes(template: str | Path = DEFAULT_TEMPLATE) -> dict[str, list[str]]:
    """Valeurs des listes déroulantes de l'identité, lues dans le gabarit (feuille « Listes formulaire »)."""
    import re

    import pandas as pd

    df = pd.read_excel(template, sheet_name="Listes formulaire")
    out = {}
    for desc, colonne in LISTES.items():
        col = next((c for c in df.columns if str(c).strip() == colonne), None)
        vals = [] if col is None else df[col].dropna().tolist()
        vals = [str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip() for v in vals]
        out[desc] = list(dict.fromkeys(v for v in vals if v and not re.fullmatch(r"(?i)x+|abreviation", v)))
    return out


def build(result: rules.Result, cfg: Config, template: str | Path, project_id=None, project_name=None,
          infos: list[dict] | None = None, identite: dict | None = None) -> Workbook:
    """`infos` : champs des corrections « renseigner » appliquées (corrections.Applied.infos) ;
    `identite` : fiche « Identité du projet » (IDENTITE), prioritaire sur `project_id` et `project_name`."""
    wb = Workbook(template)
    missing = [c for c in ["tgm_id", *reader.EXTRA_COLUMNS] if c not in result.surfaces]
    if missing:   # source sans propriétés Treegram (IFC) : colonnes vides
        result = dataclasses.replace(result, surfaces=result.surfaces.assign(**{c: None for c in missing}))
    info = {r["Description"]: i for i, r in enumerate(wb.table_rows("InfosProjet"))} if "InfosProjet" in wb.tables else {}
    info_row = lambda desc: wb.tables["InfosProjet"].header_row + 1 + info[desc]  # noqa: E731
    if project_id is not None and "ID projet" in info:
        wb.set_cell("InfosProjet", f"C{info_row('ID projet')}", project_id)
    pid = wb.cell_value("InfosProjet", f"C{info_row('ID projet')}") if "ID projet" in info else project_id
    if project_name and "Nom Projet HRS" in info:
        wb.set_cell("InfosProjet", f"C{info_row('Nom Projet HRS')}", project_name)

    if identite:
        set_identite(wb, identite)
        pid = wb.cell_value("InfosProjet", f"C{info_row('ID projet')}") if "ID projet" in info else pid

    kinds = _decoupage(wb)
    levels, lots = _project_levels(result, kinds), _lots(result)
    wb.fill_table("SurfacesSIA4168", brutes_records(result, cfg, kinds, pid))
    wb.fill_table("SurfacesSIA41610", nettes_records(result, cfg, pid))
    wb.fill_table("SurfacesSIA41611", uspi_records(lots, cfg, pid))
    wb.fill_table("Logements", logements_records(lots, cfg, pid, infos, wb.tables["Logements"].columns))
    wb.fill_table("SurfacesSIA416", enveloppe_records(result, cfg, pid))
    wb.fill_table("Tableau3", batiments_records(levels, pid, infos, wb.tables["Tableau3"].columns))
    for desc, value in projet_values(levels, lots).items():
        if desc in info:
            wb.set_cell("InfosProjet", f"C{info_row(desc)}", value)
    return wb


def write(result: rules.Result, cfg: Config, path: str | Path, template: str | Path | None = None,
          project_id=None, project_name=None, infos: list[dict] | None = None, identite: dict | None = None) -> Path:
    return build(result, cfg, template or DEFAULT_TEMPLATE, project_id, project_name, infos, identite).save(path)
