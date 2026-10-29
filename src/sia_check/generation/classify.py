"""Nature et classement des espaces de la maquette (V4_PLAN §3.1, phase 21).

1. **Nature** : tous les `IfcSpace` ne sont pas des pièces. Un espace dont l'emprise couvre au moins deux autres
   espaces du niveau est un *contour* : surface de plancher (`GFA`, « Surface de plancher ») ou logement dessiné
   en entier. Les extérieurs (balcons, terrasses…) et le terrain sont mis de côté pour la phase 22.
2. **Classement des pièces**, sources de la plus sûre à la moins sûre (config.yaml > generation.classify) :
   code SIA écrit dans une propriété (`SIA416` = SUP), catégorie en toutes lettres (`Pset_SpaceCommon.Category`
   = « Surface utile principal »), code en préfixe du nom (`SUS_CON`), dictionnaire des noms de pièces.
   Le sous-type Treegram (`Type`) vient du dictionnaire quand il s'accorde avec le code retenu, sinon du type
   par défaut du code.
3. **Conventions Treegram** : un dégagement dans un logement est de la SUP « Distribution ».

Chaque décision garde sa source, sa confiance (0 à 1), sa raison et les sources en désaccord : c'est ce que
l'analyse IA (phase 24) et l'ajustement manuel reprendront, en commençant par les moins sûres.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .ingest import Item, Model
from .plans import Plan

PIECE, PLANCHER, LOGEMENT, EXTERIEUR, SITE, CONSTRUCTION = "piece", "plancher", "logement", "exterieur", "site", "construction"
CONFIDENCE = {"propriete": 0.95, "categorie": 0.9, "prefixe": 0.9, "dictionnaire": 0.7}
DECIDED = 0.85   # règle tranchée avec l'utilisateur (convention Treegram vérifiée sur un MDP, décision) : plus à confirmer
CONFLICT_PENALTY = 0.2


@dataclass
class Decision:
    gid: str
    nature: str
    code: str | None = None
    type: str | None = None
    source: str | None = None        # propriete | categorie | prefixe | dictionnaire | convention | None
    confidence: float = 0.0
    reason: str = ""
    conflicts: list[str] = field(default_factory=list)
    in_lot: bool = False


def norm(text) -> str:
    """Sans accents ni casse, séparateurs (_ - . /) remplacés par des espaces : « SD_ASC_1 » -> « sd asc 1 »."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[_\-.]+", " ", t).strip()


def _label(item: Item) -> str:
    return " / ".join(x for x in (item.name, item.long_name) if x)


def _containers(plan: Plan, need: int, cover: float) -> set[str]:
    shapes = [(p.item.gid, p.shape) for p in plan.spaces if p.shape is not None]
    out = set()
    for gid, g in shapes:
        inside = 0
        for other, h in shapes:
            if other != gid and h.area > 0 and g.intersection(h).area >= cover * h.area and h.area < g.area:
                inside += 1
                if inside >= need:
                    out.add(gid)
                    break
    return out


