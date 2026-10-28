"""Maquette architecte IFC synthétique, avec géométrie, pour le moteur de génération (V4).

Bâtiment A, deux niveaux (N00 à 0 m, N01 à 3 m, repère décalé de 400 m comme une maquette géoréférencée) :

    N00   logement 1A.00.01 : séjour 5 × 4 m, chambre 3 × 4 m ; couloir commun 8 × 1,5 m (1A.99.00) ;
          un mur de façade, une porte, une dalle 8 × 5,5 m
    N01   chambre 4 × 4 m, sans numéro de pièce ; local hors structure spatiale (rattaché par l'altitude)

Les pièces sont agrégées à leur niveau, comme dans les exports Revit. Quantités déclarées : le séjour annonce
20 m² (juste), la chambre du N00 annonce 10 m² au lieu de 12 (G6).
"""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api as api
import numpy as np

Z0 = 400.0


def _matrix(x=0.0, y=0.0, z=0.0):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def _box(f, body, cls, name, storey, x, y, w, d, h, z=None, aggregate=False, props=None, area=None, **attrs):
    e = api.run("root.create_entity", f, ifc_class=cls, name=name)
    for k, v in attrs.items():
        setattr(e, k, v)
    if storey is not None:
        if aggregate:
            api.run("aggregate.assign_object", f, products=[e], relating_object=storey)
        else:
            api.run("spatial.assign_container", f, products=[e], relating_structure=storey)
    rep = api.run("geometry.add_slab_representation", f, context=body, depth=h,
                  polyline=[(0, 0), (w, 0), (w, d), (0, d)])
    api.run("geometry.assign_representation", f, product=e, representation=rep)
    base = z if z is not None else (storey_z[storey.Name] if storey is not None else 0.0)
    api.run("geometry.edit_object_placement", f, product=e, matrix=_matrix(x, y, base))
    if props:
        for pset, values in props.items():
            ps = api.run("pset.add_pset", f, product=e, name=pset)
            api.run("pset.edit_pset", f, pset=ps, properties=values)
    if area is not None:
        q = api.run("pset.add_qto", f, product=e, name="Qto_SpaceBaseQuantities")
        api.run("pset.edit_qto", f, qto=q, properties={"NetFloorArea": area})
    return e


storey_z = {"N00": Z0, "N01": Z0 + 3.0}


def build(path: Path) -> Path:
    f = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", f, ifc_class="IfcProject", name="Synth")
    api.run("unit.assign_unit", f)
    model = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body",
                   target_view="MODEL_VIEW", parent=model)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    bld = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="A")
    api.run("aggregate.assign_object", f, products=[site], relating_object=project)
    api.run("aggregate.assign_object", f, products=[bld], relating_object=site)
    st = {}
    for name, z in storey_z.items():
        s = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name=name)
        api.run("aggregate.assign_object", f, products=[s], relating_object=bld)
        api.run("geometry.edit_object_placement", f, product=s, matrix=_matrix(z=z))
        s.Elevation = z
        st[name] = s

    def room(name, long_name, storey, x, y, w, d, numero=None, area=None):
        props = {"Pset_HRS": {"NumeroPiece": numero}} if numero else None
        return _box(f, body, "IfcSpace", name, st[storey], x, y, w, d, 2.6, aggregate=True, props=props, area=area,
                    LongName=long_name)

    room("SEJ", "Séjour", "N00", 0, 0, 5, 4, "1A.00.01.01", area=20.0)
    room("CHS", "Chambre", "N00", 5, 0, 3, 4, "1A.00.01.02", area=10.0)
    room("DEG", "Couloir", "N00", 0, 4, 8, 1.5, "1A.99.00.01")
    room("CHS", "Chambre", "N01", 0, 0, 4, 4)
    _box(f, body, "IfcSpace", "LT", None, 4, 0, 2, 2, 2.6, z=Z0 + 3.0, LongName="Local technique")
    _box(f, body, "IfcWall", "Façade", st["N00"], 0, -0.2, 8, 0.2, 3.0)
    _box(f, body, "IfcDoor", "Porte", st["N00"], 2, -0.2, 0.9, 0.2, 2.1)
    _box(f, body, "IfcSlab", "Dalle", st["N00"], 0, 0, 8, 5.5, 0.25, z=Z0 - 0.25)
    f.write(str(path))
    return path
