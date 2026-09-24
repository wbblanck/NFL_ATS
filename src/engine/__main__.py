"""CLI.  python -m engine <command>

  capture-cbs        fetch CBS odds pages, archive opening lines (append-only)
  freeze-cbs         derive frozen openers (first valid capture per game)
  capture-market     archive current market spreads for games near lock
  run --game ID      final pick for one game (manual fallback) -- modeling not
                     built yet (Phase 0/1); exits non-zero with an explanation
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
    r = sub.add_parser("run")
    r.add_argument("--game", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "run":
        print(f"run --game {a.game}: no model exists yet. The spec gates modeling behind "
              "Phases 2-7; Phase 0/1 deliver the audit and line capture only.", file=sys.stderr)
        return 2

    from engine.data import cbs_lines, market, nflverse

    if a.cmd == "freeze-cbs":
        out = cbs_lines.freeze()
        print(f"frozen openers: {len(out)} games")
        return 0

    sched, sid = nflverse.regular_season_schedule(save=False)
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
