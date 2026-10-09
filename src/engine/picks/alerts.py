"""Phone alerts for locked picks.

The lock run (a GitHub Action) sends each group's alert line to ntfy right after it commits the picks
(`python -m engine alert --local --send --since <ISO>`; topic in the NTFY_TOPIC secret). The older route, a Claude
session watching origin/main (`alert --watch`), cannot reach a phone and is kept only for printing.
The alert opens with a summary line listing each official pick with the spread it carries on the pool line, e.g.
'Picks locked (Sun 1:00 PM): LAC +7.5 · CLE +2.5 · NYJ +6.5', then one line per game with every tracked model's pick
(official, hybrid, team-only v1, player v3, key-number variant). ntfy accepts up to 4,096 bytes per message
(docs.ntfy.sh, publish limits); the summary line alone is kept to MAX_LEN for the lock-screen preview.
A second alert, 'CHECK PICKS: ...', follows only when a pick was made under a data-quality flag (picked more than
15 min before lock, fewer than 5 books, no market, fallback line or total, or after lock).
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
from engine.picks import dashboard, strength

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


# flag -> short phrase for the check-these-picks alert ({m} = minutes before lock, {b} = books)
WARN = {"EARLY_PICK": "picked {m} min before lock (stale market)", "LATE_AFTER_LOCK": "picked after lock",
        "FEW_BOOKS": "only {b} books", "NO_MARKET": "no market", "NO_LEAGUE_LINE": "no pool line",
        "LINE_FROM_CBS_ODDS_PAGE_OPEN": "pool line from CBS odds page",
        "TOTAL_FROM_SCHEDULE": "total from schedule", "MARKET_MEDIAN_FALLBACK": "no Pinnacle line, used median", "NO_TOTAL_SHIFTED_FALLBACK": "no total"}


def warning_message(rows: list[dict], max_len: int = MAX_LEN) -> str:
    """Second alert listing picks made under a data-quality flag; '' when every pick is clean."""
    bad = []
    for r in sorted(rows, key=lambda r: (r["kickoff_utc"], r["game_id"])):
        fl = [f for f in (r.get("flags") or "").split(";") if f in WARN]
        if fl:
            m = round(float(r.get("minutes_to_lock") or 0))
            bad.append(f"{r['away_team']}@{r['home_team']} " + ", ".join(WARN[f].format(m=m, b=r.get("market_books")) for f in fl))
    if not bad:
        return ""
    head = "CHECK PICKS: "
    for keep in range(len(bad), 0, -1):
        more = f" · +{len(bad) - keep} more" if keep < len(bad) else ""
        text = head + " · ".join(bad[:keep]) + more
        if len(text) <= max_len:
            return text
    return (head + bad[0])[:max_len]


FULL_MAX_BYTES = 4000          # ntfy's limit is 4,096 bytes per message
MODEL_TAGS = (("hybrid", "Hybrid"), ("proj-poisson-v1", "v1"), ("proj-players-v3", "v3"), ("keynum", "Key"))


def _team_spread(r: dict, team: str | None) -> str:
    if not team:
        return "—"
    if r.get("league_line") in (None, ""):
        return team
    line = float(r["league_line"])
    return f"{team} {_spread(line if team == r.get('home_team') else -line)}"


def _move(drift) -> str:
    try:
        d = abs(float(drift))
    except (TypeError, ValueError):
        return "no market"
    if d == 0:
        return "no move"
    w, f = int(d), d - int(d)
    return "moved " + ((str(w) if w else "") + ("½" if f else "")) + (" pt" if d <= 1 else " pts")


def model_picks(r: dict, projs: dict | None) -> dict:
    """{'hybrid': team, 'proj-poisson-v1': team, 'proj-players-v3': team, 'keynum': team} for one pick row."""
    from engine.picks import hybrid
    pj = (projs or {}).get(r["game_id"], {})
    v1 = pj.get("proj-poisson-v1") or None
    return {"hybrid": hybrid.pick(r.get("pick_team"), r.get("drift"), v1)[0], "proj-poisson-v1": v1,
            "proj-players-v3": pj.get("proj-players-v3") or None, "keynum": r.get("shadow_pick_keynum") or None}


def full_message(rows: list[dict], projs: dict | None = None, max_bytes: int = FULL_MAX_BYTES) -> str:
    """Summary line, then one line per game: official pick (move, cover chance) and every tracked model's pick.
    Models that disagree with the official pick are marked with ≠."""
    if not rows:
        return ""
    tbl = strength.table()
    rows = sorted(rows, key=lambda r: (r["kickoff_utc"], r["game_id"]))
    lines = [message(rows, max_len=10_000)]
    for r in rows:
        off = r.get("pick_team")
        try:
            pc = f", {round(100 * max(float(r['p_home_cover']), float(r['p_away_cover'])))}%"
        except (KeyError, TypeError, ValueError):
            pc = ""
        mp = model_picks(r, projs)
        noinj = (projs or {}).get(r["game_id"], {}).get("v3_no_injury_report")
        rest = " · ".join(f"{tag} {_team_spread(r, mp[k])}" + (" ≠" if mp[k] and off and mp[k] != off else "")
                          + (" (no injury report)" if k == "proj-players-v3" and noinj and mp[k] else "")
                          for k, tag in MODEL_TAGS)
        tg = strength.tag(r.get("drift"), tbl)
        lines.append(f"{r['away_team']}@{r['home_team']}: Pick {_team_spread(r, off)} ({_move(r.get('drift'))}{pc}{', ' + tg if tg else ''}) | {rest}")
    text = "\n".join(lines)
    while len(text.encode("utf-8")) > max_bytes and len(lines) > 2:
        lines.pop()
        text = "\n".join(lines + ["…"])
    return text


def local_projections() -> dict:
    """game_id -> {model_version: proj_pick, 'v3_no_injury_report': True when v3 ran without injury statuses}."""
    from engine.data import store
    from engine.picks import final
    out: dict = {}
    for p in store.read_rows(final.projections_path()):
        v = p.get("model_version") or final.PROJ_VERSION
        g = out.setdefault(p["game_id"], {})
        g[v] = p.get("proj_pick")
        if v == "proj-players-v3" and "INJ_STATUS_MISSING" in (p.get("inputs") or ""):
            g["v3_no_injury_report"] = True      # scored separately in the live record (engine/picks/live.py)
    return out


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
