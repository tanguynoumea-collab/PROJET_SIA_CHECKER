"""Analyse IA du classement généré (V4_PLAN §3.3, phase 24).

L'algorithme classe tout ce qu'il peut ; l'IA ne reçoit que les espaces où il hésite (confiance sous
engine.SURE, sources en désaccord, aucune source), avec des preuves compactes tirées de `generation/rapport.json` :
noms, propriétés de classement, aire, logement, voisins, décision des règles et sources en désaccord.

    questions(rapport)       -> generation/questions-ia.json   (les cas, lisibles)
    prompt(questions)        -> generation/prompt-ia.json      (system + user, ce que l'app envoie à l'API)
    parse(réponse, questions) -> décisions du journal (journal.py) : « proposée », ou « confirmée » si l'IA garde
                                le classement des règles

L'app (C#, AiGenerationService) estime le coût, demande l'accord, appelle l'API avec la clé chiffrée DPAPI et
enregistre la réponse brute dans `generation/reponse-ia.txt` ; `sia-check --reponse-ia` la lit. Rien n'est
appliqué sans acceptation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import journal
from .classify import EXTERIEUR, PIECE

FORMAT, VERSION = "sia-check-questions-ia", 1
QUESTIONS, PROMPT, RESPONSE, SUMMARY = (Path("generation") / f for f in
                                        ("questions-ia.json", "prompt-ia.json", "reponse-ia.txt", "synthese-ia.md"))
SURE = 0.8
MAX_QUESTIONS = 300
CERTAINTIES = ("sûr", "probable", "incertain")

# Codes et sous-types Treegram qu'une décision peut donner (relevés sur L'Orée)
TYPES = {
    "SUP": ["PieceDeVie", "Chambre", "PieceSecondaire_2PointsEau", "PieceSecondaire_3PointsEau",
            "PieceSecondaire_4PointsEau", "Distribution"],
    "SUS": ["SUS"],
    "SUT": ["Commerce"],
    "SD": ["CirculationH", "Escalier", "Ascenseur"],
    "SI": ["Gaine", "Local"],
    "SEU": ["Balcon", "Terrasse"],
    "SED": ["CirculationExt"],
    "SEI": [],
}
NAMES = {
    "SUP": "surface utile principale (logement : pièces, cuisines, sanitaires, dégagements du logement)",
    "SUS": "surface utile secondaire (caves, buanderies, locaux vélos et poussettes, dépôts, abris, parkings, "
           "sanitaires et vestiaires communs)",
    "SUT": "surface utile hors logement, catégorie Treegram (commerces, bureaux, ateliers, salles, crèches)",
    "SD": "surface de dégagement commune (couloirs, paliers, halls, escaliers, ascenseurs)",
    "SI": "surface d'installations (gaines, locaux techniques, chaufferies, locaux électriques)",
    "SEU": "surface externe utile (balcons, loggias, terrasses, jardins privatifs, entrées couvertes)",
    "SED": "surface externe de dégagement (coursives, passages, préaux)",
    "SEI": "surface externe d'installations",
}

SYSTEM = """\
Tu es l'analyse IA du moteur de génération de SIA Check. Le moteur lit une maquette architecte IFC et classe
chaque espace (IfcSpace) selon la SIA 416, au modèle de Treegram, dont les surfaces alimentent ensuite toute la
chaîne de contrôle et le benchmark. Ses règles ont classé l'essentiel ; elles te transmettent uniquement les
espaces où elles hésitent.

Pour chaque question, décide du code SIA et du sous-type Treegram de l'espace, d'après ses preuves : noms,
propriétés de classement de l'architecte, aire, logement (lot), pièces du même logement, voisins, décision des
règles et sources en désaccord. Tu n'as que ces preuves : pas de plan, pas de maquette.

Codes possibles :
{codes}

Conventions de Treegram, à respecter :
- Dans un logement (lot renseigné), un dégagement, un hall, un réduit ou un dressing est de la SUP, de type
  Distribution, pas de la SD ni de la SUS. La SD est réservée aux circulations communes.
