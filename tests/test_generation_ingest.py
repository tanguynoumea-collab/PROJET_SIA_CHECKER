"""Moteur de génération, phase 20 : ingestion IFC, plans par niveau, audit d'entrée et inventaire."""

import json

import pytest

from sia_check import cli
from sia_check.generation import audit, ingest, plans
from ifc_synth import Z0, build


@pytest.fixture(scope="module")
def ifc(tmp_path_factory):
    return build(tmp_path_factory.mktemp("ifc") / "synth.ifc")


@pytest.fixture(scope="module")
def model(ifc):
    from sia_check import config
    from conftest import ROOT
    return ingest.load(ifc, config.load(ROOT / "config.yaml").generation)


@pytest.fixture(scope="module")
def plan_list(model):
    return plans.build(model)


def space(model, long_name, storey=None):
    return next(s for s in model.spaces if s.long_name == long_name
                and (storey is None or model.storey(s.storey).name == storey))


def test_storeys_in_metres_from_placement(model):
    assert [(s.name, s.elevation, s.height, s.rank) for s in model.storeys] == [
        ("N00", Z0, 3.0, 0), ("N01", Z0 + 3.0, None, 1)]
    assert model.buildings == ["A"] and model.schema == "IFC4"


def test_spaces_attached_by_structure_or_altitude(model):
    sej = space(model, "Séjour")
    assert (sej.name, sej.building, model.storey(sej.storey).name, sej.storey_by) == ("SEJ", "A", "N00", "structure")
    lt = space(model, "Local technique")
    assert (model.storey(lt.storey).name, lt.storey_by, lt.building) == ("N01", "altitude", "A")


def test_lot_from_room_number(model):
    assert space(model, "Séjour").lot == "1A.00.01" and space(model, "Chambre", "N00").lot == "1A.00.01"
    assert space(model, "Couloir").lot == "1A.99.00" and space(model, "Chambre", "N01").lot is None


def test_properties_flattened_and_geometry_in_world_coordinates(model):
    sej = space(model, "Séjour")
    assert sej.props["Pset_HRS.NumeroPiece"] == "1A.00.01.01"
    assert sej.props["Qto_SpaceBaseQuantities.NetFloorArea"] == pytest.approx(20.0)
    assert (sej.z_min, sej.z_max) == (pytest.approx(Z0), pytest.approx(Z0 + 2.6))
    assert {e.ifc_class for e in model.elements} == {"IfcWall", "IfcDoor", "IfcSlab"}
    assert all(e.mesh is not None for e in model.elements) and not model.errors


def test_footprints_are_horizontal_projections(plan_list):
    n00, n01 = plan_list
    areas = {p.item.long_name: round(p.area, 3) for p in n00.spaces}
    assert areas == {"Séjour": 20.0, "Chambre": 12.0, "Couloir": 12.0}
    assert round(n00.union("IfcSlab").area, 3) == 44.0 and round(n00.union("IfcWall").area, 3) == 1.6
    assert {p.item.long_name for p in n01.spaces} == {"Chambre", "Local technique"}
    assert n00.of("IfcWall")[0].item.name == "Façade"


def test_footprint_of_vertical_faces_only_is_none():
    from sia_check.geom import Mesh
    wall_face = Mesh([0, 0, 0, 1, 0, 0, 1, 0, 3, 0, 0, 3], [0, 1, 2, 0, 2, 3])
    assert plans.footprint(wall_face) is None and plans.footprint(None) is None


def test_audit(model, plan_list):
    issues = {i.code: i for i in audit.run(model, plan_list, {"lot": {"pset": "x"}, "audit": {}})}
    assert set(issues) == {"G4", "G6", "G10"}
    assert issues["G6"].gids == [space(model, "Chambre", "N00").gid]
    assert len(issues["G10"].gids) == 2 and not audit.blocking(list(issues.values()))


def test_audit_blocks_without_spaces(model):
    empty = ingest.Model("x.ifc", "IFC4", None, [], [], [])
    assert {i.code for i in audit.run(empty, [], {})} == {"G1", "G2"}


def test_inventory_cli(ifc, tmp_path, capsys):
    out = tmp_path / "inv.json"
    assert cli.main(["--inventaire", str(ifc), "--inventaire-json", str(out)]) == 0
    inv = json.loads(out.read_text(encoding="utf-8"))
    assert inv["format"] == audit.FORMAT and inv["counts"]["spaces"] == 5 and not inv["blocking"]
    n00 = inv["buildings"][0]["storeys"][0]
    assert (n00["name"], n00["spaces"], n00["spaces_m2"], n00["lots"]) == ("N00", 3, 44.0, 2)
    assert n00["elements"] == {"IfcDoor": 1, "IfcSlab": 1, "IfcWall": 1}
    sej = next(s for s in inv["spaces"] if s["long_name"] == "Séjour")
    assert (sej["area_plan"], sej["area_declared"], sej["lot"]) == (20.0, 20.0, "1A.00.01")
    assert "Bâtiment A" in capsys.readouterr().out


def test_inventory_of_missing_file(tmp_path):
    assert cli.main(["--inventaire", str(tmp_path / "absent.ifc")]) == 2
