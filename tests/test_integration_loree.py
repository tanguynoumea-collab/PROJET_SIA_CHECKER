"""Intégration sur le vrai projet L'Orée (ignoré si le projet Treegram n'est pas sur le poste).

Chemin surchargeable par la variable d'environnement SIA_LOREE_DIR.
"""

import os
from pathlib import Path

import pytest

from sia_check import cli, reader, rules, treegram

LOREE = Path(os.environ.get(
    "SIA_LOREE_DIR",
    Path.home() / "OneDrive - HRS Real Estate AG/Documents/Treegram/Projects/L OREE",
))
TGM = LOREE / "L OREE.tgm"
IFC = LOREE / "Exports/L OREE - Export Surfaces.ifc"
BUILDINGS = {"A01", "B03", "B04", "E09", "G12", "H16", "I14", "I17", "I18"}

needs_tgm = pytest.mark.skipif(not TGM.is_file(), reason="projet L'Orée absent")


@pytest.fixture(scope="module")
def loree(request):
    from sia_check import config
    cfg = config.load(Path(__file__).resolve().parents[1] / "config.yaml")
    df = reader.read(TGM, cfg)
    return df, rules.run(df, cfg)


def failing(res, rule):
    f = res.failing
    return {(r.building, r.level) for r in f[f.rule == rule].itertuples()}


@needs_tgm
def test_counts_match_viewer(loree):
    # Compteurs du viewer Treegram : 80 SP, 80 SEP (un total par niveau).
    df, _ = loree
    assert len(df) == 6090
    nodes = df[df.kind == "node"].category.value_counts()
    assert nodes["SP"] == 80 and nodes["SEP"] == 80
    assert set(df.building) == BUILDINGS
    assert df[(df.kind == "node") & (df.category == "SP")].area.sum() == pytest.approx(56210.12, abs=0.01)


@needs_tgm
def test_known_anomaly_level_without_su(loree):
    # Anomalie connue « niveau avec SP sans SU » (I18 N00) : en norme stricte elle sort en R5 ;
    # avec la règle personnalisée P1 (SU = SUP + SUS + SUT), ses 284 m² de SUT forment sa surface utile.
    import yaml
    from sia_check import config
    df, res = loree
    assert ("I18", "N00") not in failing(res, "R5")
    raw = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text(encoding="utf-8"))
    raw.pop("custom_rules")
    assert ("I18", "N00") in failing(rules.run(df, config.from_dict(raw)), "R5")


@needs_tgm
def test_known_anomaly_ground_sep(loree):
    _, res = loree
    ground = {(b, "N00") for b in BUILDINGS}
    assert failing(res, "A1") == ground
    assert ground <= failing(res, "R3")


@needs_tgm
def test_known_anomaly_roof_sep(loree):
    _, res = loree
    roofs = {(b, "Toiture") for b in BUILDINGS}
    assert failing(res, "A2") == roofs
    assert roofs <= failing(res, "R3")


@needs_tgm
def test_uspi_chain_consistent(loree):
    _, res = loree
    u = res.residuals[res.residuals.rule.str.startswith("U")]
    assert len(u) > 1000 and (u.verdict == "OK").all()


@needs_tgm
def test_cli_exit_code(capsys):
    assert cli.main([str(TGM), "--config", str(Path(__file__).resolve().parents[1] / "config.yaml")]) == 1
    assert "A1" in capsys.readouterr().out


@pytest.mark.skipif(not IFC.is_file(), reason="export IFC L'Orée absent")
def test_promoter_ifc_only_unknown_codes():
    # L'export IFC Treegram porte la nomenclature promoteur : tout est inconnu, rien ne plante.
    # Exception : « ST » (surface taxable française) a le même code que ST SIA 416 §1 (surface de terrain).
    from sia_check import config
    cfg = config.load(Path(__file__).resolve().parents[1] / "config.yaml")
    res = rules.run(reader.read(IFC, cfg), cfg)
    assert set(res.residuals.rule) == {"A3", "R0"}
    assert set(res.surfaces.category) == {"ST"}
    assert len(res.unknown) == 880 - 80


@needs_tgm
def test_treegram_exports_match_treegram(loree):
    # Comparé le 22.10.2026 aux exports Treegram 1778-SurfacesNettes / -SurfacesBrutes : mêmes lignes, mêmes
    # valeurs, même ordre ; s'y ajoutent les 26 SED et 47 SUT que l'export Treegram omet.
    from sia_check import config
    cfg = config.load(Path(__file__).resolve().parents[1] / "config.yaml")
    _, res = loree
    n, b = treegram.nettes(res, cfg), treegram.brutes(res, cfg)
    assert len(n) == 3221 + 26 + 47 and len(b) == 160
    assert n["Catégorie SIA"].value_counts()[["SED", "SUT"]].tolist() == [26, 47]
    assert n["ID TGM"].iloc[0] == "H170::H2527" and n["ID TGM"].is_unique and n["ID TGM"].notna().all()
    assert b.Area.sum() == pytest.approx(74518.54, abs=0.01)
    assert b.Perimeter.sum() == pytest.approx(17233.96, abs=0.01)