class Classifier:
    def __init__(self, cfg_generation: dict):
        c = (cfg_generation or {}).get("classify") or {}
        self.c = c
        self.codes = set(c.get("sia_codes") or [])
        self.code_props = {norm(k) for k in c.get("code_properties") or []}
        self.cat_prop = c.get("category_property")
        self.categories = [(re.compile(k), v) for k, v in (c.get("categories") or {}).items()]
        self.prefix = re.compile(r"^(%s)(?=[\s_\-.]|$)" % "|".join(sorted(self.codes, key=len, reverse=True))) \
            if self.codes else None
        self.exterior = re.compile(c["exterior_names"]) if c.get("exterior_names") else None
        self.rooms = [dict(r, rx=re.compile(r["match"])) for r in c.get("rooms") or []]
        self.common = re.compile(c["common_lot"]) if c.get("common_lot") else None
        self.defaults = c.get("default_types") or {}

    def in_lot(self, item: Item) -> bool:
        """Pièce d'un logement : numéro de logement présent et hors parties communes (sans logements : aucune)."""
        return item.lot is not None and not (self.common and self.common.search(item.lot))

    # --------------------------------------------------------------- sources
    def _from_property(self, item: Item):
        for k, v in item.props.items():
            if norm(k.rsplit(".", 1)[-1]) in self.code_props and isinstance(v, str) and v.strip().upper() in self.codes:
                return v.strip().upper(), f"propriété {k} = {v.strip()}"
        return None

    def _from_category(self, item: Item):
        v = item.props.get(self.cat_prop) if self.cat_prop else None
        t = norm(v)
        for rx, spec in self.categories:
            if t and rx.search(t):
                return spec, f"catégorie « {v} »"
        return None

    def _from_prefix(self, item: Item):
        for text in (item.long_name, item.name):
            m = self.prefix.match(text.strip().upper()) if (self.prefix and text) else None
            if m:
                return m[1], f"préfixe du nom « {text} »"
        return None

    def _from_rooms(self, item: Item, in_lot: bool, code: str | None = None):
        """Première entrée du dictionnaire qui correspond au nom long, sinon au nom ; avec `code`, parmi les seules
        entrées de ce code (sous-type d'une pièce dont le code vient d'une autre source)."""
        for text in (item.long_name, item.name):
            t = norm(text)
            if not t:
                continue
            for r in self.rooms:
                where = r.get("where")
                if where and (where == "lot") != in_lot or code is not None and r["code"] != code:
                    continue
                if r["rx"].search(t):
                    return r, f"nom « {text} »"
        return None

    def _type(self, item: Item, in_lot: bool, code: str, room) -> str | None:
        """Sous-type : celui du dictionnaire pour ce code (« CIR » classé SUS par l'architecte : la voie du parking),
        sinon le sous-type par défaut du code."""
        if room and room[0]["code"] == code:
            return room[0].get("type")
        own = self._from_rooms(item, in_lot, code)
        return own[0].get("type") if own else self.defaults.get(code)

    #: codes dont le sous-type compte pour l'export MDP (affectation) : introuvable dans le nom, la question part à l'IA
    TYPED = ("SUS",)

    # --------------------------------------------------------------- décision
    def nature(self, item: Item, container: bool) -> tuple[str, str]:
        cat = self._from_category(item)
        cat_nature = cat[0].get("nature") if cat else None
        gfa = (self.c.get("predefined") or {}).get(str(item.predefined or "").upper())
        # Un extérieur l'emporte sur tout le reste : les « Surface externe de plancher » des Myonaz sont typées GFA
        if cat_nature in (EXTERIEUR, SITE):
            return cat_nature, cat[1]
        if self.exterior and self.exterior.search(norm(item.long_name) + " " + norm(item.name)):
            return EXTERIEUR, f"nom « {_label(item)} »"
        if container:
            if gfa == PLANCHER or cat_nature == PLANCHER or "surface de plancher" in norm(item.long_name):
                return PLANCHER, "contour des pièces, surface de plancher"
            return LOGEMENT, "contour d'autres espaces du niveau (logement dessiné en entier)"
        if gfa:
            return gfa, f"type prédéfini {item.predefined}"
        if cat_nature:
            return cat_nature, cat[1]
        return PIECE, ""

    def _exterior(self, item: Item, d: Decision) -> Decision:
        """Extérieur : contour SEP (« plancher externe ») ou surface élémentaire SEU / SED / SEI avec son type."""
        c = self.c
        text = " ".join(norm(x) for x in (item.long_name, item.props.get(self.cat_prop) if self.cat_prop else None))
        if c.get("exterior_floor") and re.search(c["exterior_floor"], text):
            d.code, d.type, d.source, d.confidence = "SEP", None, "categorie", CONFIDENCE["categorie"]
            d.reason = d.reason or f"contour d'extérieur « {_label(item)} »"
            return d
        room = None
        for t in (item.long_name, item.name):
            for r in c.get("exterior_rooms") or []:
                where = r.get("where")
                if norm(t) and (not where or (where == "lot") == d.in_lot) and re.search(r["match"], norm(t)):
                    room = (r, f"nom « {t} »")
                    break
            if room:
                break
        found = []
        if (p := self._from_property(item)) and p[0] in ("SEU", "SED", "SEI"):
            found.append(("propriete", p[0], p[1]))
        cat = norm(item.props.get(self.cat_prop)) if self.cat_prop else ""
        for k, code in (c.get("exterior_categories") or {}).items():
            if cat and re.search(k, cat):
                found.append(("categorie", code, f"catégorie « {item.props.get(self.cat_prop)} »"))
                break
        if room:
            found.append(("dictionnaire", room[0]["code"], room[1]))
        if not found:
            dflt = c.get("exterior_default") or {"code": "SEU", "type": "Terrasse"}
            d.code, d.type, d.source, d.confidence = dflt["code"], dflt.get("type"), None, 0.5
            d.reason = f"extérieur sans précision « {_label(item)} » : {dflt['code']} par défaut"
            return d
        source, code, why = found[0]
        d.code, d.source, d.reason = code, source, why
        d.conflicts = [f"{s} : {k} ({w})" for s, k, w in found[1:] if k != code]
        d.confidence = CONFIDENCE[source] - (CONFLICT_PENALTY if d.conflicts else 0.0)
        if source == "dictionnaire" and not d.conflicts:
            d.confidence = DECIDED   # noms d'extérieurs (BAL, ENT, ESC…) validés sur les MDP avec l'utilisateur, 28–29.10.2026
        d.type = room[0].get("type") if room and room[0]["code"] == code else (c.get("exterior_default_types") or {}).get(code)
        return d

    def decide(self, item: Item, container: bool) -> Decision:
        nature, why = self.nature(item, container)
        lot = self.in_lot(item)
        d = Decision(item.gid, nature, in_lot=lot, reason=why)
        if nature == EXTERIEUR:
            return self._exterior(item, d)
        if nature != PIECE:
            return d
        found = []   # (source, code, raison)
        if (p := self._from_property(item)):
            found.append(("propriete", p[0], p[1]))
        if (cat := self._from_category(item)) and cat[0].get("code"):
            found.append(("categorie", cat[0]["code"], cat[1]))
        if (p := self._from_prefix(item)):
            found.append(("prefixe", p[0], p[1]))
        room = self._from_rooms(item, lot)
        if room:
            found.append(("dictionnaire", room[0]["code"], room[1]))
        if not found:
            d.code, d.reason = self.c.get("unclassified", "NONCLASSE"), f"aucune source pour « {_label(item)} »"
            return d
        source, code, why = found[0]
        d.code, d.source, d.reason = code, source, why
        if (other := (self.c.get("code_natures") or {}).get(code)):
            d.nature, d.confidence = other, CONFIDENCE[source]
            return self._exterior(item, d) if other == EXTERIEUR else d
        d.conflicts = [f"{s} : {c} ({w})" for s, c, w in found[1:] if c != code]
        if room and room[0]["code"] != code and self._from_rooms(item, lot, code):
            # le nom vaut aussi pour le code retenu (« CIR » qu'une catégorie SUS met au parking : sa voie) : le
            # dictionnaire n'est pas en désaccord, il donnait seulement sa première lecture
            d.conflicts = [x for x in d.conflicts if not x.startswith("dictionnaire")]
        d.confidence = CONFIDENCE[source] - (CONFLICT_PENALTY if d.conflicts else 0.0)
        if self.c.get("technical_over_sus", True) and code == "SUS" and room and room[0]["code"] == "SI":
            # local technique (électricité, CVC) que l'architecte compte en SUS : une installation, SIA 416 (29.10.2026)
            d.conflicts = [f"{source} : SUS ({why})"]
            code, d.code, d.source = "SI", "SI", "dictionnaire"
            d.reason, d.confidence = f"local technique, {room[1]} : SI (installations, SIA 416)", DECIDED
        d.type = self._type(item, lot, code, room)
        if code in self.TYPED and not (room and room[0]["code"] == code) and not self._from_rooms(item, lot, code):
            d.conflicts.append(f"sous-type : aucun nom reconnu pour une {code}, « {d.type} » par défaut")
        if self.c.get("treegram_conventions", True) and lot and code == "SD" and d.type in ("CirculationH", None):
            d.conflicts.append(f"{source} : SD ({why})")
            d.code, d.type, d.source = "SUP", "Distribution", "convention"
            d.reason = "convention Treegram : dégagement d'un logement compté en SUP « Distribution »"
            d.confidence = DECIDED   # conforme aux MDP Myonaz
        elif (self.c.get("treegram_conventions", True) and lot and code == "SUS" and room
              and room[0]["code"] == "SUP"):
            # le sous-type SUS « par défaut » ne vaut plus : la pièce est une SUP du logement
            d.conflicts = [x for x in d.conflicts if not x.startswith("sous-type :")] + [f"{source} : SUS ({why})"]
            d.code, d.type, d.source = "SUP", room[0].get("type"), "convention"
            d.reason = f"convention Treegram : {room[1]} dans un logement compté en SUP (MDP Myonaz : réduits en SUP)"
            d.confidence = DECIDED
        return d


