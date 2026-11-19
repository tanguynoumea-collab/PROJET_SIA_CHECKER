"""Données SIG des projets du benchmark (sia_check.sig, docs/V6_PLAN.md partie 4), sans réseau : geo.admin.ch simulé."""

import json

import pytest

from sia_check import benchmark, cli, sig

from test_benchmark import mdp

REPONSES = {
    "ch.are.bauzonen": [{"attributes": {"ch_bez_f": "Zones d'habitation"}}],
    "ch.bag.radonkarte": [{"attributes": {"probability_prozent": 9}}],
    "ch.are.gueteklassen_oev": [{"attributes": {"klasse_fr": "B - bonne desserte"}}],
    "ch.are.reisezeit-oev": [{"attributes": {"oev_reisezeit_z": 34}}],
    "ch.bav.haltestellen-oev": [{"attributes": {"name": "Raccordement", "verkehrsmittel_fr": ""}, "geometry": {"points": [[2534341, 1155700]]}},
                                {"attributes": {"name": "Loin", "verkehrsmittel_fr": "Bus"}, "geometry": {"x": 2534700, "y": 1155700}},
                                {"attributes": {"name": "Proche", "verkehrsmittel_fr": "Bus"}, "geometry": {"x": 2534400, "y": 1155700}}],
    "ch.bfs.gebaeude_wohnungs_register": [{"attributes": {"strname_deinr": "Chemin de la Palissade 2", "gbauj": 2024, "gastw": 9,
                                                          "ganzwhg": 60, "lparz": "2015", "gkode": 2534341, "gkodn": 1155702}}],
    "ch.bfe.fernwaerme-nachfrage_wohn_dienstleistungsgebaeude": [{"attributes": {"needtotal": 1835.5}}],
}


@pytest.fixture
def geo(monkeypatch):
    """geo.admin.ch simulé : réponses fixes ; habitants seulement jusqu'en 2024 (2025 et 2026 vides)."""
    appels = []

    def identify(couche, e, n, tolerance, geometrie=False, annee=None, geojson=False):
        appels.append((couche, annee))
        if couche == sig.COUCHE_PARCELLES:     # bien-fonds de 50 × 40 m, et un DDP de 20 × 20 m superposé
            carre = lambda c: {"type": "Polygon", "coordinates": [[[0, 0], [c[0], 0], [c[0], c[1]], [0, c[1]], [0, 0]]]}
            return [{"geometry": carre((20, 20)), "properties": {"number": "2015-DDP", "ak": "VD"}},
                    {"geometry": carre((50, 40)), "properties": {"number": "2015", "egris_egrid": "CH975778123615", "ak": "VD"}}]
        if couche == "ch.bfs.volkszaehlung-bevoelkerungsstatistik_einwohner":
            return [{"attributes": {"number": 283}}, {"attributes": {"number": 283}}] if annee and annee <= 2024 else []
        if couche == "ch.bfs.betriebszaehlungen-beschaeftigte_vollzeitaequivalente":     # 2024 publiée incomplète
            return {2024: [{"attributes": {"number": 56}}], 2023: [{"attributes": {"number": 865}}]}.get(annee, [])
        return REPONSES.get(couche, [])

    monkeypatch.setattr(sig, "_identify", identify)
    return appels


def test_collecte_au_point_et_dans_le_rayon(geo):
    v = sig.collecter(2534340, 1155700, annee=2026)
    assert v["zone"]["valeur"] == "Zones d'habitation" and v["zone"]["source"] == "ARE"
    assert v["desserte"]["valeur"] == "B - bonne desserte"
    assert v["arret"]["valeur"] == "Proche" and v["arret"]["distance"] == 60            # le plus proche desservi
    assert v["batiment"]["annee_construction"] == 2024 and v["batiment"]["logements"] == 60
    assert v["chaleur"]["valeur"] == 1835.5
    # dernière année disponible (2024), total du disque de 300 m rapporté à sa surface
    assert v["habitants"]["annee"] == 2024
    assert v["habitants"]["valeur"] == pytest.approx(566 / sig.SURFACE_HA, abs=0.05)
    assert v["emplois"]["annee"] == 2023                                              # 2024 incomplète écartée
    assert v["emplois"]["valeur"] == pytest.approx(865 / sig.SURFACE_HA, abs=0.05)
    assert "isos" not in v                                                           # pas de donnée : omis


