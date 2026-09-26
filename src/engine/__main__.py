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
  coverprob          Phase 4: walk-forward cover-probability evaluation
                     -> docs/phase4_results.md, data/backtests/phase4_*.csv
  calibrate          Phase 5: chronological calibration report
                     -> docs/phase5_results.md, data/backtests/phase5_*.csv
  features           Phase 6: residual feature ablation -> docs/phase6_results.md
  backtest           Phase 7: full-system walk-forward -> docs/phase7_results.md
  grade              grade final predictions vs league line -> data/predictions/live_record.md
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
    sub.add_parser("coverprob")
    sub.add_parser("calibrate")
    sub.add_parser("features")
    sub.add_parser("backtest")
    sub.add_parser("grade")
    sub.add_parser("holdout2025")
    pv = sub.add_parser("preview")
    pv.add_argument("--season", type=int, required=True)
    pv.add_argument("--week", type=int, required=True)
    db = sub.add_parser("dashboard")
    db.add_argument("--season", type=int, required=True)
    db.add_argument("--week", type=int, required=True)
    db.add_argument("--out", default=None)
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
    if a.cmd == "coverprob":
        from engine import config
        from engine.backtest import phase4
        r = phase4.run(config.ROOT / "docs" / "phase4_results.md")
        print(r["pooled"]); print("D0-full same games", r["d0_full_same_games"])
        print("coinflip ll", r["coinflip_ll"], "best", r["best"], "switch", r["switch_pick_rule"], r["counts"])
        return 0
    if a.cmd == "calibrate":
        from engine import config
        from engine.backtest import phase5
        r = phase5.run(config.ROOT / "docs" / "phase5_results.md")
        print(r["pooled"]); print("chosen", r["chosen"], "use calibrated pick", r["use_calibrated_pick"])
        print(r["coefs"])
        return 0
    if a.cmd == "features":
        from engine import config
        from engine.backtest import phase6
        r = phase6.run(config.ROOT / "docs" / "phase6_results.md")
        print(r["table"]); print("kept", r["kept"]); print(r["feature_means"])
        return 0
    if a.cmd == "backtest":
        from engine import config
        from engine.backtest import walk_forward
        r = walk_forward.run(config.ROOT / "docs" / "phase7_results.md")
        print(r["pooled"]); print("z vs bar", round(r["z_vs_bar"], 2), "PASS" if r["passed"] else "FAIL")
        print(r["per_season"]); print(r["subgroups"])
        return 0
    if a.cmd == "holdout2025":
        from engine import config
        from engine.backtest import holdout2025
        r = holdout2025.run(config.ROOT / "docs" / "holdout2025_results.md")
        for k, v in r.items():
            if k != "per_week":
                print(k, v)
        print(r["per_week"])
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
        try:
            import nflreadpy as _nfl
            from engine.models import projection as _P
            _all, _ = nflverse.pull("schedules", save=False)
            proj_games = _P.team_games(_nfl.load_team_stats(seasons=list(range(1999, 2027))), _all)
        except Exception as e:
            print("projection comparison unavailable:", e, file=sys.stderr)
            proj_games = None
        out = final.run(sched, window_minutes=getattr(a, "window_minutes", 25), snapshot_id=sid,
                        game_id=getattr(a, "game", None), proj_games=proj_games)
        for r in out:
            print(f"{r['away_team']}@{r['home_team']} lock {r['lock_utc']} ({r['minutes_to_lock']} min): "
                  f"line {r['league_line']} market {r['market_at_lock']} drift {r['drift']} -> "
                  f"{r['pick_team']} [{r['data_status']} {r['flags']}]")
        print(f"{len(out)} final predictions written")
        return 0
    if a.cmd == "grade":
        from engine.picks import live
        print(live.grade(sched))
        return 0
    if a.cmd == "preview":
        from engine.picks import preview
        rows = preview.build(sched, a.season, a.week)
        print(preview.write_md(rows, a.season, a.week))
        for r in rows:
            print(r["away"], "@", r["home"], r["league_line"], r["market"], r["drift"], r["p_home"], r["pick"], r["status"])
        return 0
    if a.cmd == "dashboard":
        import datetime as _dt
        from engine import config
        from engine.picks import dashboard, live, preview
        try:
            import nflreadpy as _nfl
            from engine.models import projection as _P
            _all, _ = nflverse.pull("schedules", save=False)
            _pg = _P.team_games(_nfl.load_team_stats(seasons=list(range(1999, 2027))), _all)
        except Exception:
            _pg = None
        rows = preview.build(sched, a.season, a.week, proj_games=_pg)
        try:
            lv = live.grade(sched)
        except Exception:
            lv = {"N": 0, "W": 0, "L": 0}
        out = a.out or str(config.path("predictions") / f"dashboard_{a.season}_w{a.week:02d}.html")
        open(out, "w").write(dashboard.render(rows, a.season, a.week, lv, _dt.datetime.now(_dt.timezone.utc)))
        print(out)
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
