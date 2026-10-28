"""Contrat `.siagen.json` (V4, siagen.py) : un projet tiré d'un `.tgm` se lit exactement comme lui."""

import json
import struct

import pandas as pd
import pytest

from sia_check import cli, geom, reader, siagen, viewer, rules
from test_geom import SQUARE, drtgm, mesh_block
from test_tgm import CAT, bag, node
from test_integration_loree import TGM, needs_tgm


def record(eid: int) -> bytes:
    """En-tête d'enregistrement : conteneur 170, identifiant de l'élément (tgm.RECORD_ID_RE)."""
    return struct.pack("<i", 170) + b"\x04" + struct.pack("<i", eid) + b"\x04\x01" + b"\x00" * 7


@pytest.fixture
def project(tmp_path):
    """Projet Treegram minimal : un niveau, une pièce avec maillage, son lot, un balcon, et le cache VWR."""
    (tmp_path / "Mini.tgm").write_bytes(b"".join([
        node("SUP", 20.0), record(101) + bag("A_N01_ShellByTgm-1_SpaceByTgm-1_SUP", {CAT: "SUP", "Area": 20.0,
                                                                                  "Type": "Chambre"}),
        node("SP", 30.0), node("SEP", 5.0),
        record(102) + bag("A_N01_ExtShellByTgm-1_SEU", {CAT: "SEU", "Area": 5.0, "Type": "Balcon"}),
        # sans en-tête propre : le lot prend l'identifiant du balcon qui le précède (deux éléments, un identifiant)
        bag("A_N01_Apart-1_SNH", {CAT: "SNH", "Area": 20.0, "ApartmentByTgm": "A_N01_Apart-1", "Bedrooms": 1}),
    ]))
    data = tmp_path / "VWR" / "H1__H1" / "_Data"
    data.mkdir(parents=True)
    (data / "A_N01-SiaSurface.3drtgm").write_bytes(drtgm([101, 102], [
        mesh_block(0, SQUARE, [[0, 1, 2], [0, 2, 3]]), mesh_block(1, SQUARE, [[0, 1, 2]])]))
    return tmp_path


def same_surfaces(a: pd.DataFrame, b: pd.DataFrame):
    pd.testing.assert_frame_equal(a.drop(columns="source"), b.drop(columns="source"))


def test_roundtrip_gives_the_same_surfaces_and_meshes(project, cfg, tmp_path):
    out = tmp_path / "gen"
    assert cli.main(["-q", str(project), "--siagen", str(out)]) in (0, 1)
    gen = out / f"Mini{siagen.SUFFIX}"
    same_surfaces(reader.read(project / "Mini.tgm", cfg), reader.read(gen, cfg))
    a, b = geom.read_cache(project).meshes, geom.for_model(gen).meshes
    assert {k: [(m.vertices, m.indices) for m in v] for k, v in a.items()} == \
           {k: [(m.vertices, m.indices) for m in v] for k, v in b.items()}


def test_folder_with_a_siagen_is_a_project(project, cfg, tmp_path):
    out = tmp_path / "gen"
    cli.main(["-q", str(project), "--siagen", str(out)])
    assert cli._resolve(out).name == f"Mini{siagen.SUFFIX}"
    assert siagen.project_name(cli._resolve(out)) == "Mini"
    doc = tmp_path / "viewer.json"
    assert cli.main(["-q", str(out), "--viewer-json", str(doc)]) in (0, 1)
    ref = tmp_path / "viewer-tgm.json"
    cli.main(["-q", str(project), "--viewer-json", str(ref)])
    d, r = (json.loads(f.read_text(encoding="utf-8")) for f in (doc, ref))
    assert d["project"] == "Mini" and not d["cache"]["stale"]
    assert d["surfaces"] == r["surfaces"] and sum(1 for s in d["surfaces"] if s["mesh"]) >= 2


def test_folder_with_two_sources_is_refused(project, tmp_path):
    cli.main(["-q", str(project), "--siagen", str(project)])
    with pytest.raises(reader.ReadError):
        cli._resolve(project)


