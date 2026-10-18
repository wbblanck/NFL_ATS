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
import sys
import time
import uuid

import polars as pl

from engine import config
from engine.data import league_lines, market, oddslink, oddspapi, store
from engine.models.margin_dist import MarginDist, TotalDist
from engine.picks.grading import is_half_point

FIELDS = [
    "prediction_id", "created_at", "season", "week", "game_id", "home_team", "away_team",
    "kickoff_utc", "lock_utc", "minutes_to_lock", "league_line", "cbs_open", "market_at_lock",
    "market_books", "drift", "model_margin", "p_home_cover", "p_away_cover", "pick", "pick_team",
    "pick_rule", "sim_count", "seed", "model_version", "feature_version", "data_snapshot",
    "training_period", "data_status", "missing_input", "expected_impact", "flags", "supersedes",
    "shadow_p_home_keynum", "shadow_pick_keynum", "market_total", "market_total_books",
]
# Shadow estimator: recorded for every pick, never used to pick (docs/keynumber_report.md).
SHADOW = "keynum"
MODEL_VERSION = "total-shifted-empirical-argmax"
# Market input (from 2026-10-04, the user's decision): Pinnacle's line at lock; the all-book median only when Pinnacle
# has no line, flagged MARKET_MEDIAN_FALLBACK. Recorded in feature_version as market:pinnacle / market:median.
MARKET_BOOK = "pinnacle"
ESTIMATOR = "shifted"   # fallback when no total is available (docs/phase4_results.md)
# Adopted per docs/total_report.md: width of the margin distribution depends on the market total.


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


def fit_total_dist(sched: pl.DataFrame, now: dt.datetime) -> TotalDist | None:
    if "total_line" not in sched.columns or "result" not in sched.columns:
        return None
    h = sched.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(),
                     pl.col("total_line").is_not_null(), pl.col("kickoff_utc") < now)
    if h.height < 500:
        return None
    return TotalDist("shifted_total").fit(-h["spread_line"].to_numpy(), h["result"].to_numpy(),
                                          h["total_line"].to_numpy())


def predictions_path():
    return config.path("predictions") / "predictions.csv"


def existing_game_ids() -> set[str]:
    return {r["game_id"] for r in store.read_rows(predictions_path())}


def _cbs_frozen() -> dict[str, float]:
    rows = store.read_rows(config.path("lines") / "cbs_open_frozen.csv")
    return {r["game_id"]: float(r["spread"]) for r in rows if r.get("spread")}


def decide(league_line: float | None, market_at_lock: float | None, cbs_open: float | None,
           dist=None) -> dict:
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
            p_home, p_away = dist(market_at_lock, line) if callable(dist) else dist.cover_probs(market_at_lock, line)
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


PROJ_FIELDS = ["prediction_id", "created_at", "season", "week", "game_id", "home_team", "away_team",
               "proj_home_pts", "proj_away_pts", "proj_line", "proj_median_margin", "league_line",
               "proj_p_home_cover", "proj_pick", "model_version", "hyperparams", "inputs"]
PROJ_VERSION, PROJ_H, PROJ_LAM = "proj-poisson-v1", 8, 5.0   # tuned on 1999-2006 (docs/projection_report.md)


def projections_path():
    return config.path("predictions") / "projections.csv"


