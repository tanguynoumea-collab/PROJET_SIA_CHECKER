"""Projet généré comparé à un MDP de référence (V4_PLAN §4) : le moteur face à ce que HRS a livré.

Faute de paire IFC ↔ `.tgm`, la référence est le MDP du projet dans la base du benchmark. Ses feuilles
SurfacesNettesSIA416 (une ligne par local) et SurfacesBrutesVolumeSIA416 (SP et SEP par étage) viennent de la
chaîne Treegram → Excel → MDP.

- **Par étage et par code** : m² et nombre de locaux, MDP contre projet généré.
- **Local par local** : chaque local du MDP est apparié à une pièce générée du même étage, de même nom (sans
  accents ni casse) et d'aire voisine, sinon d'aire voisine seule ; la matrice de confusion des codes dit où le
  classement diffère.

`sia-check <projet généré> --comparer-mdp MDP.xlsx --batiment-mdp "Bat. 1"` (le bâtiment du MDP, quand il en
compte plusieurs).
"""

from __future__ import annotations

import json
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from .. import benchmark, reader, siagen
from ..config import Config
from .classify import norm

CODES = ["SP", "SUP", "SUS", "SD", "SI", "SUT"]
AREA_ABS, AREA_REL = 0.5, 0.03


def _sheet(path: Path, name: str) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        x = pd.ExcelFile(path)
        return benchmark._sheet(x, name)


