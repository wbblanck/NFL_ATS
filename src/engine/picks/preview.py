"""Provisional picks for games that have not locked yet, from the LATEST captured market.

Not a final prediction: nothing is written to predictions.csv. The official, immutable
pick is made by lock-run 15-25 min before each lock, when the market may differ.
"""
from __future__ import annotations

import datetime as dt
import statistics

import polars as pl

from engine import config
from engine.data import league_lines, store
from engine.picks import final
from engine.picks.grading import is_half_point


def latest_market(game_ids: set[str]) -> dict[str, dict]:
    rows = [r for r in store.read_rows(config.path("lines") / "market_captures.csv")
            if r.get("status") == "ok" and r.get("game_id") in game_ids]
    out = {}
    for g in game_ids:
        rs = [r for r in rows if r["game_id"] == g]
        if not rs:
            continue
        t = max(r["captured_at"] for r in rs)
        pts = [float(r["home_spread"]) for r in rs if r["captured_at"] == t]
        pin = [float(r["home_spread"]) for r in rs if r["captured_at"] == t and r["book"] == "pinnacle"]
        out[g] = {"median": statistics.median(pts), "n_books": len(pts), "captured_at": t,
                  "pinnacle": pin[0] if pin else None}
    return out


def build(sched: pl.DataFrame, season: int, week: int, now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    wk = sched.filter((pl.col("season") == season) & (pl.col("week") == week)).sort("kickoff_utc")
    ll = {r["game_id"]: float(r["spread"]) for r in league_lines.load()}
    finals = {r["game_id"]: r for r in store.read_rows(final.predictions_path())}
    mk = latest_market(set(wk["game_id"].to_list()))
    dist, _ = final.fit_dist(sched, now)
    tdist = final.fit_total_dist(sched, now)
    out = []
    for g in wk.to_dicts():
        gid = g["game_id"]
        base = {"game_id": gid, "away": g["away_team"], "home": g["home_team"],
                "kickoff_utc": g["kickoff_utc"].isoformat(), "league_line": ll.get(gid)}
        if gid in finals:
            f = finals[gid]
            out.append({**base, "status": "final", "market": f["market_at_lock"], "drift": f["drift"],
                        "p_home": f["p_home_cover"], "p_away": f["p_away_cover"], "pick": f["pick_team"],
                        "flags": f["flags"], "market_time": f["created_at"]})
            continue
        if g["kickoff_utc"] <= now:
            out.append({**base, "status": "started_no_final_pick", "market": None, "drift": None,
                        "p_home": None, "p_away": None, "pick": None, "flags": "NO_FINAL_PICK", "market_time": None})
            continue
        m = mk.get(gid)
        total = g.get("total_line")
        use_t = tdist is not None and total is not None
        prob = (lambda a, b, T=total: tdist.cover_probs(a, b, T)) if use_t else dist
        d = final.decide(ll.get(gid), m["median"] if m else None, None, prob)
        flags = [x for x in d["flags"].split(";") if x] + ["PROVISIONAL"]
        pick = None if d["pick"] is None else (g["home_team"] if d["pick"] == "home" else g["away_team"])
        out.append({**base, "status": "provisional", "market": m["median"] if m else None,
                    "market_books": m["n_books"] if m else 0, "pinnacle": m["pinnacle"] if m else None,
                    "drift": d["drift"], "p_home": d["p_home"], "p_away": d["p_away"], "pick": pick,
                    "flags": ";".join(flags), "market_time": m["captured_at"] if m else None, "total": total})
    return out


def write_md(rows: list[dict], season: int, week: int) -> str:
    L = [f"# Preview — {season} week {week}\n",
         f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}. **Provisional** rows use the "
         "latest captured market and can change: the official pick is made at lock and archived in predictions.csv.\n",
         "| Game | Kickoff (UTC) | League line (home) | Market (home) | Drift | P(home)/P(away) | Pick | Status |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ph = "—" if r["p_home"] in (None, "", "UNAVAILABLE") else f"{float(r['p_home']):.3f}/{float(r['p_away']):.3f}"
        L.append(f"| {r['away']} @ {r['home']} | {r['kickoff_utc'][:16]} | {r['league_line'] if r['league_line'] is not None else 'MISSING'} | "
                 f"{r['market'] if r['market'] not in (None, '') else '—'} | {r['drift'] if r['drift'] not in (None, '') else '—'} | "
                 f"{ph} | **{r['pick'] or '—'}** | {r['status']} |")
    p = config.path("predictions") / f"preview_{season}_w{int(week):02d}.md"
    p.write_text("\n".join(L) + "\n")
    return str(p)