def classify(model: Model, plans: list[Plan], cfg_generation: dict | None = None) -> dict[str, Decision]:
    c = (cfg_generation or {}).get("classify") or {}
    need, cover = int(c.get("container_min_children", 2)), float(c.get("container_cover", 0.9))
    k = Classifier(cfg_generation or {})
    out = {}
    for plan in plans:
        containers = _containers(plan, need, cover)
        for p in plan.spaces:
            out[p.item.gid] = k.decide(p.item, p.item.gid in containers)
    for s in model.spaces:   # espaces sans niveau : jugés quand même, ils ne seront pas comptés
        out.setdefault(s.gid, k.decide(s, False))
    if c.get("treegram_conventions", True) and c.get("sut_without_flats", True):
        without_flats(model, out, k)
    return out


def type_for(model: Model, decisions: dict[str, Decision], cfg_generation: dict | None = None):
    """(gid, code) -> sous-type que le dictionnaire donne à cet espace pour ce code (journal.apply)."""
    k = Classifier(cfg_generation or {})
    items = {s.gid: s for s in model.spaces}

    def f(gid: str, code: str) -> str | None:
        it = items.get(gid)
        return k._type(it, decisions[gid].in_lot, code, None) if it is not None else None
    return f


SANITARY = re.compile(r"\b(wc|wch|toilettes?|sanitaires?|lavabos?|douches?|salle de bains?|sdb|vestiaires?)\b")


