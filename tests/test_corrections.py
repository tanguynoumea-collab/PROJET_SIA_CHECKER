"""Journal de corrections (corrections.py) : opérations, totaux de niveau, refus, avant / après."""

import json

import pandas as pd
import pytest

from sia_check import cli, corrections, rules
from test_tgm import bag, leaf, node


def surfaces() -> pd.DataFrame:
    """Un niveau : SP 100 = SUP 60 + SUS 10 + SD 15 (+ 15 % de SC implicite) ; SEP 40 sans détail."""
    rows = [
        ("A_N01_SP#total", "SP", 100.0, "node", None),
        ("A_N01_SUP#total", "SUP", 60.0, "node", None),
        ("sup-1", "SUP", 40.0, "leaf", "Chambre"),
        ("sup-2", "SUP", 20.0, "leaf", "PieceDeVie"),
        ("A_N01_SUS#total", "SUS", 10.0, "node", None),
        ("sus-1", "SUS", 10.0, "leaf", "SUS"),
        ("sd-1", "SD", 15.0, "leaf", "Escalier"),
        ("A_N01_SEP#total", "SEP", 40.0, "node", None),
    ]
    return pd.DataFrame([{"id": i, "building": "A", "level": "N01", "category": c, "area": a, "kind": k,
                          "room_type": t, "lot": None} for i, c, a, k, t in rows])


def journal(*cs) -> dict:
    return {"version": 1, "corrections": [{"statut": "acceptée", **c} for c in cs]}


def check(result, rule, category="SEP"):
    r = result.residuals
    r = r[(r.level == "N01") & (r.rule == rule) & (r.category == category)]
    return r.iloc[0] if len(r) else None


def test_reclasser_leaf_moves_level_totals():
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "reclasser", "cible": {"ids": ["sup-2"]}, "vers": "SUS"}))
    s = a.surfaces.set_index("id")
    assert s.loc["sup-2", "category"] == "SUS" and s.loc["sup-2", "original_category"] == "SUP"
    assert s.loc["A_N01_SUP#total", "area"] == 40 and s.loc["A_N01_SUS#total", "area"] == 30
    assert s.loc["sup-2", "corrections"] == "c1"
    assert a.log.iloc[0].application == corrections.APPLIED and a.log.iloc[0].m2 == 20


def test_reclasser_last_leaf_does_not_revive_stale_total(cfg):
    # sus-1 est la seule SUS : sans décalage, le total SUS (10) reprendrait la main et compterait deux fois.
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "reclasser", "cible": {"ids": ["sus-1"]}, "vers": "SUP"}))
    t = rules.level_totals(rules.classify(a.kept, cfg)[0]).loc[("A", "N01")]
    assert t["SUP"] == 70 and (pd.isna(t["SUS"]) or t["SUS"] == 0)


def test_exclure_node_removes_sep_check(cfg):
    df = surfaces()
    before = rules.run(df, cfg)
    assert check(before, "R3").verdict == "ERREUR"
    a = corrections.apply(df, journal({"id": "c1", "op": "exclure", "cible": {"selection": {"category": "SEP", "kind": "node"}}}))
    assert a.surfaces.set_index("id").loc["A_N01_SEP#total", "excluded"]
    assert "A_N01_SEP#total" not in set(a.kept.id)
    assert check(rules.run(a.kept, cfg), "R3") is None


def test_exclure_leaf_lowers_its_total():
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "exclure", "cible": {"ids": ["sup-1"]}}))
    assert a.surfaces.set_index("id").loc["A_N01_SUP#total", "area"] == 20


def test_decouper_sep_to_abords(cfg):
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "découper", "cible": {"ids": ["A_N01_SEP#total"]},
                                               "vers": "SA", "aire": 30.0, "polygone": [[0, 0], [6, 0], [6, 5]]}))
    s = a.surfaces.set_index("id")
    assert s.loc["A_N01_SEP#total", "area"] == 10
    new = s.loc["A_N01_SEP#total#c1"]
    assert (new.category, new.area, new.kind, new.building, new.level) == ("SA", 30.0, "node", "A", "N01")
    after = rules.run(a.kept, cfg)
    assert check(after, "R3").diff_m2 == pytest.approx(10)
    assert not ((after.residuals.rule == "R4") & (after.residuals.category == "ST")).any()   # ST absent_ok


def test_ajuster_and_affecter():
    a = corrections.apply(surfaces(), journal(
        {"id": "c1", "op": "ajuster", "cible": {"ids": ["sd-1"]}, "aire": 12.5},
        {"id": "c2", "op": "affecter", "cible": {"selection": {"room_type": ["Chambre", "PieceDeVie"]}},
         "affectation": "Logement general"}))
    s = a.surfaces.set_index("id")
    assert s.loc["sd-1", "area"] == 12.5 and s.loc["sd-1", "original_area"] == 15
    assert list(s.loc[["sup-1", "sup-2"], "affectation"]) == ["Logement general"] * 2
    assert a.log.set_index("id").loc["c2", "surfaces"] == 2


