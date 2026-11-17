"""Emprise au sol de chaque bâtiment et description compacte pour l'IA (docs/V5_PLAN.md, partie 5).

Les deux analyses IA (revue IA Treegram, analyse IA de la génération IFC) proposent une forme par bâtiment, choisie
dans `formes.FORMES`. Elles ne voient pas les tracés : ce module leur décrit l'emprise de chaque bâtiment en
quelques nombres et un contour simplifié, avec une forme estimée qui n'est qu'un indice.

Règle d'emprise (la plus robuste sur les deux sources) :
- **union des SP des niveaux hors-sol, projetées en plan**. L'union donne la silhouette vue d'avion : un attique en
  retrait ou un étage en porte-à-faux ne changent pas la forme, un rez plus étendu (socle commercial) l'élargit,
  comme sur un plan masse. L'étage le plus étendu seul raterait un bâtiment dont les ailes sont à des étages
  différents ; son aire est donnée à côté (`aire_etage_max_m2`) pour juger de l'écart ;
- hors-sol : rang de niveau ≥ 0 quand il est connu (visionneuse), sinon le code d'étage (S01, SS1, U1, -1,
  « sous-sol » = sous-sol, comme config.yaml > levels.order) ;
- sans SP hors-sol : la SP des sous-sols (`source` le dit) ; sans aucune SP : l'union des surfaces intérieures,
  fermée de 0,5 m pour franchir les murs ;
- nettoyage : fermeture de 0,1 m (joints de triangulation, pièces jointives), trous de moins de 20 m² bouchés
  (gaines, puits de lumière) ; les trous restants sont des **cours** ; parties de moins de 10 m² ignorées.

Description (`decrire`) : aire, longueur et largeur du rectangle minimal orienté, élancement (longueur / largeur),
rectangularité (aire / rectangle minimal), convexité (aire / enveloppe convexe), cours, parties disjointes, angles
rentrants (sommets concaves du contour simplifié à 0,5 m, coude de plus de 20°), et le contour simplifié en mètres,
recentré sur le rectangle minimal et tourné pour que l'axe long soit l'axe x, arrondi à 0,1 m, plafonné à
MAX_SOMMETS sommets par contour.

Forme estimée (`estimer`, heuristique déterministe, un indice, pas la vérité) :
1. au moins deux parties d'au moins 10 % de l'aire : « Plusieurs plots » ;
2. une cour (trou ≥ 20 m² et ≥ 3 % de l'aire pleine) : « Cour fermée / îlot » ;
3. contour lisse (≥ 10 sommets simplifiés, 70 % des coudes < 35°, au plus 4 angles vifs ≥ 60°) : convexe, sans
   angle vif et d'aire proche de l'ellipse inscrite dans le rectangle minimal → « Rond / ovale » ; concave
   (convexité < 0,9) → « Courbe / arc » ;
4. rectangularité ≥ 0,85, aucune encoche significative, ou emprise convexe (≥ 0,95, trapèze) de rectangularité
   ≥ 0,7 : selon l'élancement, « Carré » (≤ 1,2), « Rectangle
   compact » (≤ 2), « Barre » (> 2), comme la liste de la partie 5 (rectangle compact ≤ 2:1) ;
5. sinon, les encoches (rectangle minimal moins l'emprise, morceaux ≥ 4 % du rectangle) et les côtés du rectangle
   qu'elles touchent : une encoche de coin → « En L » ; une encoche au milieu d'un côté → « En U » ; deux encoches
   de coin du même côté → « En T » ; deux de coins opposés, ou des coins en escalier → « À redans / en Z » ; deux
   encoches de milieu sur des côtés opposés → « En peigne / en H », deux ou plus sur le même côté → « En peigne / en
   H » ; le reste → « Irrégulière ».
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

from shapely import Polygon, union_all
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, MultiPolygon
from shapely.geometry.base import BaseGeometry


CLOSE_M = 0.1          # fermeture : joints entre triangles et pièces jointives
CLOSE_WALLS_M = 0.5    # sans SP : franchir les murs entre surfaces intérieures
COUR_MIN_M2 = 20.0     # trou plus petit : gaine, puits de lumière, bouché
COUR_MIN_PART = 0.03   # et au moins 3 % de l'aire pleine
PART_MIN_M2 = 10.0     # partie disjointe plus petite : ignorée (édicule, défaut de tracé)
PLOT_MIN_PART = 0.10   # partie qui compte comme un plot
SIMPLIFY_M = 0.5
MAX_SOMMETS = 40
MAX_PARTIES = 6
ANGLE_RENTRANT = 20.0  # degrés : coude sous lequel un sommet concave est un défaut de tracé
NOTCH_MIN_PART = 0.04  # encoche significative : part du rectangle minimal
CONTACT_M = 0.3        # distance à un côté du rectangle minimal pour le toucher
CONTACT_MIN_M = 1.0

_SOUS_SOL = re.compile(r"(?i)^(s{1,2}\s*-?\s*\d+|\d+\s*s{1,2}|ug?\s*\d+|sous[- ]?sol.*|.*-\s*\d+\s*)$")


def sous_sol(level: str | None, rank: float | None = None) -> bool:
    """Niveau enterré : rang < 0 s'il est connu, sinon le code d'étage (formes de config.yaml > levels.order)."""
    if rank is not None:
        return rank < 0
    return bool(_SOUS_SOL.match(str(level or "").strip()))


def polygone(vertices: list[float], indices: list[int]) -> BaseGeometry | None:
    """Projection en plan d'un maillage triangulé (x, y, z à plat, triangles)."""
    tris = []
    for t in range(0, len(indices) - 2, 3):
        pts = [(vertices[3 * k], vertices[3 * k + 1]) for k in indices[t:t + 3]]
        p = Polygon(pts)
        if p.area > 1e-6:
            tris.append(p)
    if not tris:
        return None
    g = union_all(tris).buffer(0)
    return None if g.is_empty else g


