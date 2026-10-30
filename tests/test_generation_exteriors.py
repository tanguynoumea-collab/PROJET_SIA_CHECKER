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
                            "GrossHeight": 3.0, "StoreyHeight": 3.0, "SRV": 3.0}


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


def test_bare_openings_are_deducted_from_the_facade_once():
    """CGA L04 : baie sans menuiserie (IfcOpeningElement) déduite de la SFN, hors SRV ; la même baie percée dans le
    bardage et dans le mur ne compte qu'une fois ; deux fenêtres d'angle, perpendiculaires, comptent deux fois."""
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 20, 10),
                openings=[("v1", "IfcOpeningElement", box(5, -0.3, 8, -0.1), 2.0),   # bardage
                          ("v2", "IfcOpeningElement", box(5, -0.1, 8, 0.1), 2.0),    # mur derrière : la même baie
                          ("w1", "IfcWindow", box(18.5, -0.1, 19.9, 0.1), 1.0),      # angle, façade sud
                          ("w2", "IfcWindow", box(19.9, 0.1, 20.1, 1.5), 1.0)])      # angle, façade est
    exteriors.build([n00], {}, set(), {})
    env = n00.envelope
    assert env["ReservationsArea"] == pytest.approx(3 * 2.0 + 1.4 + 1.4)
    assert env["SRV"] == pytest.approx(2.8) and env["NetArea"] == pytest.approx(180.0 - 8.8)


def test_columns_are_construction_and_railings_are_not_openings():
    """CGA L04 : poteaux dans une place de parc retirés de la surface nette ; garde-corps modélisés en porte ignorés."""
    lv = level("S01", 0.0, 3.0, sp=box(0, 0, 20, 10),
               openings=[("gc", "IfcDoor", box(5, -0.1, 7, 0.1), 1.0)])
    lv.plan.elements[0].item.type_name = "Type de garde-corps"
    park = plans.Placed(Item("p", "IfcSpace", "SUS_VOI", "A", "S01"), box(0, 0, 20, 10))
    lv.rooms.append(interiors.Room(park, classify.Decision("p", "piece", "SUS", "Parking"), 200.0))
    for k in range(3):
        lv.plan.elements.append(plans.Placed(Item(f"c{k}", "IfcColumn", "Poteau", "A", "S01"), box(5 * k + 2, 4, 5 * k + 2.3, 4.3)))
    assert interiors.without_columns(lv) == pytest.approx(0.27)
    assert lv.rooms[0].area == pytest.approx(200.0 - 0.27) and lv.rooms[0].placed.shape.area == pytest.approx(200.0 - 0.27)
    exteriors.build([lv], {}, set(), {})
    assert lv.envelope["ReservationsArea"] == 0.0


