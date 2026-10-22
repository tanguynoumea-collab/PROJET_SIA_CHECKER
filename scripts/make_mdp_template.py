"""Gabarit MDP vierge, tiré d'un MDP HRS existant : tableaux de données vidés, valeurs d'InfosProjet effacées.

    .venv/Scripts/python scripts/make_mdp_template.py "MDP-1778-Loree.xlsx"

Écrit src/sia_check/templates/MDP-gabarit.xlsx, le gabarit par défaut de `sia-check --mdp` ; les textes
de l'ancien projet sont retirés de la table des chaînes partagées. Listes
déroulantes, feuille « Listes formulaire » et mise en forme sont conservées (xlsx_tables). Le tableau
croisé de la feuille SurfacesEnveloppe garde son cache : il n'est pas lié aux tableaux remplis.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sia_check import mdp  # noqa: E402
from sia_check.xlsx_tables import Workbook  # noqa: E402

DATA_TABLES = ["SurfacesSIA4168", "SurfacesSIA41610", "SurfacesSIA41611", "Logements", "SurfacesSIA416", "Tableau3"]


def main(src: str) -> Path:
    wb = Workbook(src)
    for name in DATA_TABLES:
        wb.fill_table(name, [])
    t = wb.tables["InfosProjet"]
    for row in range(t.header_row + 1, t.last_row + 1):
        wb.set_cell("InfosProjet", f"C{row}", None)
    return wb.save(mdp.DEFAULT_TEMPLATE, compact_strings=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(main(sys.argv[1]))