def _record_projections(preds: list[dict], proj_games, now: dt.datetime, v3: dict | None = None) -> None:
    """Tracked comparison: score projections for the same games, archived separately (never picks).
    v1 (team scoring history) and, when `v3` inputs are given, proj-players-v3 (v1 x player/context
    multipliers, frozen model; docs/players_v3_report.md)."""
    import json
    import sys
    from engine.models import projection as P
    feats = {}
    if callable(v3):                     # built lazily for exactly the games being picked; never blocks picks
        try:
            v3 = v3([r["game_id"] for r in preds])
        except Exception as e:
            print("proj-players-v3 unavailable:", repr(e), file=sys.stderr)
            v3 = None
    if v3 is not None:
        for r in v3["features"].iter_rows(named=True):
            feats[(r["game_id"], r["team"])] = r
    rows = []
    for r in preds:
        try:
            rt = P.fit(proj_games, int(r["season"]) * 25 + int(r["week"]), int(r["season"]), PROJ_H, PROJ_LAM)
            home, away = P.FRANCHISE.get(r["home_team"], r["home_team"]), P.FRANCHISE.get(r["away_team"], r["away_team"])
            q = rt.rates(home, away)
        except Exception:
            continue
        variants = [(PROJ_VERSION, f"H={PROJ_H},lambda={PROJ_LAM}", q, "")]
        fh, fa = feats.get((r["game_id"], home)), feats.get((r["game_id"], away))
        missing = [c for f in (fh, fa) if f is not None for c in v3["model"]["features"] if f[c] is None] if v3 else []
        if v3 is not None and fh is not None and fa is not None and missing:
            print(f"proj-players-v3 skipped for {r['game_id']}: missing {sorted(set(missing))}", file=sys.stderr)
        elif v3 is not None and fh is not None and fa is not None:
            from engine.models import players_v3_live as L
            m = v3["model"]
            q3 = {"home_td": q["home_td"] * L.multiplier(fh, m, "td"), "home_fg": q["home_fg"] * L.multiplier(fh, m, "fg"),
                  "away_td": q["away_td"] * L.multiplier(fa, m, "td"), "away_fg": q["away_fg"] * L.multiplier(fa, m, "fg")}
            info = {side: {"starter": f["starter"], "qb_delta": round(f["qb_delta"], 4),
                           "starter_w_dropbacks": round(f["qb_wdropbacks"], 1), "depth_snapshot": f["snapshot"],
                           "qb1_out": f["qb1_out"], "injury_rows": f["n_injury_rows"],
                           **{g: round(f[g], 3) for g in ("ol", "skill", "opp_dl", "opp_lb", "opp_db")},
                           **{c: f[c] for c in ("rest_diff", "tz_shift", "division", "dome")},
                           "dome_estimated": f.get("dome_estimated", False),
                           "injury_status_published": f.get("injury_status_published")}
                    for side, f in (("home", fh), ("away", fa))}
            flags = [] if fh.get("injury_status_published") and fa.get("injury_status_published") else ["INJ_STATUS_MISSING"]
            if fh.get("snapshot") is None or fa.get("snapshot") is None:
                flags.append("NO_DEPTH_SNAPSHOT")
            info["flags"] = flags
            variants.append((L.VERSION, f"D={m['D']},k={m['k']},beta={m['trained_on']}", q3, json.dumps(info)))
        for version, hp, qq, inputs in variants:
            pr = P.Projection(P.points_pmf(qq["home_td"], qq["home_fg"], rt.p_xp, rt.p_2),
                              P.points_pmf(qq["away_td"], qq["away_fg"], rt.p_xp, rt.p_2))
            h, a = pr.mean_scores()
            line = r["league_line"]
            ph = pr.p_home_cover(float(line)) if line is not None and is_half_point(float(line)) else None
            rows.append({"prediction_id": r["prediction_id"], "created_at": now.isoformat(), "season": r["season"],
                         "week": r["week"], "game_id": r["game_id"], "home_team": r["home_team"], "away_team": r["away_team"],
                         "proj_home_pts": round(h, 1), "proj_away_pts": round(a, 1), "proj_line": round(pr.model_line(), 1),
                         "proj_median_margin": pr.median_margin(), "league_line": line,
                         "proj_p_home_cover": "" if ph is None else round(ph, 4),
                         "proj_pick": "" if ph is None else (r["home_team"] if ph > 0.5 else r["away_team"]),
                         "model_version": version, "hyperparams": hp, "inputs": inputs})
    store.append_rows(projections_path(), PROJ_FIELDS, rows)


def next_lock(sched: pl.DataFrame, now: dt.datetime, window_minutes: int, done: set[str]) -> tuple[dt.datetime | None, int]:
    """Earliest lock among games locking within `window_minutes` that have no final pick, and how many such games
    there are. Used by the waiting lock run, which picks each lock group `lead` minutes before its lock."""
    due = sched.filter((pl.col("lock_utc") > now) & (pl.col("lock_utc") <= now + dt.timedelta(minutes=window_minutes)),
                       ~pl.col("game_id").is_in(list(done)))
    if due.height == 0:
        return None, 0
    return due["lock_utc"].min(), due.height


EARLY_PICK_MIN = 15    # a pick made more than this long before lock used a stale market (week 3 picks ran 44-64 min early)
MIN_BOOKS = 5          # fewer books than this at lock: the market median is thin (week 3 low was 8)
PINNACLE_RETRY_WAIT_S = 60   # one retry, this long after the first capture, before a pick falls back to the median


