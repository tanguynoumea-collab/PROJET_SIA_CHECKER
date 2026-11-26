"""V7 : carte d'identité exploitée au benchmark (docs/V7_PLAN.md) : KPI triés, phase, forme et contexte dans la
similarité, origine des valeurs, parcelle, résumé pour le dashboard."""

import pytest

from sia_check import benchmark as b
from sia_check import carte, sig

from test_benchmark import mdp
from test_carte import _champs, _maquette

PARCELLE = [[[[2538000.0, 1152000.0], [2538040.0, 1152000.0], [2538040.0, 1152025.0], [2538000.0, 1152025.0]]]]


def test_doublons_hors_des_kpi_affiches_mais_calcules(tmp_path):
    p = b.lire(mdp(tmp_path / "MDP-1.xlsx", infos={"ID projet": 1}))
    caches = {k.id for k in b.KPIS if not k.affiche}
    assert caches == {"SN/SP", "VITRE/PLEINE", "FACADE/SP_HS"}
    assert p.ratio(b.KPI_BY_ID["FACADE/SP_HS"]) is not None              # le Programmer s'en sert toujours
    assert "EMPRISE/TERRAIN" in b.KPI_BY_ID


@pytest.mark.parametrize("mode, attendu", [(None, True), ("PPE", True), ("Mixte location et PPE", True),
                                           ("Location", False), ("Utilité publique / coopérative", False)])
def test_svn_seulement_pour_la_vente(tmp_path, mode, attendu):
    p = b.lire(mdp(tmp_path / "MDP-1.xlsx", infos={"ID projet": 1}))
    p.infos["saisies"] = {"commercialisation": mode} if mode else None
    assert (p.ratio(b.KPI_BY_ID["SVN/SP_HS"]) is not None) is attendu


@pytest.mark.parametrize("phase, attendu", [(31, False), ("33", False), (41, True), (52.0, True), (None, None), ("?", None)])
def test_phase_autorisee(phase, attendu):
    assert b.realise(phase) is attendu


def test_similarite_tient_compte_de_la_phase_de_la_forme_et_du_site(tmp_path):
    ref = b.lire(mdp(tmp_path / "MDP-1.xlsx", infos={"ID projet": 1}))
    meme = b.lire(mdp(tmp_path / "MDP-2.xlsx", infos={"ID projet": 2}))
    autre = b.lire(mdp(tmp_path / "MDP-3.xlsx", infos={"ID projet": 3}))
    etude = b.lire(mdp(tmp_path / "MDP-4.xlsx", infos={"ID projet": 4, "Phase du projet": 31}))
    for p, fam, site in ((ref, "Blocs", "Urbain"), (meme, "Blocs", "Urbain"), (autre, "Îlots", "Rural"), (etude, "Blocs", "Urbain")):
        p.infos["famille_at"], p.infos["site"] = fam, site
    proj = [ref, meme, autre, etude]
    d = dict((q.id, x) for q, x in b.similaires(ref, proj))
    assert d["2"] < d["3"]                                   # mêmes surfaces : la forme et le site départagent
    assert "4" in d                                          # filtre de phase pas actif par défaut
    assert "4" not in {q.id for q, _ in b.similaires(ref, proj, realises=True)}


