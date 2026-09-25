"""Final (lock-time) picks.

Triggered by an external timer (workflow_dispatch; audit 0.10 + the 2026-09-25
dispatch-latency measurement). For every regular-season game whose lock
(kickoff - lock_buffer) falls within the next `window` minutes and that has no
final prediction yet:

  1. capture the current market spread from every book (appended to market_captures.csv)
  2. market_at_lock = median home spread across books
  3. drift = market_at_lock - league line
  4. pick = side the market moved toward; drift == 0 -> away
     (D0-full, pre-registered in docs/phase3_preregistration.md)
  5. append ONE immutable row to data/predictions/predictions.csv

Missing inputs never block a pick (every game is picked); they set
data_status=incomplete with missing_input / expected_impact / flags.
Predictions are never overwritten. A game that already has a prediction is skipped.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import polars as pl

from engine import config
from engine.data import league_lines, market, store
from engine.picks.grading import is_half_point

FIELDS = [
    "prediction_id", "created_at", "season", "week", "game_id", "home_team", "away_team",
    "kickoff_utc", "lock_utc", "minutes_to_lock", "league_line", "cbs_open", "market_at_lock",
    "market_books", "drift", "model_margin", "p_home_cover", "p_away_cover", "pick", "pick_team",
    "pick_rule", "sim_count", "seed", "model_version", "feature_version", "data_snapshot",
    "training_period", "data_status", "missing_input", "expected_impact", "flags", "supersedes",
]
MODEL_VERSION = "phase3-drift-D0full"
TRAINING_PERIOD = "rule has no fitted parameters; validated on SBRO 2007-2021 (docs/phase3_report.md)"


def predictions_path():
    return config.path("predictions") / "predictions.csv"


def existing_game_ids() -> set[str]:
    return {r["game_id"] for r in store.read_rows(predictions_path())}


def _cbs_frozen() -> dict[str, float]:
    rows = store.read_rows(config.path("lines") / "cbs_open_frozen.csv")
    return {r["game_id"]: float(r["spread"]) for r in rows if r.get("spread")}


def decide(league_line: float | None, market_at_lock: float | None, cbs_open: float | None) -> dict:
    """Pure decision logic (tested). Returns pick fields + status fields."""
    missing, flags, impact = [], [], []
    line = league_line
    if line is None:
        missing.append("league_line")
        flags.append("NO_LEAGUE_LINE")
        if cbs_open is not None and is_half_point(cbs_open):
            line = cbs_open
            flags.append("LINE_FROM_CBS_ODDS_PAGE_OPEN")
            impact.append("drift measured vs CBS odds-page open, not the league line: UNKNOWN")
    if market_at_lock is None:
        missing.append("market_at_lock")
        flags.append("NO_MARKET")
    if line is not None and market_at_lock is not None:
        drift = market_at_lock - line
        pick = "home" if drift < 0 else "away"
        rule = "drift" if drift != 0 else "no_move_fallback_away"
    else:
        drift, pick, rule = None, "away", "missing_input_fallback_away"
        impact.append("pick is the Phase 2 fallback (always away, ~51% historically)")
    return {"drift": drift, "pick": pick, "pick_rule": rule, "line_used": line,
            "data_status": "incomplete" if missing else "complete",
            "missing_input": ";".join(missing), "expected_impact": "; ".join(impact),
            "flags": ";".join(flags)}


def run(sched: pl.DataFrame, now: dt.datetime | None = None, window_minutes: int = 25,
        events: list[dict] | None = None, snapshot_id: str = "", game_id: str | None = None) -> list[dict]:
    """game_id set = manual fallback for one game, regardless of window (late runs are flagged)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if game_id:
        due = sched.filter(pl.col("game_id") == game_id)
        if due.height == 0:
            raise ValueError(f"{game_id}: not a regular-season game in the schedule")
    else:
        due = sched.filter((pl.col("lock_utc") > now)
                           & (pl.col("lock_utc") <= now + dt.timedelta(minutes=window_minutes)))
    done = existing_game_ids()
    due = due.filter(~pl.col("game_id").is_in(list(done)))
    if due.height == 0:
        return []
    caps = market.capture(due, now=now, window_minutes=window_minutes, events=events, all_games=True)
    ll = {r["game_id"]: float(r["spread"]) for r in league_lines.load()}
    cbs = _cbs_frozen()
    out = []
    for g in due.sort("kickoff_utc").to_dicts():
        rows = [r for r in caps if r.get("game_id") == g["game_id"] and r.get("status") == "ok"]
        cons = market.consensus(rows)
        d = decide(ll.get(g["game_id"]), cons["median"], cbs.get(g["game_id"]))
        mtl = (g["lock_utc"] - now).total_seconds() / 60
        flags = [f for f in d["flags"].split(";") if f]
        if mtl <= 0:
            flags.append("LATE_AFTER_LOCK")
        pick_team = g["home_team"] if d["pick"] == "home" else g["away_team"]
        out.append({
            "prediction_id": str(uuid.uuid4()), "created_at": now.isoformat(),
            "season": g["season"], "week": g["week"], "game_id": g["game_id"],
            "home_team": g["home_team"], "away_team": g["away_team"],
            "kickoff_utc": g["kickoff_utc"].isoformat(), "lock_utc": g["lock_utc"].isoformat(),
            "minutes_to_lock": round(mtl, 1),
            "league_line": ll.get(g["game_id"]), "cbs_open": cbs.get(g["game_id"]),
            "market_at_lock": cons["median"], "market_books": cons["n_books"], "drift": d["drift"],
            "model_margin": "UNAVAILABLE", "p_home_cover": "UNAVAILABLE", "p_away_cover": "UNAVAILABLE",
            "pick": d["pick"], "pick_team": pick_team, "pick_rule": d["pick_rule"],
            "sim_count": 0, "seed": config.model().get("seed"), "model_version": MODEL_VERSION,
            "feature_version": "none", "data_snapshot": snapshot_id, "training_period": TRAINING_PERIOD,
            "data_status": d["data_status"], "missing_input": d["missing_input"],
            "expected_impact": d["expected_impact"], "flags": ";".join(flags), "supersedes": "",
        })
    store.append_rows(predictions_path(), FIELDS, out)
    write_slates({(r["season"], r["week"]) for r in out})
    return out