def retry_missing_pinnacle(caps: list[dict], due: pl.DataFrame, events: list[dict] | None = None, *,
                           capture_fn=None, sleep_fn=None, wait_s: int | None = None) -> list[dict]:
    """Once, for games in `due` with no Pinnacle line in this capture: wait, capture again, and take the retry's rows
    for a game only when the retry has Pinnacle for it. A game's rows never mix two captures."""
    capture_fn = capture_fn or market.capture
    have = {r.get("game_id") for r in caps if r.get("book") == MARKET_BOOK and r.get("status") == "ok"}
    missing = due.filter(~pl.col("game_id").is_in(list(have)))
    if missing.height == 0:
        return caps
    (sleep_fn or time.sleep)(PINNACLE_RETRY_WAIT_S if wait_s is None else wait_s)
    try:
        again = capture_fn(missing, now=dt.datetime.now(dt.timezone.utc), events=events, all_games=True)
    except Exception:
        return caps            # a failed retry must never block a pick: keep the first capture's rows
    got = {r.get("game_id") for r in again if r.get("book") == MARKET_BOOK and r.get("status") == "ok"}
    if not got:
        return caps
    return [r for r in caps if r.get("game_id") not in got] + [r for r in again if r.get("game_id") in got]


# Owner asked for the 2026-10-18 SNF and 2026-10-19 MNF games only; off after that unless renewed.
ODDSPAPI_FALLBACK_UNTIL = dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.timezone.utc)


def oddspapi_pinnacle_fallback(caps: list[dict], due: pl.DataFrame, now: dt.datetime, *, rows_fn=None) -> list[dict]:
    """Owner decision 2026-10-18 (Parlay API down): for due games still without a Parlay Pinnacle line, take
    Pinnacle from OddsPapi, recorded as a pinnacle capture row with reason "oddspapi" and flagged
    MARKET_ODDSPAPI on the pick. Any OddsPapi failure leaves the capture as it was."""
    if now >= ODDSPAPI_FALLBACK_UNTIL:
        return caps
    have = {r.get("game_id") for r in caps if r.get("status") == "ok" and r.get("book") == MARKET_BOOK}
    missing = [g for g in due.to_dicts() if g["game_id"] not in have]
    if not missing:
        return caps
    try:
        if rows_fn is None:
            smap = oddspapi.load_spread_markets(config.path("lines") / oddspapi.SPREAD_MARKETS_FILE)
            rows_fn = lambda games, t: oddspapi.pinnacle_capture_rows(games, t, smap, capture_id="oddspapi-" + t.strftime("%Y%m%dT%H%M%SZ"))
        extra = rows_fn(missing, now)
    except Exception as e:
        print(f"OddsPapi Pinnacle fallback failed: {type(e).__name__}", file=sys.stderr)
        return caps
    if extra:
        store.append_rows(config.path("lines") / "market_captures.csv", market.FIELDS, extra)
        print(f"OddsPapi Pinnacle: {len(extra)} of {len(missing)} games without a Parlay Pinnacle line", file=sys.stderr)
    return caps + extra


def oddslink_pinnacle_fallback(caps: list[dict], due: pl.DataFrame, now: dt.datetime, *, rows_fn=None) -> list[dict]:
    """Owner decision 2026-10-18: OddsLink is the backup after OddsPapi, same rules and expiry; reason "oddslink",
    flag MARKET_ODDSLINK. Any OddsLink failure leaves the capture as it was."""
    if now >= ODDSPAPI_FALLBACK_UNTIL:
        return caps
    have = {r.get("game_id") for r in caps if r.get("status") == "ok" and r.get("book") == MARKET_BOOK}
    missing = [g for g in due.to_dicts() if g["game_id"] not in have]
    if not missing:
        return caps
    try:
        rows_fn = rows_fn or (lambda games, t: oddslink.pinnacle_capture_rows(
            games, t, capture_id="oddslink-" + t.strftime("%Y%m%dT%H%M%SZ")))
        extra = rows_fn(missing, now)
    except Exception as e:
        print(f"OddsLink Pinnacle fallback failed: {type(e).__name__}", file=sys.stderr)
        return caps
    if extra:
        store.append_rows(config.path("lines") / "market_captures.csv", market.FIELDS, extra)
        print(f"OddsLink Pinnacle: {len(extra)} of {len(missing)} games still without a Pinnacle line", file=sys.stderr)
    return caps + extra