- Un WC, une douche ou une salle de bains de logement est de la SUP de type PieceSecondaire_2PointsEau (WC),
  _3PointsEau (douche, salle d'eau), _4PointsEau (salle de bains). Un séjour ou une cuisine : PieceDeVie ;
  une chambre ou un bureau de logement : Chambre.
- Une propriété SIA écrite par l'architecte est une preuve forte : ne la contredis que si le nom et les voisins
  la démentent nettement (local technique classé SUP, par exemple), et dis-le dans la raison.
- Hors logement, un bureau, une salle ou un commerce est de la SUT ; un local de rangement commun de la SUS.
- Une entrée couverte d'immeuble, un porche ou un perron est de la SEU ; une coursive ou un passage de la SED.

Garde la décision des règles quand rien ne permet de mieux faire. Certitude : « sûr » si les preuves sont
nettes, « probable » si un doute raisonnable demeure, « incertain » si c'est une hypothèse à vérifier sur plan.

Réponds exactement dans ce format, sans rien d'autre hors des deux balises :

<decisions>
{{"<id>": {{"code": "SUP", "type": "Distribution", "certitude": "sûr|probable|incertain", "raison": "une phrase"}}, …}}
</decisions>
<synthese>
(quelques lignes en français : ce que tu as changé, ce qui reste à vérifier sur plan, en regroupant les cas
semblables)
</synthese>

Le bloc <decisions> est un objet JSON valide qui contient chacun des identifiants des questions, recopiés
caractère pour caractère, et seulement eux. « type » est l'un des sous-types listés pour le code, ou null.
"""


def _codes_text() -> str:
    return "\n".join(f"- {c} : {NAMES[c]}. Sous-types : {', '.join(t) if t else 'aucun'}." for c, t in TYPES.items())


def questions(rapport: dict, limit: int = MAX_QUESTIONS) -> dict:
    """Espaces où les règles hésitent, de la confiance la plus basse à la plus haute, avec leurs preuves."""
    spaces = rapport.get("spaces") or []
    mates: dict[str, list[str]] = {}
    for s in spaces:
        if s.get("in_lot") and s["nature"] in (PIECE, EXTERIEUR):
            mates.setdefault(s["lot"], []).append(
                f"{' / '.join(v for v in (s['name'], s['long_name']) if v)} ({s['code']})")
    doubt = [s for s in spaces if s["nature"] in (PIECE, EXTERIEUR)
             and (s["confidence"] < SURE or s["conflicts"] or s["source"] is None)]
    doubt.sort(key=lambda s: (s["confidence"], s["level"] or "", s["name"] or ""))
    out = []
    for s in doubt[:limit]:
        label = " / ".join(v for v in (s["name"], s["long_name"]) if v)
        out.append({
            "id": s["gid"], "niveau": s["level"] or s["storey"], "nom": s["name"], "nom_long": s["long_name"],
            "proprietes": s.get("props") or {}, "aire_m2": s["area"] if s["area"] is not None else s["area_plan"],
            "logement": s["lot"] if s.get("in_lot") else None,
            "pieces_du_logement": [m for m in mates.get(s["lot"], []) if not m.startswith(label + " (")][:15]
            if s.get("in_lot") else [],
            "voisins": s.get("neighbours") or [],
            "regles": {"code": s["code"], "type": s["type"], "source": s["source"], "confiance": s["confidence"],
                       "raison": s["reason"], "desaccords": s["conflicts"]},
        })
    return {"format": FORMAT, "version": VERSION, "project": rapport.get("project"),
            "total": len(doubt), "questions": out}


def output_tokens(n: int) -> tuple[int, int]:
    """Sortie attendue : ~600 jetons de synthèse + ~90 par décision ; jusqu'à trois fois plus avec la réflexion."""
    text = 600 + 90 * n
    return text, 3 * text


def prompt(q: dict) -> dict:
    lo, hi = output_tokens(len(q["questions"]))
    user = (f"Projet : {q.get('project')}\n{len(q['questions'])} espaces à décider"
            + (f" (sur {q['total']} incertains, les plus douteux d'abord)" if q["total"] > len(q["questions"]) else "")
            + ".\n\n<questions>\n" + json.dumps(q["questions"], ensure_ascii=False, indent=1) + "\n</questions>\n")
    return {"system": SYSTEM.format(codes=_codes_text()), "user": user, "questions": len(q["questions"]),
            "output_tokens": [lo, hi]}


def _between(text: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    return m.group(1).strip() if m else None


def _unfence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s[s.index("\n") + 1: s.rindex("```")]
    return s


class ResponseError(ValueError):
    pass


def parse(text: str, q: dict) -> tuple[list[dict], str, list[str]]:
    """(décisions du journal, synthèse markdown, questions sans réponse exploitable). Une clé inconnue, un code
    hors liste sont écartés ; un sous-type hors liste devient le premier du code."""
    raw = _between(text, "decisions")
    if raw is None:
        raise ResponseError("réponse sans bloc <decisions>")
    try:
        answers = json.loads(_unfence(raw))
    except ValueError as ex:
        raise ResponseError(f"décisions illisibles : {ex}") from ex
    if not isinstance(answers, dict):
        raise ResponseError("décisions : objet JSON attendu")
    by_id = {x["id"]: x for x in q["questions"]}
    out, date = [], journal.now()
    for gid, a in answers.items():
        x = by_id.get(gid)
        if x is None or not isinstance(a, dict) or a.get("code") not in TYPES:
            continue
        code = a["code"]
        typ = a.get("type") if a.get("type") in TYPES[code] else (TYPES[code][0] if TYPES[code] else None)
        before = {"code": x["regles"]["code"], "type": x["regles"]["type"]}
        same = code == before["code"] and (typ == before["type"] or not typ)
        out.append({
            "id": gid, "nom": " / ".join(v for v in (x["nom"], x["nom_long"]) if v), "origine": "ia",
            "statut": "confirmée" if same else "proposée", "avant": before, "code": code, "type": typ,
            "certitude": a.get("certitude") if a.get("certitude") in CERTAINTIES else "incertain",
            "raison": str(a.get("raison") or "").strip(), "date": date,
        })
    answered = {d["id"] for d in out}
    missing = [g for g in by_id if g not in answered]
    return out, (_between(text, "synthese") or "").strip(), missing
