"""Phase 2 report: null baselines against every available opening-line source.

Sources (see docs/data_audit.md 0.3/0.4):
  league     CBS Pick'em spread recorded from the pool (the real grading line)
  sbro_open  SBRO opening line, 2007-2021 (opening proxy; book unnamed)
  sbro_close SBRO closing line, 2007-2021 (reference only)
  nfl_close  nflverse spread_line, 1999-2025 (closing proxy; NOT an opener)
Scores always come from nflverse. Regular season only (config.league.game_types).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from engine import config
from engine.data import league_lines, nflverse, sbro
from engine.models.null import baseline_table


def games_with_lines(sched: pl.DataFrame) -> dict[str, pl.DataFrame]:
    reg = sched.filter(pl.col("game_type").is_in(list(config.league().game_types)),
                       pl.col("home_score").is_not_null(), pl.col("away_score").is_not_null())
    base = reg.select("game_id", "season", "week", "home_team", "away_team",
                      (pl.col("home_score") - pl.col("away_score")).alias("margin"),
                      (-pl.col("spread_line")).alias("nfl_close"))
    out = {"nfl_close": base.filter(pl.col("nfl_close").is_not_null())
           .rename({"nfl_close": "home_spread"})}

    raw = config.ROOT / "data" / "raw" / "sbro"
    if any(raw.glob("nfl-odds-*.html")):
        m = sbro.match_schedule(sbro.load_all(raw), sched)
        m = m.filter(pl.col("match_status").str.starts_with("ok")
                     | pl.col("match_status").str.starts_with("score_mismatch"))
        proc = config.path("processed") / "sbro_lines.csv"
        m.select("game_id", "season", "date", "home_team", "away_team", "open_home_spread",
                 "close_home_spread", "open_status", "close_status", "raw_open", "raw_close",
                 "match_status").sort("game_id").write_csv(proc)
        j = base.drop("nfl_close").join(m.select("game_id", "open_home_spread", "close_home_spread"),
                                        on="game_id", how="inner")
        out["sbro_open"] = j.filter(pl.col("open_home_spread").is_not_null()) \
            .rename({"open_home_spread": "home_spread"}).drop("close_home_spread")
        out["sbro_close"] = j.filter(pl.col("close_home_spread").is_not_null()) \
            .rename({"close_home_spread": "home_spread"}).drop("open_home_spread")

    ll = league_lines.load()
    if ll:
        lf = pl.DataFrame([{"game_id": r["game_id"], "home_spread": float(r["spread"])} for r in ll])
        out["league"] = base.drop("nfl_close").join(lf, on="game_id", how="inner")
    return out


def _fmt(t: pl.DataFrame, by: str | None) -> str:
    cols = ([by] if by else []) + ["strategy", "W", "L", "P", "no_fav", "N", "win_rate", "se", "z_vs_50"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in t.select(cols).to_dicts():
        cells = []
        for c in cols:
            v = r[c]
            cells.append(f"{v:.4f}" if c in ("win_rate", "se", "z_vs_50") and v is not None else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def run(out_md: Path | None = None) -> dict[str, pl.DataFrame]:
    sched, sid = nflverse.regular_season_schedule(save=False)
    sched_all, _ = nflverse.pull("schedules", save=False)
    srcs = games_with_lines(sched_all)
    bt = config.path("backtests")
    results = {}
    md = ["# Phase 2 — Null model and baselines\n",
          f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by "
          f"`python -m engine baselines` (nflverse schedule snapshot {sid}). Regular season only. "
          "Scores from nflverse. W/L exclude pushes; P = game landed exactly on a whole-number line "
          "(impossible under league half-point lines, reported separately). no_fav = pick'em line, "
          "excluded from favorite/underdog. win_rate = W/(W+L); se = sqrt(p(1-p)/N); "
          "z_vs_50 = (win_rate - 0.5)/se. Interpretation: docs/phase2_report.md.\n"]
    for name in ("league", "sbro_open", "nfl_close", "sbro_close"):
        if name not in srcs:
            continue
        df = srcs[name]
        pooled = baseline_table(df)
        by_season = baseline_table(df, by=["season"])
        pooled.write_csv(bt / f"phase2_{name}_pooled.csv")
        by_season.write_csv(bt / f"phase2_{name}_by_season.csv")
        results[name] = pooled
        seasons = f"{df['season'].min()}–{df['season'].max()}" if df.height else "none"
        md.append(f"## Source: `{name}` — {df.height} graded games, seasons {seasons}\n")
        md.append("### Pooled\n\n" + _fmt(pooled, None) + "\n")
        md.append("### Per season\n\n" + _fmt(by_season, "season") + "\n")
    if out_md:
        out_md.write_text("\n".join(md))
    return results
