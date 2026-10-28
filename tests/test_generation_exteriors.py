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
    # SRV : vitrages extérieurs ; la porte de façade (pleine) est une réservation sans vitrage
    assert n00.envelope == {"GrossArea": 180.0, "NetArea": 175.0, "ReservationsArea": 5.0, "Perimeter": 60.0,
                            "GrossHeight": 3.0, "SRV": 3.0}


def test_interior_glazing_and_glazed_doors():
    """IsExternal de la maquette : une fenêtre intérieure près du contour n'est pas de la façade ; une porte vitrée
    de façade est un vitrage."""
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 20, 10),
                openings=[("w1", "IfcWindow", box(5, -0.1, 7, 0.1), 1.5), ("w2", "IfcWindow", box(12, 0.1, 13, 0.3), 1.0),
                          ("pf", "IfcDoor", box(15, -0.1, 16, 0.1), 2.0)])
    n00.plan.elements[1].item.props = {"Pset_WindowCommon.IsExternal": False}
    n00.plan.elements[2].item.type_name = "Porte-fenêtre vitrée"
    exteriors.build([n00], {}, set(), {})
    assert n00.envelope["ReservationsArea"] == 5.0 and n00.envelope["SRV"] == 5.0


def test_dims_follow_the_minimal_rectangle():
    assert exteriors.dims(box(0, 0, 4, 10)) == {"Perimeter": 28.0, "DeltaX": 10.0, "DeltaY": 4.0}
    assert exteriors.dims(None) == {"Perimeter": 0.0, "DeltaX": 0.0, "DeltaY": 0.0}


def test_facade_and_glazing_meshes_are_vertical():
    n00 = level("N00", 10.0, 3.0, sp=box(0, 0, 20, 10), openings=[("w1", "IfcWindow", box(5, -0.1, 7, 0.1), 1.5)])
    exteriors.build([n00], {}, set(), {})
    f, g = n00.facade, n00.glazing
    # façade percée de la fenêtre : aire du maillage = brut − réservations, sommets de 10 à 13 m (et la baie)
    v, i = f.vertices, f.indices
    area = 0.0
    for t in range(0, len(i), 3):
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = (v[3 * i[t + k]: 3 * i[t + k] + 3] for k in range(3))
        ux, uy, uz, wx, wy, wz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
        area += ((uy * wz - uz * wy) ** 2 + (uz * wx - ux * wz) ** 2 + (ux * wy - uy * wx) ** 2) ** 0.5 / 2
    assert area == pytest.approx(180.0 - 3.0) and {10.0, 13.0} <= set(v[2::3]) <= {10.0, 11.5, 13.0}
    assert len(g.indices) == 6 and set(g.vertices[2::3]) == {10.0, 11.5}


def test_stair_inside_a_landing_becomes_its_own_cage():
    """Myonaz : palier « PAL » de 17,6 m² dont l'escalier occupe 8,2 m² -> une cage Escalier et un palier."""
    lv = level("N01", 0.0, 3.0)
    pal = plans.Placed(Item("pal", "IfcSpace", "PAL", "A", "N01", long_name="Palier"), box(0, 0, 6, 3))
    lv.rooms.append(interiors.Room(pal, classify.Decision("pal", "piece", "SD", "CirculationH"), 18.0))
    lv.plan.elements.append(plans.Placed(Item("st", "IfcStair", "Escalier", "A", "N01"), box(0, 0, 3, 3)))
    assert interiors.split_stairs(lv) == 1
    (rest, cage) = lv.rooms
    assert (rest.decision.type, cage.decision.type) == ("CirculationH", "Escalier")
    assert rest.area == pytest.approx(9.0) and cage.area == pytest.approx(9.0)   # aire déclarée au prorata
    small = level("N02", 3.0, 3.0)
    small.rooms.append(interiors.Room(plans.Placed(pal.item, box(0, 0, 3.5, 3)), classify.Decision("pal", "piece", "SD", "CirculationH"), 10.5))
    small.plan.elements.append(plans.Placed(Item("st", "IfcStair", "Escalier", "A", "N02"), box(0, 0, 3, 3)))
    interiors.split_stairs(small)
    assert [r.decision.type for r in small.rooms] == ["Escalier"]               # palier résiduel : tout en cage


def test_level_altitude_is_the_floor_of_most_rooms():
    """Myonaz 2 S01 : niveau IFC à 612,04, pièces à 611,40, un escalier qui descend à 610,20 : tout à 611,40."""
    s01, n00 = level("S01", 612.04, 2.96), level("N00", 615.0, 2.81)
    for gid, shape, z in (("cave", box(0, 0, 10, 10), 611.40), ("esc", box(10, 0, 12, 3), 610.20)):
        s01.rooms.append(interiors.Room(plans.Placed(Item(gid, "IfcSpace", gid, "A", "S01", z_min=z), shape),
                                        classify.Decision(gid, "piece", "SUS"), 1.0))
    n00.rooms.append(interiors.Room(plans.Placed(Item("ch", "IfcSpace", "ch", "A", "N00", z_min=615.0), box(0, 0, 9, 9)),
                                    classify.Decision("ch", "piece", "SUP"), 1.0))
    for lv in (s01, n00):
        lv.floor_z = interiors.floor_z(lv)
    interiors.heights([s01, n00])
    assert s01.z == 611.40 and n00.z == 615.0 and s01.height == pytest.approx(3.6)
    assert level("N01", 618.0, 3.0).z == 618.0          # sans pièce : altitude du niveau IFC
