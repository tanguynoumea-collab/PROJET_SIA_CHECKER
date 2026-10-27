"""Sujets et corrections de base (sujets.py)."""

import json

import pytest

from sia_check import corrections, geom, rules, sujets, viewer


@pytest.fixture
def subjects(result, cfg):
    doc = viewer.build(result, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-21")
    return {s["id"]: s for s in sujets.build(doc, cfg)["subjects"]}


def test_grouping_by_cause(subjects):
    assert sorted(subjects["toitures"]["points"]) == ["A2|ERR|Toiture||SEP", "R3|ERR|Toiture||SEP"]
    assert set(subjects["abords"]["points"]) == {"A1|ERR|N00||SEP", "R3|ERR|N00||SEP"}
    assert "sc-implicite" not in subjects        # construction implicite : pas un point d'attention, pas de sujet
    agg = subjects.get("agregats", {"points": []})["points"]
    assert all("|*|" in k for k in agg)
    assert not any(k.startswith("A3") for k in agg)     # codes inconnus : à part
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
    cs = sj["subjects"][0]["corrections"]
    # Deux morceaux d'un seul tenant, de part et d'autre du plancher : une correction chacun, à décider à part.
    assert sj["geometry"] and [c["aire"] for c in cs] == pytest.approx([100.0, 50.0])
    assert [c["id"] for c in cs] == ["abords-A-N00-1", "abords-A-N00-2"]
    assert [c["morceau"] for c in cs] == ["1/2", "2/2"] and {c["groupe"] for c in cs} == {"abords-A-N00"}
    assert all(c["polygone"]["type"] == "Polygon" for c in cs)
    json.dumps(cs)                                                 # sérialisable tel quel dans le journal


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
    tgm.write_bytes(b"".join([node("SP", 0.0), node("SEP", 30.0),      # 20 m² de SEP hors toiture SPT
                              leaf("A_Toiture_ShellByTgm-1_SpaceByTgm-1_SPT", "SPT", 10.0)]))
    out = tmp_path / "sujets.json"
    cli.main([str(tgm), "-q", "--sujets", str(out), "--config", str(cli._default_config())])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["corrections"] and data["corrections"][0]["sujet"] == "toitures"
    assert corrections.validate(data) is data


# --------------------------------------------------------------------------- revue IA (bloc « sujets »)

def base_subjects():
    def corr(cid, sid, **kw):
        return {"id": cid, "op": "exclure", "cible": {"ids": [f"{cid}-sep"]}, "sujet": sid, "origine": "règle",
                "statut": "proposée", "m2": 10.0, **kw}
    return {"version": 1, "subjects": [
        {"id": "toitures", "titre": "T", "cause": "toitures", "action": "corriger", "explication": "", "m2": 30.0,
         "points": ["A2|A|Toiture||SEP", "A2|B|Toiture||SEP"],
         "corrections": [corr("toit-a", "toitures"), corr("toit-b", "toitures"), corr("toit-c", "toitures")]},
        {"id": "abords", "titre": "A", "cause": "abords", "action": "corriger", "explication": "", "m2": 50.0,
         "points": ["A1|A|N00||SEP"],
         "corrections": [corr("abords-a", "abords", op="découper", vers="SA", aire=50.0, polygone={"type": "Polygon"})]},
        {"id": "sc-implicite", "titre": "SC", "cause": "sc", "action": "aucune", "explication": "", "m2": 0.0,
         "points": ["R1|A|N01||SP"], "corrections": []},
    ]}


SURFACES = {"toit-a-sep", "toit-b-sep", "toit-c-sep", "abords-a-sep", "x-sep"}


def review(**sujets_):
    return {"revue_ia": "2026-10-22", "modele": "test", "points": {
        "A2|A|Toiture||SEP": {"verdict_ia": "vrai sujet", "sujet": "S2"},
        "A2|B|Toiture||SEP": {"verdict_ia": "vrai sujet", "sujet": "S2"},
        "A1|A|N00||SEP": {"verdict_ia": "vrai sujet", "sujet": "S1"},
        "R1|A|N01||SP": {"verdict_ia": "faux positif", "sujet": None}}, "sujets": sujets_}


def test_review_default_keeps_all_and_rejects_one():
    out = sujets.apply_review(base_subjects(), review(S2={
        "titre": "Toitures", "base": ["toitures"], "par_defaut": "garder",
        "decisions": [{"id": "toit-b", "decision": "rejeter", "explication": "toiture-jardin"}]}), SURFACES)
    s2 = out["subjects"][0]
    assert s2["id"] == "S2" and s2["points"] == ["A2|A|Toiture||SEP", "A2|B|Toiture||SEP"]
    status = {c["id"]: (c["statut"], c["origine"], c["sujet"]) for c in s2["corrections"]}
    assert status == {"toit-a": ("proposée", "ia", "S2"), "toit-b": ("rejetée", "ia", "S2"), "toit-c": ("proposée", "ia", "S2")}
    assert s2["m2"] == 20.0
    assert "toitures" not in {s["id"] for s in out["subjects"]}          # vidé par la revue
    assert {s["id"] for s in out["subjects"]} >= {"abords", "sc-implicite"}   # non repris : restent tels quels
    assert out["revue"]["problemes"] == [] and out["revue"]["decisions"] == 3


def test_review_takes_the_points_of_a_subject_it_emptied():
    # S1 reprend toutes les propositions d'« abords » sans citer son point : le point suit, pas de doublon vide
    pts = review(S1={"titre": "Abords", "base": ["abords"], "par_defaut": "garder", "decisions": []})
    pts["points"].pop("A1|A|N00||SEP")
    out = sujets.apply_review(base_subjects(), pts, SURFACES)
    by = {s["id"]: s for s in out["subjects"]}
    assert "abords" not in by and by["S1"]["points"] == ["A1|A|N00||SEP"]
    # un sujet IA sans point ni correction n'est pas montré
    out = sujets.apply_review(base_subjects(), review(S6={"titre": "SC", "action": "aucune"}), SURFACES)
    assert "S6" not in {s["id"] for s in out["subjects"]}


def test_review_modify_add_and_invalid_decisions():
    out = sujets.apply_review(base_subjects(), review(S1={
        "titre": "Abords", "base": ["abords"],
        "decisions": [
            {"id": "abords-a", "decision": "modifier", "aire": 42.0, "explication": "terrasse privative gardée"},
            {"id": "s1-x", "decision": "ajouter", "op": "découper", "cible": {"ids": ["x-sep"]}, "vers": "SA", "aire": 5.0},
            {"id": "s1-y", "decision": "ajouter", "op": "exclure", "cible": {"ids": ["inventée"]}},
            {"id": "s1-z", "decision": "ajouter", "op": "découper", "cible": {"ids": ["x-sep"]}},   # vers, aire manquants
            {"id": "inconnue", "decision": "garder"},
            {"id": "abords-a", "decision": "garder"},
            {"id": "toit-a", "decision": "fusionner"},
        ]}), SURFACES)
    s1 = next(s for s in out["subjects"] if s["id"] == "S1")
    mod = next(c for c in s1["corrections"] if c["id"] == "abords-a")
    assert (mod["aire"], mod["base"], mod.get("a_retracer"), "polygone" in mod) == (42.0, {"aire": 50.0, "explication": None}, True, False)
    assert next(c for c in s1["corrections"] if c["id"] == "s1-x")["revue"] == "ajoutée"
    bad = {p["id"]: p["raison"] for p in out["revue"]["problemes"]}
    assert set(bad) == {"s1-y", "s1-z", "inconnue", "abords-a", "toit-a"}
    assert bad["abords-a"] == "proposition décidée deux fois" and bad["s1-y"] == "cible inconnue"
    toits = next(s for s in out["subjects"] if s["id"] == "toitures")   # non repris : propositions intactes
    assert len(toits["corrections"]) == 3 and toits["corrections"][0]["origine"] == "règle"


def test_reviewed_journal_skips_rejected(synth, cfg, result):
    doc = viewer.build(result, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-21")
    base = sujets.build(doc, cfg)
    roof = base["subjects"][0]["corrections"][0]["id"]
    out = sujets.apply_review(base, {"points": {}, "sujets": {"S2": {"base": ["toitures"], "decisions": [
        {"id": roof, "decision": "rejeter", "explication": "terrasse accessible"}]}}}, {s["id"] for s in doc["surfaces"]})
    j = sujets.journal(out)
    for c in j["corrections"]:
        c["statut"] = "acceptée" if c["statut"] == "proposée" else c["statut"]
    applied, _, _ = corrections.run(synth, j, cfg)
    log = applied.log.set_index("id")
    assert log.loc[roof, "application"] == corrections.SKIPPED and log.loc[roof, "statut"] == "rejetée"


def test_covered_aggregates_are_not_points(result, cfg):
    doc = viewer.build(result, cfg, geom.Cache(), "Synth", ["synth.csv"], date="2026-10-21")
    keys = {i["key"] for i in doc["issues"]}
    assert "R1|ERR|N01||SP" in keys or any(k.startswith("R1|ERR|") for k in keys)
    covered = result.residuals[rules.covered_aggregates(result.residuals)]
    assert len(covered) and not keys & {viewer.issue_key(r) for _, r in covered.iterrows()}


def test_unclassified_residual_proposals(subjects, synth, cfg):
    # ERR N00 : SP 2 classée à moitié -> une découpe vers SUS par défaut, dans le sujet R1-SP qui passe « corriger ».
    sp = subjects["R1-SP"]
    assert sp["action"] == "corriger" and [c["id"] for c in sp["corrections"]] == ["non-classe-ERR-N00-SP"]
    c = sp["corrections"][0]
    assert (c["op"], c["vers"]) == ("découper", "SUS") and c["aire"] > 0
    applied, before, after = corrections.run(synth, {"corrections": [{**c, "statut": "acceptée"}]}, cfg)
    assert set(applied.log.application) == {corrections.APPLIED}
    r = after.residuals
    assert not len(r[(r.building == "ERR") & (r.level == "N00") & (r.rule == "R1") & (r.verdict == "ERREUR")])
