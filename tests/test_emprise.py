"""Emprise des bâtiments et forme estimée (sia_check.emprise, docs/V5_PLAN.md partie 5)."""

import pytest

pytest.importorskip("shapely")

from shapely import Point, Polygon, box  # noqa: E402
from shapely.affinity import rotate, scale  # noqa: E402

from sia_check import emprise, formes  # noqa: E402


def decrire(g, level="N00", code="SP"):
    return emprise.emprises([("B", level, None, g, code)])["B"]


@pytest.mark.parametrize("nom, g, attendu", [
    ("carré", box(0, 0, 20, 20), "Carré"),
    ("rectangle", box(0, 0, 30, 18), "Rectangle compact"),
    ("barre tournée", rotate(box(0, 0, 60, 12), 30), "Barre"),
    ("L", Polygon([(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)]), "En L"),
    ("T", box(0, 20, 30, 30).union(box(10, 0, 20, 20)), "En T"),
    ("U", Polygon([(0, 0), (30, 0), (30, 25), (20, 25), (20, 10), (10, 10), (10, 25), (0, 25)]), "En U"),
    ("H", box(0, 0, 10, 30).union(box(20, 0, 30, 30)).union(box(10, 10, 20, 20)), "En peigne / en H"),
    ("Z", box(0, 0, 20, 10).union(box(10, 10, 30, 20)), "À redans / en Z"),
    ("cour fermée", box(0, 0, 40, 40).difference(box(10, 10, 30, 30)), "Cour fermée / îlot"),
    ("deux plots", box(0, 0, 15, 15).union(box(30, 0, 45, 15)), "Plusieurs plots"),
    ("ellipse", scale(Point(0, 0).buffer(10, 32), 2, 1), "Rond / ovale"),
    ("arc", Point(0, 0).buffer(40, 64).difference(Point(0, 0).buffer(28, 64)).intersection(box(-50, 0, 50, 50)),
     "Courbe / arc"),
])
def test_forme_estimee(nom, g, attendu):
    d = decrire(g)
    assert d["forme_estimee"] == attendu, (nom, d["forme_estimee_raison"])
    assert d["forme_estimee"] in formes.FORMES


def test_mesures_d_une_barre_tournee():
    d = decrire(rotate(box(0, 0, 60, 12), 30))
    assert (d["aire_m2"], d["longueur_m"], d["largeur_m"], d["elancement"]) == (720.0, 60.0, 12.0, 5.0)
    assert d["rectangularite"] == d["convexite"] == 1.0 and d["axe_long_deg"] == 30
    assert d["parties"] == 1 and d["cours"] == {"nombre": 0, "aires_m2": []} and d["angles_rentrants"] == 0
    # contour recentré et tourné sur l'axe long : un rectangle de ±30 × ±6 m
    assert sorted(map(tuple, d["contours"][0]["contour"])) == [(-30, -6), (-30, 6), (30, -6), (30, 6)]


def test_cour_et_angles_rentrants():
    d = decrire(box(0, 0, 40, 40).difference(box(10, 10, 30, 30)).difference(box(1, 1, 3, 3)))
    assert d["cours"] == {"nombre": 1, "aires_m2": [400.0]}       # trou de 4 m² (gaine) bouché
    assert len(d["contours"][0]["cours"]) == 1
    assert decrire(Polygon([(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)]))["angles_rentrants"] == 1


def test_regle_d_emprise_union_hors_sol():
    items = [("A", "S01", None, box(-20, -20, 60, 60), "SP"),            # sous-sol plus grand : ignoré
             ("A", "N00", None, box(0, 0, 40, 10), "SP"),
             ("A", "N01", None, box(0, 0, 10, 40), "SP"),                # ailes à des étages différents : un L
             ("A", "N01", None, box(0, 0, 5, 5), "SUP")]
    d = emprise.emprises(items)["A"]
    assert d["source"] == "SP hors-sol" and d["niveaux"] == ["N00", "N01"]
    assert d["aire_m2"] == 700.0 and d["aire_etage_max_m2"] == 400.0 and d["forme_estimee"] == "En L"
    # rang connu (visionneuse) : il l'emporte sur le code d'étage
    assert emprise.sous_sol("X", -1) and not emprise.sous_sol("S01", 0)
    assert emprise.sous_sol("S01") and emprise.sous_sol("2SS") and emprise.sous_sol("-1") and not emprise.sous_sol("N03")


def test_sans_sp_hors_sol_puis_sans_sp():
    d = emprise.emprises([("A", "S01", -1, box(0, 0, 20, 10), "SP")])["A"]
    assert d["source"].startswith("SP des sous-sols")
    # sans SP : surfaces intérieures, murs de 0,3 m franchis
    d = emprise.emprises([("A", "N00", None, box(0, 0, 10, 10), "SUP"),
                          ("A", "N00", None, box(10.3, 0, 20, 10), "SD")])["A"]
    assert d["source"].startswith("surfaces intérieures") and d["parties"] == 1
    assert emprise.emprises([("A", "N00", None, None, "SP")]) == {}


def test_contour_plafonne():
    d = decrire(Point(0, 0).buffer(30, 256).union(box(-5, 0, 5, 40)))
    assert len(d["contours"][0]["contour"]) <= emprise.MAX_SOMMETS
