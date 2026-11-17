"""Forme des bâtiments d'un projet (docs/V5_PLAN.md, partie 5).

Une forme par bâtiment, choisie dans FORMES. Le MDP la porte dans InfosProjet (champ « Forme ») sous forme de texte :
- un seul bâtiment : la forme seule, « Rectangle compact » ;
- plusieurs bâtiments : « A : Carré ; B : Rectangle compact » (bâtiment, deux-points, forme ; séparés par « ; »).

Le champ « Forme (origine) » dit qui l'a renseignée : « saisie » (l'utilisateur) ou « IA » (revue IA ou analyse IA
de la génération). L'IA ne remplace une saisie qu'après confirmation de l'utilisateur (application).

Au benchmark, un projet à plusieurs bâtiments est un « Îlot de bâtiments » suivi des formes de ses bâtiments.
"""

from __future__ import annotations

FORMES = ("Carré", "Rectangle compact", "Barre", "En L", "En T", "En U", "Cour fermée / îlot", "À redans / en Z",
          "En peigne / en H", "Rond / ovale", "Courbe / arc", "Plusieurs plots", "Irrégulière")
ILOT = "Îlot de bâtiments"
ORIGINES = ("saisie", "IA")
SEP_BATIMENTS, SEP_FORME = ";", ":"


def normaliser(forme: str | None) -> str | None:
    """La forme de FORMES qui correspond (casse, espaces, accents tolérés), ou None."""
    if not forme:
        return None
    cle = _cle(forme)
    return next((f for f in FORMES if _cle(f) == cle), None)


def decoder(texte: str | None) -> dict[str, str]:
    """{bâtiment: forme} ; bâtiment « » pour un projet à une seule forme. Les formes inconnues sont ignorées."""
    formes: dict[str, str] = {}
    for part in (texte or "").split(SEP_BATIMENTS):
        if not part.strip():
            continue
        bat, _, forme = part.rpartition(SEP_FORME)
        if (f := normaliser(forme)) is not None:
            formes[bat.strip()] = f
    return formes


def encoder(formes: dict[str, str]) -> str:
    """Texte du MDP ; un seul bâtiment : la forme seule."""
    propres = {b.strip(): n for b, f in formes.items() if (n := normaliser(f))}
    if len(propres) == 1:
        return next(iter(propres.values()))
    return f" {SEP_BATIMENTS} ".join(f"{b} {SEP_FORME} {f}" for b, f in sorted(propres.items()))


def libelle(formes: dict[str, str]) -> str:
    """Forme du projet en clair : la forme du bâtiment seul, ou « Îlot de bâtiments : Carré, Rectangle compact »."""
    if not formes:
        return ""
    if len(formes) == 1:
        return next(iter(formes.values()))
    distinctes = sorted(set(formes.values()), key=FORMES.index)
    return f"{ILOT} : {', '.join(distinctes)}"


def _cle(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s.strip().lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())
