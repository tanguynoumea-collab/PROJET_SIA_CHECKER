"""Journal des décisions de classement d'un projet généré : `generation/decisions.json` (V4_PLAN §3.3, phase 24).

Une décision change le code SIA (et le sous-type Treegram) d'un espace de la maquette. Elle vient de l'IA
(`origine: ia`) ou de l'utilisateur (`origine: manuel`, phase 25). Une décision de l'IA arrive **proposée** :
elle ne change rien tant qu'elle n'est pas **acceptée**. À chaque génération, le moteur applique les décisions
acceptées par-dessus le classement des règles ; le journal survit aux régénérations.

{
  "format": "sia-check-decisions", "version": 1,
  "decisions": [{
      "id":        GlobalId de l'IfcSpace
      "nom":       nom / nom long de l'espace, pour la lecture
      "origine":   "ia" | "manuel"
      "statut":    "proposée" | "acceptée" | "rejetée" | "confirmée" (l'IA garde le classement des règles)
      "avant":     {"code", "type"} : classement des règles au moment de la décision
      "code", "type":  classement décidé
      "certitude": "sûr" | "probable" | "incertain" (IA)
      "raison":    une phrase
      "date":      ISO
  }]
}
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .classify import EXTERIEUR, PIECE, Decision

FORMAT, VERSION = "sia-check-decisions", 1
FILE = Path("generation") / "decisions.json"
STATUSES = ("proposée", "acceptée", "rejetée", "confirmée")
ORIGINS = ("ia", "manuel")


class JournalError(ValueError):
    pass


def path(folder: Path) -> Path:
    return Path(folder) / FILE


def load(folder: Path) -> list[dict]:
    """Décisions du projet généré ; liste vide sans journal. JournalError si le fichier ne suit pas le format."""
    p = path(folder)
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as ex:
        raise JournalError(f"{p.name} illisible : {ex}") from ex
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise JournalError(f"{p.name} : format « {FORMAT} » attendu")
    out = []
    for n, d in enumerate(doc.get("decisions") or []):
        if not isinstance(d, dict) or not d.get("id") or not d.get("code"):
            raise JournalError(f"{p.name}, décision {n} : « id » et « code » attendus")
        if d.get("statut") not in STATUSES or d.get("origine") not in ORIGINS:
            raise JournalError(f"{p.name}, décision {n} : statut ou origine inconnus")
        out.append(d)
    return out


def save(folder: Path, decisions: list[dict]) -> Path:
    p = path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"format": FORMAT, "version": VERSION, "decisions": decisions},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def merge(old: list[dict], new: list[dict]) -> list[dict]:
    """Ajoute les nouvelles décisions. Une décision acceptée, rejetée ou manuelle n'est jamais remplacée par une
    nouvelle proposition de l'IA sur le même espace ; une ancienne proposition encore ouverte l'est."""
    kept = {d["id"]: d for d in old}
    for d in new:
        prev = kept.get(d["id"])
        if prev is not None and (prev["origine"] == "manuel" or prev["statut"] in ("acceptée", "rejetée")):
            continue
        kept[d["id"]] = d
    return list(kept.values())


def set_status(decisions: list[dict], status: str, ids: set[str] | None = None) -> int:
    """Statut des propositions ouvertes (toutes, ou celles de `ids`) ; renvoie le nombre changé."""
    n = 0
    for d in decisions:
        if d["statut"] == "proposée" and (ids is None or d["id"] in ids):
            d["statut"] = status
            n += 1
    return n


def _nature(code: str, cfg_generation: dict | None) -> str:
    natures = ((cfg_generation or {}).get("classify") or {}).get("code_natures") or {}
    return natures.get(code, PIECE)


def apply(entries: list[dict], decisions: dict[str, Decision], cfg_generation: dict | None = None) -> int:
    """Remplace, dans `decisions`, le classement des espaces dont une décision est acceptée ; renvoie leur nombre."""
    n = 0
    for e in entries:
        d = decisions.get(e["id"])
        if e["statut"] != "acceptée" or d is None:
            continue
        nature = _nature(e["code"], cfg_generation)
        if d.nature not in (PIECE, EXTERIEUR) or nature not in (PIECE, EXTERIEUR):
            continue   # contours, sites : hors du champ des décisions de classement
        c = (cfg_generation or {}).get("classify") or {}
        defaults = (c.get("default_types") or {}) | (c.get("exterior_default_types") or {})
        typ = e.get("type") or (d.type if e["code"] == d.code else defaults.get(e["code"]))
        decisions[e["id"]] = Decision(d.gid, nature, e["code"], typ, e["origine"], 1.0,
                                      f"{e['origine']} : {e.get('raison') or ''}".strip(), [], d.in_lot)
        n += 1
    return n


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")
