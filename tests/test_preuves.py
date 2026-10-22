"""Preuves géométriques de la revue IA (sia_check.preuves) sur un document visionneuse minimal."""

import pytest

pytest.importorskip("shapely")

from sia_check import preuves  # noqa: E402


def rect(x0, y0, x1, y1, z=0.0):
    return {"v": [x0, y0, z, x1, y0, z, x1, y1, z, x0, y1, z], "i": [0, 1, 2, 0, 2, 3]}


def surface(sid, level, code, area, mesh, kind="leaf"):
    return {"id": sid, "building": "B01", "level": level, "category": code, "code": code, "kind": kind,
            "area": area, "mesh": mesh}


@pytest.fixture
def doc():
    return {
        "project": "SYNTH", "date": "2026-10-22", "cache": {}, "counts": {}, "tolerance": {},
        "levels": [
            {"building": "B01", "level": "S01", "rank": -1, "values": {"SP": 200.0}, "r1": None, "alerts": []},
            {"building": "B01", "level": "N00", "rank": 0, "values": {"SP": 100.0, "SUP": 60.0, "SUS": 30.0,
                                                                       "SEP": 100.0},
             "r1": {"diff": 10.0, "verdict": "INFO"}, "alerts": ["A1"]},
        ],
        "surfaces": [
            surface("sp-s01", "S01", "SP", 200.0, rect(0, 0, 20, 10), kind="node"),
            surface("sp-n00", "N00", "SP", 100.0, rect(0, 0, 10, 10), kind="node"),
            surface("sup", "N00", "SUP", 60.0, rect(0, 0, 6, 10)),
            # Recouvre la SUP sur 1 m × 10 m, et déborde de la SP de 1 m × 10 m.
            surface("sus", "N00", "SUS", 30.0, rect(5, 0, 11, 10)),
            surface("sut", "N00", "SUT", 5.0, None),
            # Terrasse à côté du bâtiment, entièrement au-dessus du sous-sol.
            surface("sep-n00", "N00", "SEP", 100.0, rect(10, 0, 20, 10), kind="node"),
        ],
        "issues": [{"key": "R1|B01|N00||SP", "rule": "R1", "verdict": "INFO", "building": "B01", "level": "N00",
                    "lot": None, "category": "SP", "expected": 100.0, "obtained": 90.0, "diff_m2": 10.0,
                    "diff_pct": 10.0, "title": "t", "message": "m", "hint": "h", "surface_ids": []}],
    }


def test_residual_recomputed_when_sut_ignored(doc):
    # Fichier sans statut de catégorie (antérieur aux règles personnalisées) : SUT était ignoré.
    n00 = next(l for l in preuves.build(doc)["levels"] if l["level"] == "N00")
    assert n00["SUT"] == 5.0 and not n00["SUT_counted_by_engine"]
    assert n00["R1_residual_if_SUT_counted"] == 5.0
    assert n00["R1_pct_if_SUT_counted"] == 5.0


def test_sut_not_subtracted_twice_under_custom_rule(doc):
    # Règle personnalisée P1 : le moteur a déjà compté SUT dans la SU, donc dans le résidu R1.
    doc["categories"] = [{"code": "SUT", "status": "checked", "custom_rule": "P1"}]
    n00 = next(l for l in preuves.build(doc)["levels"] if l["level"] == "N00")
    assert n00["SUT_counted_by_engine"] and n00["SUT_custom_rule"] == "P1"
    assert n00["R1_residual_if_SUT_counted"] == n00["R1_residual"] == 10.0


def test_overlap_and_outside_footprint(doc):
    ev = preuves.build(doc)
    assert [(o["a"], o["b"], o["overlap"]) for o in ev["interior_overlaps"]] == [("sup", "sus", 10.0)]
    assert [(o["id"], o["area_outside_SP"]) for o in ev["interior_outside_SP"]] == [("sus", 10.0)]


def test_sep_over_basement(doc):
    sep = preuves.build(doc)["sep_decomposition"]
    assert len(sep) == 1
    s = sep[0]
    assert s["SEP_geom"] == 100.0
    assert s["under_SP_same_level"] == 0.0
    assert s["level_below"] == "S01"
    assert s["over_level_below"] == 100.0
    assert s["over_nothing"] == 0.0


def test_issues_keep_their_key(doc):
    assert [i["key"] for i in preuves.build(doc)["issues"]] == ["R1|B01|N00||SP"]


def test_ratios_passed_to_review(doc):
    doc["ratios"] = [{"building": "*", "id": "SN/SP", "value": 0.85, "status": "ok"}]
    assert preuves.build(doc)["ratios"] == doc["ratios"]