@pytest.mark.parametrize("c, application", [
    ({"id": "x", "op": "reclasser", "cible": {"ids": ["sup-1"]}}, corrections.REFUSED),            # vers manquant
    ({"id": "x", "op": "fondre", "cible": {"ids": ["sup-1"]}}, corrections.REFUSED),               # op inconnue
    ({"id": "x", "op": "exclure", "cible": {"ids": ["absent"]}}, corrections.NOT_FOUND),
    ({"id": "x", "op": "découper", "cible": {"selection": {"category": "SUP", "kind": "leaf"}},
      "vers": "SUS", "aire": 1.0}, corrections.REFUSED),                                           # deux cibles
    ({"id": "x", "op": "découper", "cible": {"ids": ["sd-1"]}, "vers": "SI", "aire": 99.0}, corrections.REFUSED),
    ({"id": "x", "op": "exclure", "cible": {"ids": ["sup-1"]}, "statut": "proposée"}, corrections.SKIPPED),
])
def test_refused_or_skipped_corrections_change_nothing(c, application):
    j = journal(c)
    j["corrections"][0].update({k: v for k, v in c.items() if k == "statut"})
    a = corrections.apply(surfaces(), j)
    assert a.log.iloc[0].application == application
    pd.testing.assert_series_equal(a.kept.area, surfaces().area, check_names=False)


def test_journal_validation(tmp_path):
    with pytest.raises(corrections.JournalError):
        corrections.validate({"corrections": [{"id": "a"}, {"id": "a"}]})
    with pytest.raises(corrections.JournalError):
        corrections.validate({"corrections": [{"op": "exclure"}]})
    bad = tmp_path / "j.json"
    bad.write_text("{pas du json", encoding="utf-8")
    with pytest.raises(corrections.JournalError):
        corrections.load(bad)
    with pytest.raises(corrections.JournalError):
        corrections.apply(surfaces(), journal({"id": "c", "op": "exclure", "cible": {"selection": {"couleur": "x"}}}))


def test_compare_marks_resolved(cfg):
    applied, before, after = corrections.run(
        surfaces(), journal({"id": "c1", "op": "exclure", "cible": {"ids": ["A_N01_SEP#total"]}}), cfg)
    cmp = corrections.compare(before, after)
    r3 = cmp[(cmp.rule == "R3") & (cmp.level == "N01")].iloc[0]
    assert (r3.verdict_avant, r3.verdict_apres, r3.change) == ("ERREUR", "absent", "résolu")
    summary = corrections.summary(applied, before, after)
    assert summary["changements"]["résolu"] >= 1 and summary["corrections"][0]["application"] == "appliquée"


def test_cli_applies_journal(tmp_path, capsys):
    tgm = tmp_path / "mini.tgm"
    tgm.write_bytes(b"".join([
        node("SP", 100.0), leaf("A_N01_ShellByTgm-1_SpaceByTgm-1_SUP", "SUP", 85.0), node("SEP", 30.0),
    ]))
    j = tmp_path / "journal.json"
    corrections.write(journal({"id": "c1", "op": "exclure", "cible": {"selection": {"category": "SEP"}},
                               "sujet": "S2"}), j)
    code = cli.main([str(tgm), "--corrections", str(j), "--out", str(tmp_path / "out"), "--project", "Mini", "-q",
                     "--config", str(cli._default_config())])
    out = capsys.readouterr().out
    assert code == 0 and "c1" in out and "appliquée" in out
    summary = json.loads(next((tmp_path / "out").glob("*_corrections.json")).read_text(encoding="utf-8"))
    assert summary["corrections"][0]["surfaces"] == 1


def test_cli_rejects_bad_journal(tmp_path):
    tgm = tmp_path / "mini.tgm"
    tgm.write_bytes(bag("A_N01_ShellByTgm-1_SpaceByTgm-1_SUP", {"Catégorie SIA": "SUP", "Area": 1.0}))
    j = tmp_path / "journal.json"
    j.write_text('{"corrections": "non"}', encoding="utf-8")
    assert cli.main([str(tgm), "--corrections", str(j), "-q", "--config", str(cli._default_config())]) == 2


