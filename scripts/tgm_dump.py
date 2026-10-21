"""Exploration : vide tous les sacs de propriétés d'un projet Treegram `.tgm` dans un CSV.

Usage : python scripts/tgm_dump.py "L OREE.tgm" out.csv

Le décodeur est celui du package (src/sia_check/tgm.py) ; ce script garde tous les
éléments, y compris ceux sans catégorie SIA, pour étudier le format.
"""

from __future__ import annotations

import csv
import sys

from sia_check import tgm


def main() -> int:
    src, out = sys.argv[1], sys.argv[2]
    bags = list(tgm.scan(open(src, "rb").read()))
    keys = sorted({k for g in bags for k in g.props})
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["offset", "element", *keys])
        for g in bags:
            w.writerow([g.offset, g.name, *[g.props.get(k, "") for k in keys]])
    print(f"{len(bags)} éléments, {len(keys)} propriétés distinctes -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
