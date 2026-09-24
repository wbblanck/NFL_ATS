"""Team-code mapping to the canonical nflverse abbreviations.

Canonical codes are those used in nflverse schedules (verified 2026-09-24 via
nflreadpy.load_schedules(): 35 codes 1999-2026, incl. relocated OAK/SD/STL).
Aliases below were observed in source data:
  * CBS odds page: data-game-abbrev uses JAC for Jacksonville
    (evidence: NFL_20260927_NE@JAC) while its team text shows JAX.
  * nflreadpy.load_teams() lists both LA and LAR for the Rams.
  * Parlay API uses full team names ("Green Bay Packers").
"""
from __future__ import annotations

CANONICAL = frozenset({
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
    "HOU", "IND", "JAX", "KC", "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ",
    "OAK", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEN", "WAS",
})

# Franchises active in the current era (2020+).
CURRENT = frozenset(CANONICAL - {"OAK", "SD", "STL"})

ALIASES = {
    "JAC": "JAX",
    "LAR": "LA",
    "WSH": "WAS",
    "GNB": "GB",
    "KAN": "KC",
    "NWE": "NE",
    "NOR": "NO",
    "SFO": "SF",
    "TAM": "TB",
    "LVR": "LV",
}

FULL_NAMES = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Los Angeles Rams": "LA", "Los Angeles Chargers": "LAC",
    "Las Vegas Raiders": "LV", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "Seattle Seahawks": "SEA", "San Francisco 49ers": "SF", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
    # historical names
    "Oakland Raiders": "OAK", "San Diego Chargers": "SD", "St. Louis Rams": "STL",
    "Washington Football Team": "WAS", "Washington Redskins": "WAS",
}


class UnknownTeam(ValueError):
    pass


def to_canonical(code: str) -> str:
    """Map an abbreviation or full team name to the nflverse code; raise if unknown."""
    if code is None:
        raise UnknownTeam("None")
    c = code.strip()
    if c in FULL_NAMES:
        return FULL_NAMES[c]
    u = c.upper()
    if u in CANONICAL:
        return u
    if u in ALIASES:
        return ALIASES[u]
    raise UnknownTeam(code)
