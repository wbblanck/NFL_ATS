"""Per-game detail for the dashboard: every book's line over time, the books at the pick's capture, which books
matched the pool line on Tuesday, the recorded projection inputs, and a plain-language 'why this pick'.
Pure functions over rows already read from data/ (see build_from_files for the file wrapper)."""
from __future__ import annotations

import datetime as dt
import json
import statistics
from zoneinfo import ZoneInfo

from engine.picks import final

ET = ZoneInfo("America/New_York")
LOCK_TOLERANCE_S = 120          # a pick's capture can differ from the pick's created_at by a few seconds
V3 = "proj-players-v3"
HOOK_MATCH = ("hook_fav", "hook_dog", "hook_pk")


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _z(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clock(d: dt.datetime) -> str:
    return d.astimezone(ET).strftime("%-I:%M %p")


def american(decimal: float | None) -> str:
    """Decimal odds to American (1.877 -> -114, 2.5 -> +150)."""
    if not decimal or decimal <= 1:
        return ""
    v = (decimal - 1) * 100 if decimal >= 2 else -100 / (decimal - 1)
    return f"{v:+.0f}".replace("-", "−")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def history(caps: list[dict], game_id: str, kickoff: dt.datetime) -> dict:
    """Book lines per capture before kickoff: {'t': [iso...], 'b': {book: [spread|None per capture]}, 'raw': {t: rows}}."""
    by_t: dict[str, list[dict]] = {}
    for r in caps:
        if r.get("game_id") != game_id or r.get("status") != "ok" or _f(r.get("home_spread")) is None:
            continue
        if _t(r["captured_at"]) > kickoff:
            continue
        by_t.setdefault(r["captured_at"], []).append(r)
    order = sorted(by_t, key=_t)
    books = sorted({r["book"] for rows in by_t.values() for r in rows})
    b = {bk: [None] * len(order) for bk in books}
    for i, k in enumerate(order):
        for r in by_t[k]:
            b[r["book"]][i] = _f(r["home_spread"])
    return {"t": [_z(_t(k)) for k in order], "b": b, "_rows": [by_t[k] for k in order], "_when": [_t(k) for k in order]}


def _lock_index(h: dict, pick_at: dt.datetime | None) -> int | None:
    if not h["t"]:
        return None
    if pick_at is None:
        return len(h["t"]) - 1
    ok = [i for i, w in enumerate(h["_when"]) if (w - pick_at).total_seconds() <= LOCK_TOLERANCE_S]
    return ok[-1] if ok else 0


def tuesday_match(h: dict, pool_line: float | None, window: tuple[dt.datetime, dt.datetime] | None) -> dict | None:
    """Each book's line at the capture nearest Tuesday 12:00 ET inside the posting window, and whether it equals the
    pool line (`same`), is the whole-number neighbour (`hook`), or differs (`off`). None with no capture in the window."""
    from engine.backtest.cbs_lines import match
    if pool_line is None or window is None:
        return None
    lo, hi = window
    inside = [i for i, w in enumerate(h["_when"]) if lo <= w <= hi]
    if not inside:
        return None
    target = lo + dt.timedelta(hours=4)
    i = min(inside, key=lambda j: abs((h["_when"][j] - target).total_seconds()))
    out = {}
    for r in h["_rows"][i]:
        x = _f(r["home_spread"])
        m = match(x, pool_line)
        out[r["book"]] = {"line": x, "m": "same" if m == "exact" else "hook" if m in HOOK_MATCH else "off"}
    return {"at": _clock(h["_when"][i]) + " ET " + h["_when"][i].astimezone(ET).strftime("%a"), "books": out}


def _pts(a: float) -> str:
    w, f = int(a), a - int(a)
    frac = {0: "", 0.25: "¼", 0.5: "½", 0.75: "¾"}.get(round(f, 2), f"{f:.2f}"[1:])
    t = (str(w) if w else "") + frac
    return (t or "0") + (" pt" if a <= 1 else " pts")


def _sgn(v: float) -> str:
    """-7.0 -> '−7.0', 8.25 -> '+8.25', 2.5 -> '+2.5'."""
    body = f"{abs(v):.2f}".rstrip("0")
    body += "0" if body.endswith(".") else ""
    return ("+" if v > 0 else "−" if v < 0 else "") + body


def _pick_p(r: dict) -> float | None:
    if r.get("pick_p") is not None:
        return r["pick_p"]
    ph, pa = r.get("p_home"), r.get("p_away")
    if ph in (None, "", "UNAVAILABLE") or not r.get("pick"):
        return None
    return float(ph) if r["pick"] == r["home"] else float(pa)


def why(row: dict, pred: dict | None, proj_row: dict | None) -> list[str]:
    """Plain-language reasons, built only from recorded numbers."""
    out = []
    drift, line, mkt = row.get("drift"), row.get("league_line"), row.get("market")
    home, away, pick = row["home"], row["away"], row.get("pick")
    if drift not in (None, "", "UNAVAILABLE") and line is not None and mkt not in (None, ""):
        d = float(drift)
        if d == 0:
            out.append(f"The market did not move off the pool line ({home} {_sgn(line)}), so there is no line-movement "
                       "signal and the pick is close to a coin flip.")
        else:
            toward = away if d > 0 else home
            hist = "57% historically" if abs(d) >= 1 else "about 51% historically"
            extra = "; 52% in the 2025 holdout" if abs(d) >= 1 else ""
            out.append(f"The market moved {_pts(abs(d))} toward {toward}: {home} {_sgn(line)} on the pool line, "
                       f"{_sgn(float(mkt))} {'at the pick' if row.get('status') == 'final' else 'now'}. Sides that the market moves toward have covered {hist}{extra}.")
    pick_p = _pick_p(row)
    if pick_p is not None and pick:
        tot = ""
        if pred and pred.get("market_total") not in (None, ""):
            tot = f" It also uses the game total ({float(pred['market_total']):g})."
        out.append(f"Model cover chance for {pick}: {pick_p * 100:.1f}%, from how games have finished around the "
                   f"market spread since 1999.{tot}")
    if row.get("proj_home") is not None:
        who = "Player projection" if (row.get("proj_version") or V3) == V3 else "Team-only projection"
        diff = ""
        if row.get("proj_pick") and pick and row["proj_pick"] != pick:
            diff = (f" It would take {row['proj_pick']} against the pool line, so it disagrees with the pick. It is "
                    "tracked for comparison only and does not make the pick.")
        out.append(f"{who}: {away} {row['proj_away']} – {home} {row['proj_home']}.{diff}")
    if row.get("home_score") is not None and line is not None:
        m = (row["home_score"] - row["away_score"]) + float(line)
        out.append(f"Final {away} {row['away_score']} – {home} {row['home_score']}: "
                   f"{home if m > 0 else away} covered the pool line by {_pts(abs(m))}.")
    return out


def inputs_block(proj_row: dict | None, names: dict | None) -> dict | None:
    """Recorded projection inputs (only games that have a proj-players-v3 row: written at the pick)."""
    if not proj_row or not proj_row.get("inputs"):
        return None
    try:
        info = json.loads(proj_row["inputs"])
    except ValueError:
        return None
    names = names or {}
    out = {"flags": info.get("flags", [])}
    for side in ("home", "away"):
        s = dict(info.get(side, {}))
        s["starter_name"] = names.get(s.get("starter")) or s.get("starter")
        out[side] = s
    return out


def build(rows: list[dict], caps: list[dict], preds: list[dict], projs: list[dict], names: dict | None = None,
          windows: dict | None = None) -> dict[str, dict]:
    """game_id -> detail. `rows` are dashboard/preview rows; `windows` maps game_id -> Tuesday posting window (UTC)."""
    pred_by = {p["game_id"]: p for p in preds if not p.get("supersedes")}
    proj_by: dict[str, dict] = {}
    for p in sorted(projs, key=lambda r: r.get("created_at", "")):
        if (p.get("model_version") or "") == V3:
            proj_by[p["game_id"]] = p
    out = {}
    for r in rows:
        gid = r["game_id"]
        ko = dt.datetime.fromisoformat(r["kickoff_utc"])
        h = history(caps, gid, ko)
        pick_at = None
        if r.get("status") == "final" and r.get("market_time"):
            pick_at = dt.datetime.fromisoformat(str(r["market_time"]))
        li = _lock_index(h, pick_at)
        lock = None
        if li is not None:
            spreads = [_f(x["home_spread"]) for x in h["_rows"][li]]
            lock = {"at": _clock(h["_when"][li]), "i": li, "n": len(spreads), "median": statistics.median(spreads),
                    "books": sorted(({"book": x["book"], "spread": _f(x["home_spread"]),
                                      "price": american(_f(x.get("home_price_decimal"))),
                                      "upd": _clock(_t(x["book_last_update"])) if x.get("book_last_update") else ""}
                                     for x in h["_rows"][li]), key=lambda z: (z["spread"], z["book"]))}
        out[gid] = {"t": h["t"], "b": h["b"], "lock": lock,
                    "tue": tuesday_match(h, _f(r.get("league_line")), (windows or {}).get(gid)),
                    "why": why(r, pred_by.get(gid), proj_by.get(gid)),
                    "inputs": inputs_block(proj_by.get(gid), names),
                    "total": _f((pred_by.get(gid) or {}).get("market_total"))}
    return out


def build_from_files(rows: list[dict], sched_week, names: dict | None = None) -> dict[str, dict]:
    """Read the capture, prediction and projection files and build the details for `rows` (one week)."""
    from engine import config
    from engine.backtest.cbs_lines import tuesday_window
    from engine.data import store
    caps = store.read_rows(config.path("lines") / "market_captures.csv")
    preds = store.read_rows(final.predictions_path())
    projs = store.read_rows(final.projections_path())
    windows = {}
    try:
        w = tuesday_window(sched_week)
        windows = {r["game_id"]: w for r in rows}
    except Exception:
        pass
    return build(rows, caps, preds, projs, names, windows)