def read_mdp(path: Path, building: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """(locaux, brutes, bâtiments du MDP) : colonnes building, level, code, m2 (+ name, unit pour les locaux)."""
    out = []
    for sheet in ("SurfacesNettesSIA416", "SurfacesBrutesVolumeSIA416"):
        df = _sheet(path, sheet)
        if df.empty:
            out.append(pd.DataFrame(columns=["building", "level", "code", "m2", "name", "unit"]))
            continue
        col = lambda *n: benchmark._col(df, *n)   # noqa: E731
        c_b, c_l, c_c, c_m = col("partie d'ouvrage"), col("etage"), col("categorie"), col("m2")
        c_n, c_u = col("nom du local"), col("appartement")
        none = [None] * len(df)
        out.append(pd.DataFrame({
            "building": df[c_b].astype(str).str.strip() if c_b else none,
            "level": df[c_l].astype(str).str.strip().str.upper() if c_l else none,
            "code": df[c_c].ffill().map(benchmark.code) if c_c else none,
            "m2": pd.to_numeric(df[c_m], errors="coerce").fillna(0.0) if c_m else 0.0,
            "name": df[c_n] if c_n else none, "unit": df[c_u] if c_u else none,
        }))
    nettes, brutes = out
    # même bâtiment écrit avec ou sans accent selon la feuille (MDP La Bâtie : « Batiment B », « Bâtiment B »)
    names = {}
    for b in pd.concat([nettes.building, brutes.building]).dropna():
        if b != "nan":
            names.setdefault(norm(b), b)
    buildings = sorted(names.values())
    if building is not None:
        nettes, brutes = nettes[nettes.building.map(norm) == norm(building)], brutes[brutes.building.map(norm) == norm(building)]
    return nettes.reset_index(drop=True), brutes.reset_index(drop=True), buildings


def _generated(folder: Path, cfg: Config) -> tuple[pd.DataFrame, dict]:
    src = next(folder.glob(f"*{siagen.SUFFIX}"))
    df = reader.read(src, cfg)
    rapport = folder / "generation" / "rapport.json"
    spaces = {}
    if rapport.is_file():
        spaces = {s["gid"]: s for s in json.loads(rapport.read_text(encoding="utf-8"))["spaces"]}
    _, els = siagen.load(src)
    gid = {e.name: e.props.get("IfcGlobalId") for e in els if e.kind == "leaf"}
    df["gid"] = df.id.map(gid)
    df["name"] = df.gid.map(lambda g: (spaces.get(g) or {}).get("long_name") or (spaces.get(g) or {}).get("name"))
    return df, spaces


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(AREA_ABS, AREA_REL * max(a, b))


def match(mdp: pd.DataFrame, gen: pd.DataFrame) -> list[tuple[int | None, int | None]]:
    """Appariement local du MDP -> pièce générée (index), même étage : même nom et aire voisine, puis aire seule."""
    pairs, used = [], set()
    by_level = defaultdict(list)
    for i, r in gen.iterrows():
        by_level[r.level].append(i)
    for passe in ("nom", "aire"):
        for i, r in mdp.iterrows():
            if any(p[0] == i for p in pairs):
                continue
            cands = [j for j in by_level.get(r.level, []) if j not in used and _close(r.m2, gen.at[j, "area"])
                     and (passe == "aire" or norm(gen.at[j, "name"]) == norm(r["name"]))]
            if cands:
                j = min(cands, key=lambda j: abs(gen.at[j, "area"] - r.m2))
                used.add(j)
                pairs.append((i, j))
    matched = {p[0] for p in pairs}
    pairs += [(i, None) for i in mdp.index if i not in matched]
    pairs += [(None, j) for j in gen.index if j not in used]
    return pairs


def compare(folder: Path, mdp_path: Path, cfg: Config, building: str | None = None) -> dict:
    nettes, brutes, buildings = read_mdp(mdp_path, building)
    if building is None and len(buildings) > 1:
        raise ValueError(f"le MDP compte {len(buildings)} bâtiments ({', '.join(buildings)}) : choisir --batiment-mdp")
    df, _ = _generated(folder, cfg)
    leaves = df[(df.kind == "leaf") & df.category.isin(CODES)].reset_index(drop=True)
    nodes = df[(df.kind == "node") & (df.category == "SP")]
    nettes = nettes[nettes.code.isin(CODES)].reset_index(drop=True)
    levels = sorted(set(nettes.level) | set(brutes[brutes.code == "SP"].level) | set(leaves.level) | set(nodes.level))
    table = []
    for lv in levels:
        row = {"level": lv}
        for code in CODES:
            if code == "SP":
                ref = brutes[(brutes.level == lv) & (brutes.code == "SP")].m2.sum()
                got = nodes[nodes.level == lv].area.sum()
                n_ref = n_got = None
            else:
                part_r, part_g = nettes[(nettes.level == lv) & (nettes.code == code)], leaves[(leaves.level == lv) & (leaves.category == code)]
                ref, got, n_ref, n_got = part_r.m2.sum(), part_g.area.sum(), len(part_r), len(part_g)
            row[code] = {"mdp": round(float(ref), 2), "genere": round(float(got), 2), "ecart": round(float(got - ref), 2),
                         "n_mdp": n_ref, "n_genere": n_got}
        table.append(row)
    pairs = match(nettes, leaves)
    confusion = Counter()
    for i, j in pairs:
        confusion[(nettes.at[i, "code"] if i is not None else "—", leaves.at[j, "category"] if j is not None else "—")] += 1
    paired = [(i, j) for i, j in pairs if i is not None and j is not None]
    disagree = [{"level": nettes.at[i, "level"], "mdp_nom": nettes.at[i, "name"], "mdp_code": nettes.at[i, "code"],
                 "m2": round(float(nettes.at[i, "m2"]), 2), "genere_nom": leaves.at[j, "name"],
                 "genere_code": leaves.at[j, "category"], "genere_type": leaves.at[j, "room_type"]}
                for i, j in paired if nettes.at[i, "code"] != leaves.at[j, "category"]]
    return {
        "mdp": str(mdp_path), "batiment_mdp": building, "batiments_mdp": buildings, "projet": str(folder),
        "locaux_mdp": len(nettes), "pieces_generees": len(leaves), "apparies": len(paired),
        "meme_code": sum(1 for i, j in paired if nettes.at[i, "code"] == leaves.at[j, "category"]),
        "etages": table,
        "confusion": [{"mdp": a, "genere": b, "n": n} for (a, b), n in sorted(confusion.items())],
        "desaccords": disagree,
        "sans_pair_mdp": [{"level": nettes.at[i, "level"], "nom": nettes.at[i, "name"], "code": nettes.at[i, "code"],
                           "m2": round(float(nettes.at[i, "m2"]), 2)} for i, j in pairs if j is None],
        "sans_pair_genere": [{"level": leaves.at[j, "level"], "nom": leaves.at[j, "name"], "code": leaves.at[j, "category"],
                              "m2": round(float(leaves.at[j, "area"]), 2)} for i, j in pairs if i is None],
    }


def summary(c: dict) -> str:
    def tot(code, k):
        return sum(r[code][k] for r in c["etages"])
    lines = [f"Référence : {Path(c['mdp']).name}" + (f" · {c['batiment_mdp']}" if c["batiment_mdp"] else ""),
             f"Locaux : {c['locaux_mdp']} au MDP, {c['pieces_generees']} générés, {c['apparies']} appariés, "
             f"{c['meme_code']} au même code ({c['meme_code'] / c['apparies']:.0%} des appariés)" if c["apparies"] else
             "Aucun local apparié"]
    head = f"\n  {'étage':<9}" + "".join(f"{code:>22}" for code in CODES)
    lines += [head, "  " + " " * 9 + "".join(f"{'MDP → généré':>22}" for _ in CODES)]
    for r in c["etages"] + [{"level": "Total", **{code: {"mdp": tot(code, "mdp"), "genere": tot(code, "genere")} for code in CODES}}]:
        cells = []
        for code in CODES:
            a, b = r[code]["mdp"], r[code]["genere"]
            cells.append(f"{a:>9.1f} → {b:>9.1f}" if (a or b) else f"{'·':>21}")
        lines.append(f"  {r['level']:<9}" + "".join(f"{x:>22}" for x in cells))
    lines.append("\nConfusion des codes (MDP → généré) : " + " · ".join(
        f"{x['mdp']}→{x['genere']} {x['n']}" for x in c["confusion"] if x["mdp"] != x["genere"]))
    if c["desaccords"]:
        lines.append("Désaccords (extrait) :")
        for d in c["desaccords"][:15]:
            lines.append(f"  {d['level']:<6}{str(d['mdp_nom'])[:28]:<30}{d['m2']:>8.2f}  MDP {d['mdp_code']:<5} généré "
                         f"{d['genere_code']:<5} {d['genere_type'] or ''}")
    return "\n".join(lines)