def test_written_elements_keep_treegram_names_and_ids(project, cfg, tmp_path):
    p = tmp_path / f"x{siagen.SUFFIX}"
    cli.main(["-q", str(project), "--siagen", str(p)])
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["format"] == siagen.FORMAT and doc["version"] == siagen.VERSION
    sup = next(e for e in doc["elements"] if e["name"].endswith("_SUP"))
    assert (sup["kind"], sup["building"], sup["level"], sup["element_id"], sup["container_id"]) == \
           ("leaf", "A", "N01", 101, 170)
    assert sup["props"] == {CAT: "SUP", "Area": 20.0, "Type": "Chambre"} and len(sup["meshes"]) == 1
    sp = next(e for e in doc["elements"] if e["name"] == "SP")
    assert (sp["kind"], sp["building"], sp["level"]) == ("node", "A", "N01")


def element(**over):
    e = {"name": "A_N01_X_SUP", "kind": "leaf", "building": "A", "level": "N01", "props": {CAT: "SUP", "Area": 1.0}}
    return e | over


@pytest.mark.parametrize("doc, message", [
    ({"format": "autre", "version": 1}, "format"),
    ({"format": siagen.FORMAT, "version": 2}, "version"),
    ({"format": siagen.FORMAT, "version": 1, "elements": [element(kind="total")]}, "kind"),
    ({"format": siagen.FORMAT, "version": 1, "elements": [element(level="")]}, "level"),
    ({"format": siagen.FORMAT, "version": 1, "elements": [element(element_id="12")]}, "entier"),
    ({"format": siagen.FORMAT, "version": 1,
      "elements": [element(meshes=[{"v": siagen._b64([0.0] * 9, "f"), "i": siagen._b64([0, 1, 5], "I")}])]},
     "incohérent"),
])
def test_contract_violations_are_read_errors(tmp_path, cfg, doc, message):
    p = tmp_path / f"bad{siagen.SUFFIX}"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(reader.ReadError, match=message):
        reader.read(p, cfg)


def test_hand_written_project_is_analysed(tmp_path, cfg):
    """Ce qu'écrira le moteur de génération : bâtiment et niveau explicites, aucun ordre de fichier à deviner."""
    els = [siagen.Element("SP", "node", "B", "N00", {CAT: "SP", "Area": 100.0}, 1, 9),
           siagen.Element("SUP", "node", "B", "N00", {CAT: "SUP", "Area": 80.0}, 2, 9),
           siagen.Element("B_N00_ShellByTgm-1_SpaceByTgm-1_SUP", "leaf", "B", "N00",
                          {CAT: "SUP", "Area": 80.0, "Type": "PieceDeVie"}, 3, 9,
                          [geom.Mesh([0, 0, 0, 8, 0, 0, 8, 10, 0], [0, 1, 2])])]
    p = siagen.write(els, tmp_path / f"B{siagen.SUFFIX}", "B")
    df = reader.read(p, cfg)
    assert set(df.id) == {"B_N00_SP#total", "B_N00_SUP#total", "B_N00_ShellByTgm-1_SpaceByTgm-1_SUP"}
    assert df.set_index("id").tgm_id["B_N00_ShellByTgm-1_SpaceByTgm-1_SUP"] == "H9::H3"
    doc = viewer.build(rules.run(df, cfg), cfg, geom.for_model(p), "B", [str(p)])
    assert next(s for s in doc["surfaces"] if s["kind"] == "leaf")["mesh"] is not None


@needs_tgm
def test_loree_siagen_reads_like_its_tgm(cfg, tmp_path):
    p = tmp_path / f"L OREE{siagen.SUFFIX}"
    assert cli.main(["-q", str(TGM), "--siagen", str(p)]) in (0, 1)
    same_surfaces(reader.read(TGM, cfg), reader.read(p, cfg))
    a, b = geom.read_cache(TGM.parent).meshes, geom.for_model(p).meshes
    assert set(a) >= set(b) and all([m.vertices for m in a[k]] == [m.vertices for m in b[k]] for k in b)