def without_flats(model: Model, decisions: dict[str, Decision], classifier: "Classifier | None" = None) -> dict[str, int]:
    """Bâtiment sans logement (aucune pièce dans un lot) : la SUP de l'architecte, au sens de la SIA 416, est de
    la SUT chez Treegram, dont les sous-types SUP sont ceux du logement (décision du 28.10.2026, sur la
    proposition de l'analyse IA d'Afiro). Les sanitaires passent en SUS, comme des sanitaires communs. Avec le
    `classifier`, un nom qui dit SUS, SD ou SI (`name_wins_without_flats` : stockage, circulation, local technique)
    l'emporte sur la SUP de l'architecte (décision du 29.10.2026).
    Renvoie, par bâtiment touché, le nombre de pièces reclassées."""
    building = {s.gid: s.building for s in model.spaces}
    items = {s.gid: s for s in model.spaces}
    wins = set((classifier.c.get("name_wins_without_flats") or []) if classifier else [])
    words = {s.gid: norm(" ".join(str(v) for v in (s.name, s.long_name, *s.props.values()) if v)) for s in model.spaces}
    flats = {building[g] for g, d in decisions.items() if d.nature == PIECE and d.in_lot}
    out: dict[str, int] = {}
    for g, d in decisions.items():
        b = building.get(g)
        if d.nature != PIECE or d.code != "SUP" or b in flats:
            continue
        # décision approuvée : pas un désaccord, l'espace ne repart pas à l'analyse IA pour cette seule raison
        # sanitaire : sous-type à points d'eau, ou le nom le dit sans sous-type (CGA L04 : « SUP_WC », « WC handicapés »)
        sanitary = (d.type or "").startswith("PieceSecondaire") or bool(SANITARY.search(words.get(g, "")))
        named = classifier._from_rooms(items[g], False) if wins and g in items and not sanitary else None
        if named and named[0]["code"] in wins:
            code = named[0]["code"]
            d.code, d.type = code, named[0].get("type") or classifier.defaults.get(code)
            d.reason = f"bâtiment sans logement : {named[1]} l'emporte sur la SUP de l'architecte ({d.source} : {d.reason})"
            d.conflicts = [x for x in d.conflicts if not x.startswith("dictionnaire")]
            d.source, d.confidence = "convention", DECIDED
            out[b] = out.get(b, 0) + 1
            continue
        d.code, d.type = ("SUS", "Sanitaires") if sanitary else ("SUT", "Commerce")
        d.reason = f"convention Treegram : bâtiment sans logement, SUP ({d.source} : {d.reason}) comptée en {d.code}"
        d.source = "convention"
        agree = [x for x in d.conflicts if x.startswith(f"dictionnaire : {d.code} ")]
        if agree:   # le nom dit déjà ce code (« SUP_WC » : SUS) : plus de désaccord
            d.conflicts = [x for x in d.conflicts if x not in agree]
            d.confidence = max(d.confidence, DECIDED)
        out[b] = out.get(b, 0) + 1
    return out
