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


def test_stairs_per_housing_floor(cfg):
    """Cages d'escalier : SD de sous-type escalier ; étages de logements (SUP et lots) seulement."""
    rows = [  # (bâtiment, niveau, catégorie, aire, sous-type, lot)
        ("A", "N01", "SP", 300.0, None, None), ("A", "N01", "SUP", 100.0, "PieceDeVie", "A.11"),
        ("A", "N01", "SUP", 100.0, "PieceDeVie", "A.12"), ("A", "N01", "SUP", 50.0, "Chambre", "A.13"),
        ("A", "N01", "SD", 20.0, "Escalier", None), ("A", "N01", "SD", 18.0, "Cage d'escaliers", None),
        ("A", "N01", "SUP", 6.0, "Escalier", "A.13"),                       # escalier de duplex : pas une cage
        ("A", "N02", "SP", 300.0, None, None), ("A", "N02", "SUP", 200.0, "PieceDeVie", "A.21"),
        ("A", "N02", "SD", 20.0, "CirculationH", None),                     # étage de logements sans cage
        ("A", "S01", "SP", 300.0, None, None), ("A", "S01", "SD", 20.0, "Escalier", None),   # sous-sol sans SUP
    ]
    df = pd.DataFrame([{"id": f"s{k}", "building": b, "level": l, "category": c, "area": a,
                        "kind": "node" if c == "SP" else "leaf", "room_type": t, "lot": lot}
                       for k, (b, l, c, a, t, lot) in enumerate(rows)])
    res = rules.run(df, cfg)
    st = ratios.stairs(res.surfaces, res.totals)
    assert st.loc[("A", "N01"), ["CAGES", "LOGEMENTS", "SUP_CAGES", "LOG_CAGES"]].tolist() == [2, 3, 256, 3]
    assert st.loc[("A", "N02"), "CAGES"] == 0 and pd.isna(st.loc[("A", "N02"), "SUP_CAGES"])
    assert st.loc[("A", "S01")].isna().all()
    r = res.ratios.set_index(["building", "id"])
    assert r.at[("*", "SUP/cage"), "value"] == pytest.approx(128.0)
    assert r.at[("*", "log/cage"), "value"] == pytest.approx(1.5)


def test_references_follow_the_typology():
    """Repères tirés des projets de logement : sans typologie, aucun ; pour un parking, aucun ; refs propres sinon."""
    from sia_check import ratios
    r = {"id": "SD/SP", "ref": [0.05, 0.12], "refs": {"activites": [0.08, 0.2]}}
    assert ratios.typology_key("Logement Mixte (>10% autres affectations)") == "mixte"
    assert ratios.typology_key("Activités (Bureaux, Artisanat, Commerce)") == "activites"
    assert ratios.typology_key("") is None and ratios.typology_key("Autre") == "autre"
    assert ratios.reference(r, "logement") == [0.05, 0.12] and ratios.reference(r, "mixte") == [0.05, 0.12]
    assert ratios.reference(r, "activites") == [0.08, 0.2] and ratios.reference(r, "autre") is None
    assert ratios.reference(r, None) is None
    assert ratios._status(0.3, None, None) == "typologie" and ratios._status(0.3, None, "autre") == "info"
    assert ratios._status(0.3, [0.05, 0.12], "logement") == "haut"


def test_typology_is_suggested_from_the_surfaces():
    from sia_check import ratios
    park = pd.DataFrame([{"kind": "leaf", "code": "SUS", "area": 980.0, "room_type": "Parking", "lot": None},
                         {"kind": "leaf", "code": "SUS", "area": 20.0, "room_type": "LocauxCommuns", "lot": None}])
    assert ratios.suggest(park) == ("Autre", "parking : 98 % de la SU")
    flats = pd.DataFrame([{"kind": "leaf", "code": "SUP", "area": 95.0, "room_type": "Chambre", "lot": "A"},
                          {"kind": "leaf", "code": "SUS", "area": 5.0, "room_type": "Cave", "lot": None}])
    assert ratios.suggest(flats)[0] == "Logement (100-90% SU)"
