"""Chargement et validation de la configuration YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(ValueError):
    pass


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

    def children(self, code: str) -> list[str]:
        return self.categories.get(code, {}).get("children") or []

    def canonical(self, code: str) -> str:
        return self.categories[code].get("alias_of") or code


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return from_dict(raw)


def from_dict(raw: dict) -> Config:
    cats = raw.get("categories") or {}
    if not cats:
        raise ConfigError("config : section 'categories' vide")
    for code, spec in cats.items():
        spec = cats[code] = spec or {}
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
    )
