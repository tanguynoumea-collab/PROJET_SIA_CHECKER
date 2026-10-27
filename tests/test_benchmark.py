"""Benchmark (benchmark.py) : lecture et normalisation des MDP, contrôles, ratios combinés, projets similaires."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sia_check import benchmark as b
from sia_check import cli

BASE = Path(__file__).resolve().parents[1] / "00_RESSOURCES" / "03-DataBase-DonneesProjets"


def mdp(path: Path, *, sp_hs=800.0, sp_ss=200.0, sup=650.0, sd=60.0, si=20.0, sus=100.0, lots=((1, 50.0), (3, 90.0)),
        infos=None, decoupage=True, etages=("N00", "N01", "S01")) -> Path:
    """Un MDP minimal : brutes par niveau (catégorie saisie par bloc), nettes, logements, USPI, enveloppe.
    Par défaut SP 1 000 (800 hors-sol), SN 830, SC 17 %."""
    infos = {"ID projet": 9001.0, "Nom Projet HRS": path.stem, "Canton": "Vaud",
             "Categorie d'Ouvrage": "Logement (100-90% SU)", "Type d'intervention": "Nouvelle construction",
             **(infos or {})}
    brutes = pd.DataFrame({"ID Projet": 9001, "Categorie SIA416": ["SP", None, "SP"], "Etage": list(etages),
                           "Decoupage": ["Hors-sol", "Hors-sol", "Sous-sol"] if decoupage else [None] * 3,
                           "m2": [sp_hs / 2, sp_hs / 2, sp_ss], "m3": [sp_hs * 1.5, sp_hs * 1.5, sp_ss * 3]})
    nettes = [("SD", "N00", None, sd), ("SI", "N01", None, si), ("SUS", "S01", None, sus)]
    nettes += [("SUP", "N01", f"A_N01_Apart-{i}", s) for i, (_, s) in enumerate(lots)]
    nettes += [("Surface Utile Principale (SUP)", "N00", None, sup - sum(s for _, s in lots))]
    nettes = pd.DataFrame([{"ID Projet": 9001, "Categorie SIA416": c, "Affectation": "Logement general", "Etage": e,
                            "Appartement_Unite": a, "m2": m} for c, e, a, m in nettes])
    logements = pd.DataFrame({"ID Projet": 9001, "Etage": "N01",
                              "Appartement_Unite": [f"A_N01_Apart-{i}" for i in range(len(lots))],
                              "Nbr de chambres": [c for c, _ in lots]})
    with pd.ExcelWriter(path) as w:
        pd.DataFrame({"Catégorie": "Identification", "Description": list(infos), "Valeur": list(infos.values())}
                     ).to_excel(w, sheet_name="InfosProjet", index=False)
        brutes.to_excel(w, sheet_name="SurfacesBrutesVolumeSIA416", index=False)
        nettes.to_excel(w, sheet_name="SurfacesNettesSIA416", index=False)
        pd.DataFrame({"ID Projet": 9001, "Categorie USPI": ["Surface de Vente Nette"], "Appartement_Unite": ["x"],
                      "m2": [560.0]}).to_excel(w, sheet_name="SurfacesUSPI", index=False)
        logements.to_excel(w, sheet_name="ListeLogements", index=False)
        pd.DataFrame({"ID Projet": 9001, "Partie de l'enveloppe": "Façade", "Etage": ["N00"], "Surface Brutte": [700.0],
                      "Surface nette (m2)": [550.0], "Surface vitrée": [150.0]}
                     ).to_excel(w, sheet_name="SurfacesEnveloppe", index=False)
    return path


@pytest.fixture
def projet(tmp_path) -> b.Projet:
    return b.lire(mdp(tmp_path / "MDP-9001-Test.xlsx"))


def test_totaux(projet):
    t = projet.totaux
    assert projet.id == "9001" and projet.nom == "MDP-9001-Test" and projet.infos["canton"] == "VD"
    assert t["SP"] == 1000 and t["SP_HS"] == 800 and t["SP_SS"] == 200     # 2e ligne SP sans catégorie
    assert t["SUP"] == 650 and t["SUP_HS"] == 650 and t["SUS_SS"] == 100 and t["SN"] == 830 and t["SC"] == 170
    assert t["VB"] == pytest.approx(3000) and t["ETAGES_HS"] == 2 and t["LOG"] == 2
    assert t["SVN"] == 560 and t["FACADE"] == 700 and t["VITRE"] == 150


def test_projet_fiable(projet):
    assert projet.fiable and projet.score == 1
    assert projet.ratio(b.KPI_BY_ID["SUP/SP_HS"]) == (650, 800)
    assert [lg["sup"] for lg in projet.logements] == [50, 90]
    assert projet.features()["PART_GRANDS"] == 0.5 and projet.features()["PART_SS"] == 0.25


def test_sc_hors_fourchette_ecarte_le_projet(tmp_path):
    p = b.lire(mdp(tmp_path / "MDP-9001-B.xlsx", sup=400))     # SN 580, SC 42 % : nettes tronquées
    ctrl = {c.id: c for c in p.controles}
    assert ctrl["coherence"].ok and not ctrl["plausible"].ok and ctrl["plausible"].detail == "SC / SP = 42%"
    assert not p.fiable
    assert b.combiner([p], b.KPI_BY_ID["SUP/SP_HS"])["n"] == 0


def test_codes_et_zones():
    assert b.code("Surface Utile Principale (SUP)") == "SUP" and b.code("SD") == "SD"
    assert b.code("SEP-Toiture") == "SPT" and b.code("Volume Bâti (VB)") == "VB" and b.code(None) is None
    assert b.zone("N03") == "HS" and b.zone("ATT") == "HS" and b.zone("S02") == "SS"
    assert b.zone("N00", "Sous-sol") == "SS" and b.zone("Toiture", "Divers") == "HS" and b.zone(None) is None


def test_decoupage_par_code_d_etage_sinon_absent(tmp_path):
    p = b.lire(mdp(tmp_path / "MDP-9001-B.xlsx", decoupage=False))
    assert p.totaux["SP_HS"] == 800
    p = b.lire(mdp(tmp_path / "MDP-9001-C.xlsx", decoupage=False, etages=("A", "B", "C")))
    assert "SP_HS" not in p.totaux and p.ratio(b.KPI_BY_ID["SUP/SP_HS"]) is None
    assert not {c.id: c for c in p.controles}["decoupage"].ok


def test_ratio_combine_pondere_par_la_surface(tmp_path):
    a = b.lire(mdp(tmp_path / "MDP-1-A.xlsx", infos={"ID projet": 1}))
    c = b.lire(mdp(tmp_path / "MDP-2-C.xlsx", infos={"ID projet": 2}, sp_hs=1600, sp_ss=400, sup=1200, sd=150, si=40,
                   sus=250))
    r = b.combiner([a, c], b.KPI_BY_ID["SUP/SP_HS"])
    assert r["n"] == 2 and r["combine"] == pytest.approx((650 + 1200) / (800 + 1600))
    assert r["mediane"] == pytest.approx((650 / 800 + 1200 / 1600) / 2)
    assert set(r["valeurs"]) == {"1", "2"}


def test_similaires_filtres_et_distance(tmp_path):
    ref = b.lire(mdp(tmp_path / "MDP-1.xlsx", infos={"ID projet": 1}))
    proche = b.lire(mdp(tmp_path / "MDP-2.xlsx", infos={"ID projet": 2}, sp_hs=900, sup=720))
    loin = b.lire(mdp(tmp_path / "MDP-3.xlsx", infos={"ID projet": 3}, sp_hs=4000, sp_ss=2000, sup=3300, sd=300,
                      si=100, sus=500, lots=((0, 30.0), (1, 50.0), (1, 52.0), (1, 48.0))))
    autre = b.lire(mdp(tmp_path / "MDP-4.xlsx", infos={"ID projet": 4, "Type d'intervention": "Rénovation"}))
    inconnu = b.lire(mdp(tmp_path / "MDP-5.xlsx", infos={"ID projet": 5, "Type d'intervention": None}))
    ids = [p.id for p, _ in b.similaires(ref, [ref, proche, loin, autre, inconnu])]
    assert "4" not in ids and "1" not in ids                 # filtre « type d'intervention », lui-même exclu
    assert ids.index("2") < ids.index("3") and "5" in ids    # valeur inconnue : gardé


def test_dossier_et_json(tmp_path):
    mdp(tmp_path / "MDP-1-A.xlsx", infos={"ID projet": 1})
    mdp(tmp_path / "MDP-2-B.xlsx", infos={"ID projet": 2}, sp_hs=900, sup=720)
    (tmp_path / "MDP-3-casse.xlsx").write_text("pas un classeur")
    out = tmp_path / "out" / "benchmark.json"
    assert cli.main(["--benchmark", str(tmp_path), "--benchmark-json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["projets"]) == 2 and len(data["erreurs"]) == 1
    p1 = data["projets"][0]
    assert p1["fiable"] and p1["similaires"][0]["id"] == "2" and p1["reference"]["SUP/SP_HS"]["n"] == 1
    assert data["typologies"][0]["chambres"] == 1 and data["typologies"][0]["n"] == 2


@pytest.mark.skipif(not BASE.is_dir(), reason="base MDP de référence absente (00_RESSOURCES)")
def test_base_de_reference():
    projets, erreurs = b.lire_dossier(BASE)
    assert not erreurs and len(projets) == 10
    assert {p.id for p in projets if p.fiable} == {"1467", "1712", "1714", "1746", "1784"}
    assert not next(p for p in projets if p.id == "1778").fiable     # nettes tronquées : SC / SP = 56 %
    r = b.combiner(projets, b.KPI_BY_ID["SUP/SP_HS"])
    assert r["n"] == 5 and 0.70 < r["combine"] < 0.76