def write_slates(weeks: set[tuple]) -> None:
    rows = store.read_rows(predictions_path())
    ll = {r["game_id"]: r for r in league_lines.load()}
    for season, week in weeks:
        wk = [r for r in rows if str(r["season"]) == str(season) and str(r["week"]) == str(week)]
        wk.sort(key=lambda r: r["kickoff_utc"])
        lines = [f"# Slate — {season} week {week}\n",
                 f"Updated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}. "
                 f"Model {MODEL_VERSION}. Each row froze at its game's lock and is never changed.\n",
                 "Spread = home team's line (negative = home favored). Drift = market at lock − league line; "
                 "the pick follows the market's move (no move → away).\n",
                 "| Game | Kickoff (UTC) | League line | CBS odds-page open | Market at lock | Drift | "
                 "Model margin | P(home) / P(away) | Pick | Flags / status |",
                 "|---|---|---|---|---|---|---|---|---|---|"]
        for r in wk:
            flags = r["flags"] or ""
            lines.append(
                f"| {r['away_team']} @ {r['home_team']} | {r['kickoff_utc'][:16]} | "
                f"{r['league_line'] or 'MISSING'} | {r['cbs_open'] or '—'} | "
                f"{r['market_at_lock'] or 'UNAVAILABLE'} ({r['market_books']} books) | {r['drift'] or '—'} | "
                f"{r['model_margin']} | {r['p_home_cover']} | **{r['pick_team']}** | "
                f"{r['data_status']} {flags} |")
        (config.path("predictions") / f"slate_{season}_w{int(week):02d}.md").write_text("\n".join(lines) + "\n")
