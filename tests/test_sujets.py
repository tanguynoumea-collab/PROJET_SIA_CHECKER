"""Sujets et corrections de base (sujets.py)."""

import json

import pytest

from sia_check import corrections, geom, sujets, viewer


@pytest.fixture
def subjects(result, cfg):
    doc = viewer.build(result, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-21")
    return {s["id"]: s for s in sujets.build(doc, cfg)["subjects"]}


def test_grouping_by_cause(subjects):
    assert subjects["toitures"]["points"] == ["A2|ERR|Toiture||SEP", "R3|ERR|Toiture||SEP"]
    assert set(subjects["abords"]["points"]) == {"A1|ERR|N00||SEP", "R3|ERR|N00||SEP"}
    assert subjects["sc-implicite"]["action"] == "aucune" and subjects["sc-implicite"]["points"]
    assert all("|*|" in k for k in subjects["agregats"]["points"])
    assert not any(k.startswith("A3") for k in subjects["agregats"]["points"])     # codes inconnus : à part
    assert subjects["R4-SP"]["action"] == "à vérifier" and not subjects["R4-SP"]["corrections"]


def test_base_corrections_without_geometry(subjects):
    roof = subjects["toitures"]["corrections"][0]
    assert (roof["op"], roof["cible"], roof["statut"], roof["origine"]) == (
        "exclure", {"ids": ["err-toit-sep"]}, "proposée", "règle")
    assert "aire" not in roof                                    # SEP de toiture entière
    ground = subjects["abords"]["corrections"][0]
    assert (ground["op"], ground["vers"], ground["aire"], ground["polygone"]) == ("découper", "SA", 45.0, None)


def test_every_point_in_exactly_one_subject(result, cfg):
    doc = viewer.build(result, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-21")
    keys = [k for s in sujets.build(doc, cfg)["subjects"] for k in s["points"]]
    assert sorted(keys) == sorted(i["key"] for i in doc["issues"])


def test_proposals_apply_cleanly(synth, cfg, result):
    doc = viewer.build(result, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-21")
    sj = sujets.build(doc, cfg)
    journal = sujets.journal(sj, "Synth")
    for c in journal["corrections"]:
        c["statut"] = "acceptée"
    applied, before, after = corrections.run(synth, journal, cfg)
    assert set(applied.log.application) == {corrections.APPLIED}
    failing = lambda r: {(x.rule, x.level) for x in r.failing.itertuples()}   # noqa: E731
    assert ("A2", "Toiture") in failing(before) and ("A2", "Toiture") not in failing(after)


def square(x0, y0, x1, y1, z=0.0) -> dict:
    return {"v": [x0, y0, z, x1, y0, z, x1, y1, z, x0, y1, z], "i": [0, 1, 2, 0, 2, 3]}


def test_ground_tracing_from_geometry(cfg):
    pytest.importorskip("shapely")
    # N00 : plancher 10 × 10, SEP 30 × 10 autour, terrasse SEU 5 × 10 -> abords = 300 − 100 − 50 = 150 m².
    doc = {
        "issues": [{"key": "A1|A|N00||SEP", "rule": "A1", "verdict": "ALERTE", "building": "A", "level": "N00",
                    "category": "SEP", "hint": ""}],
        "levels": [{"building": "A", "level": "N00", "values": {"SP": 100, "SEP": 300, "SEU": 50}}],
        "surfaces": [
            {"id": "A_N00_SP#total", "building": "A", "level": "N00", "code": "SP", "category": "SP", "kind": "node",
             "area": 100, "mesh": square(0, 0, 10, 10)},
            {"id": "A_N00_SEP#total", "building": "A", "level": "N00", "code": "SEP", "category": "SEP", "kind": "node",
             "area": 300, "mesh": square(-10, 0, 20, 10)},
            {"id": "seu", "building": "A", "level": "N00", "code": "SEU", "category": "SEU", "kind": "leaf",
             "area": 50, "mesh": square(15, 0, 20, 10)},
        ],
    }
    sj = sujets.build(doc, cfg)
    c = sj["subjects"][0]["corrections"][0]
    assert sj["geometry"] and c["aire"] == pytest.approx(150.0)
    assert c["polygone"]["type"] in ("Polygon", "MultiPolygon")
    json.dumps(c)                                                  # sérialisable tel quel dans le journal


def test_partial_exclusion(cfg):
    df = __import__("pandas").DataFrame([
        {"id": "sep", "building": "A", "level": "N05", "category": "SEP", "area": 100.0, "kind": "node"},
        {"id": "sp", "building": "A", "level": "N05", "category": "SP", "area": 50.0, "kind": "node"},
    ])
    j = {"corrections": [{"id": "c", "op": "exclure", "statut": "acceptée", "cible": {"ids": ["sep"]}, "aire": 60.0}]}
    a = corrections.apply(df, j)
    s = a.surfaces.set_index("id")
    assert s.loc["sep", "area"] == 40 and not s.loc["sep", "excluded"] and a.log.iloc[0].m2 == 60
    j["corrections"][0]["aire"] = 160.0
    assert corrections.apply(df, j).log.iloc[0].application == corrections.REFUSED


def test_cli_writes_subjects_usable_as_journal(tmp_path):
    from sia_check import cli
    from test_tgm import leaf, node
    tgm = tmp_path / "mini.tgm"
    tgm.write_bytes(b"".join([node("SP", 0.0), node("SEP", 30.0),
                              leaf("A_Toiture_ShellByTgm-1_SpaceByTgm-1_SPT", "SPT", 30.0)]))
    out = tmp_path / "sujets.json"
    cli.main([str(tgm), "-q", "--sujets", str(out), "--config", str(cli._default_config())])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["corrections"] and data["corrections"][0]["sujet"] == "toitures"
    assert corrections.validate(data) is data
