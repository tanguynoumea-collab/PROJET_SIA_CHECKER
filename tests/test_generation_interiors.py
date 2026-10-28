"""Moteur de génération, phase 21 : nature et classement des espaces, SP, assemblage au modèle Treegram."""

import json
from pathlib import Path

import pytest
from shapely.geometry import box

from sia_check import cli, config, reader, rules, siagen
from sia_check.generation import assemble, classify, engine, ingest, interiors, plans
from sia_check.generation.ingest import Item, Storey
from conftest import ROOT
from ifc_synth import build


@pytest.fixture(scope="module")
def gen_cfg():
    return config.load(ROOT / "config.yaml").generation


@pytest.fixture(scope="module")
def generated(tmp_path_factory, gen_cfg):
    tmp = tmp_path_factory.mktemp("gen")
    return engine.generate(build(tmp / "synth.ifc"), gen_cfg, tmp / "out", "Synth")


def space(gid, name=None, long_name=None, lot=None, predefined=None, **props):
    return Item(gid, "IfcSpace", name, "A", "N00", long_name=long_name, lot=lot, predefined=predefined, props=props)


@pytest.fixture(scope="module")
def k(gen_cfg):
    return classify.Classifier(gen_cfg)


@pytest.mark.parametrize("item, code, typ, source", [
    (space("1", "SEJ", "Séjour - Cuisine", lot="1A.01.02"), "SUP", "PieceDeVie", "dictionnaire"),
    (space("2", "CHS", "Chambre", lot="1A.01.02"), "SUP", "Chambre", "dictionnaire"),
    (space("3", "SDB", "Salle de bain", lot="1A.01.02"), "SUP", "PieceSecondaire_4PointsEau", "dictionnaire"),
    (space("4", "WCD", "WC/D", lot="1A.01.02"), "SUP", "PieceSecondaire_3PointsEau", "dictionnaire"),
    (space("5", "PAL", "Palier", lot="1A.01.00"), "SD", "CirculationH", "dictionnaire"),       # palier du niveau
    (space("6", "CAV", "Cave", lot="1A.99.00"), "SUS", "SUS", "dictionnaire"),
    (space("7", "GTC", "gaine", lot="1A.01.02"), "SI", "Gaine", "dictionnaire"),
    (space("8", "X", "Local", **{"Données.SIA416": "SUS"}), "SUS", "SUS", "propriete"),
    (space("9", "L04_A_CON_001", "SUS_CON"), "SUS", "SUS", "prefixe"),
    (space("10", "ASC", "Ascenseur", **{"Pset_SpaceCommon.Category": "Surface de dégagement"}), "SD", "Ascenseur", "categorie"),
    (space("11", "Raum 12", None), "NONCLASSE", None, None),
])
def test_room_classification(k, item, code, typ, source):
    d = k.decide(item, False)
    assert (d.nature, d.code, d.type, d.source) == ("piece", code, typ, source)


def test_property_beats_dictionary_and_disagreement_lowers_confidence(k):
    d = k.decide(space("1", "E0", "CAGE DES SECOURS", **{"Données.SIA416": "SUP"}), False)
    assert (d.code, d.source) == ("SUP", "propriete") and d.conflicts and d.confidence == pytest.approx(0.75)


def test_treegram_convention_apartment_hall_is_sup_distribution(k):
    d = k.decide(space("1", "HAL", "Hall", lot="1A.01.02", **{"Pset_SpaceCommon.Category": "Surface de dégagement"}), False)
    assert (d.code, d.type, d.source) == ("SUP", "Distribution", "convention") and "SD" in d.conflicts[-1]


@pytest.mark.parametrize("item, container, nature", [
    (space("1", "LOG", "Surface de plancher", predefined="GFA"), True, "plancher"),
    (space("2", "LOG", "SBH"), True, "logement"),
    (space("3", "LOG", "Surface externe de plancher", predefined="GFA",
           **{"Pset_SpaceCommon.Category": "Surface externe de plancher"}), True, "exterieur"),
    (space("4", "LOG", "Loggia", lot="1A.01.02"), False, "exterieur"),
    (space("5", "TER", "Surface de terrain", **{"Pset_SpaceCommon.Category": "Surface de terrain"}), False, "site"),
    (space("6", "X", "Déchets", **{"Données.SIA416": "SEU"}), False, "exterieur"),
])
def test_natures(k, item, container, nature):
    assert k.decide(item, container).nature == nature


