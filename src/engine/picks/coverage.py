"""Pick classes and schedule coverage (audit A, 2026-11-19; approved by the owner 2026-11-26). Reporting only:
nothing here changes a pick, a prediction row or the grade.

Every scheduled game gets exactly one class, so every reported denominator can be rebuilt from prediction ids:

  LIVE_MARKET     Pinnacle line (direct feed, OddsPapi or OddsLink), picked at most STALE_MIN before lock
  LIVE_MEDIAN     all-book median (Pinnacle missing, or before the 2026-10-04 switch to Pinnacle), on time
  STALE_MARKET    picked more than STALE_MIN before lock, so the market it used was older than the rule intends
  LATE_PICK       picked after lock (LATE_AFTER_LOCK)
  BLIND_FALLBACK  no market line at all (NO_MARKET): the always-away fallback
  INVALID_INPUT   no usable pool line at pick time (NO_LEAGUE_LINE, LEAGUE_LINE_INVALID, LEAGUE_LINE_CONFLICT)
  MISSING_PICK    the game's lock has passed and it has no prediction row

Coverage also checks upcoming kickoffs against the recurring lock-run jobs (docs/scheduling.md), so a game that
needs a one-off job is named days ahead instead of being missed.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl

STALE_MIN = 15          # same threshold as final.EARLY_PICK_MIN
ET = ZoneInfo("America/New_York")

LIVE_MARKET, LIVE_MEDIAN, STALE_MARKET, LATE_PICK = "LIVE_MARKET", "LIVE_MEDIAN", "STALE_MARKET", "LATE_PICK"
BLIND_FALLBACK, INVALID_INPUT, MISSING_PICK = "BLIND_FALLBACK", "INVALID_INPUT", "MISSING_PICK"
CLASSES = (LIVE_MARKET, LIVE_MEDIAN, STALE_MARKET, LATE_PICK, BLIND_FALLBACK, INVALID_INPUT, MISSING_PICK)

# The six recurring cron-job.org jobs (docs/scheduling.md): (weekday Mon=0, hour, minute ET, window_minutes).
RECURRING_JOBS = ((3, 19, 15, 55), (6, 8, 30, 55), (6, 12, 0, 55), (6, 15, 5, 75), (6, 19, 20, 55), (0, 19, 15, 55))
LEAD_MIN = 5            # lock runs pick this many minutes before lock


def classify(pred: dict) -> str:
    """The one class of a prediction row (see module docstring). Order matters: a blind pick is blind even if late."""
    flags = set((pred.get("flags") or "").split(";"))
    if "NO_MARKET" in flags:
        return BLIND_FALLBACK
    if flags & {"NO_LEAGUE_LINE", "LEAGUE_LINE_INVALID", "LEAGUE_LINE_CONFLICT"}:
        return INVALID_INPUT
    try:
        mtl = float(pred.get("minutes_to_lock"))
    except (TypeError, ValueError):
        mtl = None
    if "LATE_AFTER_LOCK" in flags or (mtl is not None and mtl <= 0):
        return LATE_PICK
    if mtl is not None and mtl > STALE_MIN:
        return STALE_MARKET
    return LIVE_MARKET if pred.get("feature_version") == "market:pinnacle" else LIVE_MEDIAN


def covered_by_recurring_job(kickoff_utc: dt.datetime) -> bool:
    """True if one of the recurring jobs fires on the lock's day before the pick time and its window holds the lock."""
    lock = (kickoff_utc - dt.timedelta(minutes=15)).astimezone(ET)
    for wd, h, m, window in RECURRING_JOBS:
        if lock.weekday() != wd:
            continue
        fire = lock.replace(hour=h, minute=m, second=0, microsecond=0)
        if fire < lock - dt.timedelta(minutes=LEAD_MIN) and lock <= fire + dt.timedelta(minutes=window):
            return True
    return False


def _kick(v) -> dt.datetime:
    return v if isinstance(v, dt.datetime) else dt.datetime.fromisoformat(str(v))


def report(sched: pl.DataFrame, preds: list[dict], now: dt.datetime, season: int | None = None,
           ahead_days: int = 4) -> dict:
    """Coverage of every regular-season game whose lock has passed (one class each) and the upcoming games within
    `ahead_days` that no recurring job covers. `preds` are the official rows (one per game, supersedes empty)."""
    by_game = {p["game_id"]: p for p in preds if not p.get("supersedes")}
    s = sched if season is None else sched.filter(pl.col("season") == season)
    # Coverage starts with the first week that has any live pick (2026: week 3); earlier weeks predate the pipeline.
    weeks = [int(p["week"]) for p in by_game.values() if season is None or str(p.get("season")) == str(season)]
    if weeks:
        s = s.filter(pl.col("week") >= min(weeks))
    rows, upcoming = [], []
    for g in s.sort("kickoff_utc").iter_rows(named=True):
        if g.get("kickoff_utc") is None:
            continue
        ko = _kick(g["kickoff_utc"])
        lock = ko - dt.timedelta(minutes=15)
        if lock <= now:
            p = by_game.get(g["game_id"])
            rows.append({"game_id": g["game_id"], "week": g["week"], "kickoff_utc": ko.isoformat(),
                         "prediction_id": p["prediction_id"] if p else "",
                         "class": classify(p) if p else MISSING_PICK})
        elif ko <= now + dt.timedelta(days=ahead_days) and g["game_id"] not in by_game and not covered_by_recurring_job(ko):
            fire = (lock - dt.timedelta(minutes=45)).astimezone(ET)
            upcoming.append({"game_id": g["game_id"], "kickoff_et": ko.astimezone(ET).strftime("%a %b %-d %-I:%M %p"),
                             "suggested_fire_et": fire.strftime("%a %b %-d %-I:%M %p"), "window_minutes": 55})
    counts = {c: sum(r["class"] == c for r in rows) for c in CLASSES}
    return {"locked_games": len(rows), "prediction_rows": len(rows) - counts[MISSING_PICK], "counts": counts,
            "rows": rows, "needs_one_off_job": upcoming}


def alert_text(rep: dict, now: dt.datetime, since_hours: float = 24) -> str:
    """Phone-alert text: games missed since `since_hours` ago and upcoming games no recurring job covers.
    Empty when there is nothing to say."""
    cut = now - dt.timedelta(hours=since_hours)
    missed = [r["game_id"] for r in rep["rows"] if r["class"] == MISSING_PICK and _kick(r["kickoff_utc"]) >= cut]
    parts = []
    if missed:
        parts.append("NO PICK (lock passed): " + ", ".join(missed))
    if rep["needs_one_off_job"]:
        parts.append("NEEDS ONE-OFF JOB: " + "; ".join(
            f"{u['game_id']} kickoff {u['kickoff_et']} (fire ~{u['suggested_fire_et']} ET, window {u['window_minutes']})"
            for u in rep["needs_one_off_job"]))
    return " | ".join(parts)


def summary_line(rep: dict) -> str:
    """One plain line for live_record.md and the dashboard."""
    c = rep["counts"]
    return (f"Coverage: {rep['locked_games']} scheduled games past lock, {rep['prediction_rows']} picks recorded, "
            f"{c[MISSING_PICK]} missed. Classes: live Pinnacle {c[LIVE_MARKET]}, live median {c[LIVE_MEDIAN]}, "
            f"stale market {c[STALE_MARKET]}, late {c[LATE_PICK]}, blind fallback {c[BLIND_FALLBACK]}, "
            f"invalid input {c[INVALID_INPUT]}.")
