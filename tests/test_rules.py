"""Règles sur le jeu synthétique tests/data/synth.csv : un cas qui boucle et un cas en défaut par règle."""

import pandas as pd
import pytest

from sia_check import rules
from conftest import pick, verdict


# R1 — SP = SN + SC (SIA 416 §2)
def test_r1_loops(result):
    assert verdict(result, "OK", "N01", "R1") == "OK"


def test_r1_positive_residual_is_error(result):
    r = pick(result, "ERR", "N00", "R1").iloc[0]
    assert r.verdict == "ERREUR" and r.diff_m2 == pytest.approx(35)


def test_r1_small_residual_is_implicit_sc(result):
    r = pick(result, "ERR", "N01", "R1").iloc[0]
    assert r.verdict == "INFO" and "SC implicite" in r.message and r.diff_m2 == pytest.approx(8)


def test_r1_ignored_code_not_summed(result):
    # SUT (100 m², ignore: true) sur ERR N01 ne doit pas combler le résidu.
    assert pick(result, "ERR", "N01", "R1").obtained.iloc[0] == pytest.approx(92)


# R2 — SU = SUP + SUS (SIA 416 §2.1.1)
def test_r2_loops(result):
    assert verdict(result, "OK", "N02", "R2") == "OK"


def test_r2_mismatch(result):
    assert verdict(result, "ERR", "N05", "R2") == "ERREUR"


def test_r2_not_emitted_without_su(result):
    assert verdict(result, "OK", "N01", "R2") is None


# R3 — SEP = SEN + SEC (SIA 416 §3)
def test_r3_loops(result):
    assert verdict(result, "OK", "N01", "R3") == "OK"


def test_r3_residual_and_leaves_win_over_node(result):
    # SEU fourni en total de niveau (99) et en surface élémentaire (5) : l'élémentaire fait foi.
    r = pick(result, "ERR", "N00", "R3").iloc[0]
    assert r.verdict == "ERREUR" and r.obtained == pytest.approx(5)


# R4 — sous-catégorie sans parent
def test_r4_children_exceed_parent(result):
    r = pick(result, "ERR", "N02", "R4").iloc[0]
    assert r.verdict == "ERREUR" and r.diff_m2 == pytest.approx(-10)


def test_r4_child_without_parent(result):
    r = pick(result, "ERR", "N04", "R4").iloc[0]
    assert r.category == "SP" and r.expected == 0 and r.obtained == pytest.approx(30)


def test_r4_absent_when_loops(result):
    assert pick(result, "OK", "N01", "R4").empty


# R5 — niveau avec SP sans surface utile
def test_r5_level_without_su(result):
    assert verdict(result, "ERR", "N03", "R5") == "ALERTE"


def test_r5_not_raised_when_su(result):
    assert verdict(result, "ERR", "N00", "R5") is None


def test_r5_technical_level_exempt(result, synth, cfg):
    assert verdict(result, "TEC", "LT1", "R5") is None
    cfg.technical = []
    assert verdict(rules.run(synth, cfg), "TEC", "LT1", "R5") == "ALERTE"


# A1 — SEP au niveau du terrain
def test_a1_ground_sep(result):
    assert verdict(result, "ERR", "N00", "A1") == "ALERTE"


def test_a1_not_on_upper_level(result):
    assert verdict(result, "OK", "N01", "A1") is None


# A2 — SEP sans plancher adjacent
def test_a2_roof_sep(result):
    r = pick(result, "ERR", "Toiture", "A2").iloc[0]
    assert r.verdict == "ALERTE"
    assert "niveau sans SP" in r.message and "au-dessus du dernier niveau avec SP" in r.message


def test_a2_not_on_floor_with_sp(result):
    assert verdict(result, "OK", "N01", "A2") is None


def test_level_rank(cfg):
    assert rules.level_rank("S02", cfg) < rules.level_rank("N00", cfg) < rules.level_rank("N07", cfg)
    assert rules.level_rank("Toiture", cfg) > rules.level_rank("N07", cfg)
    assert rules.level_rank("Mezzanine", cfg) is None


# A3 — codes inconnus : listés, exclus, jamais bloquants
def test_a3_unknown_codes(result):
    a3 = result.residuals[result.residuals.rule == "A3"].set_index("category")
    assert set(a3.index) == {"XYZ", "(vide)"}
    assert a3.loc["XYZ", "obtained"] == pytest.approx(12)
    assert len(result.unknown) == 2


def test_only_unknown_codes_does_not_crash(cfg):
    df = pd.DataFrame({"id": ["a"], "building": ["X"], "level": ["N01"], "category": ["SHAB"],
                       "area": [10.0], "kind": ["leaf"], "room_type": [None], "lot": [None], "elevation": [None]})
    res = rules.run(df, cfg)
    assert list(res.residuals.rule) == ["A3"] and res.exit_code == 1


# USPI — ordre de la chaîne par lot
def test_uspi_chain_ok(result):
    lot = "OK_N01_Apart-1"
    assert {verdict(result, "OK", "N01", u, lot) for u in ("U1", "U2", "U3", "U4")} == {"OK"}


def test_uspi_order_violations(result):
    lot = "ERR_N01_Apart-2"
    assert [verdict(result, "ERR", "N01", u, lot) for u in ("U1", "U2", "U3")] == ["ALERTE"] * 3


def test_uspi_mem_mismatch(result):
    lot = "ERR_N01_Apart-3"
    assert [verdict(result, "ERR", "N01", u, lot) for u in ("U1", "U2", "U3", "U4")] == ["OK", "OK", "OK", "ALERTE"]


# Agrégation par bâtiment et au total
def test_building_scope_with_partial_intermediate_category(result):
    # SU n'existe que sur OK N02 : l'agrégat ne doit pas comparer 70 m² de SU à 140 m² de SUP+SUS.
    assert verdict(result, "OK", "*", "R2") == "OK"
    assert verdict(result, "OK", "*", "R1") == "OK"


def test_total_scope(result):
    r = pick(result, "*", "*", "R1").iloc[0]
    assert r.expected == pytest.approx(200 + 500 + 40)  # SP de OK, ERR, TEC
    assert r.verdict == "ERREUR"


# Tolérance : écart signalé seulement si l'absolu ET le relatif sont dépassés
@pytest.mark.parametrize("diff, ref, expected", [
    (0.4, 10, False),      # sous 0,5 m²
    (0.6, 1000, False),    # sous 0,5 %
    (0.6, 10, True),
    (0.6, 0, True),
])
def test_tolerance(cfg, diff, ref, expected):
    assert rules._exceeds(diff, ref, cfg) is expected


# Code de sortie
def test_clean_model_exits_zero(synth, cfg):
    res = rules.run(synth[synth.building == "OK"], cfg)
    assert res.exit_code == 0
    assert res.residuals[res.residuals.verdict != "OK"].empty


def test_faulty_model_exits_one(result):
    assert result.exit_code == 1