def test_sp_from_floor_spaces_minus_exteriors(gen_cfg):
    st = Storey("st", "N00", "A", 0.0)
    plan = plans.Plan(st)
    floor = space("f", "LOG", "Surface de plancher", predefined="GFA")
    loggia = space("l", "LOG", "Loggia", lot="1A.00.01")
    room = space("r", "SEJ", "Séjour", lot="1A.00.01")
    plan.spaces = [plans.Placed(floor, box(0, 0, 10, 10)), plans.Placed(loggia, box(8, 0, 10, 3)),
                   plans.Placed(room, box(0, 0, 8, 10))]
    decisions = {"f": classify.Decision("f", "plancher"), "l": classify.Decision("l", "exterieur"),
                 "r": classify.Decision("r", "piece", "SUP")}
    sp, why = interiors.surface_de_plancher(plan, decisions, 0.3, 4.0)
    assert sp.area == pytest.approx(94.0) and "moins 6.00 m² d'extérieurs" in why


def test_synthetic_model_generated(generated):
    c = generated.data["counts"]
    assert (c["pieces"], c["unclassified"]) == (5, 0)
    by = {(s["storey"], s["long_name"]): (s["code"], s["type"], s["in_lot"]) for s in generated.data["spaces"]}
    assert by[("N00", "Séjour")] == ("SUP", "PieceDeVie", True)
    assert by[("N00", "Chambre")] == ("SUP", "Chambre", True)
    assert by[("N00", "Couloir")] == ("SD", "CirculationH", False)     # 1A.99.00 : parties communes
    assert by[("N01", "Local technique")] == ("SI", "Local", False)
    n00 = next(lv for lv in generated.data["levels"] if lv["storey"] == "N00")
    # pièces 8 × 5,5 et mur de façade 8 × 0,2 : contour extérieur 8 × 5,7 ; la chambre compte son aire déclarée
    # (10 m², generation.sp.area_source: declared), pas son emprise (12 m²)
    assert n00["sp_m2"] == pytest.approx(45.6) and n00["totals"] == {"SD": 12.0, "SUP": 30.0}


def test_generated_project_follows_the_treegram_model(generated):
    doc = json.loads(generated.siagen.read_text(encoding="utf-8"))
    n00 = [e for e in doc["elements"] if e["level"] == "N00"]
    assert [e["name"] for e in n00 if e["kind"] == "node"] == ["SUP", "SUS", "SD", "SI", "SUT", "SP"]
    leaves = {e["props"]["IfcGlobalId"]: e for e in n00 if e["kind"] == "leaf"}
    names = sorted(e["name"] for e in leaves.values())
    assert names == ["A_N00_ShellByTgm-01_SpaceByTgm-1_SUP", "A_N00_ShellByTgm-01_SpaceByTgm-2_SUP",
                     "A_N00_ShellByTgm-02_SpaceByTgm-1_SD"]
    sup = next(e for e in leaves.values() if e["props"].get("Type") == "Chambre")
    assert sup["props"]["ApartmentByTgm"] == "A_N00_Apart-01" and sup["props"]["Area"] == 10.0 and sup["meshes"]
    assert all(e["meshes"] for e in n00 if e["name"] == "SP")


def test_generated_project_is_checked_like_a_treegram_project(generated, cfg):
    df = reader.read(generated.siagen, cfg)
    res = rules.run(df, cfg)
    r1 = res.residuals[(res.residuals.rule == "R1") & (res.residuals.level == "N00")].iloc[0]
    assert r1.expected == pytest.approx(45.6) and r1.diff_m2 == pytest.approx(3.6) and r1.verdict == "INFO"
    assert set(df[df.kind == "leaf"].lot.dropna()) == {"A_N00_Apart-01"}


def test_mesh_of_polygon_with_hole():
    g = box(0, 0, 10, 10).difference(box(4, 4, 6, 6))
    m = assemble.mesh_of(g, 3.0)
    tri_area = 0.0
    v = m.vertices
    for t in range(0, len(m.indices), 3):
        a, b, c = (v[3 * m.indices[t + j]: 3 * m.indices[t + j] + 2] for j in range(3))
        tri_area += abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
    assert tri_area == pytest.approx(96.0) and set(v[2::3]) == {3.0}


def test_cli_generer(tmp_path, capsys):
    ifc = build(tmp_path / "synth.ifc")
    assert cli.main(["--generer", str(ifc), "--out", str(tmp_path / "out")]) == 0
    folder = tmp_path / "out" / "synth"
    assert (folder / f"synth{siagen.SUFFIX}").is_file() and (folder / "generation" / "rapport.json").is_file()
    assert "Sources du classement" in capsys.readouterr().out
    assert cli.main(["-q", str(folder), "--viewer-json", str(tmp_path / "v.json")]) in (0, 1)


def test_cli_generer_blocked_without_spaces(tmp_path):
    import ifcopenshell.api as api
    f = api.run("project.create_file", version="IFC4")
    api.run("root.create_entity", f, ifc_class="IfcProject", name="Vide")
    p = tmp_path / "vide.ifc"
    f.write(str(p))
    assert cli.main(["--generer", str(p), "--out", str(tmp_path)]) == 1


