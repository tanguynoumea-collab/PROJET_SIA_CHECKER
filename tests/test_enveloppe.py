"""Enveloppe (V3_PLAN §10) : façades SFN et vitrages SRV, lecture .tgm, contrôles E1–E5, ratios, export MDP."""

import pandas as pd
import pytest

from sia_check import mdp, reader, rules

from test_tgm import CAT, bag, leaf, node


def sfn(gross, net, res, perimeter=None, height=None):
    props = {"GrossArea": gross, "NetArea": net, "ReservationsArea": res}
    if perimeter is not None:
        props |= {"Perimeter": perimeter, "GrossHeight": height}
    return bag("SFN", props)


def test_srv_read_only_right_after_its_sfn(tmp_path, cfg):
    p = tmp_path / "env.tgm"
    p.write_bytes(b"".join([
        bag("SRV", {"Area": 99.0}),                       # arbre de quantités : pas une surface SIA
        node("SP", 100.0),
        sfn(120.0, 90.0, 30.0, 40.0, 3.0),
        bag("SRV", {"Area": 29.5}),                       # vitrages du niveau : juste après la SFN
        leaf("A_N01_ShellByTgm-1_SpaceByTgm-1_SUP", "SUP", 80.0),
        bag("SFB2", {"Area": 120.0, "Perimeter": 40.0}),
        bag("SRV", {"Area": 50.0}),                       # après un autre total : ignoré
    ]))
    df = reader.read(p, cfg).set_index("category")
    assert df.loc["SRV", "area"] == 29.5 and df.loc["SRV", "level"] == "N01" and df.loc["SRV", "kind"] == "node"
    assert df.loc["SFN", "area"] == 120.0 and df.loc["SFN", "net_area"] == 90.0


def frame(rows):
    base = {"lot": None, "elevation": None, "room_type": None, "gross_area": None, "net_area": None,
            "reservations_area": None, "perimeter": None, "gross_height": None}
    return pd.DataFrame([base | r for r in rows])


def level(bld, lvl, sp, gross=None, net=None, res=None, srv=None, per=None, h=None):
    rows = [{"id": f"{bld}{lvl}sp", "building": bld, "level": lvl, "category": "SP", "area": sp, "kind": "node"},
            {"id": f"{bld}{lvl}sup", "building": bld, "level": lvl, "category": "SUP", "area": sp * 0.8, "kind": "leaf"}]
    if gross is not None:
        rows.append({"id": f"{bld}{lvl}sfn", "building": bld, "level": lvl, "category": "SFN", "area": gross, "kind": "node",
                     "gross_area": gross, "net_area": net, "reservations_area": res, "perimeter": per, "gross_height": h})
    if srv is not None:
        rows.append({"id": f"{bld}{lvl}srv", "building": bld, "level": lvl, "category": "SRV", "area": srv, "kind": "node"})
    return rows


def checks(res, rule):
    r = res.residuals
    return r[r.rule == rule].set_index(["building", "level"]).verdict.to_dict()


def test_envelope_checks(cfg):
    df = frame(level("A", "N00", 100, gross=120, net=90, res=30, srv=29.5, per=40, h=3)        # tout boucle
               + level("A", "N01", 100, gross=120, net=80, res=30, srv=20, per=40, h=2.5)      # E1, E2, E3
               + level("A", "N02", 100, gross=50, net=0, res=50, srv=60)                      # E4
               + level("A", "N03", 100)                                                       # E5 : pas de façade
               + level("A", "S01", 100))                                                      # sous-sol : pas d'E5
    res = rules.run(df, cfg)
    assert checks(res, "E1") == {("A", "N00"): "OK", ("A", "N01"): "ERREUR", ("A", "N02"): "OK"}
    assert checks(res, "E2")[("A", "N00")] == "OK" and checks(res, "E2")[("A", "N01")] == "INFO"
    assert checks(res, "E3") == {("A", "N00"): "OK", ("A", "N01"): "ALERTE"}
    assert checks(res, "E4")[("A", "N02")] == "ERREUR"
    assert checks(res, "E5") == {("A", "N03"): "ALERTE"}
    # hors des sommes : la SFN ne pèse sur aucune règle de niveau
    assert not res.residuals[res.residuals.rule.str.startswith("R")].category.isin(["SFN", "SRV"]).any()


def test_no_envelope_no_checks(cfg):
    res = rules.run(frame(level("A", "N00", 100)), cfg)
    assert not res.residuals.rule.str.startswith("E").any()


def test_envelope_ratios(cfg):
    df = frame(level("A", "N00", 100, gross=120, net=90, res=30, srv=30)
               + level("A", "S01", 200, gross=50, net=50, res=0, srv=0))     # sous-sol : hors ratios hors-sol
    r = rules.run(df, cfg).ratios.set_index(["building", "id"])
    assert r.loc[("*", "SRV/SFN"), "value"] == pytest.approx(30 / 120)
    assert r.loc[("*", "SRV/PLEINE"), "value"] == pytest.approx(30 / 90)     # pleine = brute − vitrages
    assert r.loc[("*", "SFN/SP"), "value"] == pytest.approx(120 / 100)


def test_mdp_glazing_is_srv(cfg):
    df = frame(level("A", "N00", 100, gross=120, net=90, res=30, srv=29.5, per=40, h=3) + level("A", "N01", 100, gross=120, net=90, res=30))
    recs = mdp.enveloppe_records(rules.run(df, cfg), cfg, 1)
    vitree = {r["Etage"]: r["Surface vitrée"] for r in recs}
    assert vitree == {"N00": 29.5, "N01": 30}      # SRV, sinon les réservations de la façade


def test_srv_is_an_envelope_category(cfg):
    assert cfg.categories["SRV"]["family"] == "enveloppe" and cfg.categories["SFN"]["ignore"]
    assert CAT  # même propriété de catégorie que le lecteur


def test_envelope_in_level_balance(cfg):
    from sia_check import report
    df = frame(level("A", "N00", 100, gross=120, net=90, res=30, srv=29.5) + level("A", "N01", 100))
    env = report.envelope_by_level(rules.run(df, cfg))
    assert env.loc[("A", "N00")].to_dict() == {"SFN": 120, "SFN_NETTE": 90, "SFN_RESERVATIONS": 30, "SRV": 29.5}
    assert ("A", "N01") not in env.index                       # pas de façade : pas de ligne
