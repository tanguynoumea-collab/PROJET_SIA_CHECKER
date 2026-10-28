"""Moteur de génération, phase 24 : analyse IA (questions, prompt, réponse) et journal des décisions."""

import json

import pytest

from sia_check import cli, config
from sia_check.generation import classify, engine, ia, journal
from conftest import ROOT
from ifc_synth import build


def space(gid, name, long_name, code, typ, conf=0.9, conflicts=(), lot=None, source="dictionnaire", nature="piece"):
    return {"gid": gid, "name": name, "long_name": long_name, "level": "N00", "storey": "E00", "lot": lot,
            "in_lot": lot is not None, "nature": nature, "code": code, "type": typ, "source": source,
            "confidence": conf, "reason": "…", "conflicts": list(conflicts), "area": 12.0, "area_plan": 12.0,
            "neighbours": ["Couloir (SD CirculationH)"], "props": {"Pset_SpaceCommon.Category": "Technique E"}}


RAPPORT = {"project": "P", "spaces": [
    space("a", "SEJ", "Séjour", "SUP", "PieceDeVie", lot="L1"),                                  # sûr : pas de question
    space("b", "RED", "Réduit", "SUP", "Distribution", 0.7, ["categorie : SUS"], lot="L1", source="convention"),
    space("c", "ELE", "SUS_ELE_CFA", "SUS", "SUS", 0.7, ["dictionnaire : SI"], source="prefixe"),
    space("d", None, "Local", "SUS", "SUS", 0.5, source=None),
    space("g", "LOG", "SBH", None, None, 0.9, source=None, nature="logement"),                    # contour : jamais
]}


def test_only_hesitant_rooms_become_questions():
    q = ia.questions(RAPPORT)
    assert [x["id"] for x in q["questions"]] == ["d", "c", "b"] and q["total"] == 3   # le plus douteux d'abord
    b = next(x for x in q["questions"] if x["id"] == "b")
    assert b["pieces_du_logement"] == ["SEJ / Séjour (SUP)"] and b["regles"]["desaccords"] == ["categorie : SUS"]
    p = ia.prompt(q)
    assert p["questions"] == 3 and p["output_tokens"] == [870, 2610]
    assert "PieceSecondaire_2PointsEau" in p["system"] and '"id": "c"' in p["user"]


def test_response_becomes_proposals():
    q = ia.questions(RAPPORT)
    text = """Voici.
<decisions>
```json
{"b": {"code": "SUP", "type": "Distribution", "certitude": "sûr", "raison": "réduit de logement"},
 "c": {"code": "SI", "type": "Inconnu", "certitude": "probable", "raison": "local électrique"},
 "zz": {"code": "SUP"}, "d": {"code": "XYZ"}}
```
</decisions>
<synthese>Un local électrique passe en SI.</synthese>"""
    decisions, summary, missing = ia.parse(text, q)
    by = {d["id"]: d for d in decisions}
    assert set(by) == {"b", "c"} and missing == ["d"]                   # clé inventée écartée, code inconnu sans réponse
    assert by["b"]["statut"] == "confirmée"                              # l'IA garde le classement des règles
    assert by["c"]["statut"] == "proposée" and by["c"]["type"] == "Gaine" and by["c"]["avant"]["code"] == "SUS"
    assert summary == "Un local électrique passe en SI."
    with pytest.raises(ia.ResponseError):
        ia.parse("pas de balise", q)


def test_journal_keeps_human_decisions_and_applies_accepted_ones():
    old = [{"id": "c", "origine": "ia", "statut": "rejetée", "code": "SI"},
           {"id": "d", "origine": "ia", "statut": "proposée", "code": "SUS"}]
    new = [{"id": "c", "origine": "ia", "statut": "proposée", "code": "SUT"},
           {"id": "d", "origine": "ia", "statut": "proposée", "code": "SI"}]
    merged = {d["id"]: d for d in journal.merge(old, new)}
    assert merged["c"]["code"] == "SI" and merged["d"]["code"] == "SI"   # rejet gardé, proposition ouverte remplacée
    assert journal.set_status(list(merged.values()), "acceptée", {"d"}) == 1
    cfg = config.load(ROOT / "config.yaml").generation
    decisions = {"d": classify.Decision("d", "piece", "SUS", "SUS", None, 0.5, "", [], False)}
    assert journal.apply([merged["d"]], decisions, cfg) == 1
    assert (decisions["d"].code, decisions["d"].type, decisions["d"].source, decisions["d"].confidence) == \
        ("SI", "Local", "ia", 1.0)


