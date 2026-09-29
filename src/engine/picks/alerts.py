"""Phone alerts for locked picks.

The lock run (a GitHub Action) sends each group's alert line to ntfy right after it commits the picks
(`python -m engine alert --local --send --since <ISO>`; topic in the NTFY_TOPIC secret). The older route, a Claude
session watching origin/main (`alert --watch`), cannot reach a phone and is kept only for printing.
Messages are one line of at most 200 characters (the notification limit), listing each pick with the spread it
carries on the pool line, e.g. 'Picks locked (Sun 1:00 PM): LAC +7.5 · CLE +2.5 · NYJ +6.5'.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import subprocess
import urllib.request

import polars as pl

from engine import config
from engine.picks import dashboard

MAX_LEN = 200
MISSING_LEAD_MIN = 3        # warn when a game locks within this many minutes and still has no pick


def _spread(v: float) -> str:
    body = f"{abs(v):.1f}"
    return ("+" if v > 0 else "−" if v < 0 else "") + body


def pool_spread(row: dict) -> float | None:
    """The picked team's spread on the pool line (the pool line is the home spread)."""
    if row.get("league_line") in (None, ""):
        return None
    line = float(row["league_line"])
    return line if row.get("pick_team") == row.get("home_team") else -line


def slot_label(rows: list[dict]) -> str:
    kicks = [dt.datetime.fromisoformat(r["kickoff_utc"]) for r in rows]
    if len({k.astimezone(dashboard.ET).date() for k in kicks}) > 1:
        return f"{len(rows)} games"                       # picks from different days in one alert
    day, times = dashboard._slot_label(kicks)
    return f"{day[:3]} {times}"


def _item(r: dict) -> str:
    if not r.get("pick_team"):
        return f"{r['away_team']}@{r['home_team']} NO PICK"
    sp = pool_spread(r)
    late = " LATE" if "LATE_AFTER_LOCK" in (r.get("flags") or "") else ""
    return f"{r['pick_team']} {_spread(sp) if sp is not None else '?'}{late}"


def message(rows: list[dict], max_len: int = MAX_LEN) -> str:
    """One alert line for the given pick rows, oldest kickoff first; '' when there are none."""
    if not rows:
        return ""
    rows = sorted(rows, key=lambda r: (r["kickoff_utc"], r["game_id"]))
    head = f"Picks locked ({slot_label(rows)}): "
    items = [_item(r) for r in rows]
    for keep in range(len(items), 0, -1):
        more = f" · +{len(items) - keep} more" if keep < len(items) else ""
        text = head + " · ".join(items[:keep]) + more
        if len(text) <= max_len:
            return text
    return (head + items[0])[:max_len]


def new_rows(preds: list[dict], since: str, ids: set[str] | None = None) -> list[dict]:
    """Final (not superseded) pick rows created after `since` (ISO), optionally only for `ids`."""
    return [p for p in preds if not p.get("supersedes") and p["created_at"] > since
            and (ids is None or p["game_id"] in ids)]


def missing_message(due: list[dict], picked: set[str], now: dt.datetime) -> str:
    """Alert for games that lock within MISSING_LEAD_MIN and have no pick yet; '' when nothing is missing."""
    late = [g for g in due if g["game_id"] not in picked and 0 < (g["lock_utc"] - now).total_seconds() <= MISSING_LEAD_MIN * 60]
    if not late:
        return ""
    names = ", ".join(f"{g['away_team']}@{g['home_team']}" for g in late[:4])
    mins = max(1, round(min((g["lock_utc"] - now).total_seconds() for g in late) / 60))
    return f"PICK MISSING: {names} locks in {mins} min with no pick yet. Running the fallback."[:MAX_LEN]


def watch_step(preds: list[dict], since: str, due: list[dict], warned: set[str], now: dt.datetime) -> tuple[list[str], str, bool]:
    """One poll: (alert lines, new `since`, done). `due` are the schedule rows (game_id, home_team, away_team,
    lock_utc) this watch covers. A missing-pick warning is sent once per game."""
    ids = {g["game_id"] for g in due}
    fresh = new_rows(preds, since, ids)
    out = []
    if fresh:
        out.append(message(fresh))
        since = max(p["created_at"] for p in fresh)
    picked = {p["game_id"] for p in preds if not p.get("supersedes")} & ids
    miss = [g for g in due if g["game_id"] not in warned]
    text = missing_message(miss, picked, now)
    if text:
        out.append(text)
        warned |= {g["game_id"] for g in miss if g["game_id"] not in picked and 0 < (g["lock_utc"] - now).total_seconds() <= MISSING_LEAD_MIN * 60}
    return out, since, picked >= ids


def origin_predictions() -> list[dict]:
    """predictions.csv as it is on origin/main (fetched; the working tree and branch are not touched)."""
    root = str(config.ROOT)
    subprocess.run(["git", "-C", root, "fetch", "-q", "origin", "main"], check=False, timeout=120)
    out = subprocess.run(["git", "-C", root, "show", "origin/main:data/predictions/predictions.csv"],
                         capture_output=True, text=True, check=True, timeout=60).stdout
    return list(csv.DictReader(io.StringIO(out)))


def due_games(sched: pl.DataFrame, now: dt.datetime, window_minutes: int, done: set[str]) -> list[dict]:
    d = sched.filter((pl.col("lock_utc") > now) & (pl.col("lock_utc") <= now + dt.timedelta(minutes=window_minutes)),
                     ~pl.col("game_id").is_in(list(done)))
    return d.select("game_id", "home_team", "away_team", "lock_utc").sort("lock_utc").to_dicts()


NTFY_URL = "https://ntfy.sh/"


def send(text: str, topic: str | None = None, opener=urllib.request.urlopen) -> bool:
    """Post `text` to the ntfy topic (env NTFY_TOPIC when not given). False when there is no topic, no text or the
    post fails (an alert must never fail a lock run)."""
    topic = (topic if topic is not None else os.environ.get("NTFY_TOPIC", "")).strip()
    if not topic or not text:
        return False
    req = urllib.request.Request(NTFY_URL + topic, data=text.encode("utf-8"), method="POST",
                                 headers={"Title": "NFL picks", "Tags": "football", "Priority": "high"})
    try:
        with opener(req, timeout=20) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def local_predictions() -> list[dict]:
    """predictions.csv from the working tree (the lock run has just written it)."""
    from engine.data import store
    from engine.picks import final
    return store.read_rows(final.predictions_path())
