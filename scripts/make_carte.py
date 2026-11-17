"""Fond de carte hors ligne de la Suisse et répertoire des localités (docs/V5_PLAN.md, partie 3 : vue Carte du dashboard).

    .venv/Scripts/python scripts/make_carte.py ch-combined.json ortschaftenverzeichnis_plz_2056.csv.zip

La carte du dashboard affiche en ligne les fonds et calques de swisstopo (geo.admin.ch). Ce fond-ci est le minimum
livré avec la page, pour travailler sans réseau : pays, cantons, districts, communes (avec leur nom) et lacs.

Sources (à télécharger, puis à passer à ce script) :
    ch-combined.json   swiss-maps 4.5.0, millésime 2024 (Interactive Things, BSD-3, d'après swisstopo et l'OFS) :
                       https://cdn.jsdelivr.net/npm/swiss-maps@4.5.0/2024/ch-combined.json
    *.csv.zip          Répertoire officiel des localités, swisstopo (données ouvertes, OGD) :
                       https://data.geo.admin.ch/ch.swisstopo-vd.ortschaftenverzeichnis_plz/ortschaftenverzeichnis_plz/
                       ortschaftenverzeichnis_plz_2056.csv.zip

Écrit :
    dashboard/carte-suisse.json            TopoJSON (WGS84) des pays, cantons, districts, communes et lacs ; nom et canton
                                           de chaque commune par numéro OFS ; sigle de chaque canton par numéro
    src/sia_check/data/localites.json      noms normalisés de localité et de commune → [canton, E, N] (LV95, m) ;
                                           lu par sia_check.localites pour placer un projet sans adresse
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sia_check.localites import cle  # noqa: E402  (même clé à l'écriture et à la lecture)

CANTONS = ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR",
           "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU"]   # numéros OFS 1 à 26


def lignes_localites(zip_path: Path) -> list[dict]:
    z = zipfile.ZipFile(zip_path)
    nom = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    return list(csv.DictReader(io.StringIO(z.read(nom).decode("utf-8-sig")), delimiter=";"))


def localites(lignes: list[dict]) -> dict[str, list]:
    """Clé → [[canton, E, N], …] : chaque localité (part d'adresses la plus forte) et chaque commune (centre pondéré)."""
    kc = next(k for k in lignes[0] if k.lower().startswith("kanton"))
    part = lambda r: float(r["Adressenanteil"].rstrip(" %") or 0)   # noqa: E731
    lieux: dict[tuple[str, str], tuple[float, float, float]] = {}
    communes: dict[tuple[str, str], list[float]] = {}
    for r in lignes:
        if not r["E"] or not r["N"]:
            continue
        e, n, w = float(r["E"]), float(r["N"]), part(r) or 0.01
        k = (cle(re.sub(r"\s+\d+$", "", r["Ortschaftsname"])), r[kc])     # « Lausanne 25 » → Lausanne
        if k not in lieux or w > lieux[k][2]:
            lieux[k] = (e, n, w)
        c = communes.setdefault((cle(r["Gemeindename"]), r[kc]), [0.0, 0.0, 0.0])
        c[0] += e * w
        c[1] += n * w
        c[2] += w
    out: dict[str, dict] = {}
    # la commune fait foi sur une localité du même nom (Lancy commune plutôt que le lieu-dit)
    for (k, kt), (e, n, _) in lieux.items():
        out.setdefault(k, {})[kt] = [kt, round(e), round(n)]
    for (k, kt), (se, sn, sw) in communes.items():
        out.setdefault(k, {})[kt] = [kt, round(se / sw), round(sn / sw)]
    return {k: sorted(v.values()) for k, v in sorted(out.items())}


def noms_communes(lignes: list[dict]) -> dict[str, list[str]]:
    """Numéro OFS → [nom, canton] des communes."""
    kc = next(k for k in lignes[0] if k.lower().startswith("kanton"))
    return {r["BFS-Nr"]: [r["Gemeindename"], r[kc]] for r in lignes if r.get("BFS-Nr")}


def main(topo_path: Path, zip_path: Path) -> None:
    topo = json.loads(topo_path.read_text(encoding="utf-8"))
    lignes = lignes_localites(zip_path)
    communes = noms_communes(lignes)
    ids = [str(g.get("id")) for g in topo["objects"]["municipalities"]["geometries"]]
    carte = {
        "source": "swiss-maps 4.5.0, 2024 (Interactive Things, BSD-3 ; swisstopo, OFS) · noms : répertoire des localités, swisstopo",
        "topo": topo,
        "communes": {i: communes[i] for i in ids if i in communes},
        "cantons": {str(k + 1): s for k, s in enumerate(CANTONS)},
    }
    sortie = ROOT / "dashboard" / "carte-suisse.json"
    sortie.write_text(json.dumps(carte, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    lieux = localites(lignes)
    data = ROOT / "src" / "sia_check" / "data"
    data.mkdir(exist_ok=True)
    (data / "localites.json").write_text(json.dumps({
        "source": "Répertoire officiel des localités, swisstopo (OGD) · LV95, m", "lieux": lieux},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{sortie.name} : {sortie.stat().st_size // 1024} Ko, {len(ids)} communes dont {len(carte['communes'])} nommées")
    print(f"localites.json : {(data / 'localites.json').stat().st_size // 1024} Ko, {len(lieux)} noms")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
