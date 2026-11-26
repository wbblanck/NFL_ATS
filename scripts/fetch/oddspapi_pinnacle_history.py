"""One-off: how much timestamped Pinnacle NFL spread history does OddsPapi hold for 2026?

Research only (audit B block M: Pinnacle open-to-lock move). Touches no capture job and no pick.
For every finished 2026 NFL fixture: /fixtures (team names; about 1 request per 7 days, metered) and
/historical-odds with Pinnacle only (free, 5.5 s apart). Per game it records the main full-game home
spread at a few offsets before kickoff plus the first snapshot time, to
data/lines/oddspapi_pinnacle_history.csv, and a summary to docs/evidence/pinnacle_history/summary.md.
Refuses to run if fewer than MIN_LEFT of the month's requests remain (the key is shared with kmodel).
Never prints the key. Run from GitHub Actions only (the sandbox cannot reach the API).
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

from engine.data import oddspapi as op

ROOT = Path(__file__).resolve().parents[2]
CSV_OUT = ROOT / "data" / "lines" / "oddspapi_pinnacle_history.csv"
SUMMARY = ROOT / "docs" / "evidence" / "pinnacle_history" / "summary.md"
SMAP = ROOT / "data" / "lines" / op.SPREAD_MARKETS_FILE
SEASON_START = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
MIN_LEFT = 80
# hours before kickoff; 0.25 h = the lock (kickoff minus 15 min)
OFFSETS = {"h168": 168.0, "h48": 48.0, "h24": 24.0, "h6": 6.0, "lock": 0.25}
FIELDS = ["fixture_id", "home_team", "away_team", "kickoff_utc", "first_seen_utc", "span_h",
          *[f"{k}_spread" for k in OFFSETS], "open_spread", "n_lines_lock"]


def game_row(fixture: dict, home: str, away: str, hist: dict, smap: dict) -> dict:
    """One CSV row from one fixture's Pinnacle history. `open_spread` = main spread one hour after
    the first snapshot (a guess at 'line established'); offsets with no active two-sided line are blank."""
    ko = op.parse_ts(fixture.get("startTime"))
    book = ((hist or {}).get("bookmakers") or {}).get("pinnacle") or {}
    row = {"fixture_id": fixture.get("fixtureId"), "home_team": home, "away_team": away,
           "kickoff_utc": ko.isoformat() if ko else ""}
    first = None
    for k, h in OFFSETS.items():
        r = op.main_spread_at(book, smap, ko - dt.timedelta(hours=h)) if ko else None
        row[f"{k}_spread"] = r["home_spread"] if r else ""
        if r and r.get("first_seen"):
            first = r["first_seen"]
        if k == "lock":
            row["n_lines_lock"] = r["n_lines"] if r else ""
    if first is None and ko:       # no offset had a line: still find first_seen with the latest time
        r = op.main_spread_at(book, smap, ko)
        first = r["first_seen"] if r else None
    row["first_seen_utc"] = first or ""
    f_ts = op.parse_ts(first) if first else None
    row["span_h"] = round((ko - f_ts).total_seconds() / 3600, 1) if (f_ts and ko) else ""
    o = op.main_spread_at(book, smap, f_ts + dt.timedelta(hours=1)) if f_ts else None
    row["open_spread"] = o["home_spread"] if o else ""
    return row


def main() -> int:
    from engine.teams import UnknownTeam, to_canonical
    try:
        before = op.request_count()
    except op.MissingKey:
        print("ODDSPAPI_API_KEY is not set: the workflow passes it from the repository secret ODDS_PAPI.")
        return 1
    used, limit = before
    log = [f"# OddsPapi Pinnacle NFL history, run {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%MZ}",
           "", f"requests before: {used} of {limit}"]
    if used is None or limit is None or limit - used < MIN_LEFT:
        log.append(f"stopped: fewer than {MIN_LEFT} requests left (or counts unavailable)")
        _write(log, [])
        return 0
    smap = op.load_spread_markets(SMAP)
    now = dt.datetime.now(dt.timezone.utc)
    fixtures, t = {}, SEASON_START
    while t < now:
        hi = min(t + dt.timedelta(days=7), now)
        s, fx = op.call("fixtures", tournamentId=op.NFL_TOURNAMENT,
                        **{"from": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": hi.strftime("%Y-%m-%dT%H:%M:%SZ")})
        for f in op.items_of(fx):
            fixtures[f.get("fixtureId")] = f
        t = hi
    done = [f for f in fixtures.values()
            if (op.parse_ts(f.get("startTime")) or now) < now - dt.timedelta(hours=4)]
    log.append(f"fixtures found: {len(fixtures)}; finished: {len(done)}")
    rows, nohist, nonames = [], 0, 0
    for f in sorted(done, key=lambda f: f.get("startTime") or ""):
        try:
            home, away = (to_canonical(f.get("participant1Name") or ""), to_canonical(f.get("participant2Name") or ""))
        except UnknownTeam:
            nonames += 1
            continue
        s, hist = op.call("historical-odds", pause=5.5, fixtureId=f.get("fixtureId"), bookmakers="pinnacle")
        if not hist:
            nohist += 1
            continue
        rows.append(game_row(f, home, away, hist, smap))
    log.append(f"games with a history response: {len(rows)}; no response: {nohist}; unmapped team names: {nonames}")
    after = op.request_count()
    log.append(f"requests after: {after[0]} of {after[1]}")
    _write(log, rows)
    return 0


def _write(log: list[str], rows: list[dict]) -> None:
    if rows:
        CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(CSV_OUT, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        spans = [r["span_h"] for r in rows if r["span_h"] != ""]
        has = lambda k: sum(1 for r in rows if r[f"{k}_spread"] != "")
        log += ["", f"games {len(rows)}; with a first snapshot {len(spans)}; "
                + "; ".join(f"{k} line {has(k)}" for k in OFFSETS),
                f"span at least 24 h: {sum(1 for x in spans if x >= 24)}; at least 72 h: {sum(1 for x in spans if x >= 72)}"]
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    sys.exit(main())
