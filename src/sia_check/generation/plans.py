"""Plans par niveau : contours 2D des espaces et des éléments de la maquette (V4_PLAN §3.1, phase 20).

Chaque objet est projeté en plan (SIA 416 §0.4 : surfaces en projection horizontale) : union de ses triangles
non verticaux, nettoyée par `buffer(0)`. Les faces verticales (murs d'un espace, tranches d'une dalle) ne
comptent pas. Le plan d'un niveau rassemble ses espaces et ses éléments, avec leurs contours ; les étapes
suivantes (SP, extérieurs, logements) ne travaillent que sur ces plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from ..geom import Mesh
from .ingest import Item, Model, Storey

MIN_TRIANGLE_M2 = 1e-6   # triangles plus petits (faces verticales, dégénérés) : ignorés
MIN_AREA_M2 = 0.01       # contour plus petit : objet sans emprise en plan


def footprint(mesh: Mesh | None) -> BaseGeometry | None:
    """Projection horizontale d'un maillage, None si l'objet n'a pas d'emprise en plan."""
    if mesh is None or not mesh.indices:
        return None
    v = np.asarray(mesh.vertices, dtype=float).reshape(-1, 3)[:, :2]
    tri = v[np.asarray(mesh.indices, dtype=np.int64).reshape(-1, 3)]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    area = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
    tri = tri[area > MIN_TRIANGLE_M2]
    if not len(tri):
        return None
    rings = np.concatenate([tri, tri[:, :1]], axis=1)
    g = shapely.union_all(shapely.polygons(rings)).buffer(0)
    return None if g.is_empty or g.area < MIN_AREA_M2 else g


@dataclass
class Placed:
    item: Item
    shape: BaseGeometry | None

    @property
    def area(self) -> float:
        return self.shape.area if self.shape is not None else 0.0


@dataclass
class Plan:
    storey: Storey
    spaces: list[Placed] = field(default_factory=list)
    elements: list[Placed] = field(default_factory=list)

    def of(self, *classes: str) -> list[Placed]:
        """Éléments de ces classes IFC (sous-classes comprises par le préfixe : IfcWall couvre IfcWallStandardCase)."""
        return [p for p in self.elements if p.item.ifc_class.startswith(classes)]

    def union(self, *classes: str) -> BaseGeometry | None:
        shapes = [p.shape for p in self.of(*classes) if p.shape is not None]
        return shapely.union_all(shapes) if shapes else None


def build(model: Model) -> list[Plan]:
    """Un plan par niveau, dans l'ordre des bâtiments puis des altitudes ; objets sans niveau écartés."""
    plans = {s.gid: Plan(s) for s in sorted(model.storeys, key=lambda s: (model.buildings.index(s.building), s.rank))}
    for item in model.spaces + model.elements:
        plan = plans.get(item.storey)
        if plan is None:
            continue
        placed = Placed(item, footprint(item.mesh))
        (plan.spaces if item.is_space else plan.elements).append(placed)
    return list(plans.values())
