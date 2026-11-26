"""Données SIG des projets du benchmark (docs/V6_PLAN.md, partie 4) : le contexte de chaque projet lu sur geo.admin.ch,
gardé dans une fiche SIG-<id>.json à côté de son MDP, dans le dossier de la base.

Seules les coordonnées LV95 du projet partent sur le réseau (API identify, comme un clic sur la carte du dashboard).
La fiche est figée à la collecte : chaque valeur garde son année et sa source. Elle n'est refaite que si le projet a
changé de place (adresse corrigée), ou si son format a changé. Sans réseau, la collecte est reportée, jamais bloquante.

Au point du projet : parcelle (numéro et surface, mensuration officielle), zone à bâtir, site ISOS, radon, sol de
fondation, desserte et accessibilité en transports publics, temps de parcours jusqu'au centre, arrêt le plus proche,
bâtiment du registre fédéral le plus proche, et pour lui le besoin de chaleur. Dans un rayon de 300 m : habitants, logements et emplois à l'hectare, dernière année disponible.

Exclues, faute de réponse point par point de geo.admin.ch (calques image) : bruit routier et ferroviaire, fibre,
ruissellement.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

FORMAT = "sia-check-sig"
VERSION = 2                                   # 2 : parcelle (V6_PLAN, partie 7)
IDENTIFY = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify"
RAYON = 300                                   # m : densités autour du projet
SURFACE_HA = math.pi * RAYON ** 2 / 10_000    # 28,3 ha : la moyenne divise le total du disque par sa surface
DEPLACEMENT = 10                              # m : au-delà, le projet a changé de place, la fiche est refaite
DELAI = 30                                    # s par requête
ESSAIS = 3                                    # tentatives par requête (connexion coupée par le serveur)
PAUSE = 1                                     # s avant de réessayer, croissante


class Hors(OSError):
    """geo.admin.ch injoignable : la collecte est reportée."""


def nom_fichier(id_projet: str) -> str:
    return f"SIG-{str(id_projet).strip()}.json"


def _identify(couche: str, e: float, n: float, tolerance: int, geometrie=False, annee: int | None = None,
              geojson=False) -> list[dict]:
    # 1 000 px pour 1 000 m : la tolérance, en pixels, est une distance en mètres
    q = {"geometryType": "esriGeometryPoint", "geometry": f"{e},{n}", "sr": "2056", "imageDisplay": "1000,1000,96",
         "mapExtent": f"{e - 500},{n - 500},{e + 500},{n + 500}", "tolerance": str(tolerance),
         "layers": f"all:{couche}", "returnGeometry": "true" if geometrie else "false", "lang": "fr"}
    if annee is not None:
        q["timeInstant"] = str(annee)
    if geojson:
        q["geometryFormat"] = "geojson"
    for essai in range(ESSAIS):
        try:
            with urllib.request.urlopen(f"{IDENTIFY}?{urllib.parse.urlencode(q)}", timeout=DELAI) as r:
                return json.load(r).get("results", [])
        except urllib.error.HTTPError as ex:
            log.warning("SIG : calque %s non interrogeable (%s)", couche, ex.code)
            return []
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            # une connexion coupée par le serveur arrive : on réessaie avant de conclure au réseau absent
            if essai + 1 == ESSAIS:
                raise Hors(f"geo.admin.ch injoignable ({ex})") from ex
            time.sleep(PAUSE * (essai + 1))
    return []


def _distance(res: dict, e: float, n: float) -> float:
    # géométrie esri : {x, y} ou {points: [[x, y]]} ; sinon le centre de la bbox, ou les coordonnées du RegBL
    g = res.get("geometry") or {}
    if "x" in g:
        return math.hypot(g["x"] - e, g["y"] - n)
    if g.get("points"):
        x, y = g["points"][0][:2]
        return math.hypot(x - e, y - n)
    a = res.get("attributes", {})
    if a.get("gkode"):
        return math.hypot(a["gkode"] - e, a["gkodn"] - n)
    if b := res.get("bbox"):
        return math.hypot((b[0] + b[2]) / 2 - e, (b[1] + b[3]) / 2 - n)
    return math.inf


def _aire(anneau) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1, *_), (x2, y2, *_) in zip(anneau, anneau[1:] + anneau[:1]))) / 2


def surface(geometrie: dict | None) -> float:
    """Surface d'un polygone GeoJSON (m², LV95), trous déduits ; 0 pour une autre géométrie."""
    g = geometrie or {}
    polys = [g.get("coordinates")] if g.get("type") == "Polygon" else g.get("coordinates") if g.get("type") == "MultiPolygon" else []
    return sum(_aire(p[0]) - sum(_aire(t) for t in p[1:]) for p in polys if p)


