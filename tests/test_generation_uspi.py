"""Moteur de génération, phase 23 : logements et chaîne USPI (uspi.py), au modèle Treegram relevé sur L'Orée."""

import pytest
from shapely.geometry import box

from sia_check.generation import classify, ingest, interiors, plans, uspi
from sia_check.generation.ingest import Item, Storey

CFG = {"uspi": {"partition_m": 0.2, "wall_max_m": 0.6, "step_m": 0.05}, "sp": {"area_source": "plan"}}


def room(lv, gid, shape, code, typ=None, lot=None, nature="piece"):
    it = Item(gid, "IfcSpace", gid, "A", "N01", lot=lot, z_min=0.0)
    p = plans.Placed(it, shape)
    lv.plan.spaces.append(p)
    d = classify.Decision(gid, nature, code, typ, in_lot=lot is not None)
    if nature == "piece":
        lv.rooms.append(interiors.Room(p, d, shape.area))
    elif nature == "exterieur":
        lv.exteriors.append(interiors.Room(p, d, shape.area))
    return gid, d


@pytest.fixture
def level():
    """Deux logements de part et d'autre d'un couloir commun, murs de 0,2 m (mitoyens) et 0,4 m (façade)."""
    lv = interiors.Level(plans.Plan(Storey("N01", "N01", "A", 0.0, 3.0)))
    decisions = dict([
        room(lv, "a1", box(0.4, 0.4, 4.4, 5.4), "SUP", "PieceDeVie", "L1"),
        room(lv, "a2", box(4.5, 0.4, 7.4, 5.4), "SUP", "Chambre", "L1"),      # cloison de 0,1 m entre a1 et a2
        room(lv, "a3", box(7.5, 0.4, 8.4, 1.4), "SI", None, "L1"),            # gaine : pas dans la SHA
        room(lv, "b1", box(0.4, 7.6, 7.4, 12.6), "SUP", "Chambre", "L2"),
        room(lv, "c", box(0.4, 5.6, 9.6, 7.4), "SD", "CirculationH"),          # couloir commun
        room(lv, "e", box(0.4, 13.0, 4.4, 15.0), "SEU", "Balcon", "L2", nature="exterieur"),
    ])
    lv.sp = box(0, 0, 10, 13)
    return lv, decisions


def test_chain_follows_treegram(level):
    lv, decisions = level
    l1, l2 = uspi.build(lv, decisions, CFG)
    assert (l1.key, l2.key) == ("L1", "L2")
    assert l1.areas["SNH"] == pytest.approx(20.0 + 14.5)                    # SUP seules, la gaine non
    assert l1.bedrooms == 1 and l2.bedrooms == 1
    assert l1.areas["SHA"] == pytest.approx(34.5 + 0.1 * 5.0, abs=0.01)    # + cloison entre a1 et a2
    assert l1.areas["SNH"] < l1.areas["SHA"] < l1.areas["SBH"]
    assert l2.areas["SVN"] == pytest.approx(l2.areas["SHA"] + 8.0)          # SVN = SHA + SEU du logement
    assert l2.areas["SVB"] == pytest.approx(l2.areas["SBH"] + 8.0)
    # les murs sont partagés : rien n'est compté deux fois, et rien ne sort de la SP
    assert not l1.shapes["SBH"].intersection(l2.shapes["SBH"]).area > 1e-6
    assert lv.sp.covers(l1.shapes["SBH"].buffer(-1e-3))
    # mur de 0,2 m entre L1 et le couloir : L1 en prend la moitié
    assert l1.shapes["SBH"].bounds[3] == pytest.approx(5.5, abs=0.06)


def test_drawn_gross_contour_is_the_sbh(level):
    lv, decisions = level
    gid, d = room(lv, "g", box(0, 0, 8.6, 5.5), None, lot="L1", nature="plancher")   # La Bâtie : « 3P »
    decisions[gid] = d
    l1 = uspi.build(lv, decisions, CFG)[0]
    assert l1.areas["SBH"] == pytest.approx(8.6 * 5.5) and l1.sbh_source == "contour du logement"


def test_storey_without_flats_has_no_chain(level):
    lv, decisions = level
    lv.rooms = [r for r in lv.rooms if r.decision.code != "SUP"]
    assert uspi.build(lv, decisions, CFG) == []


def test_lot_key_puts_the_staircase_first():
    """La Bâtie : cage 28, appartement 2, au 1er étage -> « 1erEtage/28-2 » (le MDP : « 28-202 »)."""
    spec = [{"pset": "P", "property": "Appartement", "scope": "storey", "with": ["P.CageEscalier"]}]
    assert ingest._lot({"P.Appartement": "2", "P.CageEscalier": "28"}, spec, "1erEtage") == "1erEtage/28-2"
    assert ingest._lot({"P.Appartement": "2"}, spec, "1erEtage") == "1erEtage/2"
