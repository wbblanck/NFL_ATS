"""Spread conventions, half-point validation, and ATS grading.

Canonical convention (spec section 2): the spread S is quoted from the HOME
team's perspective, negative = home favored.  Margin = home - away.

    home covers  <=>  Margin > -S
    away covers  <=>  Margin < -S
    push         <=>  Margin == -S   (impossible for half-point S)

nflverse `spread_line` uses the opposite sign: positive = home favored
(verified: nflreadr dictionary_schedules.csv, and 3252/3253 games with
spread_line > 0 have a negative home moneyline).  Convert with
`from_nflverse_spread_line`.
"""
from __future__ import annotations

import math
from enum import Enum


class Side(str, Enum):
    HOME = "home"
    AWAY = "away"


class Result(str, Enum):
    HOME_COVER = "home_cover"
    AWAY_COVER = "away_cover"
    PUSH = "push"


class InvalidLeagueLine(ValueError):
    """Raised for a line that cannot occur under league rules (e.g. whole number)."""


def is_half_point(spread: float) -> bool:
    return math.isfinite(spread) and abs(abs(spread) % 1 - 0.5) < 1e-9


def validate_league_line(spread: float) -> float:
    """Return the spread if it is a legal league line; raise otherwise."""
    if spread is None or not isinstance(spread, (int, float)) or not math.isfinite(spread):
        raise InvalidLeagueLine(f"non-numeric spread: {spread!r}")
    if not is_half_point(spread):
        raise InvalidLeagueLine(f"whole-number spread {spread} (league lines are always x.5)")
    return float(spread)


def from_nflverse_spread_line(spread_line: float) -> float:
    """nflverse (positive = home favored) -> canonical S (negative = home favored)."""
    return -float(spread_line)


def to_nflverse_spread_line(s: float) -> float:
    return -float(s)


def favorite(s: float) -> Side | None:
    if s < 0:
        return Side.HOME
    if s > 0:
        return Side.AWAY
    return None


def grade(home_score: int, away_score: int, s: float) -> Result:
    """Grade one game against canonical spread S. Pushes are only possible for
    whole-number lines, which callers in league mode must have rejected."""
    margin = home_score - away_score
    if margin > -s:
        return Result.HOME_COVER
    if margin < -s:
        return Result.AWAY_COVER
    return Result.PUSH


def grade_league(home_score: int, away_score: int, s: float) -> Result:
    """Grade under league rules: the line must be a half-point, so no push."""
    return grade(home_score, away_score, validate_league_line(s))


def pick_won(pick: Side, result: Result) -> bool | None:
    if result is Result.PUSH:
        return None
    return (pick is Side.HOME) == (result is Result.HOME_COVER)