def test_affectation_reaches_mdp(cfg, tmp_path):
    import warnings

    import openpyxl

    from sia_check import mdp
    applied, _, after = corrections.run(surfaces(), journal(
        {"id": "c1", "op": "affecter", "cible": {"selection": {"room_type": "Escalier"}}, "affectation": "Inconnu"}), cfg)
    out = mdp.write(after, cfg, tmp_path / "m.xlsx")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ws = openpyxl.load_workbook(out)["SurfacesNettesSIA416"]
    rows = {r[7]: r[3] for r in ws.iter_rows(min_row=2, values_only=True)}
    assert rows["Escalier"] == "Inconnu" and rows["Chambre"] is None


def test_viewer_json_carries_before_excluded_and_log(tmp_path):
    tgm = tmp_path / "mini.tgm"
    tgm.write_bytes(b"".join([
        node("SP", 100.0), leaf("A_N01_ShellByTgm-1_SpaceByTgm-1_SUP", "SUP", 85.0), node("SEP", 30.0),
    ]))
    j = tmp_path / "journal.json"
    corrections.write(journal({"id": "c1", "op": "exclure", "cible": {"selection": {"category": "SEP"}}}), j)
    out = tmp_path / "v.json"
    assert cli.main([str(tgm), "--corrections", str(j), "--viewer-json", str(out), "-q",
                     "--config", str(cli._default_config())]) in (0, 1)
    doc = json.loads(out.read_text(encoding="utf-8"))
    lv = next(lv for lv in doc["levels"] if lv["level"] == "N01")
    assert lv["before"]["values"]["SEP"] == 30 and "SEP" not in lv["values"]
    assert [s["status"] for s in doc["surfaces"] if s["category"] == "SEP"] == ["excluded"]
    assert doc["corrections_log"][0]["application"] == "appliquée"


def test_traced_area_recomputed_from_polygon():
    shapely = pytest.importorskip("shapely")
    from shapely.geometry import box
    df = pd.DataFrame([
        {"id": "sep", "building": "A", "level": "N00", "category": "SEP", "area": 200.0, "kind": "node"},
        {"id": "seu", "building": "A", "level": "N00", "category": "SEU", "area": 50.0, "kind": "leaf"},
    ])
    shapes = {"sep": box(0, 0, 20, 10), "seu": box(15, 0, 20, 10)}
    geometry = lambda r: shapes.get(r["id"])  # noqa: E731
    poly = {"type": "Polygon", "coordinates": [[[10, 0], [30, 0], [30, 10], [10, 10], [10, 0]]]}
    j = journal({"id": "c", "op": "découper", "cible": {"ids": ["sep"]}, "vers": "SA", "aire": 80.0, "polygone": poly})
    a = corrections.apply(df, j, geometry)
    assert a.surfaces.set_index("id").loc["sep#c", "area"] == pytest.approx(50.0)     # ∩ SEP − SEU
    assert "recalculée" in a.log.iloc[0].raison
    j["corrections"][0]["aire"] = 50.3                                                 # dans la tolérance : gardée
    b = corrections.apply(df, j, geometry)
    assert b.surfaces.set_index("id").loc["sep#c", "area"] == pytest.approx(50.3) and b.log.iloc[0].raison == ""
    assert corrections.apply(df, j).surfaces.set_index("id").loc["sep#c", "area"] == pytest.approx(50.3)   # sans géométrie


def test_decouper_into_subcategory_keeps_parent(cfg):
    # SEP 40 sans détail : 34 m² classés SEU (balcons), la SEP garde son aire et le résidu R3 tombe.
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "découper", "cible": {"ids": ["A_N01_SEP#total"]},
                                               "vers": "SEU", "aire": 34.0}), cfg=cfg)
    s = a.surfaces.set_index("id")
    assert s.loc["A_N01_SEP#total", "area"] == 40
    assert s.loc["A_N01_SEP#total#c1", "category"] == "SEU"
    assert check(rules.run(a.kept, cfg), "R3").verdict in ("OK", "INFO")


def test_decouper_into_subcategory_joins_existing_leaves(cfg):
    # SP -> SUS alors que SUS a déjà du détail : la nouvelle surface est élémentaire, sinon le détail la masquerait.
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "découper", "cible": {"ids": ["A_N01_SP#total"]},
                                               "vers": "SUS", "aire": 5.0}), cfg=cfg)
    s = a.surfaces.set_index("id")
    assert s.loc["A_N01_SP#total", "area"] == 100 and s.loc["A_N01_SP#total#c1", "kind"] == "leaf"
    assert s.loc["A_N01_SUS#total", "area"] == 15
    t = rules.level_totals(rules.classify(a.kept, cfg)[0]).loc[("A", "N01")]
    assert t["SUS"] == 15


SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [4, 0], [4, 5], [0, 5], [0, 0]]]}   # 20 m²


