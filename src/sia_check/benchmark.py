"""Benchmark des surfaces : la base de projets lue dans les tableaux MDP HRS (V3, docs/V3_PLAN.md).

Chaque `MDP-*.xlsx` d'un dossier devient un `Projet` : totaux SIA 416 et USPI, logements, caractéristiques,
contrôles de fiabilité. Les MDP anciens (copier-coller) n'ont pas tous les mêmes libellés : catégories en code
ou en toutes lettres, étages, en-têtes, cantons. Tout est normalisé ici, pas dans les ratios.

Il n'y a pas de ratios idéaux : la référence d'un projet est le **ratio combiné** des projets qui lui ressemblent
(`similaires`), soit Σ numérateurs / Σ dénominateurs (le groupe vu comme un seul grand projet), accompagné de la
médiane, des quartiles et de la valeur de chaque projet (`combiner`). Un projet n'entre dans un ratio que s'il en
a les deux termes : chaque ratio a son propre n.

Totaux (`Projet.totaux`, m² sauf mention) :
    SP, SP_HS, SP_SS     surface de plancher (brutes), hors-sol et sous-sol (découpage, sinon code d'étage)
    SUP, SUS, SD, SI     nettes, avec suffixe _HS / _SS ; la SUT (activités Treegram) est comptée dans la SUP
    SN, SC               SN = SUP + SUS + SD + SI ; SC = SP − SN (Treegram ne fournit pas la SC)
    SEP, VB              surface externe de plancher ; volume bâti (m³ : lignes VB, sinon m³ des SP)
    SVN, SVB, SNH        USPI, somme des lots
    FACADE, VITRE        enveloppe hors-sol : façade brute et partie vitrée (SRV ; réservations de façade dans les
                         anciens MDP), sans toitures ni murs enterrés
    PLEINE               façade pleine = FACADE − VITRE (seulement si la vitrée est connue)
    TOITURE              toitures hors-sol (lignes « toiture » de SurfacesEnveloppe) : avec FACADE, l'enveloppe du
                         coefficient de forme ; absente, le coefficient n'est pas calculé (il serait surestimé)
    LOG, ETAGES_HS       nombre de logements, d'étages hors-sol
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import re
import statistics
import unicodedata
import warnings
from pathlib import Path

import pandas as pd

from . import mdp

VERSION = 1
NETTES = ("SUP", "SUS", "SD", "SI")
CANTONS = {"vaud": "VD", "geneve": "GE", "fribourg": "FR", "valais": "VS", "neuchatel": "NE", "jura": "JU",
           "berne": "BE", "bern": "BE", "tessin": "TI", "ticino": "TI", "zurich": "ZH"}


@dataclasses.dataclass(frozen=True)
class Kpi:
    id: str
    famille: str
    label: str
    num: tuple[str, ...]
    den: tuple[str, ...]
    unite: str = "%"
    note: str = ""
    sens: int = 0          # +1 plus haut = favorable, −1 plus bas = favorable, 0 neutre
    objet: str = ""        # ce que mesure le numérateur, pour traduire un écart en m² (« de SUP hors-sol »)
    typologie: str = ""    # « logement » : sans objet pour une autre typologie (le dashboard le masque)


KPIS = [
    Kpi("SUP/SP_HS", "Rendement", "SUP hors-sol / SP hors-sol", ("SUP_HS",), ("SP_HS",),
        note="Le m² qui rapporte par m² construit au-dessus du sol.", sens=1, objet="de SUP hors-sol"),
    Kpi("SVN/SP_HS", "Rendement", "SVN / SP hors-sol", ("SVN",), ("SP_HS",), note="Rendement commercial (USPI).",
        sens=1, objet="de surface de vente nette"),
    Kpi("SN/SP", "Rendement", "SN / SP", ("SN",), ("SP",), sens=1, objet="de surface nette"),
    Kpi("SC/SP", "Pertes", "Construction : SC / SP", ("SC",), ("SP",), note="SC = SP − SN.",
        sens=-1, objet="de construction"),
    Kpi("SD/SP_HS", "Pertes", "Circulations : SD hors-sol / SP hors-sol", ("SD_HS",), ("SP_HS",),
        sens=-1, objet="de circulations"),
    Kpi("SI/SP", "Pertes", "Installations : SI / SP", ("SI",), ("SP",), sens=-1, objet="d'installations"),
    Kpi("SUS_HS/SP_HS", "Pertes", "Utile secondaire hors-sol / SP hors-sol", ("SUS_HS",), ("SP_HS",),
        sens=-1, objet="de SUS hors-sol"),
    Kpi("SP_SS/SUP", "Sous-sol", "SP sous-sol / SUP", ("SP_SS",), ("SUP",),
        note="m² de sous-sol construits par m² utile principal.", sens=-1, objet="de sous-sol"),
    # Enveloppe : le vitrage est neutre (lumière et vente contre coût), le benchmark situe sans juger
    Kpi("VITRE/PLEINE", "Enveloppe", "Vitrée / pleine", ("VITRE",), ("PLEINE",),
        note="Surface vitrée / surface pleine de façade (pleine = façade brute − vitrée)."),
    Kpi("VITRE/FACADE", "Enveloppe", "Part vitrée : vitrée / façade", ("VITRE",), ("FACADE",)),
    # Coefficient de forme (équipe DEV, 27.10.2026) : SP hors-sol / surface d'enveloppe (façades hors-sol + toitures).
    # Plus il est haut, plus le bâtiment est compact : moins d'enveloppe, donc de coût et de pertes thermiques, par m².
    Kpi("FORME", "Enveloppe", "Coefficient de forme : SP hors-sol / enveloppe", ("SP_HS",), ("FACADE", "TOITURE"), unite="",
        note="Enveloppe = façades hors-sol + toitures. Un bâtiment compact (rectangle) l'emporte sur une forme découpée.",
        sens=1, objet="de SP hors-sol"),
    Kpi("FACADE/SP_HS", "Enveloppe", "Façade / SP hors-sol", ("FACADE",), ("SP_HS",), unite="", sens=-1, objet="de façade"),
    Kpi("VB/SP", "Enveloppe", "Hauteur brute moyenne : VB / SP", ("VB",), ("SP",), unite="m"),
    Kpi("SUP/LOG", "Programme", "SUP par logement", ("SUP",), ("LOG",), unite="m²", typologie="logement"),
    Kpi("SP_HS/LOG", "Programme", "SP hors-sol par logement", ("SP_HS",), ("LOG",), unite="m²", typologie="logement"),
]
KPI_BY_ID = {k.id: k for k in KPIS}

# Caractéristiques de proximité (§4.4) : échelle logarithmique pour les tailles.
FEATURES = {"SP_HS": "log", "LOG": "log", "ETAGES_HS": "lin", "PART_SS": "lin", "PART_GRANDS": "lin"}
FILTRES = ("categorie", "intervention")
# Hors de cette fourchette, SP et SN ne décrivent pas le même périmètre (nettes tronquées, brutes partielles) :
# le projet reste affiché mais n'entre pas dans les références.
SC_PLAUSIBLE = (0.08, 0.30)
REQUIS = ("coherence", "plausible")


class MdpError(Exception):
    pass


@dataclasses.dataclass
class Controle:
    id: str
    label: str
    ok: bool
    detail: str = ""


@dataclasses.dataclass
class Projet:
    id: str
    nom: str
    fichier: str
    infos: dict
    totaux: dict[str, float]
    logements: list[dict]
    controles: list[Controle]

    @property
    def score(self) -> float:
        return sum(c.ok for c in self.controles) / len(self.controles) if self.controles else 0.0

    @property
    def fiable(self) -> bool:
        """Admis dans les références : SP et SN cohérentes (contrôles REQUIS)."""
        return all(c.ok for c in self.controles if c.id in REQUIS)

    def terme(self, tokens: tuple[str, ...]) -> float | None:
        vals = [self.totaux.get(t) for t in tokens]
        return None if any(v is None for v in vals) else sum(vals)

    def ratio(self, kpi: Kpi) -> tuple[float, float] | None:
        """(numérateur, dénominateur), None si un terme manque ou si le dénominateur est nul."""
        num, den = self.terme(kpi.num), self.terme(kpi.den)
        return None if num is None or not den else (num, den)

    def features(self) -> dict[str, float]:
        t = self.totaux
        f = {k: t[k] for k in ("SP_HS", "LOG", "ETAGES_HS") if t.get(k)}
        if t.get("SP_SS") is not None and t.get("SP_HS"):
            f["PART_SS"] = t["SP_SS"] / t["SP_HS"]
        ch = [lg["chambres"] for lg in self.logements if lg["chambres"] is not None]
        if ch and len(ch) == len(self.logements):
            f["PART_GRANDS"] = sum(c >= 3 for c in ch) / len(ch)
        return f


# --- normalisation -------------------------------------------------------------------------------------------

def _key(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _empty(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


def _col(df: pd.DataFrame, *names: str) -> str | None:
    """Colonne dont l'en-tête normalisé commence par l'un des noms (variantes des anciens MDP)."""
    keys = {_key(c): c for c in df.columns}
    for n in names:
        for k, c in keys.items():
            if k.startswith(_key(n)):
                return c
    return None


def code(label) -> str | None:
    """Code SIA d'un libellé de catégorie : « SUP », « Surface Utile Principale (SUP) », « SEP-Toiture » (SPT)."""
    if _empty(label):
        return None
    s = str(label).strip()
    if re.match(r"(?i)^SEP[-_ ]?TOI", s):
        return "SPT"
    if re.fullmatch(r"[A-Z]{1,4}", s):
        return s
    m = re.search(r"\(([A-Z]{1,4})\)", s)
    return m.group(1) if m else None


