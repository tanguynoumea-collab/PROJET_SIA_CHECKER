"""Chargement et validation de la configuration YAML."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CustomRule:
    """Écart assumé à la SIA 416 (« règle personnalisée ») : `adds` deviennent enfants de `parent`.

    Exemple : Treegram a créé SUT à côté de SUP et SUS ; P1 déclare SU = SUP + SUS + SUT.
    L'arbre normatif de `categories` reste celui de la norme ; l'écart est appliqué au
    chargement et signalé dans les messages, les rapports et l'export visionneuse.
    """
    id: str
    title: str
    parent: str
    adds: tuple[str, ...]
    description: str = ""


@dataclass
class Config:
    categories: dict[str, dict]
    abs_m2: float = 0.5
    rel: float = 0.005
    ground: list[str] = field(default_factory=list)
    technical: list[str] = field(default_factory=list)
    order: list[dict] = field(default_factory=list)
    sources: dict[str, dict] = field(default_factory=dict)
    labels: dict[str, dict] = field(default_factory=dict)   # code -> {name, ref, def}
    custom_rules: list[CustomRule] = field(default_factory=list)

    def children(self, code: str) -> list[str]:
        return self.categories.get(code, {}).get("children") or []

    def canonical(self, code: str) -> str:
        return self.categories[code].get("alias_of") or code

    def custom_rule_of(self, code: str) -> CustomRule | None:
        """Règle personnalisée qui a ajouté `code` à l'arbre, s'il y en a une."""
        return next((r for r in self.custom_rules if code in r.adds), None)


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return from_dict(raw)


def _custom_rules(raw: list[dict] | None, cats: dict[str, dict]) -> list[CustomRule]:
    rules = []
    for r in raw or []:
        rule = CustomRule(id=str(r["id"]), title=str(r.get("title", r["id"])), parent=str(r["parent"]),
                          adds=tuple(r.get("adds") or ()), description=str(r.get("description", "")).strip())
        for code in (rule.parent, *rule.adds):
            if code not in cats:
                raise ConfigError(f"config : règle personnalisée {rule.id} cite {code}, absent de 'categories'")
        parent = cats[rule.parent]
        parent["children"] = list(parent.get("children") or []) + [c for c in rule.adds if c not in (parent.get("children") or [])]
        for code in rule.adds:
            if cats[code].get("ignore"):
                raise ConfigError(f"config : {code} est « ignore » mais la règle {rule.id} l'ajoute à {rule.parent}")
            cats[code]["parent"] = rule.parent
        rules.append(rule)
    return rules


def from_dict(raw: dict) -> Config:
    cats = copy.deepcopy(raw.get("categories") or {})
    if not cats:
        raise ConfigError("config : section 'categories' vide")
    for code, spec in cats.items():
        cats[code] = spec or {}
    custom = _custom_rules(raw.get("custom_rules"), cats)
    for code, spec in cats.items():
        for child in spec.get("children") or []:
            if child not in cats:
                raise ConfigError(f"config : {code}.children cite {child}, absent de 'categories'")
        target = spec.get("alias_of")
        if target and target not in cats:
            raise ConfigError(f"config : {code}.alias_of cite {target}, absent de 'categories'")
    tol = raw.get("tolerance") or {}
    lv = raw.get("levels") or {}
    return Config(
        categories=cats,
        abs_m2=float(tol.get("abs_m2", 0.5)),
        rel=float(tol.get("rel", 0.005)),
        ground=list(lv.get("ground") or []),
        technical=list(lv.get("technical") or []),
        order=list(lv.get("order") or []),
        sources=raw.get("sources") or {},
        labels=raw.get("labels") or {},
        custom_rules=custom,
    )
