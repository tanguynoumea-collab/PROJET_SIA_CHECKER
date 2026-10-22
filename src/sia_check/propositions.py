"""Propositions pour le tableau MDP (V2_PLAN §5.3) : ce que le `.tgm` ne dit pas, mais laisse deviner.

Trois sujets, au format de sujets.py, avec des corrections au statut « proposée » que l'utilisateur
accepte ou passe à « Inconnu » (une correction rejetée écrit « Inconnu » dans le MDP, corrections.py) :

- affectation : Affectation de chaque local, par type Treegram (`config.yaml > mdp.affectation`) ; les pièces
  habitables d'un appartement (`mdp.logement`, avec lot) prennent « Logement general » ;
- typologies : par nombre de chambres, Nom typologie et nombre de pièces VD et GE. Convention proposée, à
  valider (V2_PLAN §8) : VD = chambres + 1,5 (séjour et cuisine comptée demi-pièce), GE = chambres + 2
  (cuisine comptée pièce) ; studio : 1,5 (VD) et 2 (GE) ;
- formes : forme de chaque bâtiment d'après son plus grand niveau courant : emprise presque rectangulaire
  (aire ≥ 85 % de la boîte englobante) → « Barre » si la longueur dépasse 1,6 fois la largeur, sinon
  « Carré » ; emprise entre 60 et 85 % de sa boîte → « Bloc en L » ; en dessous, pas de proposition.
"""

from __future__ import annotations

import pandas as pd

from . import rules
from .config import Config

AFFECTATION, TYPOLOGIES, FORMES = "affectation", "typologies", "formes"
ACTION = "proposer"
HOUSING = "Logement general"


def _fmt(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _proposal(cid: str, subject: str, explanation: str, **fields) -> dict:
    return {"id": cid, "sujet": subject, "origine": "règle", "statut": "proposée", "explication": explanation, **fields}


def affectation(result: rules.Result, cfg: Config) -> dict | None:
    mapping = cfg.mdp.get("affectation") or {}
    housing = set(cfg.mdp.get("logement") or [])
    s = result.surfaces
    s = s[(s.kind == "leaf") & ~s.ignored & s.room_type.notna()]
    corrections = []
    for (room_type, in_lot), g in s.groupby([s.room_type, s.lot.notna()], sort=True):
        value = HOUSING if in_lot and room_type in housing else mapping.get(room_type)
        if value is None:
            continue
        sel = {"room_type": room_type, "kind": "leaf", "avec_lot": bool(in_lot)}
        where = "des appartements" if in_lot else "hors appartements"
        corrections.append(_proposal(
            f"affectation-{room_type}{'-lot' if in_lot else ''}", AFFECTATION,
            f"{len(g)} locaux « {room_type} » {where} → « {value} ».",
            op="affecter", cible={"selection": sel}, affectation=value, m2=round(float(g.area.sum()), 2)))
    if not corrections:
        return None
    return {"id": AFFECTATION, "titre": "Affectation des locaux (tableau MDP)", "cause": AFFECTATION, "action": ACTION,
            "explication": "Affectation proposée par type Treegram. « Inconnu » si elle ne convient pas : la valeur est "
                           "écrite telle quelle dans le MDP.", "points": [], "m2": 0.0, "corrections": corrections}


def typologies(result: rules.Result) -> dict | None:
    s = result.surfaces
    if "bedrooms" not in s:
        return None
    # Nombre de chambres négatif (valeur Treegram non renseignée) : pas de proposition, le lot reste vide.
    lots = s[(s.kind == "leaf") & (s.code == "SNH") & s.lot.notna() & (pd.to_numeric(s.bedrooms, errors="coerce") >= 0)]
    corrections = []
    for beds, g in lots.groupby(lots.bedrooms.astype(int), sort=True):
        vd = 1.5 if beds == 0 else beds + 1.5
        ge = 2 if beds == 0 else beds + 2
        name = f"{vd:g}P"
        label = "studios" if beds == 0 else f"logements de {beds} chambre{'s' if beds > 1 else ''}"
        corrections.append(_proposal(
            f"typologie-{beds}ch", TYPOLOGIES,
            f"{g.lot.nunique()} {label} → {name} (VD {_fmt(vd)} pièces, GE {_fmt(ge)} pièces).",
            op="renseigner", cible={"selection": {"bedrooms": int(beds)}},
            champs={"Nom typologie": name, "Nbr de pieces (VD)": vd, "Nbr de pieces (GE)": ge}))
    if not corrections:
        return None
    return {"id": TYPOLOGIES, "titre": "Typologies des logements (tableau MDP)", "cause": TYPOLOGIES, "action": ACTION,
            "explication": "Pièces comptées selon l'usage vaudois (séjour + chambres + ½ cuisine) et genevois (cuisine "
                           "comptée pièce). Convention à valider pour le canton du projet ; « Inconnu » sinon.",
            "points": [], "m2": 0.0, "corrections": corrections}


def formes(result: rules.Result, cfg: Config) -> dict | None:
    s = result.surfaces
    if not {"dx", "dy"} <= set(s.columns):
        return None
    sp = s[(s.kind == "node") & (s.code == "SP") & (s.area.fillna(0) > 0)]
    corrections = []
    for bld, g in sp.groupby("building", sort=True):
        above = g[g.level.map(lambda lv: (rules.level_rank(lv, cfg) or 0) >= 0)]
        ref = (above if len(above) else g).sort_values("area").iloc[-1]
        if pd.isna(ref.dx) or pd.isna(ref.dy) or not ref.dx or not ref.dy:
            continue
        w, l = sorted((float(ref.dx), float(ref.dy)))
        fill = float(ref.area) / (w * l)
        if fill >= 0.85:
            shape = "Barre" if l / w > 1.6 else "Carré"
        elif fill >= 0.6:
            shape = "Bloc en L"
        else:
            continue
        corrections.append(_proposal(
            f"forme-{bld}", FORMES,
            f"{bld} {ref.level} : {_fmt(round(w, 1))} × {_fmt(round(l, 1))} m, emprise {fill:.0%} de sa boîte → {shape}.",
            op="renseigner", cible={"selection": {"building": bld}}, champs={"Forme du bâtiment": shape}))
    if not corrections:
        return None
    return {"id": FORMES, "titre": "Forme des bâtiments (tableau MDP)", "cause": FORMES, "action": ACTION,
            "explication": "Forme déduite de l'emprise du plus grand niveau courant ; « Inconnu » si elle ne convient pas.",
            "points": [], "m2": 0.0, "corrections": corrections}


def build(result: rules.Result, cfg: Config) -> list[dict]:
    """Sujets de propositions MDP (vides : absents)."""
    return [s for s in (affectation(result, cfg), typologies(result), formes(result, cfg)) if s]
