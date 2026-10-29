"""Toitures en pente (décision du 29.10.2026, Myonaz 2 : toiture à deux pans de 32°).

La SIA 416 mesure les surfaces de plancher en projection horizontale (§0.4), mais une toiture est une surface
d'enveloppe : à deux pans, elle est plus grande que son emprise (Myonaz 2 : +18 %). Le module lit les toitures de
la maquette (IfcRoof, IfcSlab de type ROOF), ou plutôt leurs faces :

- **dessus** (normale vers le haut) : la couverture. `top_z` donne l'altitude de la plus haute en un point ; la SPT
  y est drapée pour la vue 3D ;
- la **façade** du dernier niveau monte jusqu'à la couverture en pente (`top_z(..., sloped=True)`), la même surface
  que la SPT : plus bas aux rives (murets), en pointe dans les pignons ; une toiture plate ne la touche pas ;
- **surface développée** d'une emprise : chaque morceau de toiture la compte au rapport de ses faces de dessus à
  leur projection, indépendant du nombre de couches (caisson, isolant, tuiles). Le plus haut l'emporte là où deux
  se recouvrent ; hors de toute toiture, l'emprise compte à plat.

Les pannes et chevrons (morceaux de moins de `ROOF_PART_M2` en plan) n'en font pas partie.

**Pans principaux** (retour du 29.10.2026 : SPT et façades « biscornues ») : la SPT et le haut de la façade ne
suivent que les pans de la toiture, les orientations de faces qui portent au moins `MAIN_SHARE` de son aire. Les
lucarnes, souches et faîtières n'y sont pas : là où un pan est percé (lucarne) ou s'arrête (rive), le plan du pan le
plus proche est prolongé. La surface développée, elle, compte toutes les faces.

**Fenêtres de toit** : une fenêtre est d'abord une boîte, dont la grande face donne l'orientation (axe propre du
maillage le plus chargé en aire) et l'aire (silhouette vue selon cet axe : largeur × hauteur, quelle que soit la
pente). Inclinée de plus de `ROOF_WINDOW_DEG` sur la verticale, c'est une fenêtre de toit (velux) : elle perce la
toiture, pas la façade. Une fenêtre de toit que la maquette entoure de son ébrasement (joues verticales jusqu'au
plafond, Myonaz 2 « Luc ») a plus d'aire verticale que vitrée : sous la toiture, une fenêtre dont des faces sont
parallèles au pan (à `PAN_DEG` près, au moins `ROOF_GLASS_M2` et `ROOF_GLASS_SHARE` de sa silhouette verticale)
est une fenêtre de toit, sa vitre est ces faces. Une porte-fenêtre de pignon dont le linteau suit la pente n'en est pas
une : ce chant ne fait qu'une petite part de sa silhouette.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from ..geom import Mesh
from .plans import Placed

ROOF_CLASSES = ("IfcRoof",)
ROOF_PART_M2 = 5.0      # morceau de toiture plus petit en plan (panne, chevron, faîtière) : ignoré
FACE_NZ = 0.2           # composante verticale de la normale au-delà de laquelle une face est dessus ou dessous
ROOF_WINDOW_DEG = 15.0  # inclinaison sur la verticale au-delà de laquelle une fenêtre est une fenêtre de toit
DRAPE_CELL_M = 1.0      # maille du drapé de la SPT sur la couverture
SLOPED_NZ = 0.985       # pan plus horizontal (pente de moins de 10°) : toit plat, la façade ne le suit pas
ROOF_WINDOW_REACH_M = 2.5   # fenêtre de toit : à moins de cette hauteur sous la couverture
ROOF_DROP_M = 3.0       # toiture plus basse que le niveau de toiture (marquise du rez, auvent) : pas la sienne
FLAT_RATIO = 1.01       # surface développée à moins de 1 % de l'emprise : toiture plate, SPT dessinée à plat
MAIN_SHARE = 0.10       # orientation de faces portant moins de cette part de l'aire : lucarne, souche, pas un pan
PAN_DEG = 10.0          # faces d'un même pan : normales à moins de cet angle
EXTEND_M = 3.0          # plan d'un pan prolongé jusqu'à cette distance (lucarne, rive) ; au-delà, pas de toiture
ROOF_GLASS_M2 = 0.3     # vitre parallèle au pan plus petite : cadre ou tablette, pas une fenêtre de toit
ROOF_GLASS_SHARE = 0.3  # vitre parallèle au pan plus petite par rapport à la silhouette verticale : linteau en pente
LAYER_M = 0.8           # couches d'un même pan (tuiles, isolant, chevrons) : à moins de cette distance l'une de l'autre


def _triangles(mesh: Mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(triangles n×3×3, aires, normales unitaires) d'un maillage."""
    v = np.asarray(mesh.vertices, float).reshape(-1, 3)
    t = v[np.asarray(mesh.indices, np.int64).reshape(-1, 3)]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = 0.5 * np.linalg.norm(n, axis=1)
    ok = a > 1e-9
    return t[ok], a[ok], n[ok] / (2 * a[ok, None])


