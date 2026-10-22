"""Exports au gabarit Excel Treegram (treegram.py)."""

import struct

import pandas as pd

from sia_check import reader, rules, treegram
from test_tgm import CAT, bag


def test_nettes_columns_and_content(result, cfg):
    df = treegram.nettes(result, cfg)
    assert list(df.columns) == treegram.NETTES_COLUMNS
    cats = set(df["Catégorie SIA"])
    assert {"SUP", "SD", "SEU", "SED", "SUT"} <= cats           # SED et SUT gardés, contrairement à Treegram
    assert not cats & {"SP", "SEP", "SNH", "SHA", "XYZ"}         # racines, USPI et inconnus exclus
    assert (df["Object.Type"] == "SiaSurfaceBySpace").all()
    assert (df["Object.Name"] == df["object.name2"]).all()
    assert "err-n00-seu-node" not in set(df["Object.Name"])      # total de niveau : pas une ligne nette


def test_brutes_one_row_per_level_sp_first(result, cfg):
    df = treegram.brutes(result, cfg)
    assert list(df.columns) == treegram.BRUTES_COLUMNS
    assert set(df["Object.Name"]) <= {"SP", "SEP"}
    names = list(df["Object.Name"])
    assert names == sorted(names, key=["SP", "SEP"].index)       # SP puis SEP, comme Treegram
    sp = df[(df["Object.Name"] == "SP") & (df.BuildingByTgm == "OK")].set_index("StoreyByTgm").Area
    assert sp.to_dict() == {"N01": 100, "N02": 100}


def test_write_two_workbooks(result, cfg, tmp_path):
    paths = treegram.write(result, cfg, tmp_path, "Synth")
    assert [p.name for p in paths] == ["Synth-SurfacesNettes.xlsx", "Synth-SurfacesBrutes.xlsx"]
    back = pd.read_excel(paths[0], sheet_name="SurfacesNettes")
    assert list(back.columns) == treegram.NETTES_COLUMNS


def test_tgm_id_and_gross_properties_from_tgm(tmp_path, cfg):
    def header(eid):
        return b"\x12" + b"\x00" * 7 + struct.pack("<i", 170) + b"\x04" + struct.pack("<i", eid) + b"\x04\x01" + b"\x00" * 7

    data = b"".join([
        header(2613), bag("SP", {CAT: "SP", "Area": 883.1841, "GrossHeight": 2.84, "Perimeter": 155.014}),
        header(2527), bag("A01_N01_ShellByTgm-12_SpaceByTgm-1_SD", {CAT: "SD", "Area": 12.5, "Type": "Escalier"}),
    ])
    p = tmp_path / "mini.tgm"
    p.write_bytes(data)
    res = rules.run(reader.read(p, cfg), cfg)
    n, b = treegram.nettes(res, cfg).iloc[0], treegram.brutes(res, cfg).iloc[0]
    assert (n["ID TGM"], n.StoreyByTgm, n.Type) == ("H170::H2527", "N01", "Escalier")
    assert (b["ID TGM"], b.Area, b.GrossHeight, b.Perimeter, b.StoreyByTgm) == ("H170::H2613", 883.184, 2.84, 155.014, "N01")
