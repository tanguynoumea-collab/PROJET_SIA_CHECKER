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


def test_cut_parts_get_their_footprint_in_the_viewer(cfg):
    # SEP 20 × 10 dont un îlot 4 × 5 passe en NC : la part a son emprise, la SEP la perd (pas de superposition en 3D).
    pytest.importorskip("shapely")
    from sia_check import geom, viewer
    from sia_check.preuves import polygon_of
    rect = lambda x0, y0, x1, y1: [geom.Mesh(vertices=[x0, y0, 3, x1, y0, 3, x1, y1, 3, x0, y1, 3], indices=[0, 1, 2, 0, 2, 3])]  # noqa: E731
    df = pd.DataFrame([
        {"id": "sp", "building": "A", "level": "N01", "category": "SP", "area": 400.0, "kind": "node", "element_id": 1},
        {"id": "sep", "building": "A", "level": "N01", "category": "SEP", "area": 200.0, "kind": "node", "element_id": 2},
    ]).assign(room_type=None, lot=None, elevation=None)
    cache = geom.Cache()
    cache.meshes.update({1: rect(0, 10, 20, 30), 2: rect(0, 0, 20, 10)})
    j = journal({"id": "c1", "op": "découper", "cible": {"ids": ["sep"]}, "vers": "NC", "aire": 20.0, "polygone": SQUARE})
    applied, before, after = corrections.run(df, j, cfg)
    doc = viewer.build(after, cfg, cache, "T", ["t"], date="2026-10-26")
    area = {s["id"]: polygon_of(s["mesh"]).area for s in doc["surfaces"] if s["mesh"]}
    assert area["sep#c1"] == pytest.approx(20) and area["sep"] == pytest.approx(180)


def test_split_part_keeps_metadata_and_level_totals(cfg):
    # SPLIT : une part de sup-1 (40 m²) découpée vers SUP, même type : mêmes métadonnées, totaux inchangés.
    a = corrections.apply(surfaces(), journal({"id": "c1", "op": "découper", "cible": {"ids": ["sup-1"]}, "vers": "SUP",
                                               "aire": 15.0, "polygone": SQUARE}), cfg=cfg)
    s = a.surfaces.set_index("id")
    assert (s.loc["sup-1", "area"], s.loc["sup-1#c1", "area"]) == (25.0, 15.0)
    assert s.loc["sup-1#c1", "room_type"] == "Chambre" and s.loc["sup-1#c1", "kind"] == "leaf"
    assert rules.level_totals(rules.classify(a.kept, cfg)[0]).loc[("A", "N01")]["SUP"] == 60


# --------------------------------------------------------------------------- toitures SPT comptées dans la SEP

def roof_surfaces() -> pd.DataFrame:
    """SEP Treegram 40 = SEU 10 (terrasse) + SPT 30 (toiture classée, comptée par Treegram dans la SEP)."""
    df = surfaces()
    more = [("A_N01_SEU#total", "SEU", 10.0, "node", None), ("seu-1", "SEU", 10.0, "leaf", "Terrasse"),
            ("A_N01_SPT#total", "SPT", 30.0, "node", None), ("spt-1", "SPT", 30.0, "leaf", "Toiture")]
    return pd.concat([df, pd.DataFrame([{"id": i, "building": "A", "level": "N01", "category": c, "area": a,
                                         "kind": k, "room_type": t, "lot": None} for i, c, a, k, t in more])],
                     ignore_index=True)


def sep_of(df, cfg) -> float:
    return rules.level_totals(rules.classify(df, cfg)[0]).at[("A", "N01"), "SEP"]


@pytest.mark.parametrize("c, sep", [
    (None, 10.0),                                                              # SEP = 40 − toiture 30
    ({"op": "reclasser", "cible": {"ids": ["spt-1"]}, "vers": "SEU"}, 40.0),    # toiture accessible : revient en SEP
    ({"op": "reclasser", "cible": {"ids": ["spt-1"]}, "vers": "NC"}, 10.0),     # toujours hors SEP
    ({"op": "exclure", "cible": {"ids": ["spt-1"]}}, 10.0),
    ({"op": "reclasser", "cible": {"ids": ["seu-1"]}, "vers": "SPT"}, 0.0),     # terrasse devenue toiture
    ({"op": "découper", "cible": {"ids": ["A_N01_SEP#total"]}, "vers": "SPT", "aire": 5.0}, 5.0),
    ({"op": "découper", "cible": {"ids": ["spt-1"]}, "vers": "NC", "aire": 5.0}, 10.0),
])
def test_roof_spt_leaves_sep(cfg, c, sep):
    df = roof_surfaces()
    if c is not None:
        a = corrections.apply(df, journal({"id": "c1", **c}), cfg=cfg)
        assert a.log.iloc[0].application == corrections.APPLIED
        df = a.kept
    assert sep_of(df, cfg) == pytest.approx(sep)


def test_qualifier_changes_subtype_and_lot_only():
    a = corrections.apply(surfaces(), journal(
        {"id": "q1", "op": "qualifier", "cible": {"ids": ["sup-2"]}, "sous_type": "Escalier", "lot": "A.01"},
        {"id": "q2", "op": "qualifier", "cible": {"ids": ["sup-1"]}, "lot": ""}))
    s = a.surfaces.set_index("id")
    assert (s.at["sup-2", "room_type"], s.at["sup-2", "lot"]) == ("Escalier", "A.01")
    assert s.at["sup-2", "area"] == 20.0 and s.at["sup-2", "category"] == "SUP"
    assert s.at["sup-1", "lot"] is None
    assert list(a.log.application) == ["appliquée", "appliquée"]


def test_qualifier_nature_moves_level_total():
    a = corrections.apply(surfaces(), journal({"id": "q1", "op": "qualifier", "cible": {"ids": ["sup-2"]}, "nature": "node"}))
    s = a.surfaces.set_index("id")
    assert s.at["sup-2", "kind"] == "node"
    assert s.at["A_N01_SUP#total", "area"] == 40.0     # le total Treegram ne compte plus la surface sortie du détail
    assert s.at["sup-2", "area"] == 20.0


@pytest.mark.parametrize("c", [
    {"id": "q", "op": "qualifier", "cible": {"ids": ["sup-2"]}},
    {"id": "q", "op": "qualifier", "cible": {"ids": ["sup-2"]}, "nature": "pièce"},
])
def test_qualifier_refused_without_valid_field(c):
    a = corrections.apply(surfaces(), journal(c))
    assert a.log.application.iloc[0] == "refusée"


def test_remodeler_carries_metadata(cfg):
    poly = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [4, 0], [4, 5], [0, 5], [0, 0]]]]}
    a = corrections.apply(surfaces(), journal({"id": "r1", "op": "remodeler", "cible": {"ids": ["sd-1"]}, "aire": 20.0,
                                              "polygone": poly, "sous_type": "Escalier", "lot": None}), cfg=cfg)
    s = a.surfaces.set_index("id")
    assert (s.at["sd-1", "area"], s.at["sd-1", "room_type"]) == (20.0, "Escalier")