def test_fiche_figee_puis_refaite_si_le_projet_change_de_place(tmp_path, geo):
    assert sig.synchroniser(tmp_path, [("1778", [2534340, 1155700], "adresse")]) == (1, 0)
    fiche = json.loads((tmp_path / "SIG-1778.json").read_text(encoding="utf-8"))
    assert fiche["format"] == sig.FORMAT and fiche["position"] == [2534340, 1155700] and fiche["valeurs"]["radon"]["valeur"] == 9
    geo.clear()
    assert sig.synchroniser(tmp_path, [("1778", [2534345, 1155703], "adresse")]) == (0, 0)  # 6 m : la fiche reste
    assert geo == []
    assert sig.synchroniser(tmp_path, [("1778", [2534600, 1155700], "adresse")]) == (1, 0)  # adresse corrigée : refaite


def test_sans_reseau_la_collecte_est_reportee(tmp_path, monkeypatch):
    def hors(*a, **k):
        raise sig.Hors("pas de réseau")
    monkeypatch.setattr(sig, "_identify", hors)
    assert sig.synchroniser(tmp_path, [("1", [2534340, 1155700], "adresse"), ("2", [2530000, 1150000], "commune"),
                                       ("3", None, None)]) == (0, 2)
    assert not list(tmp_path.glob("SIG-*.json"))


def test_fiches_dans_le_json_de_la_version_complete_seulement(tmp_path, geo):
    mdp(tmp_path / "MDP-7001-A.xlsx", infos={"ID projet": 7001, "Commune": "Crissier", "Groupe d'utilisateurs": "Light"})
    complet, light = tmp_path / "complet.json", tmp_path / "light.json"
    assert cli.main(["--benchmark", str(tmp_path), "--benchmark-json", str(complet), "--benchmark-sig"]) == 0
    assert (tmp_path / "SIG-7001.json").exists()
    assert json.loads(complet.read_text(encoding="utf-8"))["projets"][0]["sig"]["radon"]["valeur"] == 9
    assert cli.main(["--benchmark", str(tmp_path), "--benchmark-json", str(light), "--benchmark-sig",
                     "--benchmark-groupe", "Light"]) == 0
    assert json.loads(light.read_text(encoding="utf-8"))["projets"][0]["sig"] is None
    assert "radon" not in light.read_text(encoding="utf-8")


@pytest.mark.parametrize("habitants, emplois, attendu", [(140, 39, "Urbain dense"), (47, 26, "Urbain"), (36, 18, "Périurbain"),
                                                        (15, 1, "Rural"), (None, 25, "Périurbain")])
def test_type_de_site_selon_la_densite_alentour(habitants, emplois, attendu):
    v = {k: {"valeur": x} for k, x in (("habitants", habitants), ("emplois", emplois)) if x is not None}
    assert sig.type_site(v)["valeur"] == attendu
    assert sig.type_site({"zone": {"valeur": "Zones mixtes"}}) is None


def test_type_de_site_dans_le_json(tmp_path, geo):
    mdp(tmp_path / "MDP-7001-A.xlsx", infos={"ID projet": 7001, "Commune": "Crissier"})
    json_ = tmp_path / "b.json"
    assert cli.main(["--benchmark", str(tmp_path), "--benchmark-json", str(json_), "--benchmark-sig"]) == 0
    site = json.loads(json_.read_text(encoding="utf-8"))["projets"][0]["sig"]["site"]
    assert site["valeur"] == "Périurbain" and site["densite"]     # 20 habitants + 31 emplois par ha == pytest.approx((566 + 865) / sig.SURFACE_HA, abs=0.1)
    assert "site" not in json.loads((tmp_path / "SIG-7001.json").read_text(encoding="utf-8"))["valeurs"]   # calculé, pas figé


