"""Lecteur IFC sur un petit IFC généré, encodé comme les exports Treegram (Name = code, Pset Treegram.Area)."""

import ifcopenshell
import ifcopenshell.api
import pytest

from sia_check import reader, rules


def _slab(f, storey, name, area):
    s = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSlab", name=name)
    ifcopenshell.api.run("spatial.assign_container", f, products=[s], relating_structure=storey)
    pset = ifcopenshell.api.run("pset.add_pset", f, product=s, name="Treegram")
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={"Area": area})


@pytest.fixture
def ifc_file(tmp_path):
    f = ifcopenshell.api.run("project.create_file", version="IFC4")  # IFC2X3 exigerait un IfcOwnerHistory
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Test")
    ifcopenshell.api.run("unit.assign_unit", f)
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    bld = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="B1")
    st = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="N01")
    ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[bld], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[st], relating_object=bld)
    _slab(f, st, "SP", 100.0)
    _slab(f, st, "SUP", 60.0)
    _slab(f, st, "SHAB", 55.0)  # code promoteur : inconnu de la config SIA
    p = tmp_path / "mini.ifc"
    f.write(str(p))
    return p


def test_read_ifc(ifc_file, cfg):
    df = reader.read(ifc_file, cfg)
    assert sorted(df.category) == ["SHAB", "SP", "SUP"]
    assert set(df.building) == {"B1"} and set(df.level) == {"N01"}
    assert df.set_index("category").area.to_dict() == {"SP": 100.0, "SUP": 60.0, "SHAB": 55.0}
    assert df.id.str.len().eq(22).all()  # GlobalId


def test_ifc_unknown_code_reported_not_blocking(ifc_file, cfg):
    res = rules.run(reader.read(ifc_file, cfg), cfg)
    a3 = res.residuals[res.residuals.rule == "A3"]
    assert list(a3.category) == ["SHAB"]
    r1 = res.residuals[(res.residuals.rule == "R1") & (res.residuals.level == "N01")].iloc[0]
    assert r1.verdict == "ERREUR" and r1.diff_m2 == pytest.approx(40)
