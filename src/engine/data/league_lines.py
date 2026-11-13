"""The league's actual grading lines, recorded by hand from the pool screen
(CBS Office Pool "BONSAI POOL 2026"). This is the source of truth for grading;
captured CBS/market lines are only used to work out how the league sets it.

Every line must be a half-point (league rule); anything else is rejected. Rows are validated one at a time:
a bad row is quarantined and reported, and the other games stay usable. Conflicting rows for one game
quarantine that game (status CONFLICT) until the file is fixed in a reviewed commit.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field

from engine import config
from engine.data import store
from engine.picks.grading import InvalidLeagueLine, favorite, validate_league_line
from engine.teams import to_canonical

FIELDS = ["game_id", "season", "week", "home_team", "away_team", "spread", "favorite",
          "source", "recorded_at"]


# Issue kinds. DUPLICATE_IDENTICAL is informational; every other kind quarantines the row(s) involved.
INVALID_ROW = "INVALID_ROW"                # unparseable, whole-number or missing spread, bad favorite, bad teams
SCHEDULE_MISMATCH = "SCHEDULE_MISMATCH"    # game_id or home/away not in the schedule (only checked when a schedule is given)
CONFLICT = "CONFLICT"                      # same game, different spreads: all of its rows are quarantined
DUPLICATE_IDENTICAL = "DUPLICATE_IDENTICAL"
INFO_KINDS = {DUPLICATE_IDENTICAL}

# Per-game line status (see LineSet.status).
VALID, NO_LINE, INVALID, CONFLICTING = "VALID", "NO_LINE", "INVALID", "CONFLICT"


def line_id(row: dict) -> str:
    """Immutable id of one recorded line: a hash of what was transcribed, so any change to the spread, source
    or timestamp gives a different id."""
    key = "|".join(str(row.get(k, "")) for k in ("game_id", "spread", "source", "recorded_at"))
    return "LL-" + hashlib.sha1(key.encode()).hexdigest()[:12]


@dataclass
class LineSet:
    """League lines after per-row validation. `valid` holds one usable row per game (with `line_id`);
    `issues` lists everything that was rejected or quarantined, so a bad row never hides silently."""
    valid: dict[str, dict] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)

    def status(self, game_id: str) -> str:
        """VALID: usable pool line. CONFLICT: conflicting rows. INVALID: only rejected rows. NO_LINE: nothing recorded."""
        if game_id in self.valid:
            return VALID
        kinds = {i["kind"] for i in self.issues if i["game_id"] == game_id}
        if CONFLICT in kinds:
            return CONFLICTING
        if kinds & {INVALID_ROW, SCHEDULE_MISMATCH}:
            return INVALID
        return NO_LINE

    def problems(self) -> list[dict]:
        return [i for i in self.issues if i["kind"] not in INFO_KINDS]

    def spreads(self) -> dict[str, float]:
        return {g: float(r["spread"]) for g, r in self.valid.items()}


def _check_row(r: dict) -> str | None:
    """Reason the row is unusable, or None."""
    if None in r:   # csv.DictReader puts surplus fields under None: an unquoted comma in `source` shifts recorded_at
        return "more fields than the header (an unquoted comma in a field?)"
    if not (r.get("game_id") or "").strip():
        return "missing game_id"
    raw = (r.get("spread") or "").strip()
    if not raw:
        return "missing spread"
    try:
        s = validate_league_line(float(raw))
    except (ValueError, InvalidLeagueLine) as e:
        return str(e)
    try:
        home, away = to_canonical(r["home_team"]), to_canonical(r["away_team"])
    except Exception as e:  # unknown team name
        return f"unknown team: {e}"
    if home == away:
        return "home and away are the same team"
    expected = {"home": home, "away": away}[favorite(s).value]
    if r.get("favorite") != expected:
        return f"favorite {r.get('favorite')} inconsistent with spread {s}"
    return None


def load_checked(sched=None) -> LineSet:
    """Validate league_lines.csv row by row. A bad row is quarantined and reported; it never blocks other games.
    With a schedule, rows whose game_id or home/away disagree with it are quarantined too."""
    ids = None
    if sched is not None:
        ids = {r["game_id"]: (r["home_team"], r["away_team"])
               for r in sched.select("game_id", "home_team", "away_team").to_dicts()}
    out = LineSet()
    groups: dict[str, list[tuple[int, dict]]] = {}
    for n, r in enumerate(store.read_rows(config.path("lines") / "league_lines.csv"), start=2):   # n = file line number
        gid = (r.get("game_id") or "").strip()
        why = _check_row(r)
        if why:
            out.issues.append({"kind": INVALID_ROW, "game_id": gid, "line": n, "message": why})
            continue
        if ids is not None:
            sch = ids.get(gid)
            if sch is None:
                out.issues.append({"kind": SCHEDULE_MISMATCH, "game_id": gid, "line": n,
                                   "message": "not a regular-season game in the schedule"})
                continue
            if sch != (r["home_team"], r["away_team"]):
                out.issues.append({"kind": SCHEDULE_MISMATCH, "game_id": gid, "line": n,
                                   "message": f"home/away {r['home_team']}/{r['away_team']} != schedule"})
                continue
        groups.setdefault(gid, []).append((n, r))
    for gid, items in groups.items():
        spreads = {float(r["spread"]) for _, r in items}
        if len(spreads) > 1:
            out.issues.append({"kind": CONFLICT, "game_id": gid, "line": items[-1][0],
                               "message": "conflicting spreads " + ", ".join(
                                   f"{float(r['spread']):+.1f} (line {n})" for n, r in items)})
            continue
        first = dict(items[0][1], line_id=line_id(items[0][1]))
        out.valid[gid] = first
        for n, _ in items[1:]:
            out.issues.append({"kind": DUPLICATE_IDENTICAL, "game_id": gid, "line": n,
                               "message": f"same spread as line {items[0][0]}; first row kept"})
    return out


def format_issue(i: dict) -> str:
    return f"{i['kind']}: {i['game_id'] or '(no game_id)'} (file line {i['line']}): {i['message']}"


def load(sched=None) -> list[dict]:
    """Usable league lines only, one row per game. Rejected rows are reported on stderr and skipped, so one
    bad transcription cannot stop the other games (use load_checked for the full report)."""
    ls = load_checked(sched)
    for i in ls.problems():
        print("LEAGUE LINE PROBLEM, row skipped:", format_issue(i), file=sys.stderr)
    return list(ls.valid.values())


def check_against_schedule(rows: list[dict], sched) -> list[str]:
    """Problems with recorded lines: unknown game_id, home/away mismatch, duplicates."""
    probs, seen = [], set()
    ids = {r["game_id"]: r for r in sched.select("game_id", "home_team", "away_team").to_dicts()}
    for r in rows:
        g = ids.get(r["game_id"])
        if g is None:
            probs.append(f"{r['game_id']}: not a regular-season game in the schedule")
        elif (g["home_team"], g["away_team"]) != (r["home_team"], r["away_team"]):
            probs.append(f"{r['game_id']}: home/away {r['home_team']}/{r['away_team']} != schedule")
        if r["game_id"] in seen:
            probs.append(f"{r['game_id']}: duplicate row")
        seen.add(r["game_id"])
    return probs


def missing_games(rows: list[dict], sched, season: int, week: int) -> list[str]:
    import polars as pl
    have = {r["game_id"] for r in rows}
    wk = sched.filter((pl.col("season") == season) & (pl.col("week") == week))["game_id"].to_list()
    return [g for g in wk if g not in have]
