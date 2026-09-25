"""Final (lock-time) picks.

Triggered by an external timer (workflow_dispatch; audit 0.10 + the 2026-09-25
dispatch-latency measurement). For every regular-season game whose lock
(kickoff - lock_buffer) falls within the next `window` minutes and that has no
final prediction yet:

  1. capture the current market spread from every book (appended to market_captures.csv)
  2. market_at_lock = median home spread across books
  3. drift = market_at_lock - league line
  4. pick = side the market moved toward; drift == 0 -> away
     (D0-full, pre-registered in docs/phase3_preregistration.md), or with the Phase 4
     margin distribution: pick = higher P(cover) (pre-registered switch, docs/phase4_*)
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
from engine.models.margin_dist import MarginDist
from engine.picks.grading import is_half_point

FIELDS = [
    "prediction_id", "created_at", "season", "week", "game_id", "home_team", "away_team",
    "kickoff_utc", "lock_utc", "minutes_to_lock", "league_line", "cbs_open", "market_at_lock",
    "market_books", "drift", "model_margin", "p_home_cover", "p_away_cover", "pick", "pick_team",
    "pick_rule", "sim_count", "seed", "model_version", "feature_version", "data_snapshot",
    "training_period", "data_status", "missing_input", "expected_impact", "flags", "supersedes",
    "shadow_p_home_keynum", "shadow_pick_keynum",
]
# Shadow estimator: recorded for every pick, never used to pick (docs/keynumber_report.md).
SHADOW = "keynum"
MODEL_VERSION = "phase4-shifted-empirical-argmax"
ESTIMATOR = "shifted"   # lowest walk-forward log loss (docs/phase4_results.md)


def fit_dist(sched: pl.DataFrame, now: dt.datetime) -> tuple[MarginDist | None, str]:
    """Margin distribution fit ONLY on regular-season games that kicked off before `now`.
    Returns (None, reason) if there is no history (then the Phase 3 drift rule is used)."""
    if not {"result", "spread_line"} <= set(sched.columns):
        return None, "no history in schedule; Phase 3 drift rule"
    h = sched.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                     pl.col("kickoff_utc") < now)
    if h.height < 500:
        return None, f"only {h.height} historical games; Phase 3 drift rule"
    md = MarginDist(kind=ESTIMATOR).fit(-h["spread_line"].to_numpy(), h["result"].to_numpy())
    period = f"{h['season'].min()}-{h['season'].max()} REG, {h.height} games, kickoff < {now.isoformat()}"
    return md, period


def predictions_path():
    return config.path("predictions") / "predictions.csv"


def existing_game_ids() -> set[str]:
    return {r["game_id"] for r in store.read_rows(predictions_path())}


def _cbs_frozen() -> dict[str, float]:
    rows = store.read_rows(config.path("lines") / "cbs_open_frozen.csv")
    return {r["game_id"]: float(r["spread"]) for r in rows if r.get("spread")}


def decide(league_line: float | None, market_at_lock: float | None, cbs_open: float | None,
           dist: MarginDist | None = None) -> dict:
    """Pure decision logic (tested). Returns pick fields + status fields.
    With a distribution: pick = higher cover probability (Phase 4, pre-registered switch).
    Without one: D0-full drift rule (Phase 3)."""
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
    p_home = p_away = None
    if line is not None and market_at_lock is not None:
        drift = market_at_lock - line
        if dist is not None:
            p_home, p_away = dist.cover_probs(market_at_lock, line)
            pick, rule = ("home" if p_home > 0.5 else "away"), "argmax_cover_prob"
        else:
            pick = "home" if drift < 0 else "away"
            rule = "drift" if drift != 0 else "no_move_fallback_away"
    else:
        drift, pick, rule = None, "away", "missing_input_fallback_away"
        impact.append("pick is the Phase 2 fallback (always away, ~51% historically)")
    return {"drift": drift, "pick": pick, "pick_rule": rule, "line_used": line,
            "p_home": p_home, "p_away": p_away,
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
    dist, period = fit_dist(sched, now)
    shadow = None
    if dist is not None:
        shadow = MarginDist(kind=SHADOW).fit(dist.c, dist.m)
    out = []
    for g in due.sort("kickoff_utc").to_dicts():
        rows = [r for r in caps if r.get("game_id") == g["game_id"] and r.get("status") == "ok"]
        cons = market.consensus(rows)
        d = decide(ll.get(g["game_id"]), cons["median"], cbs.get(g["game_id"]), dist)
        mkt = cons["median"]
        mtl = (g["lock_utc"] - now).total_seconds() / 60
        flags = [f for f in d["flags"].split(";") if f]
        if mtl <= 0:
            flags.append("LATE_AFTER_LOCK")
        pick_team = g["home_team"] if d["pick"] == "home" else g["away_team"]
        sh_p = sh_pick = ""
        if shadow is not None and d["line_used"] is not None and mkt is not None and is_half_point(float(d["line_used"])):
            sh_p = round(shadow.cover_probs(mkt, d["line_used"])[0], 4)
            sh_pick = g["home_team"] if sh_p > 0.5 else g["away_team"]
        out.append({
            "prediction_id": str(uuid.uuid4()), "created_at": now.isoformat(),
            "season": g["season"], "week": g["week"], "game_id": g["game_id"],
            "home_team": g["home_team"], "away_team": g["away_team"],
            "kickoff_utc": g["kickoff_utc"].isoformat(), "lock_utc": g["lock_utc"].isoformat(),
            "minutes_to_lock": round(mtl, 1),
            "league_line": ll.get(g["game_id"]), "cbs_open": cbs.get(g["game_id"]),
            "market_at_lock": cons["median"], "market_books": cons["n_books"], "drift": d["drift"],
            "model_margin": "UNAVAILABLE" if mkt is None or dist is None else f"{-mkt:+.1f} / {dist.median_margin(mkt):+.0f}",
            "p_home_cover": "UNAVAILABLE" if d["p_home"] is None else round(d["p_home"], 4),
            "p_away_cover": "UNAVAILABLE" if d["p_away"] is None else round(d["p_away"], 4),
            "pick": d["pick"], "pick_team": pick_team, "pick_rule": d["pick_rule"],
            "sim_count": 0, "seed": config.model().get("seed"),
            "model_version": MODEL_VERSION if dist is not None else "phase3-drift-D0full",
            "feature_version": "none", "data_snapshot": snapshot_id, "training_period": period,
            "data_status": d["data_status"], "missing_input": d["missing_input"],
            "expected_impact": d["expected_impact"], "flags": ";".join(flags), "supersedes": "",
            "shadow_p_home_keynum": sh_p, "shadow_pick_keynum": sh_pick,
        })
    store.append_rows(predictions_path(), FIELDS, out)
    if dist is not None:
        _append_sensitivity(out, dist)
    write_slates({(r["season"], r["week"]) for r in out})
    return out


def _append_sensitivity(preds: list[dict], dist: MarginDist) -> None:
    """Diagnostic: P(cover) for lines around the league line (spec Phase 4)."""
    for r in preds:
        line = r["league_line"] if r["league_line"] is not None else r["cbs_open"]
        if line is None or r["market_at_lock"] is None or not is_half_point(float(line)):
            continue
        f = config.path("predictions") / f"sensitivity_{r['season']}_w{int(r['week']):02d}.md"
        rows = dist.sensitivity(float(r["market_at_lock"]), float(line))
        txt = [f"\n## {r['away_team']} @ {r['home_team']} — market {r['market_at_lock']}, "
               f"league line {line} (created {r['created_at'][:16]})\n",
               "| home line | P(home covers) | P(away covers) |", "|---|---|---|"]
        txt += [f"| {x['line']:+.1f} | {x['p_home']:.3f} | {x['p_away']:.3f} |" for x in rows]
        with open(f, "a") as fh:
            fh.write("\n".join(txt) + "\n")


def write_slates(weeks: set[tuple]) -> None:
    rows = store.read_rows(predictions_path())
    ll = {r["game_id"]: r for r in league_lines.load()}
    for season, week in weeks:
        wk = [r for r in rows if str(r["season"]) == str(season) and str(r["week"]) == str(week)]
        wk.sort(key=lambda r: r["kickoff_utc"])
        lines = [f"# Slate — {season} week {week}\n",
                 f"Updated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}. "
                 f"Model {MODEL_VERSION}. Each row froze at its game's lock and is never changed.\n",
                 "Spread = home team's line (negative = home favored). Drift = market at lock − league line. "
                 "P = probability of covering the league line (raw: no calibrator improved it out of sample, "
                 "docs/phase5_report.md; extremes have been overconfident, treat as a lean); "
                 "pick = higher-probability side.\n",
                 "| Game | Kickoff (UTC) | League line | CBS odds-page open | Market at lock | Drift | "
                 "Model margin (exp / median) | P(home) / P(away) | Pick | Flags / status |",
                 "|---|---|---|---|---|---|---|---|---|---|"]
        for r in wk:
            flags = r["flags"] or ""
            lines.append(
                f"| {r['away_team']} @ {r['home_team']} | {r['kickoff_utc'][:16]} | "
                f"{r['league_line'] or 'MISSING'} | {r['cbs_open'] or '—'} | "
                f"{r['market_at_lock'] or 'UNAVAILABLE'} ({r['market_books']} books) | {r['drift'] or '—'} | "
                f"{r['model_margin']} | {r['p_home_cover']} / {r['p_away_cover']} | **{r['pick_team']}** | "
                f"{r['data_status']} {flags} |")
        (config.path("predictions") / f"slate_{season}_w{int(week):02d}.md").write_text("\n".join(lines) + "\n")