def _mesh(tris):
    """Maillage de triangles donnés sommet par sommet."""
    from sia_check.geom import Mesh
    v = [c for t in tris for p in t for c in p]
    return Mesh(v, list(range(len(v) // 3)))


def _gable_roof(eave=1.0, slope_deg=30.0, thickness=0.2):
    """Toiture à deux pans sur 10 × 20 m (faîte en x = 5), sous-face à `eave` aux rives : dessous et dessus."""
    import math
    ridge = eave + 5 * math.tan(math.radians(slope_deg))
    tris = []
    for dz, up in ((0.0, False), (thickness, True)):
        e, r = eave + dz, ridge + dz
        for x0, x1, z0, z1 in ((0, 5, e, r), (5, 10, r, e)):
            a, b, c, d = (x0, 0, z0), (x1, 0, z1), (x1, 20, z1), (x0, 20, z0)
            tris += [(a, b, c), (a, c, d)] if up else [(a, c, b), (a, d, c)]
    return _mesh(tris), ridge


def _box(center, u, v, n, du, dv, dn):
    """Boîte (fenêtre) de demi-côtés du, dv, dn selon les axes u, v, n."""
    import numpy as np
    c, u, v, n = (np.asarray(x, float) for x in (center, u, v, n))
    p = [c + su * du * u + sv * dv * v + sn * dn * n for su in (-1, 1) for sv in (-1, 1) for sn in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return _mesh([tuple(map(tuple, (p[a], p[b], p[c_]))) for a, b, c_, d in faces for (a, b, c_) in ((a, b, c_), (a, c_, d))])


def test_pitched_roof_spt_facade_and_roof_window():
    """Myonaz 2 (29.10.2026) : SPT développée, façade sous les rampants (rives basses, pignons) ; un velux est un
    vitrage SRV à son aire vraie, pas une réservation de façade."""
    import math
    import numpy as np
    roof_mesh, ridge = _gable_roof()
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 10, 20))
    ttr = level("TTR", 3.0, None)
    roof = Item("r", "IfcRoof", "Toit", "A", "TTR", mesh=roof_mesh, z_min=1.0, z_max=ridge + 0.2)
    ttr.plan.elements.append(plans.Placed(roof, plans.footprint(roof_mesh)))
    s = math.radians(30)
    win = _box((2.5, 10, 1 + 2.5 * math.tan(s) + 0.1), (0, 1, 0), (math.cos(s), 0, math.sin(s)), (-math.sin(s), 0, math.cos(s)),
               0.5, 0.6, 0.05)
    zs = np.asarray(win.vertices).reshape(-1, 3)[:, 2]
    velux = Item("v", "IfcWindow", "Velux", "A", "TTR", mesh=win, z_min=float(zs.min()), z_max=float(zs.max()))
    ttr.plan.elements.append(plans.Placed(velux, plans.footprint(win)))
    exteriors.build([n00, ttr], {}, set(), {})
    assert ttr.roof_parts[0][1] == pytest.approx(200 / math.cos(s), rel=1e-3)          # 230,9 m² et non 200
    # la façade monte jusqu'à la couverture (dessus du pan, 0,20 au-dessus de la sous-face) : façade et SPT se rejoignent
    eave = 1.0 + 0.2
    gable = 10 * eave + 0.5 * 10 * (ridge - 1.0)
    assert n00.envelope["GrossArea"] == pytest.approx(2 * 20 * eave + 2 * gable, rel=1e-3)
    assert n00.envelope["ReservationsArea"] == 0.0 and n00.envelope["SRV"] == pytest.approx(1.2, rel=1e-3)
    # contrôle E3 : la SFN porte la hauteur moyenne de la façade, l'étage garde la sienne
    assert n00.envelope["GrossHeight"] * 60 == pytest.approx(n00.envelope["GrossArea"], abs=0.1)
    assert n00.envelope["StoreyHeight"] == 3.0
    # la SEP compte la toiture à son aire développée (la Fiabilisation l'en retire)
    from sia_check.generation import assemble
    seps = [e for e in assemble.elements([n00, ttr]) if e.name == "SEP" and e.kind == "node"]
    assert seps[-1].props["Area"] == pytest.approx(200 / math.cos(s), rel=1e-3)


def test_flat_roof_ignores_a_canopy_below():
    """La Bâtie (29.10.2026) : sous une toiture plate, la marquise du rez n'est pas la toiture du dernier étage ; la
    SPT reste à plat, sans « piliers » qui descendent jusqu'à elle."""
    flat = _mesh([((0, 0, 6.2), (10, 0, 6.2), (10, 20, 6.2)), ((0, 0, 6.2), (10, 20, 6.2), (0, 20, 6.2))])
    canopy = _mesh([((8, 8, 0.5), (12, 8, 0.5), (12, 12, 0.5)), ((8, 8, 0.5), (12, 12, 0.5), (8, 12, 0.5))])
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 10, 20))
    n01 = level("N01", 3.0, 3.0, sp=box(0, 0, 10, 20))
    ttr = level("TTR", 6.0, None)
    for gid, m in (("r", flat), ("m", canopy)):
        it = Item(gid, "IfcRoof", "Toit", "A", "TTR", mesh=m, z_min=0.5, z_max=6.2)
        ttr.plan.elements.append(plans.Placed(it, plans.footprint(m) if gid == "r" else box(8, 8, 12, 12)))
    exteriors.build([n00, n01, ttr], {}, set(), {})
    part, developed, mesh = ttr.spt_parts[0]
    assert developed == pytest.approx(200.0) and mesh is None                    # plate : dessinée à plat
    assert n01.envelope["GrossArea"] == pytest.approx(60 * 3.0)                  # la façade garde la hauteur d'étage


def test_pitched_roof_ignores_a_dormer():
    """Myonaz 2 (29.10.2026) : une lucarne (petit toit d'une autre orientation) ne fait ni bosse dans la SPT ni dent
    dans la façade ; le pan est prolongé sous elle."""
    import math
    import numpy as np
    roof_mesh, ridge = _gable_roof()
    dormer = _mesh([((1.5, 9, 3.5), (3.5, 9, 3.5), (2.5, 10, 4.5)), ((1.5, 11, 3.5), (2.5, 10, 4.5), (3.5, 11, 3.5))])
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 10, 20))
    ttr = level("TTR", 3.0, None)
    for gid, m in (("r", roof_mesh), ("d", dormer)):
        it = Item(gid, "IfcRoof", "Toit", "A", "TTR", mesh=m, z_min=1.0, z_max=ridge + 0.2)
        ttr.plan.elements.append(plans.Placed(it, plans.footprint(m) if gid == "r" else box(1.5, 9, 3.5, 11)))
    exteriors.build([n00, ttr], {}, set(), {})
    v = np.asarray(ttr.spt_parts[0][2].vertices).reshape(-1, 3)
    pan = 1.2 + np.minimum(v[:, 0], 10 - v[:, 0]) * math.tan(math.radians(30))   # dessus des deux pans
    assert np.abs(v[:, 2] - pan).max() < 1e-6                                     # sans la bosse de la lucarne
    gable = 10 * 1.2 + 0.5 * 10 * (ridge - 1.0)
    assert n00.envelope["GrossArea"] == pytest.approx(2 * 20 * 1.2 + 2 * gable, rel=1e-3)


