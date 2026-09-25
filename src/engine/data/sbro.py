"""Parse SBRO (sportsbookreviewsonline.com) NFL season pages into one row per game
with opening and closing HOME spreads (canonical sign: negative = home favored).

Page format (verified on 2007-08, 2014-15, 2021-22 pages in data/raw/sbro/):
one table, header `Date Rot VH Team 1st 2nd 3rd 4th Final Open Close ML 2H`,
two consecutive rows per game (V then H, or N/N for neutral sites). In each of
Open/Close, one row holds the point spread (favorite's row, positive number or
"pk") and the other holds the game total. Date is MMDD with no year.
The source book is not named by SBRO (UNVERIFIED).

Anything that does not fit (both values small/large, negative spread cell,
unknown team, no schedule match) is kept with a non-ok `status`, never guessed.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import polars as pl
from bs4 import BeautifulSoup

NAMES = {
    "Arizona": "ARI", "Atlanta": "ATL", "Baltimore": "BAL", "Buffalo": "BUF", "Carolina": "CAR",
    "Chicago": "CHI", "Cincinnati": "CIN", "Cleveland": "CLE", "Dallas": "DAL", "Denver": "DEN",
    "Detroit": "DET", "GreenBay": "GB", "Houston": "HOU", "HoustonTexans": "HOU", "Indianapolis": "IND",
    "Jacksonville": "JAX", "KansasCity": "KC", "LAChargers": "LAC", "LARams": "LA", "LasVegas": "LV",
    "Miami": "MIA", "Minnesota": "MIN", "NYGiants": "NYG", "NYJets": "NYJ", "NewEngland": "NE",
    "NewOrleans": "NO", "Oakland": "OAK", "Philadelphia": "PHI", "Pittsburgh": "PIT", "SanDiego": "SD",
    "SanFrancisco": "SF", "Seattle": "SEA", "St.Louis": "STL", "TampaBay": "TB", "Tennessee": "TEN",
    "Washington": "WAS",
    # spelling variants observed in the raw pages
    "BuffaloBills": "BUF", "KCChiefs": "KC", "Kansas": "KC", "LVRaiders": "LV", "Tampa": "TB",
    "Washingtom": "WAS",
}
# Names that depend on season / are ambiguous (resolved against the schedule).
SEASON_NAMES = {("LosAngeles", 2016): {"LA"}}          # Chargers moved to LA in 2017
AMBIGUOUS = {"NewYork": {"NYG", "NYJ"}}


def resolve(name: str, season: int) -> set[str]:
    if name in NAMES:
        return {NAMES[name]}
    return SEASON_NAMES.get((name, season)) or AMBIGUOUS.get(name, set())
TOTAL_MIN = 25.0   # a value >= this is a game total, not a spread (NFL spreads never reach 25)


def _num(v: str) -> float | None:
    v = v.strip().lower()
    if v in ("pk", "pick", "pk'"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return None


def _split(a: str, b: str) -> tuple[int | None, float | None, str]:
    """Given the two rows' cells, return (index of spread row, spread value, status)."""
    x, y = _num(a), _num(b)
    if x is None or y is None:
        return None, None, "unparsable"
    xs, ys = abs(x) < TOTAL_MIN, abs(y) < TOTAL_MIN
    if xs == ys:
        return None, None, "ambiguous_spread_total"
    i, v = (0, x) if xs else (1, y)
    if v < 0:
        return i, v, "negative_spread_cell"
    return i, v, "ok"


