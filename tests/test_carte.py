"""Carte d'identité d'un projet de la base (carte.py, docs/CARTE_IDENTITE.md)."""

import gzip
import json

from sia_check import benchmark as b
from sia_check import carte, sig

from test_benchmark import mdp


def _rect(x0, y0, x1, y1, z):
    """Lot d'un rectangle (cm entiers), deux triangles."""
    v = [x0, y0, z, x1, y0, z, x1, y1, z, x0, y1, z]
    return {"v": [round(c * 100) for c in v], "i": [0, 1, 2, 0, 2, 3]}


def _maquette(dossier, pid="9001"):
    """Une barre de 40 × 12 m sur trois étages (rez à 0 m, étages tous les 3 m) et un sous-sol."""
    niveaux = [{"b": "A", "l": l, "rang": r} for l, r in (("S01", -1), ("N00", 0), ("N01", 1), ("N02", 2))]
    lots = [{"b": "A", "l": l, "code": "SP", **_rect(0, 0, 40, 12, z)} for l, z in (("S01", -3), ("N00", 0), ("N01", 3), ("N02", 6))]
    d = {"format": "sia-check-maquette", "version": 1, "id": pid, "unite": 0.01, "niveaux": niveaux, "lots": lots}
    with gzip.open(dossier / f"MAQ-{pid}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(d, f)


def _champs(c):
    return {f["cle"]: f for bloc in c["blocs"] for f in bloc["champs"]} | {f["cle"]: f for f in c["annexe"]}


def test_schema_complet():
    s = carte.schema()
    assert len({f["cle"] for f in s}) == len(s)
    assert all(f["source"] in carte.SOURCES for f in s)
    assert {f["statut"] for f in s} <= {"existe", "ajouter", "modifier", "reléguer", "retirer"}


def test_mesures_maquette(tmp_path):
    _maquette(tmp_path)
    m = carte.mesures(tmp_path, "9001")
    assert m["emprise_m2"] == 480.0
    assert m["batiments"]["A"]["epaisseur_m"] == 12.0
    assert m["hauteur_m"] == 9.0          # 6 m de planchers + un étage de 3 m
    assert m["niveaux_ss"] == 1
    assert m["socle"] is False
    assert carte.mesures(tmp_path, "absent") is None


def test_carte_dans_le_benchmark(tmp_path):
    mdp(tmp_path / "MDP-9001.xlsx", infos={"Surface du terrain (m²)": 1000.0, "Nbr places de stationnement voiture dans": 4})
    _maquette(tmp_path)
    sig.ecrire(tmp_path, "9001", [2538000, 1152000], "adresse",
               {"zone": {"valeur": "Zone d'habitation"}, "parcelle": {"valeur": 1000, "numero": "12", "egrid": "CH123"}})
    projets, _ = b.lire_dossier(tmp_path)
    data = b.construire(projets, dossier=tmp_path)
    c = data["projets"][0]["carte"]
    f = _champs(c)
    assert f["emprise"]["valeur"] == "480 m²"
    assert f["gsi"]["valeur"] == "0,48"
    assert f["fsi"]["valeur"] == "0,80"             # SP hors-sol 800 / terrain 1 000
    assert f["l"]["valeur"] == "1,7"
    assert f["egrid"]["valeur"] == "CH123"
    assert f["zone"]["valeur"] == "Zone d'habitation"
    assert f["isos"]["valeur"] == "Hors inventaire"
    assert f["places_log"]["valeur"] == "2,00"      # 4 places, 2 logements
    assert f["affectations"]["valeur"].startswith("Logement general 100")
    assert f["commercialisation"]["valeur"] is None and f["commercialisation"]["source"] == "DEV"
    assert "doublons" not in f                         # retiré de la carte
    assert all(x["statut"] == "reléguer" for x in c["annexe"])
    assert 0 < c["remplis"] < c["total"]
    # la visionneuse ne lit que du texte : une phase saisie en nombre (5) ne doit pas casser benchmark.json
    assert all(isinstance(x["valeur"], (str, type(None))) and all(isinstance(y, str) for d in x["details"] for y in d)
               for x in f.values())


def test_valeurs_numeriques_en_texte():
    c = carte.carte({"id": "1", "infos": {"phase": 5, "date": 2024.0}, "totaux": {}, "kpis": {}})
    f = _champs(c)
    assert f["phase"]["valeur"] == "5" and f["annee"]["valeur"] == "2024"


def test_carte_sans_maquette_ni_sig(tmp_path):
    mdp(tmp_path / "MDP-9001.xlsx")
    projets, _ = b.lire_dossier(tmp_path)
    c = b.construire(projets, dossier=tmp_path)["projets"][0]["carte"]
    f = _champs(c)
    assert not c["maquette"] and not c["sig"]
    assert f["emprise"]["valeur"] is None and f["zone"]["valeur"] is None
    assert f["logements"]["valeur"] == "2"


def test_classement_a_t():
    assert sum(len(v) for v in carte.FORMALISATIONS.values()) == 33
    assert carte.famille("Îlot fermé") == "Îlots"
    assert [carte.tranche(x) for x in (12, 50, 256, 301)] == ["moins de 50", "50 à 100", "200 à 300", "plus de 300"]
    p = carte.proposer_formalisation
    assert p({"": "Barre"}, [0], 4, 12)[0] == "Bloc linéaire"
    assert p({"": "Barre"}, [0], 12, 38)[0] == "Bloc allongé"
    assert p({"A": "Barre", "B": "Rectangle compact"}, [0, 2], 6, 18)[0] == "Blocs parallèles"
    assert p({"A": "Barre", "B": "En L"}, [0, 45], 6, 18)[0] == "Blocs groupés"
    assert p({"": "Irrégulière"}, [0], 4, 12) is None


def test_mesures_rez_et_niveaux(tmp_path):
    _maquette(tmp_path)
    m = carte.mesures(tmp_path, "9001")
    assert m["hauteur_rez_m"] == 3.0
    assert m["batiments"]["A"]["niveaux"] == 3


def test_volume_et_entete(tmp_path):
    _maquette(tmp_path)
    m = carte.mesures(tmp_path, "9001")
    vol = m["volume"]
    assert len(vol) == 1                                  # trois étages identiques : un seul prisme
    assert vol[0]["z0"] == 0 and vol[0]["z1"] == 9.0
    xs = [x for x, _ in vol[0]["anneaux"][0]]
    assert max(xs) - min(xs) == 40.0 and abs(max(xs) + min(xs)) < 0.01   # centré
    c = carte.carte({"id": "1", "infos": {"categorie": "Logement"}, "totaux": {"LOG": 20, "TERRAIN": 2000, "ETAGES_HS": 3},
                     "kpis": {}}, None, m)
    e = c["entete"]
    assert e["volume_origine"] == "maquette" and e["forme"].startswith("Blocs · Bloc linéaire")
    assert e["densite"].startswith("100 log./ha") and e["typologie"] == "Logement"


def test_schema_sans_maquette():
    v = carte.schema_volume({"A": "En L", "B": "Barre"}, 4)
    assert len(v) == 2 and all(p["z1"] == 12.0 for p in v)
    assert carte.schema_volume({}, 4) is None
    assert all(carte.SCHEMAS[f] or f == "Plusieurs plots" for f in carte.SCHEMAS)
    from sia_check.formes import FORMES
    assert set(FORMES) == set(carte.SCHEMAS)


def test_saisies_ecrites_dans_le_mdp_puis_lues(tmp_path):
    from sia_check import mdp as m
    path = mdp(tmp_path / "MDP-9001.xlsx")
    try:
        m.ecrire_identite(path, {"Architecte": "Atelier X", "Mode de commercialisation": "PPE",
                                 "Forme bâtie (a+t)": "Blocs · Bloc en L", "Places vélo": "40"})
    except m.TemplateError:
        import pytest
        pytest.skip("MDP minimal sans tableau InfosProjet")
    projets, _ = b.lire_dossier(tmp_path)
    assert projets[0].infos["saisies"]["architecte"] == "Atelier X"
    c = b.construire(projets, dossier=tmp_path)["projets"][0]["carte"]
    f = _champs(c)
    assert f["architecte"]["valeur"] == "Atelier X" and f["commercialisation"]["valeur"] == "PPE"
    assert f["implantation"]["valeur"] == "Blocs · Bloc en L"
    assert c["entete"]["forme"] == "Blocs · Bloc en L"
    r = f["architecte"]["remplissage"]
    assert r["mode"] == "vous" and r["saisie"]["description"] == "Architecte" and r["saisie"]["valeur"] == "Atelier X"


def test_modes_de_remplissage():
    modes = {k: carte.remplissage(k, s, st)["mode"] for k, _, _, _, _, s, _, _, st in carte.CHAMPS}
    assert modes["architecte"] == "vous" and modes["implantation"] == "proposition"
    assert modes["emprise"] == "auto" and modes["zone"] == "auto" and modes["categorie"] == "identite"
    assert modes["indices"] == "module" and modes["couts"] == "demande"
    assert carte.remplissage("emprise", "MAQ", "existe")["prerequis"] == ["Maquette 3D du projet dans la base"]
