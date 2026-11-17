"""Position d'un projet d'après sa commune (docs/V5_PLAN.md, partie 3 : vue Carte du dashboard).

Le répertoire `data/localites.json` (scripts/make_carte.py, d'après le répertoire officiel des localités de swisstopo)
associe chaque nom de localité et de commune, normalisé, à ses coordonnées LV95 par canton. Un MDP ne porte que la
commune (et le canton) : le projet est placé au centre de la commune, ou de la localité du même nom (Petit-Lancy,
Estavayer-le-Lac…). Sans commune reconnue, il n'est pas placé.
"""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from pathlib import Path

DATA = Path(__file__).with_name("data") / "localites.json"


def cle(nom: str) -> str:
    """Clé de recherche d'un nom : sans accents ni casse, tirets et apostrophes comme des espaces, « St » = « Saint »."""
    s = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[-'’./]", " ", s)
    s = re.sub(r"\bste\b", "sainte", s)
    s = re.sub(r"\bst\b", "saint", s)
    return re.sub(r"\s+", " ", s).strip()


@functools.cache
def _lieux() -> dict[str, list]:
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))["lieux"]
    except (OSError, ValueError, KeyError):
        return {}


def position(commune, canton=None) -> list[int] | None:
    """[E, N] (LV95, m) de la commune, dans le canton donné s'il y en a un ; None si inconnue ou ambiguë sans canton."""
    if not commune or not str(commune).strip():
        return None
    k = cle(commune)
    candidats = _lieux().get(k)
    if not candidats:
        # « Lausanne - Prélaz », « Vernier, Lignon » : la commune avant le séparateur
        tete = re.split(r"\s+-\s+|,", str(commune))[0]
        candidats = _lieux().get(cle(tete)) if tete != str(commune) else None
    if not candidats:
        return None
    if canton:
        candidats = [c for c in candidats if c[0] == str(canton).strip().upper()] or (candidats if len(candidats) == 1 else [])
    return [candidats[0][1], candidats[0][2]] if len(candidats) == 1 else None