def _main(tri: np.ndarray, area: np.ndarray, normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(faces des pans principaux, groupe d'orientation de chaque face) : faces regroupées par orientation (normales à
    moins de `PAN_DEG`), on garde les groupes qui portent au moins `MAIN_SHARE` de l'aire."""
    keep = np.zeros(len(tri), dtype=bool)
    group = np.full(len(tri), -1)
    if not len(tri):
        return keep, group
    cos = np.cos(np.radians(PAN_DEG))
    for k in np.argsort(-area):   # le plus grand triangle ouvre son groupe
        if group[k] >= 0:
            continue
        group[(group < 0) & (normal @ normal[k] >= cos)] = k
    for g in np.unique(group):
        if area[group == g].sum() >= MAIN_SHARE * area.sum():
            keep |= group == g
    return keep, group


def _flatten(tri: np.ndarray, area: np.ndarray, normal: np.ndarray, group: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Chaque pan ramené à un plan : sa normale moyenne, à la hauteur de sa couche la plus haute (la couverture ;
    deux couches à moins de `LAYER_M` sont le même pan, au-delà deux pans : ailes de hauteurs différentes). Les
    sommets sont reposés sur ce plan : plus de marches entre tuiles, isolant et chevrons."""
    tri, normal = tri.copy(), normal.copy()
    for g in np.unique(group):
        m = np.flatnonzero(group == g)
        n = (normal[m] * area[m, None]).sum(axis=0)
        n /= np.linalg.norm(n)
        d = tri[m].mean(axis=1) @ n          # distance de chaque face au plan, le long de la normale
        order = np.argsort(d)
        layer = np.concatenate([[0], np.cumsum(np.diff(d[order]) > LAYER_M)])
        for k in np.unique(layer):
            faces = m[order[layer == k]]
            top = d[order[layer == k]].max()
            xy = tri[faces, :, :2]
            tri[faces, :, 2] = (top - n[0] * xy[..., 0] - n[1] * xy[..., 1]) / n[2]
            normal[faces] = n
    return tri, normal


def _plane_z(tri: np.ndarray, normal: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Altitude du plan de chaque triangle à l'aplomb du point correspondant."""
    p0 = tri[:, 0]
    return p0[:, 2] - (normal[:, 0] * (pts[:, 0] - p0[:, 0]) + normal[:, 1] * (pts[:, 1] - p0[:, 1])) / normal[:, 2]


def _distance(tri: np.ndarray, pt: np.ndarray) -> np.ndarray:
    """Distance en plan d'un point à chaque triangle (à ses côtés ; le point est hors des triangles)."""
    best = np.full(len(tri), np.inf)
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = tri[:, i, :2], tri[:, j, :2]
        ab = b - a
        t = np.clip(((pt - a) * ab).sum(axis=1) / np.maximum((ab * ab).sum(axis=1), 1e-12), 0.0, 1.0)
        best = np.minimum(best, np.linalg.norm(a + ab * t[:, None] - pt, axis=1))
    return best


def is_roof(p: Placed) -> bool:
    it = p.item
    return (it.ifc_class.startswith(ROOF_CLASSES) or it.ifc_class.startswith("IfcSlab") and it.predefined == "ROOF") \
        and it.mesh is not None and p.shape is not None and p.shape.area >= ROOF_PART_M2


@dataclass
class Part:
    shape: BaseGeometry   # emprise
    ratio: float          # dessus / projection du dessus
    z_max: float


class Roofs:
    """Toitures d'un bâtiment : faces de dessus et de dessous, morceaux et leur pente."""

    def __init__(self, placed: list[Placed]):
        tops, self.parts = [], []
        for p in placed:
            t, a, n = _triangles(p.item.mesh)
            up = n[:, 2] > FACE_NZ
            if not up.any():
                continue
            tops.append((t[up], a[up], n[up]))
            self.parts.append(Part(p.shape, float(a[up].sum() / (a[up] * n[up, 2]).sum()), float(t[:, :, 2].max())))
        self.parts.sort(key=lambda r: -r.z_max)

        def stack(faces):
            if not faces:
                return np.zeros((0, 3, 3)), np.zeros((0, 3))
            t, a, n = (np.concatenate(x) for x in zip(*faces))
            keep, group = _main(t, a, n)   # pans principaux du bâtiment : ni lucarnes, ni souches
            return _flatten(t[keep], a[keep], n[keep], group[keep])
        self._top, self._top_n = stack(tops)

    def normal_at(self, pt) -> np.ndarray | None:
        """Normale du pan principal sous le point, ou du plus proche (`EXTEND_M` au plus) ; None hors toiture."""
        if not len(self._top):
            return None
        p = np.asarray(pt, float)
        d = _distance(self._top, p)
        inside = Roofs._z(self._top, p.reshape(1, 2), np.fmax)
        k = int(np.argmin(d))
        if np.isnan(inside[0]) and d[k] > EXTEND_M:
            return None
        if not np.isnan(inside[0]):   # sous le point : le pan le plus haut
            z = _plane_z(self._top, self._top_n, np.repeat(p.reshape(1, 2), len(self._top), axis=0))
            z[d > 1e-6] = -np.inf
            k = int(np.argmax(z))
        return self._top_n[k]

    def __bool__(self) -> bool:
        return bool(self.parts)

    @staticmethod
    def _z(tri: np.ndarray, pts: np.ndarray, pick, normal: np.ndarray | None = None) -> np.ndarray:
        """Altitude de la face retenue (`pick` : np.fmax ou np.fmin) sous chaque point ; hors des faces, NaN, ou avec
        `normal` (normales des faces) le plan de la face la plus proche en plan, prolongé (lucarne, rive)."""
        out = np.full(len(pts), np.nan)
        if not len(tri):
            return out
        if normal is not None:
            out = Roofs._z(tri, pts, pick)
            miss = np.flatnonzero(np.isnan(out))
            for k in miss:
                d = _distance(tri, pts[k])
                near = int(np.argmin(d))
                if d[near] <= EXTEND_M:
                    out[k] = _plane_z(tri[near:near + 1], normal[near:near + 1], pts[k:k + 1])[0]
            return out
        lo, hi = tri[:, :, :2].min(axis=1), tri[:, :, :2].max(axis=1)
        for k, (x, y) in enumerate(pts):
            m = (lo[:, 0] <= x) & (x <= hi[:, 0]) & (lo[:, 1] <= y) & (y <= hi[:, 1])
            if not m.any():
                continue
            a, b, c = tri[m, 0], tri[m, 1], tri[m, 2]
            d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
            ok = np.abs(d) > 1e-12
            l1 = np.where(ok, ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / np.where(ok, d, 1), -1)
            l2 = np.where(ok, ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / np.where(ok, d, 1), -1)
            l3 = 1 - l1 - l2
            inside = ok & (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
            if inside.any():
                z = (l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2])[inside]
                out[k] = pick.reduce(z)
        return out

    def top_z(self, pts, z_min: float | None = None, extend: bool = False, sloped: bool = False) -> np.ndarray:
        """Couverture (pans principaux) la plus haute en chaque point ; `z_min` : seulement les faces qui montent
        au-dessus ; `extend` : hors des pans, le plan du pan le plus proche ; `sloped` : seulement les pans en pente
        (haut de la façade : une toiture plate ne la touche pas)."""
        keep = np.ones(len(self._top), dtype=bool) if z_min is None else self._top[:, :, 2].max(axis=1) >= z_min
        if sloped:
            keep &= self._top_n[:, 2] < SLOPED_NZ
        return self._z(self._top[keep], np.asarray(pts, float).reshape(-1, 2), np.fmax,
                       self._top_n[keep] if extend else None)

    def developed(self, g: BaseGeometry, z_min: float | None = None) -> float:
        """Surface développée d'une emprise mesurée sur les toitures (à plat hors toiture) ; `z_min` : seulement les
        toitures qui montent au-dessus (pas la marquise du rez sous la toiture du dernier étage)."""
        rest, area = g, 0.0
        for r in self.parts:
            if rest.is_empty:
                break
            if z_min is not None and r.z_max < z_min:
                continue
            part = rest.intersection(r.shape)
            area += part.area * r.ratio
            rest = rest.difference(r.shape)
        return area + rest.area

    def drape(self, g: BaseGeometry, z_level: float) -> Mesh | None:
        """Emprise triangulée par mailles de `DRAPE_CELL_M`, posée sur la couverture du niveau de toiture `z_level`
        (les toitures plus basses de `ROOF_DROP_M` n'en sont pas), sur ses pans principaux : une lucarne, une rive
        prolongent le pan le plus proche, la surface reste continue, sans dents ni bosses. None : toiture plate
        (SPT dessinée à plat)."""
        z_min = z_level - ROOF_DROP_M
        if self.developed(g, z_min) < FLAT_RATIO * g.area:
            return None
        x0, y0, x1, y1 = g.bounds
        cells = [shapely.box(x, y, x + DRAPE_CELL_M, y + DRAPE_CELL_M)
                 for x in np.arange(x0, x1, DRAPE_CELL_M) for y in np.arange(y0, y1, DRAPE_CELL_M)]
        tris = []
        for c in cells:
            piece = g.intersection(c)
            if piece.is_empty or piece.area <= 1e-9:
                continue
            for t in getattr(shapely.constrained_delaunay_triangles(piece), "geoms", []):
                if t.area > 1e-9 and piece.covers(t.representative_point()):
                    tris.append(list(t.exterior.coords)[:3])
        if not tris:
            return None
        xy = np.asarray(tris, float).reshape(-1, 2)
        z = self.top_z(xy, z_min, extend=True)
        if np.isnan(z).all():
            return None
        z = np.where(np.isnan(z), z_level, z)   # loin de toute toiture (terrasse) : à plat, au niveau
        v = np.column_stack([xy, z]).ravel().tolist()
        return Mesh(v, list(range(len(xy))))


def window_panel(mesh: Mesh, pan: np.ndarray | None = None) -> tuple[float, float, list] | None:
    """(inclinaison sur la verticale en degrés, aire vue de face, quadrilatère de la vitre) d'une fenêtre. `pan` :
    normale du pan de toiture ; la vitre est alors faite des faces parallèles au pan (fenêtre de toit dans son
    ébrasement), None s'il n'y en a pas assez."""
    t, a, n = _triangles(mesh)
    if not len(a):
        return None
    if pan is not None:
        glass = np.abs(n @ pan) >= np.cos(np.radians(PAN_DEG))
        if 0.5 * a[glass].sum() < ROOF_GLASS_M2:
            return None
        t, a, n, d = t[glass], a[glass], n[glass], np.asarray(pan, float)
    else:
        w, vec = np.linalg.eigh((n * a[:, None]).T @ n)
        d = vec[:, -1]
    tilt = float(np.degrees(np.arcsin(min(abs(d[2]), 1.0))))
    area = float(0.5 * np.sum(a * np.abs(n @ d)))
    # repère de la vitre : u horizontal dans son plan, v le long de la pente
    u = np.cross([0.0, 0.0, 1.0], d)
    u = u / np.linalg.norm(u) if np.linalg.norm(u) > 1e-9 else np.array([1.0, 0.0, 0.0])
    v = np.cross(d, u)
    pts = t.reshape(-1, 3)
    c = pts.mean(axis=0)
    pu, pv = (pts - c) @ u, (pts - c) @ v
    quad = [c + u * x + v * y for x, y in ((pu.min(), pv.min()), (pu.max(), pv.min()), (pu.max(), pv.max()), (pu.min(), pv.max()))]
    return tilt, area, [q.tolist() for q in quad]


def quads_mesh(quads: list[list]) -> Mesh | None:
    v, i = [], []
    for q in quads:
        k = len(v) // 3
        for p in q:
            v += p
        i += [k, k + 1, k + 2, k, k + 2, k + 3]
    return Mesh(v, i) if i else None