def zone(etage, decoupage=None) -> str | None:
    """HS (hors-sol), SS (sous-sol) ou None : découpage des brutes, sinon code d'étage (S01, N00, ATT, TOI…)."""
    d = _key(decoupage) if not _empty(decoupage) else ""
    if d.startswith("hors"):
        return "HS"
    if d.startswith("sous"):
        return "SS"
    e = _key(etage) if not _empty(etage) else ""
    # Sous-sol : un S ou un « - » dans le nom (S01, SS1, S-1, 2SS, -1, N-1, Niveau -1), « Sous-sol », UG1 / U1
    # (mêmes formes que levels.order de config.yaml, que le moteur de fiabilisation applique)
    if (re.fullmatch(r"s{1,2} ?-? ?\d+|\d+ ?s{1,2}|ug? ?\d+", e) or e.startswith("sous")
            or re.search(r"- ?\d+$", e)):
        return "SS"
    if re.fullmatch(r"n\d+", e) or e.startswith(("att", "toi", "rdc", "comble")):
        return "HS"
    return None


def _id(v, fichier: str) -> str:
    if _empty(v):
        m = re.match(r"MDP-(\d+)", fichier)
        return m.group(1) if m else Path(fichier).stem
    try:
        return str(int(float(v)))
    except ValueError:
        return str(v).strip()