def _polys(g: BaseGeometry | None) -> list[Polygon]:
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    return [p for x in getattr(g, "geoms", []) for p in _polys(x)]


def _nettoyer(g: BaseGeometry, close: float) -> BaseGeometry | None:
    g = g.buffer(close, join_style="mitre").buffer(-close, join_style="mitre")
    out = []
    for p in _polys(g):
        if p.area < PART_MIN_M2:
            continue
        trous = [h for h in p.interiors if Polygon(h).area >= COUR_MIN_M2]
        out.append(Polygon(p.exterior, trous))
    if not out:
        return None
    return out[0] if len(out) == 1 else MultiPolygon(out)


def emprise(niveaux: Iterable[tuple[str, float | None, BaseGeometry | None, str]]) -> tuple[BaseGeometry | None, dict]:
    """(emprise, informations) d'un bâtiment à partir de (niveau, rang ou None, géométrie, code SIA) : SP par niveau,
    et éventuellement les surfaces intérieures (codes SUP, SUS, SD, SI, SUT…) pour le cas sans SP."""
    sp_hs, sp_ss, autres = {}, {}, []
    for level, rank, g, code in niveaux:
        if g is None or g.is_empty:
            continue
        if code == "SP":
            (sp_ss if sous_sol(level, rank) else sp_hs).setdefault(level, []).append(g)
        else:
            autres.append(g)
    if sp_hs or sp_ss:
        par_niveau = sp_hs or sp_ss
        source = "SP hors-sol" if sp_hs else "SP des sous-sols (aucune SP hors-sol)"
        etages = {lvl: union_all(gs) for lvl, gs in par_niveau.items()}
        g = _nettoyer(union_all(list(etages.values())), CLOSE_M)
        info = {"source": source, "niveaux": sorted(etages),
                "aire_etage_max_m2": round(max(x.area for x in etages.values()), 1)}
    elif autres:
        g = _nettoyer(union_all(autres), CLOSE_WALLS_M)
        info = {"source": "surfaces intérieures (aucune SP)", "niveaux": [], "aire_etage_max_m2": None}
    else:
        return None, {}
    return g, info


def _angle_axe(rect: BaseGeometry) -> tuple[float, float, float]:
    """(angle de l'axe long en degrés, longueur, largeur) du rectangle minimal."""
    c = list(rect.exterior.coords) if isinstance(rect, Polygon) else []
    if len(c) < 4:   # rectangle dégénéré (ligne)
        return 0.0, 0.0, 0.0
    e1 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
    e2 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    l1, l2 = math.hypot(*e1), math.hypot(*e2)
    e = e1 if l1 >= l2 else e2
    ang = math.degrees(math.atan2(e[1], e[0])) % 180
    return ang, max(l1, l2), min(l1, l2)


def _coudes(ring) -> list[float]:
    """Coude signé en degrés à chaque sommet d'un anneau orienté dans le sens trigonométrique (> 0 : convexe)."""
    pts = list(ring.coords)[:-1]
    n = len(pts)
    out = []
    for k in range(n):
        a, b, c = pts[k - 1], pts[k], pts[(k + 1) % n]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        out.append(math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1])))
    return out


