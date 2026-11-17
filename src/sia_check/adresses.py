"""Position exacte d'un projet d'après son adresse (docs/V5_PLAN.md, partie 3 : vue Carte du dashboard).

Source : le répertoire officiel des adresses de bâtiments de swisstopo (données ouvertes), un CSV zippé d'environ
140 Mo, téléchargé une fois par SIA Check. À la première lecture, il est indexé dans une base SQLite posée à côté
(`adresses.sqlite`, reconstruite si le registre est plus récent) : les recherches suivantes sont instantanées et se
font hors ligne. L'adresse d'un projet ne quitte donc jamais le poste.

Une adresse est « rue numéro[, NPA localité] » (ou « numéro rue », à la française). On cherche la rue et le numéro
dans la commune (ou le NPA) du projet ; à défaut de numéro, le milieu de la rue. Sans résultat : None, et le projet
reste au centre de sa commune (sia_check.localites).
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import zipfile
from pathlib import Path

from .localites import cle

# Abréviations courantes des noms de rue, développées avant la recherche
ABREVIATIONS = {"av": "avenue", "ave": "avenue", "ch": "chemin", "che": "chemin", "rte": "route", "bd": "boulevard",
                "boul": "boulevard", "pl": "place", "r": "rue", "imp": "impasse", "sent": "sentier", "pass": "passage",
                "quai": "quai", "str": "strasse", "prom": "promenade", "all": "allee"}


def cle_rue(rue: str) -> str:
    mots = cle(rue).split()
    mots = [ABREVIATIONS.get(m, m) for m in mots]
    s = " ".join(mots)
    return re.sub(r"(\w)str\b", r"\1strasse", s)     # « Bahnhofstr. » → bahnhofstrasse


def analyser(adresse: str) -> tuple[str, str | None, str | None, str | None] | None:
    """(rue, numéro, NPA, localité) d'une adresse ; None si aucune rue ne s'en dégage."""
    if not adresse or not str(adresse).strip():
        return None
    texte = re.sub(r"\s+", " ", str(adresse)).strip()
    tete, _, reste = texte.partition(",")
    npa = lieu = None
    m = re.search(r"\b(\d{4})\b\s*(.*)$", reste)
    if m:
        npa, lieu = m.group(1), m.group(2).strip() or None
    elif reste.strip():
        lieu = reste.strip()
    m = re.match(r"^(?P<num>\d+\s?[a-zA-Z]?)\s+(?P<rue>\D.*)$", tete)                 # « 26 avenue de Morges »
    if not m:
        m = re.match(r"^(?P<rue>.*?\D)\s+(?P<num>\d+\s?[a-zA-Z]?(?:[./]\d+)?)$", tete)  # « Avenue de Morges 26 »
    if m:
        return m.group("rue").strip(), m.group("num").replace(" ", "").lower(), npa, lieu
    return tete, None, npa, lieu


def indexer(registre: Path) -> Path:
    """Base SQLite du registre (à côté du zip), construite ou reconstruite si le registre a changé."""
    base = registre.with_name("adresses.sqlite")
    if base.exists() and base.stat().st_mtime >= registre.stat().st_mtime:
        return base
    tmp = base.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute("CREATE TABLE a (rue TEXT, numero TEXT, npa TEXT, commune TEXT, canton TEXT, e REAL, n REAL)")
    with zipfile.ZipFile(registre) as z:
        nom = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(nom) as f:
            lignes = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";")
            lot = []
            for r in lignes:
                if not r.get("ADR_EASTING") or not r.get("STN_LABEL"):
                    continue
                lot.append((cle_rue(r["STN_LABEL"]), (r.get("ADR_NUMBER") or "").replace(" ", "").lower(),
                            (r.get("ZIP_LABEL") or "")[:4], cle(r.get("COM_NAME") or ""), r.get("COM_CANTON") or "",
                            float(r["ADR_EASTING"]), float(r["ADR_NORTHING"])))
                if len(lot) >= 50_000:
                    con.executemany("INSERT INTO a VALUES (?,?,?,?,?,?,?)", lot)
                    lot.clear()
            con.executemany("INSERT INTO a VALUES (?,?,?,?,?,?,?)", lot)
    con.execute("CREATE INDEX a_rue ON a (rue, numero)")
    con.commit()
    con.close()
    tmp.replace(base)
    return base


class Registre:
    """Recherches dans le registre indexé ; `position` rend ([E, N], précision) ou None."""

    def __init__(self, registre: Path):
        self.con = sqlite3.connect(indexer(Path(registre)))

    def close(self) -> None:
        self.con.close()

    def position(self, adresse, commune=None, canton=None) -> tuple[list[int], str] | None:
        parties = analyser(adresse)
        if not parties:
            return None
        rue, numero, npa, lieu = parties
        lignes = self.con.execute("SELECT numero, npa, commune, canton, e, n FROM a WHERE rue = ?", (cle_rue(rue),)).fetchall()
        if not lignes:
            return None
        # même rue ailleurs en Suisse : garder celle du NPA, sinon de la commune (fiche ou adresse), sinon du canton
        for garde in (lambda l: npa and l[1] == npa,
                      lambda l: commune and l[2] == cle(commune),
                      lambda l: lieu and l[2] == cle(lieu),
                      lambda l: canton and l[3] == str(canton).strip().upper()):
            choix = [l for l in lignes if garde(l)]
            if choix:
                lignes = choix
                break
        if len({(l[2], l[3]) for l in lignes}) > 1:
            return None                 # rue homonyme dans plusieurs communes, rien pour trancher
        exact = [l for l in lignes if numero and l[0] == numero] or \
                [l for l in lignes if numero and re.sub(r"\D.*$", "", l[0]) == re.sub(r"\D.*$", "", numero)]
        if exact:
            return [round(exact[0][4]), round(exact[0][5])], "adresse"
        return [round(sum(l[4] for l in lignes) / len(lignes)), round(sum(l[5] for l in lignes) / len(lignes))], "rue"
