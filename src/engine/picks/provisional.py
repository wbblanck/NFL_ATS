"""Provisional-pick log: the pick the dashboard showed before each game locked, written whenever the published
dashboard is rebuilt and the pick or market changed. It lets a card say 'was TB, flipped to DAL when the line moved'.
Descriptive only; nothing here feeds a pick. Rows before a game's pool line was posted are never logged (the preview
falls back to a stale CBS opener then, which is not a pick)."""
from __future__ import annotations

import csv
import datetime as dt

from engine import config

FIELDS = ["logged_at", "game_id", "pick", "market", "drift", "pick_p"]


def path():
    return config.ROOT / "data" / "predictions" / "provisional_log.csv"


def load(p=None) -> list[dict]:
    p = p or path()
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def record(rows: list[dict], now: dt.datetime, p=None) -> int:
    """Append a row for every still-provisional game whose pick or market differs from its last logged row."""
    p = p or path()
    log = load(p)
    last = {r["game_id"]: (r["pick"], r["market"]) for r in log}
    new = []
    for r in rows:
        if r.get("status") != "provisional" or not r.get("pick") or r.get("league_line") in (None, "") \
                or r.get("drift") in (None, "", "UNAVAILABLE"):
            continue
        mk = "" if r.get("market") in (None, "") else str(r["market"])
        key = (r["pick"], mk)
        if last.get(r["game_id"]) == key:
            continue
        pp = r.get("p_home") if r["pick"] == r["home"] else r.get("p_away")
        new.append({"logged_at": now.isoformat(timespec="seconds"), "game_id": r["game_id"], "pick": r["pick"],
                    "market": mk, "drift": r["drift"], "pick_p": "" if pp in (None, "", "UNAVAILABLE") else round(float(pp), 4)})
    if new:
        write_header = not p.exists()
        with open(p, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if write_header:
                w.writeheader()
            w.writerows(new)
    return len(new)


def flips(rows: list[dict], log: list[dict]) -> dict[str, dict]:
    """game_id -> {was, at, mk, n} for games whose current pick differs from the first one logged for them.
    `n` counts pick changes over the log plus the step to the current pick."""
    by: dict[str, list[dict]] = {}
    for r in log:
        by.setdefault(r["game_id"], []).append(r)
    out = {}
    for r in rows:
        seq = by.get(r["game_id"])
        if not seq or not r.get("pick"):
            continue
        picks = [x["pick"] for x in seq] + [r["pick"]]
        if picks[0] == r["pick"]:
            continue
        n = sum(1 for a, b in zip(picks, picks[1:]) if a != b)
        out[r["game_id"]] = {"was": picks[0], "at": seq[0]["logged_at"], "mk": seq[0]["market"], "n": n}
    return out
