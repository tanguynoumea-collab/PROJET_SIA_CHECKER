import json
"""Décodeur .3drtgm (geom.py), identifiant d'élément du .tgm et export visionneuse (viewer.py)."""

import struct

import pytest

from sia_check import geom, rules, tgm, viewer
from test_tgm import bag


def obj_record(k: int, eid: int) -> bytes:
    return struct.pack("<iii", k, 0xA9, eid) + struct.pack("<ii", 1, 1) + b"\x00" * 22


def mesh_block(obj_index: int, verts, groups, width="B") -> bytes:
    prefix = struct.pack("<ii", 1, obj_index) + bytes.fromhex("0100010000000000000001")  # 19 octets
    nt = sum(len(g) // 3 for g in groups)
    out = prefix + struct.pack("<ii", len(verts) // 3, nt) + struct.pack(f"<{len(verts)}f", *verts)
    out += struct.pack("<i", len(groups))
    for g in groups:
        out += struct.pack("<i", len(g) // 3) + b"\x00\x7e" + struct.pack(f"<{len(g)}{width}", *g)
    return out


SQUARE = [0, 0, 3.2, 4, 0, 3.2, 4, 5, 3.2, 0, 5, 3.2]


def drtgm(objects: list[int], meshes: list[bytes]) -> bytes:
    head = b"\x17\xb4\x14\x03\x01" + struct.pack("<iiii", len(objects), 0, 0, 0)
    head += struct.pack("<ii", len(objects), 1) + struct.pack("<f", 1.0) + b"\x00\x00"
    assert len(head) == 35
    mats = struct.pack("<i4f", 0, 0.8, 0.0, 0.2, 1.0)
    return head + mats + b"".join(obj_record(k, e) for k, e in enumerate(objects)) + b"".join(meshes)


@pytest.fixture
def vwr(tmp_path):
    data = tmp_path / "VWR" / "H1__H1" / "_Data"
    data.mkdir(parents=True)
    (data / "A_N01-SiaSurface.3drtgm").write_bytes(drtgm([101, 102], [
        mesh_block(0, SQUARE, [[0, 1, 2], [0, 2, 3]]),
        mesh_block(1, SQUARE, [[0, 1, 2]]),
        mesh_block(1, SQUARE, [[0, 2, 3]]),               # deuxième maillage du même objet
    ]))
    return tmp_path


def test_read_file_links_meshes_to_element_ids(vwr):
    meshes = geom.read_file(next(vwr.rglob("*.3drtgm")))
    assert set(meshes) == {101, 102}
    assert meshes[101][0].indices == [0, 1, 2, 0, 2, 3]
    assert meshes[101][0].vertices[2] == pytest.approx(3.2)
    assert len(meshes[102]) == 2


def test_multi_group_and_wide_indices(tmp_path):
    verts = [float(i % 7) for i in range(3 * 300)]               # 300 sommets : indices sur 2 octets
    p = tmp_path / "x.3drtgm"
    p.write_bytes(drtgm([7], [mesh_block(0, verts, [[0, 1, 299], [5, 6, 7, 8, 9, 10]], width="H")]))
    m = geom.read_file(p)[7][0]
    assert m.indices == [0, 1, 299, 5, 6, 7, 8, 9, 10]


def test_read_cache(vwr):
    c = geom.read_cache(vwr)
    assert c.files == 1 and set(c.meshes) == {101, 102} and not c.errors


def test_read_cache_without_vwr(tmp_path):
    c = geom.read_cache(tmp_path)
    assert c.files == 0 and c.errors


def test_element_id_from_record_header():
    # en-tête réel, puis une référence de même forme (conteneur 3) qui ne doit pas être prise pour lui
    header = (b"\x12\x00\x00\x00\x00\x00\x00\x00\xaa\x00\x00\x00\x04" + struct.pack("<i", 2617) + b"\x04\x01"
              + b"\x00" * 7 + b"\x5a" * 48 + b"\x00\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x00\x04\x52\x00\x00\x00"
              + b"\x04\x01\x00\x00\x00\x01" + b"\x00" * 10)
    data = header + bag("A_N01_ShellByTgm-1_SpaceByTgm-1_SUP", {"Catégorie SIA": "SUP", "Area": 1.0})
    b = next(g for g in tgm.scan(data) if g.name.endswith("_SUP"))
    assert (b.element_id, b.container_id, b.tgm_id) == (2617, 170, "H170::H2617")


# --------------------------------------------------------------------------- export visionneuse

@pytest.fixture
def doc(result, cfg):
    return viewer.build(result, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-21")


def issue(doc, key):
    return next(i for i in doc["issues"] if i["key"] == key)


def test_issue_keys_unique_and_stable(doc, result, cfg):
    keys = [i["key"] for i in doc["issues"]]
    assert len(keys) == len(set(keys))
    again = viewer.build(result, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-22")
    assert keys == [i["key"] for i in again["issues"]]


def test_r3_concerns_only_the_sep(doc):
    # La part non classée est dans la SEP : ses sous-catégories déjà classées (SEU) ne sont pas en cause.
    assert issue(doc, "R3|ERR|N00||SEP")["surface_ids"] == ["err-n00-sep"]
    assert issue(doc, "A1|ERR|N00||SEP")["surface_ids"] == ["err-n00-sep"]


def test_r5_concerns_whole_floor(doc):
    ids = set(issue(doc, "R5|ERR|N03||SU")["surface_ids"])
    assert {"err-n03-sp", "err-n03-sd", "err-n03-si"} == ids


def test_uspi_concerns_lot(doc):
    ids = issue(doc, "U1|ERR|N01|ERR_N01_Apart-2|SH")["surface_ids"]
    assert sorted(ids) == sorted(f"err-n01-lot2-{c}" for c in ("snh", "sha", "sbh", "svn", "svb"))


def test_a3_concerns_unknown_surfaces(doc):
    assert issue(doc, "A3|*|*||XYZ")["surface_ids"] == ["err-n01-xyz"]


def test_doc_shape(doc, synth):
    assert doc["format"] == "sia-check-viewer" and doc["version"] == 1
    assert len(doc["surfaces"]) == len(synth) and all(s["mesh"] is None for s in doc["surfaces"])
    lv = next(l for l in doc["levels"] if (l["building"], l["level"]) == ("ERR", "N00"))
    assert lv["values"]["SP"] == 100 and lv["r1"]["verdict"] == "ERREUR" and "A1" in lv["alerts"]
    assert {c["code"]: c["status"] for c in doc["categories"]}["SUT"] == "checked"
    assert not doc["cache"]["stale"]
    sn = next(r for r in doc["ratios"] if r["building"] == "OK" and r["id"] == "SN/SP")
    assert sn["value"] == pytest.approx(0.9) and sn["ref_min"] == 0.78
    assert doc["ratios"] == json.loads(json.dumps(doc["ratios"]))   # pas de NaN


def test_level_totals_with_detail_have_no_mesh(cfg):
    # Total SUS du niveau + sa pièce : même emprise, le total n'est pas montré en 3D (doublon), le détail fait foi.
    import pandas as pd
    from sia_check import geom, rules, viewer
    df = pd.DataFrame([
        {"id": "sp", "building": "A", "level": "N01", "category": "SP", "area": 20.0, "kind": "node", "element_id": 1},
        {"id": "sus-total", "building": "A", "level": "N01", "category": "SUS", "area": 10.0, "kind": "node", "element_id": 2},
        {"id": "sus-1", "building": "A", "level": "N01", "category": "SUS", "area": 10.0, "kind": "leaf", "element_id": 3},
    ]).assign(room_type=None, lot=None, elevation=None)
    cache = geom.Cache()
    tri = [geom.Mesh(vertices=[0, 0, 0, 1, 0, 0, 1, 1, 0], indices=[0, 1, 2])] if hasattr(geom, "Mesh") else None
    if tri is None:
        pytest.skip("geom.Mesh absent")
    cache.meshes.update({1: tri, 2: tri, 3: tri})
    doc = viewer.build(rules.run(df, cfg), cfg, cache, "T", ["t"], date="2026-10-26")
    mesh = {s["id"]: s["mesh"] is not None for s in doc["surfaces"]}
    assert mesh == {"sp": True, "sus-total": False, "sus-1": True}
    assert doc["cache"]["surfaces_without_mesh"] == 0
