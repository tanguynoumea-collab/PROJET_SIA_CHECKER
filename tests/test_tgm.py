"""Décodeur .tgm et lecteur .tgm sur un fichier binaire synthétique reproduisant la structure observée."""

import struct

import pytest

from sia_check import reader, tgm

JUNK = b"\xff\xfe" * 9  # octets non décodables entre deux sacs, comme dans un vrai .tgm


def bag(name: str, props: dict, zero_tag: bool = False) -> bytes:
    out = struct.pack("<i", len(props))
    for k, v in props.items():
        kb = k.encode()
        out += struct.pack("<i", len(kb)) + kb
        if isinstance(v, str):
            vb = v.encode()
            out += (b"\x00" if zero_tag else b"\x02") + b"\x00\x00\x02" + struct.pack("<i", len(vb)) + vb
        elif isinstance(v, float):
            out += b"\x04\x00\x00\x04" + struct.pack("<d", v)
        else:
            out += b"\x08\x00\x00\x08" + struct.pack("<i", v)
        out += b"\x00" * 4
    nb = name.encode()
    return JUNK + out + struct.pack("<q", len(nb)) + nb + JUNK


CAT = "Catégorie SIA"


def node(code, area):
    return bag(code, {CAT: code, "Area": area})


def leaf(name, code, area, **extra):
    return bag(name, {CAT: code, "Area": area, **extra})


@pytest.fixture
def tgm_file(tmp_path):
    data = b"".join([
        bag("SRV", {"Area": 3.0}),                                   # arbre promoteur : sans catégorie SIA
        # bloc niveau A_N01
        node("SUP", 50.0),
        leaf("A_N01_ShellByTgm-1_SpaceByTgm-1_SUP", "SUP", 50.0, Type="Chambre"),
        node("SP", 100.0),
        node("SNH", 50.0),
        leaf("A_N01_Apart-1_SNH", "SNH", 50.0, ApartmentByTgm="A_N01_Apart-1", Bedrooms=2),
        # bloc niveau A_N02 : premier nœud sans enfant, le niveau vient de la surface suivante
        node("SUP", 0.0),
        node("SD", 70.0),
        leaf("A_N02_ShellByTgm-1_SpaceByTgm-1_SD", "SD", 70.0),
        node("SP", 80.0),
        # surface modifiée après coup, ajoutée en fin de fichier, tag chaîne à 1er octet nul
        bag("A_N01_ExtShellByTgm-7_SEU", {CAT: "SEU", "Area": 4.3, "Type": "Balcon"}, zero_tag=True),
    ])
    p = tmp_path / "mini.tgm"
    p.write_bytes(data)
    return p


def test_scan_decodes_all_bags(tgm_file):
    bags = list(tgm.scan(tgm_file.read_bytes()))
    assert [b.name for b in bags][:3] == ["SRV", "SUP", "A_N01_ShellByTgm-1_SpaceByTgm-1_SUP"]
    assert len(bags) == 11
    snh = next(b for b in bags if b.name == "A_N01_Apart-1_SNH")
    assert snh.props["Bedrooms"] == 2 and snh.props["Area"] == pytest.approx(50.0)


def test_read_bag_rejects_garbage():
    assert tgm.read_bag(b"\x02\x00\x00\x00" + b"\xff" * 40, 0) is None


def test_read_tgm_assigns_nodes_to_levels(tgm_file, cfg):
    df = reader.read(tgm_file, cfg)
    sp = df[(df.kind == "node") & (df.category == "SP")].set_index("level").area
    assert sp.to_dict() == {"N01": 100.0, "N02": 80.0}
    assert set(df[df.kind == "node"].building) == {"A"}
    assert "SRV" not in set(df.category)  # sans catégorie SIA : hors arbre


def test_read_tgm_leaves_by_name_not_position(tgm_file, cfg):
    df = reader.read(tgm_file, cfg)
    seu = df[df.category == "SEU"].iloc[0]
    assert (seu.building, seu.level, seu.kind, seu.room_type) == ("A", "N01", "leaf", "Balcon")


def test_read_tgm_lot(tgm_file, cfg):
    df = reader.read(tgm_file, cfg)
    assert df[df.category == "SNH"].query("kind == 'leaf'").lot.iloc[0] == "A_N01_Apart-1"


def test_read_tgm_without_sia_raises(tmp_path, cfg):
    p = tmp_path / "vide.tgm"
    p.write_bytes(bag("SRV", {"Area": 1.0}))
    with pytest.raises(reader.ReadError):
        reader.read(p, cfg)


def test_read_missing_file(tmp_path, cfg):
    with pytest.raises(reader.ReadError):
        reader.read(tmp_path / "absent.tgm", cfg)
