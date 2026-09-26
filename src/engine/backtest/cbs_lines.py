"""CBS pool line-setting analysis (docs/cbs_lines_preregistration.md).

Q1 source/timing, Q2 half-point rule, Q3 value of the hook at key numbers, Q4 movement after posting.
Writes docs/cbs_lines_report.md. Descriptive; never changes the live pick rule.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

import polars as pl

from engine import config
from engine.data import league_lines, store

ET = ZoneInfo("America/New_York")
IDENTIFY_MIN_GAMES, IDENTIFY_MIN_RATE = 45, 0.90


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def match(candidate: float, league: float) -> str | None:
    """How a candidate line maps to the league line: 'exact', 'hook_fav', 'hook_dog', or None.
    Canonical home spreads (negative = home favored). For a whole-number candidate, the league line is the
    candidate +- 0.5; 'hook_fav' means the favorite must win by more (the half point went to the underdog)."""
    if candidate == league:
        return "exact"
    if candidate != round(candidate) or abs(candidate - league) != 0.5:
        return None
    if candidate == 0:
        return "hook_pk"
    fav_home = candidate < 0
    return "hook_fav" if (league < candidate) == fav_home else "hook_dog"


def tuesday_window(season_week_games: pl.DataFrame) -> tuple[dt.datetime, dt.datetime]:
    """Tuesday 08:00-17:00 ET of the week (the Tuesday before the week's first Sunday)."""
    sunday = min(season_week_games["kickoff_utc"].to_list()).astimezone(ET).date()
    while sunday.weekday() != 6:
        sunday += dt.timedelta(days=1)
    tue = sunday - dt.timedelta(days=5)
    return (dt.datetime.combine(tue, dt.time(8), ET).astimezone(dt.timezone.utc),
            dt.datetime.combine(tue, dt.time(17), ET).astimezone(dt.timezone.utc))


def q1_candidates(ll: dict, market_rows: list[dict], cbs_rows: list[dict], window) -> dict:
    """Exact/hook match rates per candidate source x snapshot inside the Tuesday window."""
    lo, hi = window
    cands: dict = defaultdict(dict)                       # (source, snapshot) -> game -> line
    for r in market_rows:
        if r.get("status") != "ok" or r.get("game_id") not in ll:
            continue
        t = _t(r["captured_at"])
        if lo <= t <= hi:
            cands[(f"book:{r['book']}", r["captured_at"][:16])][r["game_id"]] = float(r["home_spread"])
    by_snap: dict = defaultdict(lambda: defaultdict(list))
    for (src, snap), games in list(cands.items()):
        for g, x in games.items():
            by_snap[snap][g].append(x)
    for snap, games in by_snap.items():
        cands[("consensus:median", snap)] = {g: statistics.median(v) for g, v in games.items()}
    for r in cbs_rows:
        if r.get("status") != "ok" or r.get("game_id") not in ll or not r.get("current_home_spread"):
            continue
        t = _t(r["captured_at"])
        if lo <= t <= hi:
            cands[(f"cbs_page:{r.get('current_operator') or '?'}", r["captured_at"][:16])][r["game_id"]] = float(r["current_home_spread"])
    out = []
    for (src, snap), games in cands.items():
        kinds = Counter(match(x, ll[g]) for g, x in games.items())
        n = len(games)
        hit = n - kinds.get(None, 0)
        out.append({"source": src, "snapshot_utc": snap, "games": n, "matched": hit,
                    "exact": kinds.get("exact", 0), "hook_fav": kinds.get("hook_fav", 0),
                    "hook_dog": kinds.get("hook_dog", 0), "hook_pk": kinds.get("hook_pk", 0),
                    "rate": hit / n if n else float("nan")})
    return {"candidates": sorted(out, key=lambda r: (-r["rate"], -r["games"]))}


def q3_hook_values(sched: pl.DataFrame, seasons=(2006, 2025)) -> list[dict]:
    """P(favorite wins by exactly the line) for whole-number closing lines: the push probability the half point
    converts into a cover for one side. SE is binomial."""
    g = sched.filter(pl.col("game_type") == "REG", pl.col("season").is_between(*seasons), pl.col("result").is_not_null(),
                     pl.col("spread_line").is_not_null())
    g = g.with_columns((-pl.col("spread_line")).alias("home_spread"))
    g = g.filter(pl.col("home_spread") == pl.col("home_spread").round(0), pl.col("home_spread") != 0)
    rows = []
    for k in (1, 2, 3, 4, 6, 7, 10, 14):
        x = g.filter(pl.col("home_spread").abs() == k)
        if x.height < 30:
            continue
        # favorite margin = result if home favored else -result
        fav_margin = x.select(pl.when(pl.col("home_spread") < 0).then(pl.col("result")).otherwise(-pl.col("result"))).to_series()
        p = float((fav_margin == k).mean())
        rows.append({"line": k, "games": x.height, "p_exact": p, "se": math.sqrt(p * (1 - p) / x.height)})
    return rows


def q4_movement(preds: list[dict], ll: dict) -> dict:
    moves = []
    for p in preds:
        if p.get("supersedes") or p.get("game_id") not in ll or p.get("market_at_lock") in (None, ""):
            continue
        moves.append({"game_id": p["game_id"], "week": p.get("week"), "move": float(p["market_at_lock"]) - ll[p["game_id"]]})
    if not moves:
        return {"n": 0}
    m = [x["move"] for x in moves]
    return {"n": len(m), "mean": sum(m) / len(m), "abs_mean": sum(abs(x) for x in m) / len(m),
            "share_ge_1": sum(abs(x) >= 1 for x in m) / len(m), "rows": moves}


def run(sched: pl.DataFrame, out_md=None) -> dict:
    ll_rows = league_lines.load()
    ll = {r["game_id"]: float(r["spread"]) for r in ll_rows}
    weeks = sorted({(int(r["season"]), int(r["week"])) for r in ll_rows})
    market_rows = store.read_rows(config.path("lines") / "market_captures.csv")
    cbs_rows = store.read_rows(config.path("lines") / "cbs_open_captures.csv")
    res = {"weeks": {}, "q3": q3_hook_values(sched)}
    total = Counter()
    for season, week in weeks:
        wk = sched.filter((pl.col("season") == season) & (pl.col("week") == week))
        ids = {r["game_id"] for r in ll_rows if int(r["season"]) == season and int(r["week"]) == week}
        wll = {g: ll[g] for g in ids}
        win = tuesday_window(wk)
        q1 = q1_candidates(wll, market_rows, cbs_rows, win)
        res["weeks"][f"{season}-w{week:02d}"] = {"league_lines": len(wll), "tuesday_window_utc": [w.isoformat() for w in win],
                                                 "q1_top": q1["candidates"][:8], "n_candidates": len(q1["candidates"])}
        total["games"] += len(wll)
    preds = store.read_rows(config.path("predictions") / "predictions.csv")
    res["q4"] = q4_movement(preds, ll)
    res["games_with_league_lines"] = total["games"]
    if out_md:
        _write(res, out_md)
    return res


def _write(res: dict, path) -> None:
    L = ["# CBS Pool Line-Setting: Report", "",
         "Rules: `docs/cbs_lines_preregistration.md`. Regenerate: `python -m engine cbs-lines`.", "",
         f"Games with a recorded pool line: **{res['games_with_league_lines']}**. A source counts as identified only "
         f"with ≥ {IDENTIFY_MIN_GAMES} games and a match rate ≥ {IDENTIFY_MIN_RATE:.0%}.", "",
         "## Q1: which source and time the pool line copies", ""]
    for wk, w in res["weeks"].items():
        L.append(f"### {wk}: {w['league_lines']} pool lines; Tuesday window {w['tuesday_window_utc'][0][:16]} to "
                 f"{w['tuesday_window_utc'][1][:16]} UTC")
        if not w["q1_top"]:
            L += ["", "No market or CBS-page snapshot inside the Tuesday window for this week "
                      "(captures began after it). Not analysable for Q1/Q2.", ""]
            continue
        L += ["", "| Source | Snapshot (UTC) | Games | Matched | Exact | Hook to fav | Hook to dog | Rate |",
              "|---|---|---|---|---|---|---|---|"]
        for c in w["q1_top"]:
            L.append(f"| {c['source']} | {c['snapshot_utc']} | {c['games']} | {c['matched']} | {c['exact']} | "
                     f"{c['hook_fav']} | {c['hook_dog']} | {c['rate']:.0%} |")
        L.append("")
    L += ["## Q3: what the half point is worth at each key number (2006–2025, whole-number closing lines)", "",
          "| Line | Games | P(favorite wins by exactly the line) | SE | Cover chance of the side the half point favors |",
          "|---|---|---|---|---|"]
    for r in res["q3"]:
        L.append(f"| {r['line']} | {r['games']} | {100 * r['p_exact']:.1f}% | {100 * r['se']:.1f} pp | "
                 f"{100 * (0.5 + r['p_exact'] / 2):.1f}% |")
    L += ["", "If the market's whole number is fair, each side covers half of the non-push games. When the pool "
              "turns it into a half-point line, the side the half point favors also wins every game that would "
              "have pushed: cover chance of about 50% + p/2. The live model already prices this through its margin "
              "distribution; this table shows the size of the effect.", "",
          "## Q4: market movement from the pool line to lock", ""]
    q4 = res["q4"]
    if q4.get("n"):
        L.append(f"{q4['n']} games: mean move {q4['mean']:+.2f}, mean absolute move {q4['abs_mean']:.2f}, "
                 f"moves of 1+ point {100 * q4['share_ge_1']:.0f}%.")
    else:
        L.append("No locked games yet.")
    from pathlib import Path
    Path(path).write_text("\n".join(L) + "\n")