def _ccw(p: Polygon) -> Polygon:
    from shapely.geometry.polygon import orient
    return orient(p, 1.0)


def _simplifier(p: Polygon) -> Polygon:
    s = p.simplify(SIMPLIFY_M, preserve_topology=True)
    tol = SIMPLIFY_M
    while len(s.exterior.coords) - 1 > MAX_SOMMETS and tol < 50:
        tol *= 2
        s = p.simplify(tol, preserve_topology=True)
    return _ccw(s)


def _coords(ring, cx: float, cy: float, ang: float) -> list[list[float]]:
    g = rotate(translate(LineString(ring.coords), -cx, -cy), -ang, origin=(0, 0))
    return [[round(x, 1) + 0.0, round(y, 1) + 0.0] for x, y in list(g.coords)[:-1]]


def _encoches(g: BaseGeometry, rect: Polygon) -> list[str]:
    """Position de chaque encoche significative : « coin:i,j » (deux côtés adjacents), « milieu:i » (un côté),
    « traversante » (deux côtés opposés), « autre »."""
    plein = union_all([Polygon(p.exterior) for p in _polys(g)])
    reste = rect.difference(plein).buffer(-SIMPLIFY_M, join_style="mitre").buffer(SIMPLIFY_M, join_style="mitre")
    c = list(rect.exterior.coords)
    cotes = [LineString([c[k], c[k + 1]]) for k in range(4)]
    out = []
    for n in _polys(reste):
        if n.area < NOTCH_MIN_PART * rect.area:
            continue
        touche = [k for k, s in enumerate(cotes)
                  if n.buffer(CONTACT_M).intersection(s).length >= CONTACT_MIN_M]
        if len(touche) == 2 and (touche[1] - touche[0]) % 2 == 1:
            out.append(f"coin:{touche[0]},{touche[1]}")
        elif len(touche) == 1:
            out.append(f"milieu:{touche[0]}")
        elif len(touche) == 2:
            out.append("traversante")
        else:
            out.append("autre")
    return out


def _par_encoches(enc: list[str]) -> str:
    coins = [tuple(int(x) for x in e[5:].split(",")) for e in enc if e.startswith("coin:")]
    milieux = [int(e[7:]) for e in enc if e.startswith("milieu:")]
    if len(coins) + len(milieux) != len(enc) or not enc:
        return "Irrégulière"
    if len(enc) == 1:
        return "En L" if coins else "En U"
    if not milieux:
        if len(coins) == 2:
            commun = set(coins[0]) & set(coins[1])
            if commun:
                return "En T"   # deux coins du même côté : la barre et le jambage au milieu
            return "À redans / en Z"
        return "À redans / en Z"   # trois coins ou plus : contour en escalier
    if not coins:
        if len(milieux) == 2 and (milieux[0] - milieux[1]) % 4 == 2:
            return "En peigne / en H"
        if len(set(milieux)) == 1:
            return "En peigne / en H"
    return "Irrégulière"


def estimer(g: BaseGeometry | None, d: dict | None = None) -> tuple[str | None, str]:
    """(forme de FORMES, raison courte) ; (None, raison) sans emprise."""
    if g is None or g.is_empty:
        return None, "pas d'emprise"
    d = d or _mesures(g)
    parts = _polys(g)
    total = sum(p.area for p in parts)
    plots = [p for p in parts if p.area >= PLOT_MIN_PART * total]
    if len(plots) >= 2:
        return "Plusieurs plots", f"{len(plots)} parties disjointes"
    principal = max(parts, key=lambda p: p.area)
    plein = Polygon(principal.exterior).area
    cours = [Polygon(h).area for h in principal.interiors]
    if cours and sum(cours) >= COUR_MIN_PART * plein:
        return "Cour fermée / îlot", f"cour de {round(sum(cours))} m²"
    elong, rect_, conv = d["elancement"], d["rectangularite"], d["convexite"]
    simple = _simplifier(Polygon(principal.exterior))
    coudes = _coudes(simple.exterior)
    vifs = sum(1 for a in coudes if abs(a) >= 60)
    if len(coudes) >= 10 and vifs <= 4 and sum(1 for a in coudes if abs(a) < 35) >= 0.7 * len(coudes):
        L, l = d["longueur_m"], d["largeur_m"]
        ellipse = math.pi / 4 * L * l
        if conv >= 0.95 and not vifs and ellipse and 0.9 <= principal.area / ellipse <= 1.1:
            return "Rond / ovale", "contour lisse et convexe, aire proche de l'ellipse inscrite"
        if conv < 0.9:
            return "Courbe / arc", "contour lisse et concave"
    rect = principal.minimum_rotated_rectangle
    enc = _encoches(principal, rect) if isinstance(rect, Polygon) else []
    if rect_ >= 0.85 or not enc or (conv >= 0.95 and rect_ >= 0.7):
        forme = "Carré" if elong <= 1.2 else "Rectangle compact" if elong <= 2 else "Barre"
        return forme, f"rectangularité {rect_}, élancement {elong}"
    forme = _par_encoches(enc)
    return forme, f"{len(enc)} encoche(s) dans le rectangle minimal ({', '.join(e.split(':')[0] for e in enc)})"


