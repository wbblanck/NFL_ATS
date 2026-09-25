"""Config loading. All league rules and paths come from config/*.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("NFL_ATS_ROOT", Path(__file__).resolve().parents[2]))


def _load(name: str) -> dict:
    with open(ROOT / "config" / name) as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class LeagueRules:
    lock_buffer_minutes: int
    half_point_only: bool
    game_types: tuple[str, ...]
    timezone: str
    pick_every_game: bool
    line_frozen: bool


@lru_cache
def league() -> LeagueRules:
    c = _load("league.yaml")
    return LeagueRules(
        lock_buffer_minutes=int(c["lock"]["buffer_minutes"]),
        half_point_only=bool(c["spread"]["half_point_only"]),
        game_types=tuple(c["season_scope"]["game_types"]),
        timezone=c["timezone"],
        pick_every_game=bool(c["pick_every_game"]),
        line_frozen=bool(c["line_frozen"]),
    )


@lru_cache
def data() -> dict:
    return _load("data.yaml")


@lru_cache
def model() -> dict:
    return _load("model.yaml")


def path(key: str) -> Path:
    p = ROOT / data()["paths"][key]
    p.mkdir(parents=True, exist_ok=True) if p.suffix == "" else p.parent.mkdir(parents=True, exist_ok=True)
    return p