def parse_page(html: str, season: int) -> list[dict]:
    t = BeautifulSoup(html, "lxml").find("table")
    rows = [[c.get_text(strip=True) for c in r.find_all(["td", "th"])] for r in t.find_all("tr")]
    hdr, body = rows[0], rows[1:]
    ix = {k: hdr.index(k) for k in ("Date", "VH", "Team", "Final", "Open", "Close")}
    out = []
    for r1, r2 in zip(body[0::2], body[1::2]):
        mmdd = int(r1[ix["Date"]])
        month, day = divmod(mmdd, 100)
        year = season if month >= 8 else season + 1
        rec = {"season": season, "date": dt.date(year, month, day).isoformat(),
               "vh": r1[ix["VH"]] + r2[ix["VH"]], "team1_raw": r1[ix["Team"]], "team2_raw": r2[ix["Team"]],
               "score1": int(r1[ix["Final"]]), "score2": int(r2[ix["Final"]]),
               "raw_open": f'{r1[ix["Open"]]}|{r2[ix["Open"]]}',
               "raw_close": f'{r1[ix["Close"]]}|{r2[ix["Close"]]}'}
        c1, c2 = resolve(rec["team1_raw"], season), resolve(rec["team2_raw"], season)
        rec.update(team1_candidates=sorted(c1), team2_candidates=sorted(c2))
        status = "ok" if c1 and c2 else "unknown_team"
        for col in ("Open", "Close"):
            i, v, st = _split(r1[ix[col]], r2[ix[col]])
            # spread as "team1 favored by v" -> team1_spread = -v (team1 perspective)
            rec[f"{col.lower()}_team1_spread"] = None if i is None or st != "ok" else (-v if i == 0 else v)
            rec[f"{col.lower()}_status"] = st
        rec["status"] = status
        out.append(rec)
    return out


def load_all(raw_dir: Path) -> pl.DataFrame:
    rows = []
    for f in sorted(raw_dir.glob("nfl-odds-*.html")):
        season = int(re.search(r"nfl-odds-(\d{4})", f.name).group(1))
        rows += parse_page(f.read_text(), season)
    return pl.DataFrame(rows, infer_schema_length=None)


def match_schedule(sb: pl.DataFrame, sched: pl.DataFrame) -> pl.DataFrame:
    """Attach nflverse game_id and orient spreads to the nflverse home team."""
    s = sched.select("game_id", "season", "week", "game_type", "gameday", "home_team", "away_team",
                     "home_score", "away_score", "spread_line")
    out = []
    games = s.to_dicts()
    for r in sb.to_dicts():
        rec = dict(r)
        d = dt.date.fromisoformat(r["date"])
        cands = []
        for g in games:
            if abs((dt.date.fromisoformat(g["gameday"]) - d).days) > 1:
                continue
            h, a = g["home_team"], g["away_team"]
            if h in r["team1_candidates"] and a in r["team2_candidates"]:
                cands.append((g, True))       # team1 is home
            elif a in r["team1_candidates"] and h in r["team2_candidates"]:
                cands.append((g, False))      # team1 is away
        if r["status"] != "ok" or len(cands) != 1:
            rec["match_status"] = r["status"] if r["status"] != "ok" else f"{len(cands)}_schedule_matches"
            out.append(rec)
            continue
        g, team1_home = cands[0]
        flip = not team1_home
        # team1_spread is from team1's perspective; home spread = team1_spread if team1 is home else -team1_spread
        for col in ("open", "close"):
            v = r[f"{col}_team1_spread"]
            rec[f"{col}_home_spread"] = None if v is None else (v if not flip else -v)
        home_is_1 = not flip
        sc_home = r["score1"] if home_is_1 else r["score2"]
        sc_away = r["score2"] if home_is_1 else r["score1"]
        score_ok = (sc_home, sc_away) == (g["home_score"], g["away_score"])
        rec.pop("team1_candidates"); rec.pop("team2_candidates")
        rec.update(game_id=g["game_id"], week=g["week"], game_type=g["game_type"], home_team=g["home_team"],
                   away_team=g["away_team"], home_score=g["home_score"], away_score=g["away_score"],
                   nflverse_close_home_spread=None if g["spread_line"] is None else -g["spread_line"],
                   match_status="ok" if score_ok else "score_mismatch_sbro_score_ignored")
        out.append(rec)
    for r in out:
        r.pop("team1_candidates", None); r.pop("team2_candidates", None)
    return pl.DataFrame(out, infer_schema_length=None)
