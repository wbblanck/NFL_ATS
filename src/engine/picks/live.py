"""Live grading of final predictions against the recorded league line (Phase 7 live plan).
No filtering; no skill claim before 256 graded games (docs/phase7_preregistration.md)."""
from __future__ import annotations

import datetime as dt
import math
import sys

import polars as pl

from engine import config
from engine.data import league_lines, store
from engine.picks import final
from engine.picks.grading import Result, grade_league, is_half_point

MIN_GAMES_FOR_CLAIM = 256


def grade(sched: pl.DataFrame) -> dict:
    """Grade every final prediction and rewrite data/predictions/live_record.md. Returns the summary."""
    summary, rows = compute(sched)
    _write(rows, summary)
    return summary


def unique_predictions(preds: list[dict]) -> tuple[list[dict], list[dict]]:
    """One official prediction per game_id: the earliest created_at (file order breaks ties) is kept.
    Returns (kept, duplicates); a duplicate row is reported and never graded, so it cannot inflate W-L or the
    256-game count. Rows with `supersedes` set stay excluded, as everywhere else."""
    kept: dict[str, dict] = {}
    dups: list[dict] = []
    for p in sorted((p for p in preds if not p.get("supersedes")), key=lambda p: p.get("created_at") or ""):
        if p["game_id"] in kept:
            dups.append({"game_id": p["game_id"], "kept": kept[p["game_id"]]["prediction_id"],
                         "ignored": p["prediction_id"]})
        else:
            kept[p["game_id"]] = p
    return list(kept.values()), dups


def resolve_line(p: dict, lines) -> tuple[float | None, str, dict | None]:
    """The pool line to grade one prediction against, and where it came from.

    'frozen': the line stored in the prediction when it was made. Never replaced by a later edit of
    league_lines.csv; if the file now shows a different valid line, that is returned as a mismatch for the
    report, not used to grade.
    'file_after_pick': the prediction had no pool line (it was picked without one), so the line recorded
    afterwards is used, since that is what the pool graded.
    Returns (line, source, mismatch) with line None when the game cannot be graded (source says why)."""
    raw = (p.get("league_line") or "").strip()
    cur = lines.valid.get(p["game_id"])
    if raw:
        frozen = float(raw)
        if not is_half_point(frozen):
            return None, "frozen_line_invalid", None
        mm = None
        if cur is not None and float(cur["spread"]) != frozen:
            mm = {"game_id": p["game_id"], "frozen": frozen, "file": float(cur["spread"]), "file_line_id": cur["line_id"]}
        elif cur is None and lines.status(p["game_id"]) == league_lines.CONFLICTING:
            mm = {"game_id": p["game_id"], "frozen": frozen, "file": None, "file_line_id": "CONFLICT"}
        return frozen, "frozen", mm
    if cur is not None:
        return float(cur["spread"]), "file_after_pick", None
    return None, {league_lines.INVALID: "invalid_line", league_lines.CONFLICTING: "conflicting_lines"}.get(
        lines.status(p["game_id"]), "no_line"), None


