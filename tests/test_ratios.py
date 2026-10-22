"""Ratios informatifs (ratios.py) sur le bâtiment OK du jeu synthétique : SP 200, SU 140, SD 30, SI 10, SC 20."""

import pandas as pd
import pytest

from sia_check import ratios, rules


def ratio(result, rid, scope="OK") -> pd.Series:
    r = result.ratios
    r = r[(r.building == scope) & (r.id == rid)]
    assert len(r) == 1, r
    return r.iloc[0]


def test_one_row_per_scope_and_ratio(result, cfg):
    assert list(result.ratios.columns) == ratios.RATIO_COLUMNS
    scopes = set(result.ratios.building)
    assert ratios.ALL in scopes and "OK" in scopes
    assert (result.ratios.building == "OK").sum() == len(cfg.ratios)


def test_sn_over_sp_above_reference(result):
    r = ratio(result, "SN/SP")
    assert r.value == pytest.approx(0.9) and r.num_m2 == pytest.approx(180) and r.den_m2 == pytest.approx(200)
    assert r.status == "haut"


def test_sc_read_when_present(result):
    r = ratio(result, "SC/SP")
    assert r.value == pytest.approx(0.1) and r.status == "bas"


def test_sc_derived_as_sp_minus_sn(synth, cfg):
    res = rules.run(synth[synth.category != "SC"], cfg)
    assert ratio(res, "SC/SP").num_m2 == pytest.approx(20)


def test_lots_count_and_area_per_lot(result):
    r = ratio(result, "SNH/lot")
    assert r.den_m2 == 1 and r.value == pytest.approx(80) and r.unit == "m2" and r.status == "info"


def test_status():
    assert ratios._status(None, [0, 1]) == "n/a"
    assert ratios._status(0.5, None) == "info"
    assert ratios._status(0.5, [0.6, 0.8]) == "bas"
    assert ratios._status(0.7, [0.6, 0.8]) == "ok"
    assert ratios._status(0.9, [0.6, 0.8]) == "haut"


def test_no_ratios_configured(synth, cfg):
    cfg.ratios = []
    assert rules.run(synth, cfg).ratios.empty
