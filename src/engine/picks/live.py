"""Live grading of final predictions against the recorded league line (Phase 7 live plan).
No filtering; no skill claim before 256 graded games (docs/phase7_preregistration.md)."""
from __future__ import annotations

import datetime as dt
import math

import polars as pl

from engine import config
from engine.data import league_lines, store
from engine.picks import final
from engine.picks.grading import Result, grade_league

MIN_GAMES_FOR_CLAIM = 256


def grade(sched: pl.DataFrame) -> dict:
    """Grade every final prediction and rewrite data/predictions/live_record.md. Returns the summary."""
    summary, rows = compute(sched)
    _write(rows, summary)
    return summary


def compute(sched: pl.DataFrame) -> tuple[dict, list[dict]]:
    """The graded summary and one row per graded game, with no file written (the dashboard reads this)."""
    preds = store.read_rows(final.predictions_path())
    ll = {r["game_id"]: float(r["spread"]) for r in league_lines.load()}
    scores = {r["game_id"]: r for r in sched.filter(pl.col("result").is_not_null()).select(
        "game_id", "home_score", "away_score").to_dicts()}
    rows, pending, no_line = [], 0, 0
    for p in preds:
        if p.get("supersedes"):
            continue
        g = scores.get(p["game_id"])
        line = ll.get(p["game_id"])
        if g is None:
            pending += 1
            continue
        if line is None:
            no_line += 1
            continue
        res = grade_league(g["home_score"], g["away_score"], line)
        won = (p["pick"] == "home") == (res is Result.HOME_COVER)
        sh = p.get("shadow_pick_keynum") or ""
        home = p["home_team"]
        sh_won = None if not sh else ((sh == home) == (res is Result.HOME_COVER))
        rows.append({"season": p["season"], "week": p["week"], "game_id": p["game_id"], "pick": p["pick_team"],
                     "shadow_pick": sh, "shadow_result": "" if sh_won is None else ("W" if sh_won else "L"),
                     "league_line": line, "score": f"{g['away_score']}-{g['home_score']}",
                     "result": "W" if won else "L", "late": "LATE_AFTER_LOCK" in (p["flags"] or "")})
    w = sum(r["result"] == "W" for r in rows); n = len(rows)
    rate = w / n if n else float("nan")
    se = math.sqrt(rate * (1 - rate) / n) if n else float("nan")
    summary = {"W": w, "L": n - w, "N": n, "win_rate": rate, "se": se, "pending": pending,
               "ungradable_no_league_line": no_line,
               "late_picks": sum(r["late"] for r in rows),
               "claim_allowed": n >= MIN_GAMES_FOR_CLAIM}
    dis = [r for r in rows if r["shadow_pick"] and r["shadow_pick"] != r["pick"]]
    summary["shadow_keynum"] = {"W": sum(r["shadow_result"] == "W" for r in rows if r["shadow_result"]),
                                "L": sum(r["shadow_result"] == "L" for r in rows if r["shadow_result"]),
                                "disagreements": len(dis),
                                "keynum_wins_in_disagreements": sum(r["shadow_result"] == "W" for r in dis)}
    # Projection models, graded per version. For proj-players-v3, rows whose game-status injury report was not
    # published at the run (INJ_STATUS_MISSING) are excluded from its score and counted separately (fixed in
    # docs/players_v3_report.md before any 2026 v3 result existed).
    projs: dict = {}
    for r in store.read_rows(final.projections_path()):
        projs.setdefault(r.get("model_version") or "proj-poisson-v1", {})[r["game_id"]] = r
    summary["projection_models"] = {}
    for version, by_game in sorted(projs.items()):
        w_ = l_ = flagged = 0
        for r in rows:
            pj = by_game.get(r["game_id"])
            if not pj or not pj.get("proj_pick"):
                continue
            if "INJ_STATUS_MISSING" in (pj.get("inputs") or ""):
                flagged += 1
                continue
            g = scores[r["game_id"]]
            res = grade_league(g["home_score"], g["away_score"], r["league_line"])
            won = (pj["proj_pick"] == pj["home_team"]) == (res is Result.HOME_COVER)
            w_ += won; l_ += (not won)
            r[f"proj_{version}"] = f"{pj['proj_pick']} {'W' if won else 'L'}"
        summary["projection_models"][version] = {"W": w_, "L": l_, "excluded_inj_status_missing": flagged}
    summary["projection_model"] = summary["projection_models"].get("proj-poisson-v1", {"W": 0, "L": 0})
    return summary, rows


def _write(rows, s):
    L = ["# Live record vs the league line\n",
         f"Updated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `python -m engine grade`. "
         "Every final prediction is graded; nothing is filtered.\n",
         f"**{s['W']}-{s['L']}** ({s['N']} graded)" + (f", win rate {s['win_rate']:.3f} ± {s['se']:.3f} (SE)" if s["N"] else "")
         + f". Pending: {s['pending']}. Ungradable (no league line recorded): {s['ungradable_no_league_line']}. "
           f"Late picks included: {s['late_picks']}.\n",
         ("No skill claim is made: fewer than 256 graded games (pre-registered)." if not s["claim_allowed"]
          else "256+ games graded: the record can be compared with 50% and the 51.37% bar."),
         f"\nShadow key-number estimator (recorded, not used to pick): {s['shadow_keynum']['W']}-"
         f"{s['shadow_keynum']['L']}; it disagreed with the live pick {s['shadow_keynum']['disagreements']} times "
         f"and won {s['shadow_keynum']['keynum_wins_in_disagreements']} of those.",
         "\nScore-projection models (tracked comparisons, not used to pick): " + ("; ".join(
             f"{v} {x['W']}-{x['L']}" + (f" ({x['excluded_inj_status_missing']} excluded: injury statuses not yet published)"
                                         if x.get("excluded_inj_status_missing") else "")
             for v, x in s.get("projection_models", {}).items()) or "none graded yet") + ".",
         "\n| Season | Week | Game | Pick | League line (home) | Score (away-home) | Result | Shadow pick |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['season']} | {r['week']} | {r['game_id']} | {r['pick']} | {r['league_line']:+.1f} | {r['score']} | "
          f"{r['result']}{' (late)' if r['late'] else ''} | {r['shadow_pick']} {r['shadow_result']} |" for r in rows]
    (config.path("predictions") / "live_record.md").write_text("\n".join(L) + "\n")
