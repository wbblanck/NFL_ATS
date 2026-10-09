"""CLI.  python -m engine <command>

  capture-cbs        fetch CBS odds pages, archive opening lines (append-only)
  freeze-cbs         derive frozen openers (first valid capture per game)
  capture-market     archive current market spreads for games near lock
  capture-market-historical --at ISO [--at ISO ...]
                     archive past snapshots (provider keeps 48 h) as 'hist-' captures
  check-league-lines [--season S --week W]
                     validate data/lines/league_lines.csv (half-points, schedule
                     match) and list games of that week still missing a line
  cbs-lines          CBS pool line-setting analysis -> docs/cbs_lines_report.md
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
    mh = sub.add_parser("capture-market-historical")
    mh.add_argument("--at", action="append", required=True, help="ISO UTC snapshot time (repeatable; last 48 h only)")
    sub.add_parser("cbs-lines")
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
    db.add_argument("--week", type=int, default=None, help="default: the earliest week with an unfinished game")
    db.add_argument("--out", default=None)
    db.add_argument("--log-provisional", action="store_true",
                    help="append changed provisional picks to data/predictions/provisional_log.csv (the published build)")
    al = sub.add_parser("alert", help="print phone-alert lines for locked picks (see docs/scheduling.md)")
    al.add_argument("--since", default=None, help="ISO time; only picks created after it (default: last 30 min)")
    al.add_argument("--local", action="store_true", help="read predictions.csv from the working tree, not origin/main")
    al.add_argument("--send", action="store_true", help="post the alert to ntfy (topic in env NTFY_TOPIC)")
    al.add_argument("--watch", action="store_true", help="poll origin/main and print an ALERT line per new pick group")
    al.add_argument("--window-minutes", type=int, default=240, help="with --watch: games locking within this window")
    al.add_argument("--timeout-minutes", type=int, default=240)
    al.add_argument("--poll-seconds", type=int, default=30)
    lr = sub.add_parser("lock-run")
    lr.add_argument("--window-minutes", type=int, default=25)
    lr.add_argument("--wait", action="store_true",
                    help="wait for the next lock group in the window and pick it LEAD minutes before its lock")
    lr.add_argument("--lead-minutes", type=int, default=5)
    c = sub.add_parser("check-league-lines")
    c.add_argument("--season", type=int)
    c.add_argument("--week", type=int)
    sub.add_parser("bettable", help="bettable record of each model against the closing line (docs/bettable_preregistration.md)")
    sub.add_parser("strong-calls", help="tiers by market-move size, out of sample (docs/strong_calls_preregistration.md)")
    v3h = sub.add_parser("v3-history", help="per-game v3 picks for 2022-2025 (docs/v3_history_preregistration.md)")
    v3h.add_argument("--cache", default=None)
    pv3 = sub.add_parser("players-v3")
    pv3.add_argument("--cache", default=None)
    pe = sub.add_parser("efficiency-residual")
    pe.add_argument("--cache", required=True)
    pv6 = sub.add_parser("projection-v6")
    pv6.add_argument("--cache", required=True)
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
    if a.cmd == "efficiency-residual":
        import json
        import polars as pl
        from pathlib import Path
        from engine import config
        from engine.backtest import efficiency_residual as ER
        from engine.backtest import projection_v6_eval as E6
        metrics, _ = E6.load_metrics(a.cache)
        out = ER.run(metrics)
        (config.ROOT / "data" / "backtests" / "phase8_efficiency.json").write_text(json.dumps(out, indent=1, default=str))
        print("kept", out["kept"], "confirmed_2025", out["confirmed_2025"])
        return 0
    if a.cmd == "projection-v6":
        import json
        from engine import config
        from engine.backtest import projection_v6_eval as E6
        out = E6.run(a.cache)
        (config.ROOT / "data" / "backtests" / "projection_v6.json").write_text(json.dumps(out, indent=1, default=str))
        print("validation pass", out["validation"]["pass"], "decision", out.get("test", {}).get("decision"))
        return 0
    if a.cmd == "bettable":
        from engine.backtest import bettable
        bettable.main()
        return 0
    if a.cmd == "strong-calls":
        from engine.backtest import strong_calls
        strong_calls.main()
        return 0
    if a.cmd == "v3-history":
        from engine.backtest import v3_history
        return v3_history.main(a.cache)
    if a.cmd == "players-v3":
        import json
        from engine import config
        from engine.backtest import players_v3_eval as E
        ctx = E.prepare(a.cache)
        tu = E.tune(ctx)
        va = E.validate(ctx, tu["D"], tu["k"])
        if not va["pass"]:
            print("validation failed; test seasons not scored"); print(json.dumps(va, indent=1, default=str))
            return 1
        te, _ = E.test(ctx, tu["D"], tu["k"])
        se = E.sensitivity_weekly_depth(ctx, tu["D"], tu["k"])
        E.write_results(tu, va, te, se, config.ROOT / "docs" / "players_v3_results.md")
        out = config.ROOT / "data" / "backtests" / "players_v3.json"
        out.write_text(json.dumps({"tuning": tu, "validation": va, "test": te, "sensitivity": se}, indent=1, default=str))
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
    if a.cmd == "alert":
        import datetime as _dt
        import time as _time
        from engine.picks import alerts
        now = _dt.datetime.now(_dt.timezone.utc)
        since = a.since or (now - _dt.timedelta(minutes=30)).isoformat()
        if not a.watch:
            rows = alerts.new_rows(alerts.local_predictions() if a.local else alerts.origin_predictions(), since)
            full = alerts.full_message(rows, alerts.local_projections() if a.local else None)
            for text in (full, alerts.warning_message(rows)):
                if text:
                    print(text)
                    if a.send:
                        print("ntfy: " + ("sent" if alerts.send(text) else "not sent"))
            return 0
        preds = alerts.origin_predictions()
        done = {p["game_id"] for p in preds if not p.get("supersedes")}
        due = alerts.due_games(sched, now, a.window_minutes, done)
        print(f"WATCHING {len(due)} game(s): " + ", ".join(f"{g['away_team']}@{g['home_team']}" for g in due), flush=True)
        warned: set[str] = set()
        deadline = _time.time() + a.timeout_minutes * 60
        while due and _time.time() < deadline:
            lines, since, finished = alerts.watch_step(preds, since, due, warned, _dt.datetime.now(_dt.timezone.utc))
            for ln in lines:
                print("ALERT " + ln, flush=True)
            if finished:
                print("DONE all picks locked", flush=True)
                return 0
            _time.sleep(a.poll_seconds)
            preds = alerts.origin_predictions()
        print("DONE " + ("nothing to watch" if not due else "timed out"), flush=True)
        return 0
    if a.cmd in ("lock-run", "run"):
        from engine.models import players_v3_live as _v3_live
        from engine.picks import final
        run_window = getattr(a, "window_minutes", 25)
        if a.cmd == "lock-run" and a.wait:
            import datetime as _dt
            import time as _time
            _now = lambda: _dt.datetime.now(_dt.timezone.utc)
            _end = _now() + _dt.timedelta(minutes=a.window_minutes)
            lock, n = final.next_lock(sched, _now(), a.window_minutes, final.existing_game_ids())
            if lock is None:
                print("REMAINING 0")
                return 0
            target = lock - _dt.timedelta(minutes=a.lead_minutes)
            wait_s = (target - _dt.timedelta(minutes=3) - _now()).total_seconds()
            print(f"next lock {lock.isoformat()} ({n} game(s) due in window); picking at {target.isoformat()}", flush=True)
            if wait_s > 0:
                _time.sleep(wait_s)
            run_window = a.lead_minutes + 1     # only the lock group that is now due
        if a.cmd == "run" and a.game in final.existing_game_ids():
            print(f"{a.game}: final prediction already exists (immutable); see data/predictions/")
            return 0
        _all = None
        try:
            import nflreadpy as _nfl
            from engine.models import projection as _P
            _all, _ = nflverse.pull("schedules", save=False)
            proj_games = _P.team_games(_nfl.load_team_stats(seasons=list(range(1999, 2027))), _all)
        except Exception as e:
            print("projection comparison unavailable:", e, file=sys.stderr)
            proj_games = None

        if a.cmd == "lock-run" and a.wait:
            rest = (target - _now()).total_seconds()
            if rest > 0:
                _time.sleep(rest)
        out = final.run(sched, window_minutes=run_window, snapshot_id=sid,
                        game_id=getattr(a, "game", None), proj_games=proj_games,
                        v3=_v3_live.loader(sched, _all))
        for r in out:
            print(f"{r['away_team']}@{r['home_team']} lock {r['lock_utc']} ({r['minutes_to_lock']} min): "
                  f"line {r['league_line']} market {r['market_at_lock']} drift {r['drift']} -> "
                  f"{r['pick_team']} [{r['data_status']} {r['flags']}]")
        print(f"{len(out)} final predictions written")
        if a.cmd == "lock-run" and a.wait:
            left_min = max((_end - _now()).total_seconds() / 60, 0)
            _, left = final.next_lock(sched, _now(), left_min, final.existing_game_ids())
            print(f"REMAINING {left}")
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
        from engine.models import players_v3_live as _v3_live
        _nm = {}
        try:
            import nflreadpy as _nfl
            _pp = _nfl.load_players().select("gsis_id", "display_name").drop_nulls()
            _nm = dict(zip(_pp["gsis_id"].to_list(), _pp["display_name"].to_list()))
        except Exception:
            pass
        if a.week is None:
            a.week = dashboard.current_week(sched, a.season)
        rows = preview.build(sched, a.season, a.week, proj_games=_pg, names=_nm,
                             v3=_v3_live.loader(sched, _all if _pg is not None else None))
        try:
            lv, graded = live.compute(sched)         # read-only: does not rewrite live_record.md
            lv["claim_at"] = live.MIN_GAMES_FOR_CLAIM
            results = {r["game_id"]: r for r in graded}
            from engine.picks import season as _season
            season_tab = _season.build(graded, a.season)
        except Exception:
            lv, results, season_tab, graded = {"N": 0, "W": 0, "L": 0}, {}, [], []
        try:
            import polars as _pl
            from engine.picks import game_detail
            details = game_detail.build_from_files(
                rows, sched.filter((_pl.col("season") == a.season) & (_pl.col("week") == a.week)), _nm)
        except Exception as e:
            print("game detail unavailable:", repr(e), file=sys.stderr)
            details = {}
        try:
            import nflreadpy as _nfl
            _pbp = _nfl.load_pbp(seasons=[a.season])
        except Exception as e:
            print("play-by-play unavailable:", repr(e), file=sys.stderr)
            _pbp = None
        try:
            from engine.features import epa_components as _epa
            epa_tab = _epa.compute(_pbp, a.week) if _pbp is not None else {}
        except Exception as e:
            print("team EPA unavailable:", repr(e), file=sys.stderr)
            epa_tab = {}
        _paths = {}
        try:
            from engine.picks import loss_review as _lr
            _paths = _lr.game_paths(_pbp) if _pbp is not None else {}
        except Exception as e:
            print("game paths unavailable:", repr(e), file=sys.stderr)
        try:
            from engine.data import store as _store
            from engine.picks import final as _final, loss_review as _lr
            lr_data = _lr.build(graded, _store.read_rows(_final.predictions_path()), sched, _paths)
        except Exception as e:
            print("loss review unavailable:", repr(e), file=sys.stderr)
            lr_data = {}
        try:
            from engine.picks import slate_replay as _sr
            slate_data = _sr.build(graded, sched, _paths, a.season)
        except Exception as e:
            print("slate replay unavailable:", repr(e), file=sys.stderr)
            slate_data = {}
        try:
            from engine.data import store as _st2
            from engine.picks import bettable as _bt, final as _fin2
            bet_data = {"live": _bt.live(graded, _st2.read_rows(_fin2.predictions_path()), sched), "backtest": _bt.backtest()}
        except Exception as e:
            print("bettable record unavailable:", repr(e), file=sys.stderr)
            bet_data = {}
        try:
            from engine.picks import strength as _st
            strength_tbl = _st.table()
        except Exception as e:
            print("strength tiers unavailable:", repr(e), file=sys.stderr)
            strength_tbl = {}
        try:
            from engine.picks import provisional as _pv
            flips_data = _pv.flips(rows, _pv.load())
            if a.log_provisional:
                print("provisional log: +", _pv.record(rows, _dt.datetime.now(_dt.timezone.utc)), "rows", file=sys.stderr)
        except Exception as e:
            print("provisional log unavailable:", repr(e), file=sys.stderr)
            flips_data = {}
        try:
            from engine.picks import curve as _curve
            curve_data = _curve.build(sched, a.season, graded)
        except Exception as e:
            print("season curve unavailable:", repr(e), file=sys.stderr)
            curve_data = {}
        try:
            from engine.picks import tiebreak_total as _tb
            tb_rows = _tb.build(sched, a.season)
        except Exception as e:
            print("tiebreaker unavailable:", repr(e), file=sys.stderr)
            tb_rows = []
        out = a.out or str(config.path("predictions") / f"dashboard_{a.season}_w{a.week:02d}.html")
        open(out, "w").write(dashboard.render(rows, a.season, a.week, lv, _dt.datetime.now(_dt.timezone.utc), results,
                                              details, season_tab, market.credits_left(), epa_tab, curve_data, tb_rows,
                                              lr_data, flips_data, slate_data, bet_data, strength_tbl))
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
    if a.cmd == "cbs-lines":
        from engine import config
        from engine.backtest import cbs_lines
        r = cbs_lines.run(sched, config.ROOT / "docs" / "cbs_lines_report.md")
        print(f"{r['games_with_league_lines']} games with pool lines; weeks: {list(r['weeks'])}")
        return 0
    if a.cmd == "capture-market-historical":
        n = 0
        for when in a.at:
            try:
                rows = market.capture_historical(sched, when)
                n += len(rows)
                print(f"{when}: {len(rows)} rows")
            except Exception as e:                      # one bad snapshot must not stop the others
                print(f"{when}: failed {e!r}", file=sys.stderr)
        return 0 if n else 1
    if a.cmd == "capture-market":
        left = market.credits_left()
        if left is not None and left < market.CAPTURE_FLOOR:
            print(f"SKIPPED: {left} API credits left (floor {market.CAPTURE_FLOOR}); optional captures paused so "
                  "lock runs keep their budget")
            return 0
        rows = market.capture(sched, window_minutes=a.window_minutes, all_games=a.all_games)
        print(f"schedule snapshot {sid}; market rows={len(rows)} by status:",
              dict(collections.Counter(r.get("status") for r in rows)))
        return 1 if any(r.get("status") == "fetch_error" for r in rows) else 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