def test_roof_window_in_its_lining_lies_in_the_roof_plane():
    """Myonaz 2 « Luc » (29.10.2026) : une fenêtre de toit modélisée avec son ébrasement (joues verticales jusqu'au
    plafond, plus grandes que la vitre) n'est pas une baie verticale : sa vitre, parallèle au pan, est un vitrage SRV
    de toiture à son aire vraie."""
    import math
    import numpy as np
    roof_mesh, ridge = _gable_roof()
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 10, 20))
    ttr = level("TTR", 3.0, None)
    roof = Item("r", "IfcRoof", "Toit", "A", "TTR", mesh=roof_mesh, z_min=1.0, z_max=ridge + 0.2)
    ttr.plan.elements.append(plans.Placed(roof, plans.footprint(roof_mesh)))
    s = math.radians(30)
    # vitre 1,2 m (le long de la pente) × 1,0 m (en y), dans le pan x de 2 à 3,04 ; joues verticales de 1,5 m de haut
    x0, x1, y0, y1 = 2.0, 2.0 + 1.2 * math.cos(s), 9.5, 10.5
    z = lambda x: 1.2 + x * math.tan(s)
    g = [((x0, y0, z(x0)), (x1, y0, z(x1)), (x1, y1, z(x1))), ((x0, y0, z(x0)), (x1, y1, z(x1)), (x0, y1, z(x0)))]
    glass = g + [(a, c, b) for a, b, c in g]
    cheeks = []
    for y in (y0, y1):
        q = [(x0, y, z(x0) - 1.5), (x1, y, z(x1) - 1.5), (x1, y, z(x1)), (x0, y, z(x0))]
        cheeks += [(q[0], q[1], q[2]), (q[0], q[2], q[3]), (q[0], q[2], q[1]), (q[0], q[3], q[2])]
    # fond de l'ébrasement : parallèle au pan, 0,5 m plus bas, plus long que la vitre (Myonaz 2 FT02)
    nz, nx = math.cos(s), -math.sin(s)
    low = lambda x, y: (x + 0.5 * -nx, y, z(x) - 0.5 * nz)
    fond = [(low(x0 - 0.8, y0), low(x1 + 0.8, y0), low(x1 + 0.8, y0 + 0.05))]
    win = _mesh(glass + cheeks + fond)
    zs = np.asarray(win.vertices).reshape(-1, 3)[:, 2]
    luc = Item("w", "IfcWindow", "Luc", "A", "TTR", mesh=win, z_min=float(zs.min()), z_max=float(zs.max()))
    ttr.plan.elements.append(plans.Placed(luc, plans.footprint(win)))
    exteriors.build([n00, ttr], {}, set(), {})
    assert n00.envelope["RoofWindowsArea"] == pytest.approx(1.2, rel=1e-3)        # la vitre, pas les joues
    assert n00.envelope["ReservationsArea"] == 0.0
    v = np.asarray(n00.glazing.vertices).reshape(-1, 3)
    assert np.ptp(v[:, 2]) == pytest.approx(1.2 * math.sin(s), abs=1e-6)          # dans le pan, sans le fond
    # la SPT est percée au droit de la vitre ; son aire reste brute
    part, developed, mesh = ttr.spt_parts[0]
    t = np.asarray(mesh.vertices).reshape(-1, 3, 3)
    e1, e2 = t[:, 1, :2] - t[:, 0, :2], t[:, 2, :2] - t[:, 0, :2]
    plan = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()
    assert plan == pytest.approx(200 - 1.2 * math.cos(s) * 1.0, abs=0.01)
    assert developed == pytest.approx(200 / math.cos(s), rel=1e-3)