COUCHE_PARCELLES = "ch.kantone.cadastralwebmap-farbe"


def parcelle(e: float, n: float) -> dict | None:
    """La parcelle sous le point (mensuration officielle, publiée par les cantons sur geo.admin.ch) : sa surface, son
    numéro et son EGRID. Un droit de superficie (DDP) se superpose au bien-fonds qui le contient : le plus grand des
    immeubles trouvés est le bien-fonds."""
    trouves = [(surface(r.get("geometry")), r.get("properties") or r.get("attributes") or {}, r.get("geometry"))
               for r in _identify(COUCHE_PARCELLES, e, n, 0, geometrie=True, geojson=True)]
    trouves = [t for t in trouves if t[0] > 0]
    if not trouves:
        return None
    s, a, g = max(trouves, key=lambda t: t[0])
    v = _valeur(round(s), "m²", source="Mensuration officielle (cantons)", couche=COUCHE_PARCELLES)
    # V7 : le polygone (LV95, au décimètre), pour la planche des implantations et la forme de la parcelle
    if geo := geometrie_parcelle(g):
        v["geometrie"] = geo
    v.update({k: a.get(c) for k, c in (("numero", "number"), ("egrid", "egris_egrid"), ("canton", "ak")) if a.get(c)})
    if len(trouves) > 1:
        v["superposes"] = len(trouves) - 1     # DDP ou autre immeuble au même point
    return v


def geometrie_parcelle(g: dict | None) -> list[list[list[list[float]]]] | None:
    """Polygones d'une géométrie GeoJSON, [polygone][anneau][point] en LV95 arrondi au décimètre ; None sinon."""
    g = g or {}
    polys = [g.get("coordinates")] if g.get("type") == "Polygon" else g.get("coordinates") if g.get("type") == "MultiPolygon" else []
    out = [[[[round(x, 1), round(y, 1)] for x, y, *_ in anneau] for anneau in poly] for poly in polys or [] if poly]
    return out or None


def _valeur(v, unite=None, annee=None, source=None, couche=None) -> dict:
    return {k: x for k, x in {"valeur": v, "unite": unite, "annee": annee, "source": source, "couche": couche}.items()
            if x is not None}


def _densite(couche: str, e: float, n: float, source: str, annee_max: int) -> dict | None:
    """Total des hectares dans le rayon, dernière année complète, rapporté à la surface du disque (par hectare).

    Une année publiée incomplète (STATENT 2024 sur geo.admin.ch : 56 emplois là où 2023 en compte 865) est écartée :
    une année qui perd plus de la moitié du total de la précédente cède la place à celle-ci."""
    totaux: list[tuple[int, float]] = []
    for annee in range(annee_max, annee_max - 8, -1):
        res = _identify(couche, e, n, RAYON, annee=annee)
        if res:
            totaux.append((annee, sum((r["attributes"].get("number") or 0) for r in res)))
            if len(totaux) == 2:
                break
    if not totaux:
        return None
    annee, total = totaux[0]
    if len(totaux) == 2 and total < 0.5 * totaux[1][1]:
        annee, total = totaux[1]
    return _valeur(round(total / SURFACE_HA, 1), "par ha (300 m)", annee, source, couche)