def _canton(v) -> str | None:
    if _empty(v):
        return None
    k = _key(v)
    return CANTONS.get(k, str(v).strip().upper() if len(k) == 2 else str(v).strip())


def _num(v) -> float | None:
    if _empty(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _sum(df: pd.DataFrame, col: str) -> float:
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


# --- lecture -------------------------------------------------------------------------------------------------

def _sheet(x: pd.ExcelFile, name: str) -> pd.DataFrame:
    if name not in x.sheet_names:
        return pd.DataFrame()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = pd.read_excel(x, name)
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    return df.dropna(how="all")


def _infos(df: pd.DataFrame) -> dict:
    if df.shape[1] < 3:
        return {}
    raw = {_key(k): v for k, v in zip(df.iloc[:, 1], df.iloc[:, 2]) if not _empty(k)}

    def get(*names):
        for n in names:
            for k, v in raw.items():
                if k.startswith(_key(n)) and not _empty(v):
                    return v
        return None

    date = get("date fin projet", "date de la source")
    return {
        "id": get("id projet"), "nom": get("nom projet"), "canton": _canton(get("canton")),
        "commune": get("commune"), "categorie": get("categorie d'ouvrage"), "intervention": get("type d'intervention"),
        "phase": get("phase du projet"), "date": date.date().isoformat() if isinstance(date, dt.datetime) else date,
        "logements": _num(get("nbr total de logements")), "places_voiture": _num(get("nbr places de stationnement voiture dans")),
    }


def _brutes(df: pd.DataFrame, t: dict) -> None:
    c_cat, c_m2, c_m3 = _col(df, "categorie"), _col(df, "m2"), _col(df, "m3")
    c_et, c_dec = _col(df, "etage"), _col(df, "decoupage")
    if df.empty or not (c_cat and c_m2):
        return
    none = [None] * len(df)
    # saisie à la main : catégorie écrite sur la première ligne d'un bloc seulement (1747)
    df = df.assign(_c=df[c_cat].ffill().map(code),
                   _z=[zone(e, d) for e, d in zip(df[c_et] if c_et else none, df[c_dec] if c_dec else none)])
    sp = df[df._c == "SP"]
    if not sp.empty and _sum(sp, c_m2) > 0:
        t["SP"] = _sum(sp, c_m2)
        if _sum(sp[sp._z.isna()], c_m2) < 1 and _sum(sp[sp._z == "HS"], c_m2) > 0:   # toute la SP est située
            t["SP_HS"], t["SP_SS"] = _sum(sp[sp._z == "HS"], c_m2), _sum(sp[sp._z == "SS"], c_m2)
            if c_et:
                etages = sp[(sp._z == "HS") & (pd.to_numeric(sp[c_m2], errors="coerce") > 0)]
                t["ETAGES_HS"] = float(etages[c_et].astype(str).str.upper().nunique())
    sep = df[df._c == "SEP"]
    if not sep.empty:
        t["SEP"] = _sum(sep, c_m2)
    vb = df[df._c == "VB"]
    if not vb.empty:    # anciens MDP : volume saisi dans la colonne m²
        t["VB"] = _sum(vb, c_m3) or _sum(vb, c_m2)
    elif c_m3 and not sp.empty and _sum(sp, c_m3) > 0:
        t["VB"] = _sum(sp, c_m3)


def _nettes(df: pd.DataFrame, t: dict) -> pd.DataFrame:
    c_cat, c_m2, c_et = _col(df, "categorie"), _col(df, "m2"), _col(df, "etage")
    if df.empty or not (c_cat and c_m2):
        return pd.DataFrame()
    df = df.assign(_c=df[c_cat].map(code).replace({"SUT": "SUP"}),
                   _z=df[c_et].map(zone) if c_et else None,
                   _m2=pd.to_numeric(df[c_m2], errors="coerce").fillna(0))
    for c in NETTES:
        part = df[df._c == c]
        t[c] = float(part._m2.sum())
        t[c + "_HS"] = float(part[part._z == "HS"]._m2.sum())
        t[c + "_SS"] = float(part[part._z == "SS"]._m2.sum())
    t["SN"] = sum(t[c] for c in NETTES)
    c_aff = _col(df, "affectation")
    if c_aff:
        sup = df[(df._c == "SUP") & df[c_aff].notna()]
        if len(sup):
            autres = sup[~sup[c_aff].map(_key).str.startswith("logement")]._m2.sum()
            t["PART_AUTRES_SUP"] = float(autres / sup._m2.sum()) if sup._m2.sum() else None
    return df


def _uspi(df: pd.DataFrame, t: dict) -> None:
    c_cat, c_m2 = _col(df, "categorie"), _col(df, "m2")
    if df.empty or not (c_cat and c_m2):
        return
    labels = {"SVN": ("svn", "surface de vente nette"), "SVB": ("svb", "surface de ventebrute", "surface de vente brute"),
              "SNH": ("snh", "surface nette habitab"), "SBH": ("sbh", "surface brute habitab")}
    k = df[c_cat].map(_key)
    for c, names in labels.items():
        m = k.isin(names) | k.map(lambda s: any(s.startswith(n) for n in names if len(n) > 4))
        if m.any():
            t[c] = _sum(df[m], c_m2)


def _enveloppe(df: pd.DataFrame, t: dict) -> None:
    """Façade et vitrages **hors-sol**, comme les ratios d'enveloppe de la fiabilisation (config : above_ground) :
    ni toitures, ni murs enterrés des sous-sols, ni lignes de total sans étage. Les MDP remplis à la main nomment
    leurs parties librement (« Partie pleine », « Surface de façade »…) : on écarte ce qui n'est pas de la façade."""
    if df.empty:
        return
    c_et = _col(df, "etage")
    if c_et:   # sous-sol par code (S01) ou en toutes lettres (« Sous Sol ») ; sans étage : ligne de total
        df = df[[not _empty(e) and zone(e) != "SS" and not _key(e).startswith("sous") for e in df[c_et]]]
    c_brute, c_vit, c_part = _col(df, "surface brut"), _col(df, "surface vitr"), _col(df, "partie de l'enveloppe")
    if c_brute:                                             # gabarit actuel : une ligne par niveau et par partie
        k = df[c_part].map(lambda v: "" if _empty(v) else _key(v)) if c_part else pd.Series("", index=df.index)
        toiture = _sum(df[k.str.contains("toit")], c_brute)
        df, k = df[~k.str.contains("toit")], k[~k.str.contains("toit")]
        facade, vitre = _sum(df, c_brute), _sum(df, c_vit) if c_vit else 0.0
        c_net = _col(df, "surface nette")
        if vitre == 0 and c_net:   # pas de vitrée : les ouvertures de la façade (brute − nette), comme l'export MDP
            murs = df[pd.to_numeric(df[c_brute], errors="coerce").notna()]
            vitre = max(_sum(murs, c_brute) - _sum(murs, c_net), 0.0)
    else:                                                   # anciens MDP : une ligne par partie d'enveloppe
        c_part, c_m2 = _col(df, "partie de l'enveloppe"), _col(df, "surface")
        if not (c_part and c_m2):
            return
        k = df[c_part].map(_key)
        facade, vitre = _sum(df[k.str.contains("facade")], c_m2), _sum(df[k.str.contains("vitr")], c_m2)
        toiture = _sum(df[k.str.contains("toit")], c_m2)
    if toiture > 0:
        t["TOITURE"] = toiture
    if facade > 0:
        t["FACADE"] = facade
        t["VITRE"] = vitre if vitre > 0 else None
        t["PLEINE"] = facade - vitre if 0 < vitre < facade else None


def _logements(df: pd.DataFrame, nettes: pd.DataFrame) -> list[dict]:
    c_lot = _col(df, "appartement_unite", "no appart", "n appart")
    if df.empty or not c_lot:
        return []
    c_ch, c_et = _col(df, "nbr de chambres"), _col(df, "etage")
    sup = {}
    if not nettes.empty and (c_sn := _col(nettes, "appartement_unite")):
        s = nettes[nettes._c == "SUP"]
        sup = s.groupby(s[c_sn].astype(str).str.strip())._m2.sum().to_dict()
    out = []
    for _, r in df.iterrows():
        lot = r[c_lot]
        if _empty(lot):
            continue
        lot = str(lot).strip()
        surface = sup.get(lot)
        if surface is None:     # lots saisis sans le n° de local (« 2B.02.02. » pour « 2B.02.02.11 »)
            surface = sum(v for k, v in sup.items() if k.startswith(lot)) or None
        ch = _num(r[c_ch]) if c_ch else None
        out.append({"lot": lot, "etage": None if not c_et or _empty(r[c_et]) else str(r[c_et]),
                    "chambres": int(ch) if ch is not None and ch >= 0 else None, "sup": surface})
    return out


def _controles(t: dict, infos: dict, logements: list[dict]) -> list[Controle]:
    sp, sn = t.get("SP"), t.get("SN")
    coherent = sp is not None and sn is not None and sp >= sn
    sc = (sp - sn) / sp if coherent and sp else None
    lo, hi = SC_PLAUSIBLE
    ch = [lg for lg in logements if lg["chambres"] is not None]
    return [
        Controle("brutes", "Surfaces brutes (SP)", sp is not None),
        Controle("decoupage", "SP découpée hors-sol / sous-sol", t.get("SP_HS") is not None),
        Controle("nettes", "Surfaces nettes", bool(sn)),
        Controle("coherence", "SP ≥ SN", coherent,
                 "" if coherent or sp is None or sn is None else f"SP {sp:,.0f} < SN {sn:,.0f} m²"),
        Controle("plausible", f"Part de construction SC / SP entre {lo:.0%} et {hi:.0%}", sc is not None and lo <= sc <= hi,
                 "" if sc is None else f"SC / SP = {sc:.0%}"),
        Controle("logements", "Liste des logements", bool(logements)),
        Controle("chambres", "Nombre de chambres par logement", bool(logements) and len(ch) == len(logements),
                 f"{len(ch)}/{len(logements)}" if logements else ""),
        Controle("uspi", "Surfaces USPI (SVN)", bool(t.get("SVN"))),
        Controle("enveloppe", "Surfaces d'enveloppe", bool(t.get("FACADE"))),
        Controle("infos", "Canton, catégorie, type d'intervention",
                 all(infos.get(k) for k in ("canton", "categorie", "intervention"))),
    ]


def lire(path: Path) -> Projet:
    """Un tableau MDP HRS ; MdpError si le fichier n'en est pas un."""
    try:
        with warnings.catch_warnings():     # validations de données étendues des MDP, sans effet sur la lecture
            warnings.simplefilter("ignore", UserWarning)
            x = pd.ExcelFile(path)
    except (OSError, ValueError) as ex:
        raise MdpError(f"{path.name} : illisible ({ex})") from ex
    with x:     # classeur fermé après lecture : un MDP temporaire (--benchmark-projet) doit pouvoir être effacé
        if "SurfacesNettesSIA416" not in x.sheet_names:
            raise MdpError(f"{path.name} : pas de feuille SurfacesNettesSIA416, ce n'est pas un MDP")
        infos = _infos(_sheet(x, "InfosProjet"))
        t: dict[str, float] = {}
        _brutes(_sheet(x, "SurfacesBrutesVolumeSIA416"), t)
        nettes = _nettes(_sheet(x, "SurfacesNettesSIA416"), t)
        _uspi(_sheet(x, "SurfacesUSPI"), t)
        _enveloppe(_sheet(x, "SurfacesEnveloppe"), t)
        logements = _logements(_sheet(x, "ListeLogements"), nettes)
    if t.get("SP") is not None and t.get("SN") is not None and t["SP"] >= t["SN"]:
        t["SC"] = t["SP"] - t["SN"]
    if logements or infos.get("logements"):
        t["LOG"] = float(len(logements) or infos["logements"])
    # La typologie n'est jamais déduite des affectations (logique propre au logement) : absente, elle reste vide
    # et le projet est « non identifié » (V3_PLAN §9).
    nom = infos.get("nom") or re.sub(r"^MDP-[\d.]+[-_ ]*", "", path.stem).replace("_", " ").strip()
    return Projet(_id(infos.get("id"), path.name), str(nom), path.name, infos,
                  {k: v for k, v in t.items() if v is not None}, logements, _controles(t, infos, logements))


def lire_dossier(dossier: Path) -> tuple[list[Projet], list[str]]:
    """Les MDP d'un dossier (« MDP*.xlsx ») et les erreurs de lecture ; un même ID garde le fichier le plus récent."""
    projets, erreurs = {}, []
    for f in sorted(dossier.glob("MDP*.xlsx"), key=lambda p: p.stat().st_mtime):
        if f.name.startswith("~$"):
            continue
        try:
            p = lire(f)
        except MdpError as ex:
            erreurs.append(str(ex))
            continue
        projets[p.id] = p
    return sorted(projets.values(), key=lambda p: p.id), erreurs


# --- comparaison ---------------------------------------------------------------------------------------------

def _quantile(v: list[float], q: float) -> float:
    s = sorted(v)
    i = (len(s) - 1) * q
    lo = math.floor(i)
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (i - lo)


def combiner(projets: list[Projet], kpi: Kpi) -> dict:
    """Ratio combiné (Σ num / Σ den) des projets fiables qui ont les deux termes, médiane, quartiles et valeurs."""
    termes = [(p.id, r) for p in projets if p.fiable and (r := p.ratio(kpi))]
    if not termes:
        return {"n": 0, "combine": None, "mediane": None, "q1": None, "q3": None, "valeurs": {}}
    valeurs = {pid: num / den for pid, (num, den) in termes}
    v = list(valeurs.values())
    return {"n": len(v), "combine": sum(n for _, (n, _) in termes) / sum(d for _, (_, d) in termes),
            "mediane": statistics.median(v), "q1": _quantile(v, 0.25), "q3": _quantile(v, 0.75), "valeurs": valeurs}


def _echelles(projets: list[Projet]) -> dict[str, float]:
    """Étendue de chaque caractéristique sur la base, pour normaliser les écarts."""
    out = {}
    for f, kind in FEATURES.items():
        v = [x[f] for p in projets if (x := p.features()).get(f) is not None and (kind == "lin" or x[f] > 0)]
        v = [math.log(x) for x in v] if kind == "log" else v
        out[f] = (max(v) - min(v)) if len(v) > 1 and max(v) > min(v) else 1.0
    return out


def distance(a: Projet, b: Projet, echelles: dict[str, float]) -> float | None:
    """Écart moyen normalisé sur les caractéristiques connues des deux projets (0 = identiques) ; None si moins de 2."""
    fa, fb = a.features(), b.features()
    d = []
    for f, kind in FEATURES.items():
        if f in fa and f in fb:
            x, y = (math.log(fa[f]), math.log(fb[f])) if kind == "log" else (fa[f], fb[f])
            d.append(abs(x - y) / echelles[f])
    return sum(d) / len(d) if len(d) >= 2 else None


def similaires(ref: Projet, projets: list[Projet], filtres=FILTRES, k: int = 5) -> list[tuple[Projet, float]]:
    """Les k projets fiables les plus proches de `ref` (lui exclu). Un filtre écarte une valeur différente de celle de
    `ref` ; une valeur inconnue ne l'écarte pas (base encore incomplète)."""
    echelles = _echelles(projets)
    out = []
    for p in projets:
        if p.id == ref.id or not p.fiable:
            continue
        if any(ref.infos.get(f) and p.infos.get(f) and _key(ref.infos[f]) != _key(p.infos[f]) for f in filtres):
            continue
        d = distance(ref, p, echelles)
        if d is not None:
            out.append((p, d))
    return sorted(out, key=lambda x: x[1])[:k]


def typologies(projets: list[Projet]) -> list[dict]:
    """SUP par logement selon le nombre de chambres, tous projets confondus (bibliothèque de programmation)."""
    par = {}
    for p in projets:
        if not p.fiable:
            continue
        for lg in p.logements:
            if lg["chambres"] is not None and lg["sup"]:
                par.setdefault(lg["chambres"], []).append((p.id, lg["sup"]))
    out = []
    for ch, v in sorted(par.items()):
        s = [x for _, x in v]
        out.append({"chambres": ch, "n": len(s), "projets": len({pid for pid, _ in v}), "min": min(s),
                    "q1": _quantile(s, 0.25), "mediane": statistics.median(s), "q3": _quantile(s, 0.75), "max": max(s)})
    return out


# --- export --------------------------------------------------------------------------------------------------

def projet_json(p: Projet) -> dict:
    """Un projet tel que le lit le dashboard, sans sa comparaison (projet de la base ou « Mon projet »)."""
    mix = {}
    for lg in p.logements:
        if lg["chambres"] is not None:
            mix[str(lg["chambres"])] = mix.get(str(lg["chambres"]), 0) + 1
    return {
        "id": p.id, "nom": p.nom, "fichier": p.fichier, "infos": p.infos, "score": round(p.score, 3), "fiable": p.fiable,
        "controles": [dataclasses.asdict(c) for c in p.controles],
        "totaux": {k_: round(v, 2) for k_, v in p.totaux.items()}, "features": p.features(), "mix": mix,
        # logements (chambres, SUP) : la page recalcule l'onglet Typologies sur la sélection de l'utilisateur
        "logements": [{"chambres": lg["chambres"], "sup": round(lg["sup"], 2)} for lg in p.logements
                      if lg["chambres"] is not None and lg["sup"]],
        "kpis": {kpi.id: (None if (r := p.ratio(kpi)) is None else
                          {"num": round(r[0], 2), "den": round(r[1], 2), "valeur": r[0] / r[1]}) for kpi in KPIS},
    }


def _projet_json(p: Projet, projets: list[Projet], k: int) -> dict:
    groupe = similaires(p, projets, k=k)
    membres = [q for q, _ in groupe]
    return {
        **projet_json(p),
        "similaires": [{"id": q.id, "distance": round(d, 3)} for q, d in groupe],
        # distances à tous les projets fiables, sans filtre : la page refait le groupe quand on change les filtres
        "distances": {q.id: round(d, 3) for q, d in similaires(p, projets, filtres=(), k=len(projets))},
        "reference": {kpi.id: combiner(membres, kpi) for kpi in KPIS},
    }


def construire(projets: list[Projet], erreurs: list[str] | None = None, k: int = 5) -> dict:
    """Le contenu de benchmark.json, lu par le dashboard."""
    return {
        "version": VERSION, "genere": dt.datetime.now().isoformat(timespec="seconds"),
        "kpis": [dataclasses.asdict(k_) for k_ in KPIS], "features": FEATURES, "filtres": list(FILTRES),
        "projets": [_projet_json(p, projets, k) for p in projets],
        "base": {kpi.id: combiner(projets, kpi) for kpi in KPIS},
        "typologies": typologies(projets), "erreurs": erreurs or [],
        "listes": mdp.listes(),     # listes déroulantes de la fiche « Identité du projet »
    }


def ecrire(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