def test_gable_window_is_cut_to_the_slope():
    """Myonaz 2 FS01 (30.10.2026) : une porte-fenêtre de pignon dont le linteau suit la pente ne dépasse pas du toit ;
    son vitrage est rogné au contour de la façade et ne compte que sa part."""
    import math
    import numpy as np
    roof_mesh, ridge = _gable_roof()
    n00 = level("N00", 0.0, 3.0, sp=box(0, 0, 10, 20))
    ttr = level("TTR", 3.0, None)
    roof = Item("r", "IfcRoof", "Toit", "A", "TTR", mesh=roof_mesh, z_min=1.0, z_max=ridge + 0.2)
    ttr.plan.elements.append(plans.Placed(roof, plans.footprint(roof_mesh)))
    # pignon y = 0 : porte-fenêtre de x 1 à 4, jusqu'à 3,5 m (le pignon monte de 1,78 à 3,51 m sur sa largeur)
    win = Item("w", "IfcWindow", "Fenêtre", "A", "N00", z_min=0.0, z_max=3.5, props={"Pset_WindowCommon.IsExternal": True})
    n00.plan.elements.append(plans.Placed(win, box(1, -0.1, 4, 0.1)))
    exteriors.build([n00, ttr], {}, set(), {})
    v = np.asarray(n00.glazing.vertices).reshape(-1, 3)
    pan = 1.2 + v[:, 0] * math.tan(math.radians(30))
    assert (v[:, 2] <= pan + 1e-6).all()                                          # rien au-dessus du toit
    full = 3 * 1.2 + 0.5 * 3 * 3 * math.tan(math.radians(30)) + 3 * 1.0 * math.tan(math.radians(30))   # sous la pente, x 1 à 4
    assert n00.envelope["SRV"] == pytest.approx(full, rel=1e-2)


def test_construction_scp_scn_thin_bands_and_true_gaps():
    """V4.1 : murs porteurs et poteaux en SCP, autres murs en SCN, bandes minces restantes en SC (non modélisée),
    le reste est la SP non classée ; garde-corps d'un balcon en SECN."""
    from sia_check.generation import construction
    lv = level("N00", 0.0, 3.0, sp=box(0, 0, 20, 10))
    room = plans.Placed(Item("r", "IfcSpace", "SEJ", "A", "N00"), box(0.3, 0.3, 12, 9.7))   # 12..20 : rien dessiné
    lv.rooms.append(interiors.Room(room, classify.Decision("r", "piece", "SUP", "PieceDeVie"), room.area))
    walls = [("p", box(0, 0, 20, 0.2), True), ("n", box(0, 9.8, 20, 10), False)]
    for gid, shape, bearing in walls:
        lv.plan.elements.append(plans.Placed(Item(gid, "IfcWall", "Mur", "A", "N00",
                                                  props={"Pset_WallCommon.LoadBearing": bearing}), shape))
    lv.plan.elements.append(plans.Placed(Item("c", "IfcColumn", "Pot", "A", "N00"), box(15, 4, 15.3, 4.3)))
    lv.sep = box(0, 10, 20, 12)
    bal = plans.Placed(Item("b", "IfcSpace", "BAL", "A", "N00"), box(0, 10, 20, 11.9))
    lv.exteriors.append(interiors.Room(bal, classify.Decision("b", "exterieur", "SEU", "Balcon"), bal.area))
    lv.plan.elements.append(plans.Placed(Item("g", "IfcRailing", "GC", "A", "N00"), box(0, 11.9, 20, 12)))
    lv.rooms[0].area -= 1.5   # aire déclarée plus petite que l'emprise (rampant) : reportée sur la SCN
    construction.build([lv])
    c = {k: a for k, (_, a) in lv.construction.items()}
    bands = 0.1 * 11.7 * 2 + 0.3 * 9.6   # jeu espace / mur le long de la pièce : construction, avec les murs en SCN
    assert c["SCP"] == pytest.approx(20 * 0.2 + 0.09) and c["SCN"] == pytest.approx(20 * 0.2 + bands + 1.5, abs=0.05)
    assert "SC" not in c and c["ecart_SCN"] == pytest.approx(1.5)
    assert lv.unclassified["SP"].area == pytest.approx(8 * 9.6 - 0.09, abs=0.05)   # la moitié est non dessinée
    assert c["SECN"] == pytest.approx(2.0) and lv.unclassified["SEP"] is None
    # niveau sans aucun mur dans la maquette (Afiro) : les bandes sont une SC non modélisée
    bare = level("N01", 3.0, 3.0, sp=box(0, 0, 10, 10))
    r2 = plans.Placed(Item("r2", "IfcSpace", "BUR", "A", "N01"), box(0.2, 0.2, 9.8, 9.8))
    bare.rooms.append(interiors.Room(r2, classify.Decision("r2", "piece", "SUT", "Commerce"), r2.area))
    construction.build([bare])
    assert bare.construction["SC"][1] == pytest.approx(100 - 9.6 * 9.6) and bare.unclassified["SP"] is None