def compute(sched: pl.DataFrame) -> tuple[dict, list[dict]]:
    """The graded summary and one row per graded game, with no file written (the dashboard reads this)."""
    all_preds = store.read_rows(final.predictions_path())
    preds, dups = unique_predictions(all_preds)
    lines = league_lines.load_checked(sched)
    problems = lines.problems()
    for i in problems:
        print("LEAGUE LINE PROBLEM, row skipped:", league_lines.format_issue(i), file=sys.stderr)
    scores = {r["game_id"]: r for r in sched.filter(pl.col("result").is_not_null()).select(
        "game_id", "home_score", "away_score").to_dicts()}
    rows, pending, no_line = [], 0, 0
    ungradable: dict[str, list[str]] = {}
    mismatches, sources = [], {"frozen": 0, "file_after_pick": 0}
    for p in preds:
        g = scores.get(p["game_id"])
        if g is None:
            pending += 1
            continue
        line, src, mm = resolve_line(p, lines)
        if mm:
            mismatches.append(mm)
        if line is None:
            no_line += 1
            ungradable.setdefault(src, []).append(p["game_id"])
            continue
        sources[src] += 1
        res = grade_league(g["home_score"], g["away_score"], line)
        won = (p["pick"] == "home") == (res is Result.HOME_COVER)
        sh = p.get("shadow_pick_keynum") or ""
        home = p["home_team"]
        sh_won = None if not sh else ((sh == home) == (res is Result.HOME_COVER))
        rows.append({"season": p["season"], "week": p["week"], "game_id": p["game_id"], "pick": p["pick_team"],
                     "shadow_pick": sh, "shadow_result": "" if sh_won is None else ("W" if sh_won else "L"),
                     "league_line": line, "line_source": src, "score": f"{g['away_score']}-{g['home_score']}",
                     "result": "W" if won else "L", "late": "LATE_AFTER_LOCK" in (p["flags"] or ""),
                     "no_market": "NO_MARKET" in (p["flags"] or "").split(";")})
    w = sum(r["result"] == "W" for r in rows); n = len(rows)
    rate = w / n if n else float("nan")
    se = math.sqrt(rate * (1 - rate) / n) if n else float("nan")
    summary = {"W": w, "L": n - w, "N": n, "win_rate": rate, "se": se, "pending": pending,
               "ungradable_no_league_line": no_line,
               "ungradable_by_reason": ungradable,
               "duplicate_predictions": dups,
               "line_reconciliation": {"graded_on_frozen_line": sources["frozen"],
                                       "graded_on_line_recorded_after_pick": sources["file_after_pick"],
                                       "frozen_vs_file_mismatches": mismatches},
               "league_line_problems": [league_lines.format_issue(i) for i in problems],
               "late_picks": sum(r["late"] for r in rows),
               "claim_allowed": n >= MIN_GAMES_FOR_CLAIM}
    # Picks made with no market line at all are blind "always away" fallbacks (rule missing_input_fallback_away); the
    # headline record includes them, so the split is reported next to it (audit 2026-11-09, finding M1).
    nm = [r for r in rows if r["no_market"]]
    mk = [r for r in rows if not r["no_market"]]
    summary["by_market"] = {"no_market": {"W": sum(r["result"] == "W" for r in nm), "N": len(nm)},
                            "with_market": {"W": sum(r["result"] == "W" for r in mk), "N": len(mk)}}
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
    # Hybrid (tracked, docs/hybrid_tracking.md): live pick on 1+ pt moves, v1's pick otherwise.
    from engine.picks import hybrid
    by_pred = {p["game_id"]: p for p in preds}
    v1 = projs.get("proj-poisson-v1", {})
    hw = hl = h_only = l_only = 0
    for r in rows:
        p = by_pred[r["game_id"]]
        team, src = hybrid.pick(p["pick_team"], p.get("drift"), (v1.get(r["game_id"]) or {}).get("proj_pick"))
        g = scores[r["game_id"]]
        res = grade_league(g["home_score"], g["away_score"], r["league_line"])
        won = (team == p["home_team"]) == (res is Result.HOME_COVER)
        hw += won; hl += (not won)
        if team != r["pick"]:
            h_only += won; l_only += (not won)
        r["hybrid"] = f"{team} {'W' if won else 'L'}"
        r["hybrid_source"] = src
    summary["hybrid"] = {"W": hw, "L": hl, "differ": h_only + l_only, "hybrid_only": h_only, "live_only": l_only}
    return summary, rows


