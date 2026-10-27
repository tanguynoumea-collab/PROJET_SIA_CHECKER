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
    assert t["PLEINE"] == 550                                              # façade − vitrée


def test_enveloppe_hors_sol_sans_toitures(tmp_path):
    # Comme les ratios de la fiabilisation : ni les toitures, ni les murs enterrés du sous-sol
    f = mdp(tmp_path / "MDP-9001-E.xlsx")
    with pd.ExcelWriter(f, mode="a", if_sheet_exists="replace") as w:
        pd.DataFrame({"ID Projet": 9001, "Partie de l'enveloppe": ["Facade global", "Facade global", "Surface de toiture"],
                      "Etage": ["N00", "S01", "N01"], "Surface Brutte": [700.0, 300.0, 200.0],
                      "Surface nette (m2)": [550.0, 300.0, 200.0], "Surface vitrée": [150.0, 10.0, 0.0]}
                     ).to_excel(w, sheet_name="SurfacesEnveloppe", index=False)
    t = b.lire(f).totaux
    assert (t["FACADE"], t["VITRE"], t["PLEINE"]) == (700, 150, 550)


def test_kpis_d_enveloppe(projet):
    assert projet.ratio(b.KPI_BY_ID["VITRE/PLEINE"]) == (150, 550)
    assert projet.ratio(b.KPI_BY_ID["VITRE/FACADE"]) == (150, 700)
    assert {k.famille for k in b.KPIS if "VITRE" in k.num or "FACADE" in k.num} == {"Enveloppe"}
    assert b.KPI_BY_ID["VITRE/PLEINE"].sens == 0                           # le benchmark situe, sans juger


def test_sans_vitree_pas_de_pleine(tmp_path):
    import openpyxl
    f = mdp(tmp_path / "MDP-9001-V.xlsx")
    wb = openpyxl.load_workbook(f)
    wb["SurfacesEnveloppe"]["F2"] = 0
    wb.save(f)
    t = b.lire(f).totaux
    assert (t["FACADE"], t["VITRE"]) == (700, 150)          # sans vitrée : les ouvertures (brute 700 − nette 550)
    wb["SurfacesEnveloppe"]["E2"] = 700                      # ni vitrée ni ouverture
    wb.save(f)
    t = b.lire(f).totaux
    assert t["FACADE"] == 700 and "VITRE" not in t and "PLEINE" not in t


def test_kpis_propres_au_logement(projet):
    logement = {k.id for k in b.KPIS if k.typologie == "logement"}
    assert logement == {"SUP/LOG", "SP_HS/LOG"}
    data = b.construire([projet], [])
    assert {k["id"]: k["typologie"] for k in data["kpis"]}["SUP/LOG"] == "logement"


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


def test_sens_et_objet_des_kpis():
    for k in b.KPIS:
        assert k.sens in (-1, 0, 1)
        assert bool(k.objet) == (k.sens != 0)     # un écart orienté se traduit en m²
    assert b.KPI_BY_ID["SUP/SP_HS"].sens == 1 and b.KPI_BY_ID["SD/SP_HS"].sens == -1


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
    assert p1["distances"] == {"2": p1["similaires"][0]["distance"]}
    assert data["typologies"][0]["chambres"] == 1 and data["typologies"][0]["n"] == 2


def test_projet_json_sans_comparaison(projet):
    j = b.projet_json(projet)
    assert j["kpis"]["SUP/SP_HS"]["valeur"] == pytest.approx(650 / 800) and j["mix"] == {"1": 1, "3": 1}
    assert "similaires" not in j and j["features"]["SP_HS"] == 800


@pytest.mark.skipif(not BASE.is_dir(), reason="base MDP de référence absente (00_RESSOURCES)")
def test_base_de_reference():
    projets, erreurs = b.lire_dossier(BASE)
    assert not erreurs and len(projets) == 10
    # L'Orée (1778) réexportée par SIA Check au passage en traité : fiable ; Gare Casino garde ses nettes tronquées
    assert {p.id for p in projets if p.fiable} == {"1467", "1712", "1714", "1746", "1778", "1784"}
    assert not next(p for p in projets if p.id == "1747").fiable     # SC / SP = 55 %
    r = b.combiner(projets, b.KPI_BY_ID["SUP/SP_HS"])
    assert r["n"] == 6 and 0.70 < r["combine"] < 0.76
    # enveloppe hors-sol, sans toitures : L'Orée retrouve la part vitrée de la fiabilisation (32,7 %)
    loree = next(p for p in projets if p.id == "1778")
    assert loree.totaux["VITRE"] / loree.totaux["FACADE"] == pytest.approx(0.327, abs=0.005)


def test_identite_d_un_ancien_mdp_puis_relue(tmp_path):
    """Les anciens MDP n'ont pas le tableau InfosProjet du gabarit : la ligne se trouve par sa description."""
    path = mdp(tmp_path / "MDP-9001-Test.xlsx", infos={"Canton": None, "Categorie d'Ouvrage": None})
    p = b.lire(path)
    assert p.infos["canton"] is None and p.infos["categorie"] is None    # jamais déduite des affectations
    from sia_check import mdp as mdp_mod
    mdp_mod.ecrire_identite(path, {"Canton": "VD", "Categorie d'Ouvrage": "Santé"})
    p = b.lire(path)
    assert p.infos["canton"] == "VD" and p.infos["categorie"] == "Santé"


def test_listes_dans_le_json(tmp_path):
    mdp(tmp_path / "MDP-1-A.xlsx", infos={"ID projet": 1})
    data = b.construire(*b.lire_dossier(tmp_path))
    assert "VD" in data["listes"]["Canton"]


def test_logements_dans_le_json(projet):
    assert b.projet_json(projet)["logements"] == [{"chambres": 1, "sup": 50.0}, {"chambres": 3, "sup": 90.0}]
