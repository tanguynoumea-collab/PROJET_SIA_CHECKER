"""Moteur de génération, phase 22 : extérieurs, toitures, façade et vitrages."""

import pytest
from shapely.geometry import box

from sia_check import config
from sia_check.generation import classify, exteriors, interiors, plans
from sia_check.generation.ingest import Item, Storey
from conftest import ROOT


@pytest.fixture(scope="module")
def k():
    return classify.Classifier(config.load(ROOT / "config.yaml").generation)


def space(gid, name=None, long_name=None, lot=None, **props):
    return Item(gid, "IfcSpace", name, "A", "N01", long_name=long_name, lot=lot, props=props)


@pytest.mark.parametrize("item, code, typ", [
    (space("1", "LOG", "Loggia", lot="1A.01.02"), "SEU", "Balcon"),
    (space("2", "5", "BAL", lot="1erEtage/5", **{"Pset_SpaceCommon.Category": "416-SN-Surface externe nette"}), "SEU", "Balcon"),
    (space("3", "TER", "Jardin", lot="1A.00.01"), "SEU", "Terrasse"),
    (space("4", "C", "Coursive"), "SED", "CirculationExt"),
    (space("5", "X", "Balcon", **{"Données.SIA416": "SED"}), "SED", "CirculationExt"),   # la propriété l'emporte
    (space("6", "LOG", "Surface externe de plancher", **{"Pset_SpaceCommon.Category": "Surface externe de plancher"}), "SEP", None),
    (space("7", "LUP", "LUP", **{"Pset_SpaceCommon.Category": "416-SBP-Surface de plancher externe"}), "SEP", None),
])
def test_exterior_classification(k, item, code, typ):
    d = k.decide(item, False)
    assert (d.nature, d.code, d.type) == ("exterieur", code, typ)


def level(name, z, height, sp=None, exts=(), openings=()):
    st = Storey(name, name, "A", z, height)
    plan = plans.Plan(st)
    lv = interiors.Level(plan, sp=sp)
    for gid, shape, code in exts:
        plan.spaces.append(plans.Placed(space(gid), shape))
    for gid, cls, shape, h in openings:
        plan.elements.append(plans.Placed(Item(gid, cls, gid, "A", name, z_min=z, z_max=z + h), shape))
    return lv


def test_roofs_terraces_and_slab_over_basement():
    s01 = level("S01", -3.0, 3.0, sp=box(0, 0, 30, 20))
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 20, 10))
    n01 = level("N01", 3.0, 3.0, sp=box(0, 0, 10, 10), exts=[("t", box(10, 0, 14, 10), "SEU")])   # attique + terrasse
    levels = [s01, n00, n01]
    levels += exteriors.roof_levels(levels)
    assert [lv.plan.storey.name for lv in levels][-1] == "Toiture" and levels[-1].plan.storey.elevation == 6.0
    decisions = {"t": classify.Decision("t", "exterieur", "SEU", "Terrasse")}
    exteriors.build(levels, decisions, {"S01"}, {"sp": {"area_source": "plan"}})
    # dalle sur sous-sol (600 − 200 m²) : abords, ni toiture ni SEP (MDP La Bâtie)
    assert n00.spt is None and n00.sep is None and n00.slab.area == pytest.approx(400.0)
    # toiture de l'étage sous l'attique, moins la terrasse dessinée : 200 − 100 − 40
    assert n01.spt.area == pytest.approx(60.0) and n01.sep.area == pytest.approx(100.0)
    assert levels[-1].spt.area == pytest.approx(100.0)                       # toiture de l'attique
    assert levels[-1].envelope == {"GrossArea": 0.0, "NetArea": 0.0, "ReservationsArea": 0.0, "Perimeter": 0.0,
                                   "GrossHeight": 3.0, "SRV": 0.0}


def test_facade_and_glazing():
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 20, 10),
                openings=[("w1", "IfcWindow", box(5, -0.1, 7, 0.1), 1.5),     # en façade : 2 × 1,5
                          ("d1", "IfcDoor", box(10, 9.9, 11, 10.1), 2.0),      # en façade : 1 × 2
                          ("d2", "IfcDoor", box(10, 5, 11, 5.2), 2.0)])        # porte intérieure : ignorée
    exteriors.build([n00], {}, set(), {})
    assert n00.envelope == {"GrossArea": 180.0, "NetArea": 175.0, "ReservationsArea": 5.0, "Perimeter": 60.0,
                            "GrossHeight": 3.0, "SRV": 5.0}


def test_dims_follow_the_minimal_rectangle():
    assert exteriors.dims(box(0, 0, 4, 10)) == {"Perimeter": 28.0, "DeltaX": 10.0, "DeltaY": 4.0}
    assert exteriors.dims(None) == {"Perimeter": 0.0, "DeltaX": 0.0, "DeltaY": 0.0}


def test_facade_and_glazing_meshes_are_vertical():
    n00 = level("N00", 10.0, 3.0, sp=box(0, 0, 20, 10), openings=[("w1", "IfcWindow", box(5, -0.1, 7, 0.1), 1.5)])
    exteriors.build([n00], {}, set(), {})
    f, g = n00.facade, n00.glazing
    assert len(f.indices) == 4 * 6 and set(f.vertices[2::3]) == {10.0, 13.0}   # 4 murs, 2 triangles chacun
    assert len(g.indices) == 6 and set(g.vertices[2::3]) == {10.0, 11.5}