def test_parcelle_le_bien_fonds_plutot_que_le_ddp(geo):
    v = sig.collecter(2534340, 1155700, annee=2026)["parcelle"]
    assert v["valeur"] == 2000 and v["numero"] == "2015" and v["egrid"] == "CH975778123615" and v["superposes"] == 1
    # trou déduit, multipolygone additionné
    anneau = lambda x0, c: [[x0, 0], [x0 + c, 0], [x0 + c, c], [x0, c]]
    assert sig.surface({"type": "MultiPolygon", "coordinates": [[anneau(0, 10), anneau(2, 2)], [anneau(100, 5)]]}) == 100 - 4 + 25


def test_indice_d_utilisation_cadastre_ou_saisie_du_mdp(tmp_path, geo):
    from sia_check import benchmark
    mdp(tmp_path / "MDP-7001-A.xlsx", infos={"ID projet": 7001, "Commune": "Crissier", "Groupe d'utilisateurs": "Light"})
    mdp(tmp_path / "MDP-7002-A.xlsx", infos={"ID projet": 7002, "Commune": "Crissier", "Surface du terrain (m²)": 4000,
                                             "Groupe d'utilisateurs": "Light"})
    json_ = tmp_path / "b.json"
    assert cli.main(["--benchmark", str(tmp_path), "--benchmark-json", str(json_), "--benchmark-sig"]) == 0
    projets = {p["id"]: p for p in json.loads(json_.read_text(encoding="utf-8"))["projets"]}
    assert projets["7001"]["totaux"]["TERRAIN"] == 2000 and projets["7001"]["infos"]["terrain_source"] == "parcelle 2015 (cadastre)"
    assert projets["7002"]["totaux"]["TERRAIN"] == 4000 and projets["7002"]["infos"]["terrain_source"] == "MDP"
    ius = projets["7001"]["kpis"]["SP_HS/TERRAIN"]
    assert ius["den"] == 2000 and ius["valeur"] == pytest.approx(ius["num"] / 2000)
    # version sans données SIG : seule la saisie du MDP compte
    light = tmp_path / "l.json"
    assert cli.main(["--benchmark", str(tmp_path), "--benchmark-json", str(light), "--benchmark-sig", "--benchmark-groupe", "Light"]) == 0
    projets = {p["id"]: p for p in json.loads(light.read_text(encoding="utf-8"))["projets"]}
    assert "TERRAIN" not in projets["7001"]["totaux"] and projets["7002"]["totaux"]["TERRAIN"] == 4000
    assert "SP_HS/TERRAIN" in benchmark.KPI_BY_ID


def test_connexion_coupee_une_fois_on_reessaie(monkeypatch):
    import io
    import urllib.error
    appels = []

    def urlopen(url, timeout):
        appels.append(url)
        if len(appels) == 1:
            raise urllib.error.URLError("Remote end closed connection without response")
        return io.BytesIO(b'{"results": [{"attributes": {"probability_prozent": 9}}]}')

    monkeypatch.setattr(sig.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(sig, "PAUSE", 0)
    assert sig._identify("ch.bag.radonkarte", 2534340, 1155700, 5)[0]["attributes"]["probability_prozent"] == 9
    assert len(appels) == 2
    appels.clear()
    monkeypatch.setattr(sig.urllib.request, "urlopen", lambda url, timeout: (_ for _ in ()).throw(urllib.error.URLError("hors ligne")))
    with pytest.raises(sig.Hors):
        sig._identify("ch.bag.radonkarte", 2534340, 1155700, 5)


def test_sans_option_pas_de_collecte(tmp_path, geo):
    mdp(tmp_path / "MDP-7001-A.xlsx", infos={"ID projet": 7001, "Commune": "Crissier"})
    assert cli.main(["--benchmark", str(tmp_path), "--benchmark-json", str(tmp_path / "b.json")]) == 0
    assert geo == [] and not (tmp_path / "SIG-7001.json").exists()
    assert benchmark.construire(*benchmark.lire_dossier(tmp_path), dossier=tmp_path)["projets"][0]["sig"] is None