def run(sched: pl.DataFrame, now: dt.datetime | None = None, window_minutes: int = 25,
        events: list[dict] | None = None, snapshot_id: str = "", game_id: str | None = None,
        totals: list[dict] | None = None, proj_games=None, v3: dict | None = None) -> list[dict]:
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
    caps = retry_missing_pinnacle(caps, due, events=events)
    caps = oddspapi_pinnacle_fallback(caps, due, now)
    caps = oddslink_pinnacle_fallback(caps, due, now)
    ll = {r["game_id"]: float(r["spread"]) for r in league_lines.load()}
    cbs = _cbs_frozen()
    dist, period = fit_dist(sched, now)
    tdist = fit_total_dist(sched, now)
    try:
        tot = market.parse_totals(totals if totals is not None else market.fetch_totals())
    except Exception:
        tot = {}
    sched_tot = {r["game_id"]: r["total_line"] for r in sched.select("game_id", "total_line").to_dicts()} \
        if "total_line" in sched.columns else {}
    shadow = None
    if dist is not None:
        shadow = MarginDist(kind=SHADOW).fit(dist.c, dist.m)
    out = []
    for g in due.sort("kickoff_utc").to_dicts():
        rows = [r for r in caps if r.get("game_id") == g["game_id"] and r.get("status") == "ok"]
        cons = market.consensus(rows, reference_book=MARKET_BOOK)
        use_ref = cons["reference"] is not None
        mkt_in = cons["reference"] if use_ref else cons["median"]
        mt = tot.get((g["home_team"], g["away_team"]))
        total, t_books, t_flag = (mt["median"], mt["n_books"], None) if mt else (sched_tot.get(g["game_id"]), 0, "TOTAL_FROM_SCHEDULE")
        use_total = tdist is not None and total is not None
        prob = (lambda mk, ln, T=total: tdist.cover_probs(mk, ln, T)) if use_total else dist
        d = decide(ll.get(g["game_id"]), mkt_in, cbs.get(g["game_id"]), prob)
        mkt = mkt_in
        mtl = (g["lock_utc"] - now).total_seconds() / 60
        flags = [f for f in d["flags"].split(";") if f]
        if mtl <= 0:
            flags.append("LATE_AFTER_LOCK")
        elif mtl > EARLY_PICK_MIN:
            flags.append("EARLY_PICK")
        if mkt_in is not None and not use_ref:
            flags.append("MARKET_MEDIAN_FALLBACK")
        if use_ref and any(r.get("book") == MARKET_BOOK and r.get("reason") == "oddspapi" for r in rows):
            flags.append("MARKET_ODDSPAPI")
        if use_ref and any(r.get("book") == MARKET_BOOK and r.get("reason") == "oddslink" for r in rows):
            flags.append("MARKET_ODDSLINK")
        if 0 < cons["n_books"] < MIN_BOOKS:
            flags.append("FEW_BOOKS")
        if use_total and t_flag:
            flags.append(t_flag)
        if not use_total and dist is not None:
            flags.append("NO_TOTAL_SHIFTED_FALLBACK")
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
            "market_at_lock": mkt_in, "market_books": cons["n_books"], "drift": d["drift"],
            "model_margin": "UNAVAILABLE" if mkt is None or dist is None else (
                f"{-mkt:+.1f} / {tdist.median_margin(mkt, total):+.1f}" if use_total
                else f"{-mkt:+.1f} / {dist.median_margin(mkt):+.0f}"),
            "p_home_cover": "UNAVAILABLE" if d["p_home"] is None else round(d["p_home"], 4),
            "p_away_cover": "UNAVAILABLE" if d["p_away"] is None else round(d["p_away"], 4),
            "pick": d["pick"], "pick_team": pick_team, "pick_rule": d["pick_rule"],
            "sim_count": 0, "seed": config.model().get("seed"),
            "model_version": (MODEL_VERSION if use_total else "phase4-shifted-empirical-argmax")
            if dist is not None else "phase3-drift-D0full",
            "feature_version": ("market:" + MARKET_BOOK) if use_ref else ("market:median" if mkt_in is not None else "none"), "data_snapshot": snapshot_id, "training_period": period,
            "data_status": d["data_status"], "missing_input": d["missing_input"],
            "expected_impact": d["expected_impact"], "flags": ";".join(flags), "supersedes": "",
            "shadow_p_home_keynum": sh_p, "shadow_pick_keynum": sh_pick,
            "market_total": total if total is not None else "", "market_total_books": t_books,
        })
    store.append_rows(predictions_path(), FIELDS, out)
    if proj_games is not None:
        _record_projections(out, proj_games, now, v3)
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
