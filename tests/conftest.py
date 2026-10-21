from pathlib import Path

import pandas as pd
import pytest

from sia_check import config, rules

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).parent / "data"


@pytest.fixture
def cfg():
    c = config.load(ROOT / "config.yaml")
    c.technical = ["^LT"]
    return c


@pytest.fixture
def synth() -> pd.DataFrame:
    return pd.read_csv(DATA / "synth.csv", comment="#", dtype={"category": str, "lot": str})


@pytest.fixture
def result(synth, cfg) -> rules.Result:
    return rules.run(synth, cfg)


def pick(result: rules.Result, building, level, rule, lot=None) -> pd.DataFrame:
    r = result.residuals
    r = r[(r.building == building) & (r.level == level) & (r.rule == rule)]
    if lot is not None:
        r = r[r.lot == lot]
    return r


def verdict(result, building, level, rule, lot=None) -> str | None:
    """Verdict unique d'un contrôle, None s'il n'a pas été émis."""
    r = pick(result, building, level, rule, lot)
    assert len(r) <= 1, r
    return None if r.empty else r.verdict.iloc[0]
