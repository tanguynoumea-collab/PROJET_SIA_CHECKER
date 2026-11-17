"""Position d'un projet d'après son adresse (sia_check.adresses), sur un petit registre au format de swisstopo."""

import zipfile

import pytest

from sia_check import adresses, benchmark

ENTETE = ("ADR_EGAID;STR_ESID;BDG_EGID;ADR_EDID;STN_LABEL;ADR_NUMBER;BDG_CATEGORY;BDG_NAME;ZIP_LABEL;COM_FOSNR;"
          "COM_NAME;COM_CANTON;ADR_STATUS;ADR_OFFICIAL;ADR_MODIFIED;ADR_EASTING;ADR_NORTHING")
LIGNES = [
    ("Avenue de Morges", "26", "1004 Lausanne", "Lausanne", "VD", 2537130.4, 1152980.2),
    ("Avenue de Morges", "28", "1004 Lausanne", "Lausanne", "VD", 2537110.0, 1152990.0),
    ("Rue du Lac", "3", "1400 Yverdon-les-Bains", "Yverdon-les-Bains", "VD", 2539000.0, 1181000.0),
    ("Rue du Lac", "3", "1800 Vevey", "Vevey", "VD", 2554000.0, 1145600.0),
    ("Bahnhofstrasse", "1", "8001 Zürich", "Zürich", "ZH", 2683187.0, 1246862.0),
]


@pytest.fixture(scope="module")
def registre(tmp_path_factory):
    d = tmp_path_factory.mktemp("adresses")
    z = d / "registre.csv.zip"
    corps = "\n".join([ENTETE] + [f"1;1;1;0;{r};{n};residential;;{npa};1;{c};{k};real;true;01.01.2025;{e};{no}"
                                  for r, n, npa, c, k, e, no in LIGNES])
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("registre.csv", "﻿" + corps)
    reg = adresses.Registre(z)
    yield reg
    reg.close()


@pytest.mark.parametrize("texte, attendu", [
    ("Avenue de Morges 26, 1004 Lausanne", ("Avenue de Morges", "26", "1004", "Lausanne")),
    ("26 avenue de Morges", ("avenue de Morges", "26", None, None)),
    ("Chemin des Mouettes", ("Chemin des Mouettes", None, None, None)),
    ("Rue du Lac 3b, Vevey", ("Rue du Lac", "3b", None, "Vevey")),
    ("", None),
])
def test_analyse_d_une_adresse(texte, attendu):
    assert adresses.analyser(texte) == attendu


@pytest.mark.parametrize("adresse, commune, attendu", [
    ("Avenue de Morges 26, 1004 Lausanne", None, ([2537130, 1152980], "adresse")),
    ("av. de Morges 26", "Lausanne", ([2537130, 1152980], "adresse")),       # abréviation
    ("Avenue de Morges 99", "Lausanne", ([2537120, 1152985], "rue")),        # numéro inconnu : milieu de la rue
    ("Rue du Lac 3", "Vevey", ([2554000, 1145600], "adresse")),              # rue homonyme : la commune tranche
    ("Rue du Lac 3", None, None),                                            # homonyme sans commune : pas de position
    ("Bahnhofstr. 1, 8001 Zürich", None, ([2683187, 1246862], "adresse")),
    ("Rue inventée 3", "Lausanne", None),
])
def test_position_d_une_adresse(registre, adresse, commune, attendu):
    assert registre.position(adresse, commune, "VD" if commune else None) == attendu


def test_adresse_puis_commune_dans_le_benchmark(registre):
    projet = benchmark.Projet("1", "Test", "MDP-1.xlsx", {}, {"SP": 100.0}, [], [])
    projet.infos.update(adresse="Avenue de Morges 26", commune="Lausanne", canton="VD")
    j = benchmark.projet_json(projet, registre)
    assert j["position"] == [2537130, 1152980] and j["precision"] == "adresse"
    projet.infos.update(adresse="Rue inventée 3")                            # adresse introuvable : centre de la commune
    j = benchmark.projet_json(projet, registre)
    assert j["precision"] == "commune" and j["position"] is not None
    projet.infos.update(adresse=None, commune=None)
    assert benchmark.projet_json(projet, registre)["position"] is None
