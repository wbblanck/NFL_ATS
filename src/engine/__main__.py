"""CLI.  python -m engine <command>

  capture-cbs        fetch CBS odds pages, archive opening lines (append-only)
  freeze-cbs         derive frozen openers (first valid capture per game)
  capture-market     archive current market spreads for games near lock
  check-league-lines [--season S --week W]
                     validate data/lines/league_lines.csv (half-points, schedule
                     match) and list games of that week still missing a line
  baselines          Phase 2: always home/away/favorite/underdog vs every
                     opening-line source -> data/backtests/, docs/phase2_baselines.md
  drift              Phase 3: drift (open->close) strategies, pre-registered test
                     -> data/backtests/phase3_*.csv, docs/phase3_results.md
  lock-run [--window-minutes N]
                     final picks for games locking within N minutes (default 25):
                     capture market, drift vs league line, immutable prediction row
  run --game ID      manual fallback: final pick for one game now (flagged
                     LATE_AFTER_LOCK if run after its lock)
"""
from __future__ import annotations

import argparse
import collections
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("capture-cbs")
    sub.add_parser("freeze-cbs")
    m = sub.add_parser("capture-market")
    m.add_argument("--window-minutes", type=int, default=None)
    m.add_argument("--all-games", action="store_true")
    sub.add_parser("baselines")
    sub.add_parser("drift")
    lr = sub.add_parser("lock-run")
    lr.add_argument("--window-minutes", type=int, default=25)
    c = sub.add_parser("check-league-lines")
    c.add_argument("--season", type=int)
    c.add_argument("--week", type=int)
    r = sub.add_parser("run")
    r.add_argument("--game", required=True)
    a = ap.parse_args(argv)

    from engine.data import cbs_lines, market, nflverse

    if a.cmd == "baselines":
        from engine import config
        from engine.backtest import phase2
        res = phase2.run(config.ROOT / "docs" / "phase2_baselines.md")
        for k, t in res.items():
            print(k); print(t)
        return 0
    if a.cmd == "drift":
        from engine import config
        from engine.backtest import phase3
        r = phase3.run(config.ROOT / "docs" / "phase3_results.md")
        print("D0", r["d0"]); print("D0-full", r["d0_full"])
        print("z vs bar", round(r["z_vs_bar"], 2), "PASS" if r["passed"] else "FAIL")
        print(r["buckets"]); print(r["logit"]); print(r["key_numbers"]); print(r["walk_forward_pooled"])
        return 0
    if a.cmd == "freeze-cbs":
        out = cbs_lines.freeze()
        print(f"frozen openers: {len(out)} games")
        return 0

    sched, sid = nflverse.regular_season_schedule(save=False)
    if a.cmd in ("lock-run", "run"):
        from engine.picks import final
        if a.cmd == "run" and a.game in final.existing_game_ids():
            print(f"{a.game}: final prediction already exists (immutable); see data/predictions/")
            return 0
        out = final.run(sched, window_minutes=getattr(a, "window_minutes", 25), snapshot_id=sid,
                        game_id=getattr(a, "game", None))
        for r in out:
            print(f"{r['away_team']}@{r['home_team']} lock {r['lock_utc']} ({r['minutes_to_lock']} min): "
                  f"line {r['league_line']} market {r['market_at_lock']} drift {r['drift']} -> "
                  f"{r['pick_team']} [{r['data_status']} {r['flags']}]")
        print(f"{len(out)} final predictions written")
        return 0
    if a.cmd == "check-league-lines":
        from engine.data import league_lines
        rows = league_lines.load()
        probs = league_lines.check_against_schedule(rows, sched)
        for p in probs:
            print("PROBLEM:", p)
        if a.season and a.week:
            miss = league_lines.missing_games(rows, sched, a.season, a.week)
            print(f"{a.season} week {a.week}: {len(miss)} games missing a league line", *miss, sep="\n  ")
        print(f"{len(rows)} league lines OK" if not probs else f"{len(probs)} problems")
        return 1 if probs else 0
    if a.cmd == "capture-cbs":
        rows = cbs_lines.capture(sched)
        print(f"schedule snapshot {sid}; rows={len(rows)} by status:",
              dict(collections.Counter(r.get("status") for r in rows)))
        cbs_lines.freeze()
        bad = [r for r in rows if r.get("status") in ("fetch_error", "no_games")]
        return 1 if bad and len(bad) == len(rows) else 0
    if a.cmd == "capture-market":
        rows = market.capture(sched, window_minutes=a.window_minutes, all_games=a.all_games)
        print(f"schedule snapshot {sid}; market rows={len(rows)} by status:",
              dict(collections.Counter(r.get("status") for r in rows)))
        return 1 if any(r.get("status") == "fetch_error" for r in rows) else 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