def _integrity_note(s: dict) -> str:
    rec, dups, probs = s["line_reconciliation"], s["duplicate_predictions"], s["league_line_problems"]
    out = [f"\nGrading integrity: each game is graded once. {rec['graded_on_frozen_line']} graded on the pool line stored in "
           f"its prediction at pick time; {rec['graded_on_line_recorded_after_pick']} had no pool line at pick time and use "
           "the line recorded afterwards."]
    if rec["frozen_vs_file_mismatches"]:
        out.append("**LINE MISMATCH** (graded on the frozen line; league_lines.csv now differs): " + "; ".join(
            f"{m['game_id']} frozen {m['frozen']:+.1f}, file {m['file'] if m['file'] is None else format(m['file'], '+.1f')}"
            for m in rec["frozen_vs_file_mismatches"]) + ".")
    if dups:
        out.append("**DUPLICATE PREDICTIONS** (first row graded, the rest ignored): " + "; ".join(
            f"{d['game_id']}" for d in dups) + ".")
    if s["ungradable_by_reason"]:
        out.append("Ungradable by reason: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in s["ungradable_by_reason"].items()) + ".")
    if probs:
        out.append("**LEAGUE LINE PROBLEMS** (rows skipped): " + " | ".join(probs))
    return "\n".join(out)


def _market_split(s) -> str:
    bm = s.get("by_market") or {}
    nm, mk = bm.get("no_market"), bm.get("with_market")
    if not nm or not nm["N"]:
        return ""
    return (f"\nOf these, {nm['N']} were picked with no market line (blind fallback to the away team, flag NO_MARKET): "
            f"{nm['W']}-{nm['N'] - nm['W']}. The {mk['N']} picks made with a market line: {mk['W']}-{mk['N'] - mk['W']}.")


def _write(rows, s):
    L = ["# Live record vs the league line\n",
         f"Updated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `python -m engine grade`. "
         "Every final prediction is graded; nothing is filtered.\n",
         f"**{s['W']}-{s['L']}** ({s['N']} graded)" + (f", win rate {s['win_rate']:.3f} ± {s['se']:.3f} (SE)" if s["N"] else "")
         + f". Pending: {s['pending']}. Ungradable (no league line recorded): {s['ungradable_no_league_line']}. "
           f"Late picks included: {s['late_picks']}.\n",
         ("No skill claim is made: fewer than 256 graded games (pre-registered)." if not s["claim_allowed"]
          else "256+ games graded: the record can be compared with 50% and the 51.37% bar."),
         _market_split(s),
         f"\nShadow key-number estimator (recorded, not used to pick): {s['shadow_keynum']['W']}-"
         f"{s['shadow_keynum']['L']}; it disagreed with the live pick {s['shadow_keynum']['disagreements']} times "
         f"and won {s['shadow_keynum']['keynum_wins_in_disagreements']} of those.",
         "\nScore-projection models (tracked comparisons, not used to pick): " + ("; ".join(
             f"{v} {x['W']}-{x['L']}" + (f" ({x['excluded_inj_status_missing']} excluded: injury statuses not yet published)"
                                         if x.get("excluded_inj_status_missing") else "")
             for v, x in s.get("projection_models", {}).items()) or "none graded yet") + ".",
         (f"\nHybrid (tracked, docs/hybrid_tracking.md): {s['hybrid']['W']}-{s['hybrid']['L']}; it picked "
          f"differently from the live pick {s['hybrid']['differ']} times: hybrid right {s['hybrid']['hybrid_only']}, "
          f"live right {s['hybrid']['live_only']}.") if s.get("hybrid") else "",
         _integrity_note(s),
         "\n| Season | Week | Game | Pick | League line (home) | Score (away-home) | Result | Shadow pick |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['season']} | {r['week']} | {r['game_id']} | {r['pick']} | {r['league_line']:+.1f} | {r['score']} | "
          f"{r['result']}{' (late)' if r['late'] else ''} | {r['shadow_pick']} {r['shadow_result']} |" for r in rows]
    (config.path("predictions") / "live_record.md").write_text("\n".join(L) + "\n")