def collecter(e: float, n: float, annee: int | None = None) -> dict:
    """Les valeurs de contexte au point LV95 (e, n). Hors si le réseau manque ; un calque sans donnée est omis."""
    annee = annee or dt.date.today().year
    v: dict[str, dict] = {}

    def premier(couche, tol=5):
        res = _identify(couche, e, n, tol)
        return res[0]["attributes"] if res else None

    if p := parcelle(e, n):
        v["parcelle"] = p
    if a := premier("ch.are.bauzonen"):
        v["zone"] = _valeur(a.get("ch_bez_f"), source="ARE", couche="ch.are.bauzonen")
    if a := premier("ch.bak.bundesinventar-schuetzenswerte-ortsbilder"):
        v["isos"] = _valeur(a.get("ortsbildname") or a.get("name") or a.get("label"), source="OFC",
                            couche="ch.bak.bundesinventar-schuetzenswerte-ortsbilder")
    if a := premier("ch.bag.radonkarte"):
        v["radon"] = _valeur(a.get("probability_prozent"), "% de probabilité de dépasser 300 Bq/m³", source="OFSP",
                             couche="ch.bag.radonkarte")
    if a := premier("ch.bafu.gefahren-baugrundklassen"):
        v["sol"] = _valeur(a.get("bgk") or a.get("label"), source="OFEV", couche="ch.bafu.gefahren-baugrundklassen")
    if a := premier("ch.are.gueteklassen_oev"):
        v["desserte"] = _valeur(a.get("klasse_fr"), source="ARE", couche="ch.are.gueteklassen_oev")
    if a := premier("ch.are.erreichbarkeit-oev"):
        v["accessibilite"] = _valeur(a.get("oev_erreichb_ewap"), "habitants et emplois accessibles en TP", source="ARE",
                                     couche="ch.are.erreichbarkeit-oev")
    if a := premier("ch.are.reisezeit-oev"):
        v["temps_centre"] = _valeur(a.get("oev_reisezeit_z"), "min en TP", source="ARE", couche="ch.are.reisezeit-oev")

    # arrêts desservis seulement : le calque compte aussi des points d'exploitation (raccordements) sans voyageurs
    arrets = [r for r in _identify("ch.bav.haltestellen-oev", e, n, 500, geometrie=True)
              if r["attributes"].get("name") and r["attributes"].get("verkehrsmittel_fr")]
    if arrets:
        r = min(arrets, key=lambda x: _distance(x, e, n))
        a = r["attributes"]
        v["arret"] = _valeur(a.get("name"), source="OFT", couche="ch.bav.haltestellen-oev")
        if math.isfinite(d := _distance(r, e, n)):
            v["arret"]["distance"] = round(d)
        v["arret"]["moyen"] = a.get("verkehrsmittel_fr")

    batiments = _identify("ch.bfs.gebaeude_wohnungs_register", e, n, 50, geometrie=True)
    if batiments:
        r = min(batiments, key=lambda x: _distance(x, e, n))
        a = r["attributes"]
        v["batiment"] = _valeur(a.get("strname_deinr"), source="OFS RegBL", couche="ch.bfs.gebaeude_wohnungs_register")
        v["batiment"].update({k: a.get(c) for k, c in (("egid", "egid"), ("annee_construction", "gbauj"), ("niveaux", "gastw"),
                                                         ("logements", "ganzwhg"), ("parcelle", "lparz"), ("emprise", "garea"))
                              if a.get(c) not in (None, "")})
        be, bn = a.get("gkode") or e, a.get("gkodn") or n
        if c := _identify("ch.bfe.fernwaerme-nachfrage_wohn_dienstleistungsgebaeude", be, bn, 15):
            ch = c[0]["attributes"]
            v["chaleur"] = _valeur(ch.get("needtotal"), "MWh/an", source="OFEN",
                                   couche="ch.bfe.fernwaerme-nachfrage_wohn_dienstleistungsgebaeude")

    for cle, couche, source in (("habitants", "ch.bfs.volkszaehlung-bevoelkerungsstatistik_einwohner", "OFS STATPOP"),
                                ("logements", "ch.bfs.volkszaehlung-gebaeudestatistik_wohnungen", "OFS StatBL"),
                                ("emplois", "ch.bfs.betriebszaehlungen-beschaeftigte_vollzeitaequivalente", "OFS STATENT (EPT)")):
        if d := _densite(couche, e, n, source, annee):
            v[cle] = d
    return v


