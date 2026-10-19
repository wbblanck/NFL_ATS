"""Data and page for the ATS terminal (site/terminal.html), a redesign of the dashboard.

It reads the dashboard's own data (dashboard.build_data) and adds two things the old page did not carry:

* dist: for every game, the model's distribution of the final home margin, the same distribution the cover
  chance came from. A final pick is re-fit exactly as the pick was made: the margin model trained on games
  that had finished before the pick's created_at, at the market line and total recorded with the pick
  (final.fit_total_dist, else final.fit_dist). A provisional pick uses the latest market, like preview.build.
  check_dist() confirms the exported distribution reproduces the recorded cover chance.
* calib: one point per graded official pick: the recorded cover chance of the side picked, and whether it
  covered the pool line. The page bins these itself and shows the sample size of every bin.

Display only: nothing here writes a pick or a grade.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import polars as pl

from engine.data import store
from engine.picks import final

KMIN, KMAX = -40, 40
FINISHED_AFTER = dt.timedelta(hours=4)   # a game's result was available to a pick only once the game had ended


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def margin_pmf(model, c: float, total: float | None) -> dict:
    """P(home margin = k) for k in [KMIN, KMAX], plus both tails, from model.sf at half-integers."""
    t = np.arange(KMIN - 0.5, KMAX + 1.0, 1.0)                     # KMIN-.5 ... KMAX+.5
    if total is not None and hasattr(model, "scale"):
        sf = model.sf(t, np.full(t.size, c), np.full(t.size, total))
    else:
        sf = model.sf(t, np.full(t.size, c))
    sf = np.asarray(sf, float)
    p = sf[:-1] - sf[1:]
    return {"k0": KMIN, "p": [round(float(x), 5) for x in p], "lo": round(float(1 - sf[0]), 5),
            "hi": round(float(sf[-1]), 5), "c": c, "total": total,
            "model": "TotalDist shifted_total" if total is not None and hasattr(model, "scale") else f"MarginDist {final.ESTIMATOR}"}


def p_home_from(d: dict, league_line: float) -> float:
    """P(home covers a half-point pool line S) = P(margin > -S), from an exported pmf."""
    s = -league_line
    ks = np.arange(d["k0"], d["k0"] + len(d["p"]))
    return float(np.asarray(d["p"])[ks > s].sum() + d["hi"])


class _Models:
    """Margin models fit on games before a cutoff, cached by how many finished games that cutoff admits."""

    def __init__(self, sched: pl.DataFrame):
        self.sched = sched
        self.kick = sched.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())["kickoff_utc"]
        self.cache: dict = {}

    def at(self, when: dt.datetime):
        n = int((self.kick < when).sum())
        if n not in self.cache:
            self.cache[n] = (final.fit_total_dist(self.sched, when), final.fit_dist(self.sched, when)[0])
        return self.cache[n]


def distributions(sched: pl.DataFrame, rows: list[dict], now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    preds = {r["game_id"]: r for r in store.read_rows(final.predictions_path()) if not r.get("supersedes")}
    totals = {r["game_id"]: r.get("total_line") for r in sched.select("game_id", "total_line").to_dicts()}
    models, out = _Models(sched), {}
    for r in rows:
        gid, c = r["game_id"], _f(r.get("market"))
        if c is None:
            continue
        p = preds.get(gid)
        if r.get("status") == "final" and p:
            # The pick's model saw only finished games: games that kicked off in the hours before the pick were
            # still being played. Checked on every 2026 pick with a market: 41 of 44 reproduce the recorded cover
            # chance to its stored 4 decimals, the other 3 within 0.0001.
            when = dt.datetime.fromisoformat(p["created_at"]) - FINISHED_AFTER
            total = _f(p.get("market_total")) or _f(totals.get(gid))
        else:
            when, total = now, _f(r.get("total")) or _f(totals.get(gid))
        tdist, mdist = models.at(when)
        model = tdist if (tdist is not None and total is not None) else mdist
        if model is None:
            continue
        out[gid] = margin_pmf(model, c, total if model is tdist else None)
    return out


def check_dist(dists: dict, rows: list[dict], tol: float = 5.01e-5) -> dict:
    """How many exported distributions reproduce the cover chance recorded with the pick (stored to 4 decimals)."""
    n = ok = 0
    bad = []
    for r in rows:
        d, ll, ph = dists.get(r["game_id"]), _f(r.get("league_line")), _f(r.get("p_home"))
        if d is None or ll is None or ph is None:
            continue
        n += 1
        got = p_home_from(d, ll)
        if abs(got - ph) <= tol:
            ok += 1
        else:
            bad.append((r["game_id"], round(ph, 4), round(got, 4)))
    return {"n": n, "ok": ok, "bad": bad}


def calibration(graded: list[dict]) -> list[dict]:
    """[{p, w, week}] for graded official picks: recorded cover chance of the side picked, and the result."""
    preds = {r["game_id"]: r for r in store.read_rows(final.predictions_path()) if not r.get("supersedes")}
    out = []
    for g in graded:
        p = preds.get(g["game_id"])
        if not p:
            continue
        q = _f(p.get("p_home_cover")) if p.get("pick") == "home" else _f(p.get("p_away_cover"))
        if q is None:
            continue
        out.append({"p": round(q, 4), "w": 1 if g["result"] == "W" else 0, "week": int(g["week"]), "id": g["game_id"]})
    return out


def render(data: dict) -> str:
    from engine.picks.terminal_page import TEMPLATE
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload).replace("__TITLE__", f"Week {data.get('week')} · Bonsai ATS")
