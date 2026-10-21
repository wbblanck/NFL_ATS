"""2025 holdout (docs/holdout2025_preregistration.md). Frozen line = CBS odds-page Open,
market = nflverse close, distribution trained on 1999-2024 only. No retuning."""
from __future__ import annotations

import datetime as dt
import glob
import math
import re

import polars as pl

from engine import config
from engine.data import cbs_lines, nflverse
from engine.models.margin_dist import MarginDist
from engine.picks.grading import is_half_point

USER_WINS, USER_GAMES = 141, 272


def cbs_opens_2025(sched: pl.DataFrame) -> pl.DataFrame:
    rows = []
    files = glob.glob(str(config.ROOT / "docs/evidence/probe/*/cbs_odds_2025_w*.html"))
    latest = {}
    for f in sorted(files):
        w = int(re.search(r"_w(\d+)\.html", f).group(1))
        latest[w] = f            # sorted by probe stamp -> last wins
    reg = sched.filter(pl.col("season") == 2025)
    for w, f in sorted(latest.items()):
        for r in cbs_lines.match_games(cbs_lines.parse_odds_page(open(f).read()), reg):
            if r.get("game_id") and r.get("spread") is not None:
                rows.append({"game_id": r["game_id"], "cbs_open": float(r["spread"]), "page_week": w})
    return pl.DataFrame(rows).unique("game_id", keep="first")


def run(out_md=None) -> dict:
    sched, sid = nflverse.regular_season_schedule(save=False)
    hist = sched.filter(pl.col("season") <= 2024, pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())
    md = MarginDist("shifted").fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy())
    g = sched.filter(pl.col("season") == 2025, pl.col("result").is_not_null(), pl.col("spread_line").is_not_null()) \
        .select("game_id", "week", "home_team", "away_team", pl.col("result").alias("margin"),
                (-pl.col("spread_line")).alias("close"))
    opens = cbs_opens_2025(sched)
    d = g.join(opens, on="game_id", how="left")
    missing = d.filter(pl.col("cbs_open").is_null()).height
    d = d.filter(pl.col("cbs_open").is_not_null())
    p = md.sf(-d["cbs_open"].to_numpy(), d["close"].to_numpy())
    d = d.with_columns(pl.Series("p_home", p)).with_columns(
        pl.when(pl.col("p_home") > 0.5).then(pl.lit("home")).otherwise(pl.lit("away")).alias("pick"),
        pl.when(pl.col("margin") > -pl.col("cbs_open")).then(pl.lit("home"))
        .when(pl.col("margin") < -pl.col("cbs_open")).then(pl.lit("away")).otherwise(pl.lit("push")).alias("result"),
        pl.col("cbs_open").map_elements(is_half_point, return_dtype=pl.Boolean).alias("half"),
        (pl.col("close") - pl.col("cbs_open")).alias("drift"),
    ).with_columns(pl.when(pl.col("result") == "push").then(pl.lit("P"))
                   .when(pl.col("result") == pl.col("pick")).then(pl.lit("W")).otherwise(pl.lit("L")).alias("o"))

    def s(x):
        w, l, pu = (int((x["o"] == k).sum()) for k in ("W", "L", "P"))
        n = w + l; r = w / n if n else float("nan")
        return {"W": w, "L": l, "P": pu, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n) if n else float("nan")}
    prim = s(d.filter(pl.col("half")))
    res = {"primary_half_point": prim, "whole_number_opens": s(d.filter(~pl.col("half"))), "all": s(d),
           "drift_ge1": s(d.filter(pl.col("drift").abs() >= 1)), "drift_lt1": s(d.filter(pl.col("drift").abs() < 1)),
           "missing_open": missing, "games": g.height,
           "projected_272": prim["win_rate"] * USER_GAMES,
           "projected_272_lo": (prim["win_rate"] - 1.96 * prim["se"]) * USER_GAMES,
           "projected_272_hi": (prim["win_rate"] + 1.96 * prim["se"]) * USER_GAMES,
           "per_week": pl.DataFrame([{"week": w, **s(d.filter(pl.col("week") == w))} for w in range(1, 19)])}
    d.write_csv(config.path("backtests") / "holdout2025_games.csv")
    if out_md:
        out_md.write_text(_md(res, sid))
    return res


def _md(r, sid):
    f = lambda x: f"{x['W']}-{x['L']}-{x['P']} (N {x['N']}), {x['win_rate']:.4f} ± {x['se']:.4f}"  # noqa: E731
    wk = r["per_week"]
    lines = ["| Week | W | L | P | Win rate |", "|---|---|---|---|---|"] + \
        [f"| {x['week']} | {x['W']} | {x['L']} | {x['P']} | {x['win_rate']:.3f} |" for x in wk.to_dicts()]
    return "\n".join([
        "# 2025 Holdout — results\n",
        f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `python -m engine holdout2025` "
        f"(nflverse snapshot {sid}). Pre-registration: `docs/holdout2025_preregistration.md`.\n",
        f"2025 regular-season games: {r['games']}; without a parsable CBS open: {r['missing_open']}.\n",
        f"- **Primary (half-point CBS open):** {f(r['primary_half_point'])}",
        f"- Whole-number CBS open: {f(r['whole_number_opens'])}",
        f"- All: {f(r['all'])}",
        f"- Diagnostic — market moved ≥ 1 pt from CBS open: {f(r['drift_ge1'])}; < 1 pt: {f(r['drift_lt1'])}\n",
        f"Projected over 272 games: **{r['projected_272']:.0f} wins** (95% range {r['projected_272_lo']:.0f}–"
        f"{r['projected_272_hi']:.0f}). User's hand-picked 2025: **141** (vs the league line, a different line).\n",
        "## Per week\n", *lines])