# Type de site (V6_PLAN, partie 5) : la densité humaine alentour, habitants + emplois à l'hectare dans 300 m. La
# typologie officielle des communes (OFS) n'est pas interrogeable sur geo.admin.ch, et elle classe une commune entière ;
# la densité décrit le voisinage du projet. Seuils du plus dense au moins dense.
TYPES_SITE = (("Urbain dense", 150), ("Urbain", 60), ("Périurbain", 20), ("Rural", 0))


def type_site(valeurs: dict) -> dict | None:
    """Le type de site d'après les densités de la fiche ; None sans aucune des deux densités."""
    h, e = ((valeurs.get(k) or {}).get("valeur") for k in ("habitants", "emplois"))
    if h is None and e is None:
        return None
    d = (h or 0) + (e or 0)
    return {"valeur": next(nom for nom, seuil in TYPES_SITE if d >= seuil), "densite": round(d, 1),
            "unite": "habitants + emplois par ha (300 m)", "source": "SIA Check, d'après OFS STATPOP et STATENT"}


def valeurs_benchmark(dossier: Path, id_projet: str) -> dict | None:
    """Les valeurs de la fiche d'un projet pour benchmark.json, type de site compris (calculé à la lecture : les seuils
    peuvent évoluer sans refaire les fiches) ; None sans fiche."""
    fiche = lire(dossier, id_projet)
    if not fiche:
        return None
    v = dict(fiche.get("valeurs") or {})
    if site := type_site(v):
        v["site"] = site
    return v


def lire(dossier: Path, id_projet: str) -> dict | None:
    """La fiche d'un projet, ou None (absente, illisible, d'un autre format)."""
    path = Path(dossier) / nom_fichier(id_projet)
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if d.get("format") == FORMAT and d.get("version") == VERSION else None


def a_jour(fiche: dict | None, position) -> bool:
    """Fiche existante, au bon format, et prise à la même place (à DEPLACEMENT mètres près)."""
    if not fiche or not position or not fiche.get("position"):
        return False
    return math.hypot(fiche["position"][0] - position[0], fiche["position"][1] - position[1]) <= DEPLACEMENT


def ecrire(dossier: Path, id_projet: str, position, precision: str | None, valeurs: dict, date: str | None = None) -> Path:
    path = Path(dossier) / nom_fichier(id_projet)
    fiche = {"format": FORMAT, "version": VERSION, "id": str(id_projet), "date": date or dt.date.today().isoformat(),
             "position": [round(position[0]), round(position[1])], "precision": precision, "valeurs": valeurs}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(fiche, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def synchroniser(dossier: Path, projets: list[tuple[str, list | None, str | None]]) -> tuple[int, int]:
    """Collecte la fiche des projets qui n'en ont pas, ou qui ont changé de place : (collectées, reportées). Le premier
    échec réseau reporte toutes les suivantes (inutile d'attendre chaque délai)."""
    collectees = reportees = 0
    for id_projet, position, precision in projets:
        if not position:
            continue
        if a_jour(fiche := lire(dossier, id_projet), position):
            # fiche d'avant la V7 : seule la parcelle est reprise, pour son polygone ([] : pas de polygone, ne pas
            # redemander à chaque lecture) ; la fiche garde sa date
            ancienne = fiche["valeurs"].get("parcelle") or {}
            if not reportees and ancienne and "geometrie" not in ancienne:
                try:
                    p = parcelle(*fiche["position"]) or ancienne
                    ecrire(dossier, id_projet, fiche["position"], fiche.get("precision"),
                           {**fiche["valeurs"], "parcelle": {**p, "geometrie": p.get("geometrie") or []}}, date=fiche.get("date"))
                    collectees += 1
                except Hors as ex:
                    log.warning("SIG reportée : %s", ex)
                    reportees += 1
                except OSError as ex:
                    log.warning("SIG de %s non écrite : %s", id_projet, ex)
            continue
        if reportees:
            reportees += 1
            continue
        try:
            ecrire(dossier, id_projet, position, precision, collecter(*position))
            collectees += 1
        except Hors as ex:
            log.warning("SIG reportée : %s", ex)
            reportees += 1
        except OSError as ex:
            log.warning("SIG de %s non écrite : %s", id_projet, ex)
    return collectees, reportees