def _mesures(g: BaseGeometry) -> dict:
    rect = g.minimum_rotated_rectangle
    ang, L, l = _angle_axe(rect)
    hull = g.convex_hull.area
    return {"longueur_m": round(L, 1), "largeur_m": round(l, 1),
            "elancement": round(L / l, 2) if l else None,
            "rectangularite": round(g.area / rect.area, 2) if rect.area else None,
            "convexite": round(g.area / hull, 2) if hull else None, "axe_long_deg": round(ang)}


def decrire(g: BaseGeometry | None, info: dict | None = None) -> dict | None:
    """Description compacte de l'emprise, lisible par un modèle (voir le docstring du module)."""
    if g is None or g.is_empty:
        return None
    m = _mesures(g)
    parts = sorted(_polys(g), key=lambda p: -p.area)
    rect = g.minimum_rotated_rectangle
    cx, cy = rect.centroid.x, rect.centroid.y
    ang = m["axe_long_deg"]
    cours, rentrants, contours = [], 0, []
    for p in parts:
        cours += [round(Polygon(h).area, 1) for h in p.interiors]
        s = _simplifier(Polygon(p.exterior))
        rentrants += sum(1 for a in _coudes(s.exterior) if a < -ANGLE_RENTRANT)
    for p in parts[:MAX_PARTIES]:
        s = _simplifier(Polygon(p.exterior))
        c = {"aire_m2": round(p.area, 1), "contour": _coords(s.exterior, cx, cy, ang)}
        if p.interiors:
            c["cours"] = [_coords(_simplifier(Polygon(h)).exterior, cx, cy, ang) for h in p.interiors]
        contours.append(c)
    forme, raison = estimer(g, m)
    return {
        **(info or {}), "aire_m2": round(g.area, 1), **m,
        "cours": {"nombre": len(cours), "aires_m2": cours},
        "parties": len(parts), "angles_rentrants": rentrants,
        "contours": contours,
        "repere": "m, centré sur le rectangle minimal, axe long = x",
        "forme_estimee": forme, "forme_estimee_raison": raison,
    }


def emprises(niveaux: Iterable[tuple[str, str, float | None, BaseGeometry | None, str]]) -> dict[str, dict]:
    """{bâtiment: description} à partir de (bâtiment, niveau, rang, géométrie, code SIA). Un bâtiment sans
    géométrie exploitable n'apparaît pas."""
    par_bat: dict[str, list] = {}
    for b, level, rank, g, code in niveaux:
        par_bat.setdefault(str(b), []).append((level, rank, g, code))
    out = {}
    for b in sorted(par_bat):
        g, info = emprise(par_bat[b])
        if (d := decrire(g, info)) is not None:
            out[b] = d
    return out


INTERIEURS = ("SUP", "SUS", "SD", "SI", "SUT")


def emprises_siagen(elements) -> dict[str, dict]:
    """Emprises d'un projet `.siagen.json` (siagen.Element) : SP des totaux de niveau, sinon surfaces intérieures.
    Le code SIA est lu dans les propriétés (« Catégorie SIA »), sinon à la fin du nom (« …_SP »)."""
    items = []
    for e in elements:
        code = _code(e)
        if code != "SP" and code not in INTERIEURS:
            continue
        geoms = [p for m in e.meshes if (p := polygone(m.vertices, m.indices)) is not None]
        if geoms:
            items.append((e.building, e.level, None, union_all(geoms), code))
    return emprises(items)


def _code(e) -> str | None:
    for k, v in (e.props or {}).items():
        if "cat" in k.lower() and "sia" in k.lower() and isinstance(v, str) and v.strip():
            return v.strip().upper()
    tail = e.name.rsplit("_", 1)[-1].strip().upper()
    return tail or None