def test_accepted_decision_changes_the_next_generation(tmp_path):
    """Chaîne complète : questions, réponse enregistrée par l'app, acceptation, régénération."""
    cfg = config.load(ROOT / "config.yaml").generation
    ifc = build(tmp_path / "synth.ifc")
    g = engine.generate(ifc, cfg, tmp_path / "out", "Synth")
    sej = next(s for s in g.data["spaces"] if s["long_name"] == "Séjour")
    assert "CHS / Chambre (SUP Chambre)" in sej["neighbours"]
    # une question posée à la main (le synthétique est sans ambiguïté) : le séjour, classé SUP
    q = {"project": "Synth", "total": 1, "questions": [{"id": sej["gid"], "nom": "SEJ", "nom_long": "Séjour",
                                                        "regles": {"code": "SUP", "type": "PieceDeVie"}}]}
    (g.folder / ia.QUESTIONS).write_text(json.dumps(q), encoding="utf-8")
    (g.folder / ia.RESPONSE).write_text(
        f'<decisions>{{"{sej["gid"]}": {{"code": "SUP", "type": "Chambre", "certitude": "probable", '
        f'"raison": "test"}}}}</decisions><synthese>ok</synthese>', encoding="utf-8")
    assert cli.main(["--reponse-ia", str(g.folder)]) == 0
    assert [d["statut"] for d in journal.load(g.folder)] == ["proposée"]
    again = engine.generate(ifc, cfg, tmp_path / "out", "Synth")          # proposée : rien ne change
    assert next(s for s in again.data["spaces"] if s["gid"] == sej["gid"])["type"] == "PieceDeVie"
    assert cli.main(["--accepter-ia", str(g.folder)]) == 0
    again = engine.generate(ifc, cfg, tmp_path / "out", "Synth")
    s = next(s for s in again.data["spaces"] if s["gid"] == sej["gid"])
    assert (s["type"], s["source"], s["confidence"]) == ("Chambre", "ia", 1.0)
    assert cli.main(["--questions-ia", str(g.folder)]) == 0
    asked = json.loads((g.folder / ia.QUESTIONS).read_text(encoding="utf-8"))["questions"]
    assert asked and sej["gid"] not in {x["id"] for x in asked}        # tranché : plus jamais redemandé


def test_app_contract_maquette_surface_links_and_manual_decision(tmp_path):
    """Phase 25 : maquette de contexte, lien espace -> surface, décision manuelle qui remplace la proposition."""
    cfg = config.load(ROOT / "config.yaml").generation
    ifc = build(tmp_path / "synth.ifc")
    g = engine.generate(ifc, cfg, tmp_path / "out", "Synth")
    maq = json.loads((g.folder / engine.MAQUETTE).read_text(encoding="utf-8"))
    assert {e["class"] for e in maq["elements"]} == {"IfcWall", "IfcSlab"} and maq["origin"]
    sej = next(s for s in g.data["spaces"] if s["long_name"] == "Séjour")
    assert sej["surface"] == "A_N00_ShellByTgm-01_SpaceByTgm-2_SUP"
    assert cli.main(["--decider", str(g.folder), "--ids", sej["gid"], "--code", "SUS"]) == 0
    assert cli.main(["--decider", str(g.folder), "--ids", sej["gid"], "--code", "SUS", "--type", "Gaine"]) == 2
    (d,) = journal.load(g.folder)
    assert (d["origine"], d["statut"], d["code"], d["type"]) == ("manuel", "acceptée", "SUS", "SUS")
    again = engine.generate(ifc, cfg, tmp_path / "out", "Synth")
    assert next(s for s in again.data["spaces"] if s["gid"] == sej["gid"])["source"] == "manuel"
