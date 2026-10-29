"""Toitures en pente (décision du 29.10.2026, Myonaz 2 : toiture à deux pans de 32°).

La SIA 416 mesure les surfaces de plancher en projection horizontale (§0.4), mais une toiture est une surface
d'enveloppe : à deux pans, elle est plus grande que son emprise (Myonaz 2 : +18 %). Le module lit les toitures de
la maquette (IfcRoof, IfcSlab de type ROOF), ou plutôt leurs faces :

- **dessus** (normale vers le haut) : la couverture. `top_z` donne l'altitude de la plus haute en un point ; la SPT
  y est drapée pour la vue 3D ;
- **dessous** (normale vers le bas) : la sous-face. `under_z` donne l'altitude de la plus haute en un point (un
  auvent plus bas ne compte pas) ; la façade du dernier niveau monte jusque-là, plus bas aux rives (murets), en
  pointe dans les pignons ;
- **surface développée** d'une emprise : chaque morceau de toiture la compte au rapport de ses faces de dessus à
  leur projection, indépendant du nombre de couches (caisson, isolant, tuiles). Le plus haut l'emporte là où deux
  se recouvrent ; hors de toute toiture, l'emprise compte à plat.

Les pannes et chevrons (morceaux de moins de `ROOF_PART_M2` en plan) n'en font pas partie.

**Fenêtres de toit** : une fenêtre est d'abord une boîte, dont la grande face donne l'orientation (axe propre du
maillage le plus chargé en aire) et l'aire (silhouette vue selon cet axe : largeur × hauteur, quelle que soit la
pente). Inclinée de plus de `ROOF_WINDOW_DEG` sur la verticale, c'est une fenêtre de toit (velux) : elle perce la
toiture, pas la façade.
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
SLOPED_NZ = 0.985       # sous-face plus horizontale (pente de moins de 10°) : toit plat, pas de pignon
ROOF_WINDOW_REACH_M = 2.5   # fenêtre de toit : à moins de cette hauteur sous la couverture


def _triangles(mesh: Mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(triangles n×3×3, aires, normales unitaires) d'un maillage."""
    v = np.asarray(mesh.vertices, float).reshape(-1, 3)
    t = v[np.asarray(mesh.indices, np.int64).reshape(-1, 3)]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = 0.5 * np.linalg.norm(n, axis=1)
    ok = a > 1e-9
    return t[ok], a[ok], n[ok] / (2 * a[ok, None])


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
        tops, unders, sloped, self.parts = [], [], [], []
        for p in placed:
            t, a, n = _triangles(p.item.mesh)
            up, down = n[:, 2] > FACE_NZ, n[:, 2] < -FACE_NZ
            if not up.any():
                continue
            tops.append(t[up])
            unders.append(t[down])
            sloped.append(t[down & (n[:, 2] > -SLOPED_NZ)])
            self.parts.append(Part(p.shape, float(a[up].sum() / (a[up] * n[up, 2]).sum()), float(t[:, :, 2].max())))
        self.parts.sort(key=lambda r: -r.z_max)
        self._top = np.concatenate(tops) if tops else np.zeros((0, 3, 3))
        self._under = np.concatenate(unders) if unders else np.zeros((0, 3, 3))
        self._sloped = np.concatenate(sloped) if sloped else np.zeros((0, 3, 3))

    def __bool__(self) -> bool:
        return bool(self.parts)

    @staticmethod
    def _z(tri: np.ndarray, pts: np.ndarray, pick) -> np.ndarray:
        """Altitude de la face retenue (`pick` : np.fmax ou np.fmin) sous chaque point ; NaN hors des faces."""
        out = np.full(len(pts), np.nan)
        if not len(tri):
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

    def top_z(self, pts) -> np.ndarray:
        return self._z(self._top, np.asarray(pts, float).reshape(-1, 2), np.fmax)

    def under_z(self, pts, sloped: bool = False) -> np.ndarray:
        """Sous-face la plus haute en chaque point ; `sloped` : seulement les sous-faces en pente (pignons)."""
        return self._z(self._sloped if sloped else self._under, np.asarray(pts, float).reshape(-1, 2), np.fmax)

    def developed(self, g: BaseGeometry) -> float:
        """Surface développée d'une emprise mesurée sur les toitures (à plat hors toiture)."""
        rest, area = g, 0.0
        for r in self.parts:
            if rest.is_empty:
                break
            part = rest.intersection(r.shape)
            area += part.area * r.ratio
            rest = rest.difference(r.shape)
        return area + rest.area

    def drape(self, g: BaseGeometry, z_default: float) -> Mesh | None:
        """Emprise triangulée par mailles de `DRAPE_CELL_M`, posée sur la couverture (à `z_default` hors toiture)."""
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
        z = self.top_z(xy)
        z = np.where(np.isnan(z), z_default, z)
        v = np.column_stack([xy, z]).ravel().tolist()
        return Mesh(v, list(range(len(xy))))


def window_panel(mesh: Mesh) -> tuple[float, float, list] | None:
    """(inclinaison sur la verticale en degrés, aire vue de face, quadrilatère de la vitre) d'une fenêtre."""
    t, a, n = _triangles(mesh)
    if not len(a):
        return None
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