def test_resume_et_origines_dans_le_benchmark(tmp_path):
    mdp(tmp_path / "MDP-9001.xlsx", infos={"Surface du terrain (m²)": 1000.0, "Phase du projet": 52})
    _maquette(tmp_path)
    sig.ecrire(tmp_path, "9001", [2538020, 1152012], "adresse",
               {"site": {"valeur": "Urbain"}, "parcelle": {"valeur": 1000, "numero": "12", "geometrie": PARCELLE}})
    projets, _ = b.lire_dossier(tmp_path)
    data = b.construire(projets, dossier=tmp_path)
    pj = data["projets"][0]
    i = pj["identite"]
    assert i["gsi"] == 0.48 and i["fsi"] == 0.8 and i["realise"] is True
    assert i["forme_at"] == "Blocs · Bloc linéaire" and i["forme_at_origine"] == "Proposé" and i["famille"] == "Blocs"
    assert i["tranche"] == "moins de 50"                     # 2 logements sur 0,1 ha : 20 log./ha
    im = i["implantation"]
    assert im["parcelle_m2"] == 1000 and im["emprise_m2"] == 480 and im["calee"] is False
    assert pj["features"]["GSI"] == pytest.approx(0.48) and pj["features"]["FAMILLE_AT"] == "Blocs"
    assert data["formes_at"]["Blocs"][0] == "Bloc linéaire" and data["phase_autorisee"] == 41
    f = _champs(pj["carte"])
    assert f["emprise"]["origine"] == "Maquette" and f["gsi"]["origine"] == "Calcul" and f["zone"]["origine"] is None
    assert f["implantation"]["origine"] == "Proposé" and f["terrain"]["origine"] == "MDP"
    assert f["origines"]["valeur"].startswith("Calcul") and f["origines"]["origine"] == "Calcul"
    assert f["forme_parcelle"]["valeur"] == "40 × 25 m (rectangle minimal)"
    assert f["orientation_parcelle"]["valeur"] == "axe long à 90° du nord"
    assert pj["carte"]["entete"]["implantation"]["parcelle"]


def test_version_d_un_groupe_a_le_resume_sans_la_carte(tmp_path):
    mdp(tmp_path / "MDP-9001.xlsx", infos={"Surface du terrain (m²)": 1000.0})
    _maquette(tmp_path)
    projets, _ = b.lire_dossier(tmp_path)
    pj = b.construire(projets, dossier=tmp_path, avec_sig=False)["projets"][0]
    assert "carte" not in pj and pj["identite"]["gsi"] == 0.48


def test_operation_d_ensemble_et_sa_densite():
    assert carte.densite_plan({"plan_parent_log": "300", "plan_parent_surface": "20000"}) == 150
    assert carte.densite_plan({"plan_parent_log": "300"}) is None
    pj = {"infos": {"saisies": {"plan_parent": "PQ Les Prés", "plan_parent_log": 300, "plan_parent_surface": 20000}}}
    f = _champs(carte.carte(pj))
    assert f["plan_parent"]["valeur"] == "PQ Les Prés"
    assert f["plan_parent"]["details"] == [["Densité de l'opération", "150 log./ha · tranche 100 à 200"]]


def test_svn_sans_objet_en_location():
    pj = {"infos": {"saisies": {"commercialisation": "Location"}}, "kpis": {}}
    assert _champs(carte.carte(pj))["svn_sp"]["valeur"] == "sans objet (location)"


def test_geometrie_de_la_parcelle_gardee():
    g = {"type": "Polygon", "coordinates": [[[2538000.04, 1152000.0, 500.0], [2538040.0, 1152000.0], [2538040.0, 1152025.0]]]}
    assert sig.geometrie_parcelle(g) == [[[[2538000.0, 1152000.0], [2538040.0, 1152000.0], [2538040.0, 1152025.0]]]]
    assert sig.geometrie_parcelle({"type": "Point", "coordinates": [1, 2]}) is None


def test_fiche_d_avant_la_v7_completee_de_sa_parcelle(tmp_path, monkeypatch):
    sig.ecrire(tmp_path, "1", [2538020, 1152012], "adresse", {"parcelle": {"valeur": 1000}}, date="2026-11-01")
    monkeypatch.setattr(sig, "parcelle", lambda e, n: {"valeur": 1000, "geometrie": PARCELLE})
    assert sig.synchroniser(tmp_path, [("1", [2538020, 1152012], "adresse")]) == (1, 0)
    fiche = sig.lire(tmp_path, "1")
    assert fiche["valeurs"]["parcelle"]["geometrie"] == PARCELLE and fiche["date"] == "2026-11-01"
    assert sig.synchroniser(tmp_path, [("1", [2538020, 1152012], "adresse")]) == (0, 0)     # plus rien à reprendre