def test_level_codes_follow_treegram(gen_cfg):
    st = [Storey(n, n, "1", z) for n, z in [("S01", 609.0), ("E00", 612.0), ("E01", 615.0), ("TTR", 618.0)]]
    assert assemble.level_codes(st, {"S01", "E00", "E01"}, gen_cfg) == {
        "S01": "S01", "E00": "N00", "E01": "N01", "TTR": "Toiture"}
    cga = [Storey(n, n, "L04", z) for n, z in [("Niveau -1 - E00", -3.8), ("Niveau 0 - E01", -0.8), ("Niveau 1 - E02", 2.2)]]
    assert list(assemble.level_codes(cga, set(), gen_cfg).values()) == ["S01", "N00", "N01"]
    odd = [Storey("a", "Rouge", "B", 0.0), Storey("b", "Bleu_2", "B", 3.0)]
    assert assemble.level_codes(odd, set(), gen_cfg) == {"a": "Rouge", "b": "Bleu-2"}   # sans rez : noms gardés


def test_lot_from_first_property_found_and_storey_scope():
    spec = [{"pset": "Pset_HRS", "property": "NumeroPiece", "pattern": r"^(?P<lot>[^.]+\.[^.]+\.[^.]+)\."},
            {"pset": "Pset_SpaceOccupancyRequirements", "property": "Appartement", "scope": "storey"}]
    assert ingest._lot({"Pset_HRS.NumeroPiece": "1A.01.02.03"}, spec, "E01") == "1A.01.02"
    assert ingest._lot({"Pset_SpaceOccupancyRequirements.Appartement": "2"}, spec, "1erEtage") == "1erEtage/2"
    assert ingest._lot({"Pset_SpaceOccupancyRequirements.Appartement": ""}, spec, "1erEtage") is None


def test_la_batie_conventions(k):
    sjr = space("1", "4", "SJR", lot="1erEtage/2", **{"Pset_SpaceCommon.Category": "416-SN-Surface utile principale"})
    assert (k.decide(sjr, False).code, k.decide(sjr, False).in_lot) == ("SUP", True)
    commun = space("2", None, "COU", lot="1erEtage/C", **{"Pset_SpaceCommon.Category": "416-SN-Surface de degagement"})
    assert (k.decide(commun, False).code, k.decide(commun, False).in_lot) == ("SD", False)
    balcon = space("3", "5", "LUP", **{"Pset_SpaceCommon.Category": "416-SBP-Surface de plancher externe"})
    assert k.decide(balcon, True).nature == "exterieur"


def test_rooms_outside_the_drawn_floor_area_are_added():
    plan = plans.Plan(Storey("st", "N00", "A", 0.0))
    floor = space("f", "LOG", "Surface de plancher", predefined="GFA")
    room, buggy = space("r", "SEJ", "Séjour"), space("b", "BUA", "Buanderie")
    plan.spaces = [plans.Placed(floor, box(0, 0, 10, 10)), plans.Placed(room, box(0, 0, 9.8, 9.8)),
                   plans.Placed(buggy, box(10.2, 0, 12.2, 3))]
    wall = Item("w", "IfcWall", "Mur", "A", "st")
    plan.elements = [plans.Placed(wall, box(10, 0, 10.2, 10))]
    decisions = {"f": classify.Decision("f", "plancher"), "r": classify.Decision("r", "piece", "SUS"),
                 "b": classify.Decision("b", "piece", "SUS")}
    sp, why = interiors.surface_de_plancher(plan, decisions, 0.3, 4.0)
    # 100 m² dessinés + buanderie 6 m² + le mur qui la sépare, sur sa longueur (0,2 × 3,5 environ)
    assert 106.5 < sp.area < 107.5 and "1 pièce(s) hors de ce contour" in why


MYONAZ = Path.home() / ("HRS Real Estate AG/HRS BIM-WEST - Documents/10-WIP/Analyse parametrique des projets/"
                        "analys maquettes arc/1712.00 ORO - La Myonaz 1_ARC-GEN #44.ifc")
MDP_1712 = ROOT / "00_RESSOURCES/03-DataBase-DonneesProjets/MDP-1712.00_Myonaz.xlsx"


@pytest.mark.skipif(not (MYONAZ.is_file() and MDP_1712.is_file()), reason="maquette Myonaz ou MDP 1712 absents")
def test_myonaz_matches_its_mdp(tmp_path, gen_cfg, cfg):
    """Référence réelle : MDP 1712 (bâtiment 1) — même SP par étage, chaque local au même code."""
    from sia_check.generation import compare
    g = engine.generate(MYONAZ, gen_cfg, tmp_path, "Myonaz-1")
    c = compare.compare(g.folder, MDP_1712, cfg, "Bat. 1")
    assert c["apparies"] == c["meme_code"] == c["locaux_mdp"] == 101
    for row in c["etages"]:
        for code in ("SP", "SUP", "SUS", "SD", "SI"):
            assert abs(row[code]["ecart"]) < 0.5, (row["level"], code, row[code])