def test_remodeler_redraws_footprint_and_type(cfg):
    # SUP sup-2 (20 m²) redessinée à 20 m² et passée en SUS : les deux totaux de niveau suivent.
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "remodeler", "cible": {"ids": ["sup-2"]},
                                               "polygone": SQUARE, "z": 3.0, "aire": 18.0, "vers": "SUS"}), cfg=cfg)
    s = a.surfaces.set_index("id")
    assert a.log.iloc[0].application == corrections.APPLIED
    assert (s.loc["sup-2", "category"], s.loc["sup-2", "area"]) == ("SUS", 20.0)   # aire recalculée du polygone
    assert s.loc["A_N01_SUP#total", "area"] == 40 and s.loc["A_N01_SUS#total", "area"] == 30
    assert s.loc["sup-2", corrections.GEOMETRY_COLUMN] == {"polygone": SQUARE, "z": 3.0}


def test_creer_adds_a_surface_to_the_level(cfg):
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "créer", "niveau": {"building": "A", "level": "N01"},
                                               "vers": "SUS", "aire": 20.0, "polygone": SQUARE, "z": 3.0}), cfg=cfg)
    s = a.surfaces.set_index("id")
    new = s.loc["A_N01_SUS#c1"]
    assert (new.category, new.kind, new.area) == ("SUS", "leaf", 20.0)   # SUS a du détail : la nouvelle s'y joint
    assert s.loc["A_N01_SUS#total", "area"] == 30
    t = rules.level_totals(rules.classify(a.kept, cfg)[0]).loc[("A", "N01")]
    assert t["SUS"] == 30


def test_creer_refuses_unknown_level_and_missing_fields(cfg):
    a = corrections.apply(surfaces(), journal(
        {"id": "c1", "op": "créer", "niveau": {"building": "Z", "level": "N09"}, "vers": "SUS", "aire": 5.0},
        {"id": "c2", "op": "créer", "vers": "SUS", "aire": 5.0},
        {"id": "c3", "op": "remodeler", "cible": {"ids": ["sup-1"]}, "aire": 5.0}), cfg=cfg)
    assert list(a.log.application) == [corrections.REFUSED] * 3


def test_drawn_surfaces_get_their_mesh_in_the_viewer(synth, cfg):
    pytest.importorskip("shapely")
    from sia_check import geom, viewer
    j = journal({"id": "c1", "op": "créer", "niveau": {"building": "ERR", "level": "N01"}, "vers": "SUS",
                 "aire": 20.0, "polygone": SQUARE, "z": 6.0})
    applied, _, after = corrections.run(synth, j, cfg)
    doc = viewer.build(after, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-26")
    s = next(x for x in doc["surfaces"] if x["id"] == "ERR_N01_SUS#c1")
    assert s["mesh"] and set(s["mesh"]["v"][2::3]) == {6.0} and len(s["mesh"]["i"]) == 6


def test_preview_from_cache_gives_balance_and_ratios(synth, cfg, tmp_path):
    # Aperçu en direct : surfaces gardées à l'analyse, journal réappliqué, bilan et ratios seuls.
    cache = tmp_path / "s.pkl"
    synth.to_pickle(cache)
    j = tmp_path / "j.json"
    j.write_text(json.dumps(journal({"id": "c1", "op": "ajuster", "cible": {"ids": ["err-toit-sep"]}, "aire": 10.0})),
                 encoding="utf-8")
    out = tmp_path / "a.json"
    assert cli.main(["--depuis-cache", str(cache), "--corrections", str(j), "--apercu", str(out)]) in (0, 1)
    a = json.loads(out.read_text(encoding="utf-8"))
    toit = next(lv for lv in a["levels"] if (lv["building"], lv["level"]) == ("ERR", "Toiture"))
    assert toit["values"]["SEP"] == 10 and toit["before"]["values"]["SEP"] == 30
    assert a["ratios"] and a["corrections_log"][0]["application"] == corrections.APPLIED


def test_remodeler_refuses_a_total_doubled_by_its_pieces(cfg):
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "remodeler", "cible": {"ids": ["A_N01_SUP#total"]},
                                               "polygone": SQUARE, "aire": 20.0}), cfg=cfg)
    assert a.log.iloc[0].application == corrections.REFUSED and "pièces" in a.log.iloc[0].raison


def test_nc_keeps_the_surface_out_of_the_sums(cfg):
    # SUP sup-2 passée en NC (non comptabilisée) : elle reste, mais ne compte plus dans la SU.
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "reclasser", "cible": {"ids": ["sup-2"]}, "vers": "NC"}), cfg=cfg)
    surf, _ = rules.classify(a.kept, cfg)
    assert bool(surf.set_index("id").loc["sup-2", "ignored"])
    assert rules.level_totals(surf).loc[("A", "N01")]["SUP"] == 40
