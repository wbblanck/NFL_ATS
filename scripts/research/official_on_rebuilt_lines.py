"""Re-grade the official system (Phase 7 walk-forward, docs/phase7_report.md) with the
rebuilt 2018-2022 pool lines in place of the SBRO open. Research only.

The model is unchanged: trained each season on earlier seasons' nflverse close and margin,
pick = side with P(cover the frozen line) > 0.5. Only the frozen line changes.
Line sources compared on the same games: SBRO open (original), ESPN Tuesday-noon raw line,
rebuilt pool line (half / juice / moneyline rule; not yet validated).
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from engine.backtest import walk_forward as W  # noqa: E402

D = ROOT / "data" / "raw" / "espn_history"


def record(d: pl.DataFrame) -> str:
    w, l, p = (d.filter(pl.col("o") == k).height for k in "WLP")
    return f"{w}-{l}-{p} ({w / (w + l):.1%})" if w + l else "-"


def main() -> None:
    base = W.load()
    rb = pl.read_csv(D / "rebuilt_pool_lines_2018_2022.csv").select(
        "game_id", pl.col("home_spread").alias("tue_noon"), pl.col("rebuilt_pool"), "method")
    df = base.join(rb, on="game_id", how="left")
    srcs = {"SBRO open (original test)": "open", "ESPN Tuesday noon, raw": "tue_noon",
            "Rebuilt pool line": "rebuilt_pool"}
    preds = {}
    for name, col in srcs.items():
        x = df.drop("open").with_columns(pl.col(col).alias("open")) if col != "open" else df
        d, _ = W.predict(x, 2018, 2022)
        preds[name] = d.select("game_id", "season", "pick", "o", pl.col("open").alias("line"))
    common = set.intersection(*(set(p["game_id"]) for p in preds.values()))
    common21 = {g for g in common if int(g[:4]) <= 2021}
    allrb = set(preds["Rebuilt pool line"]["game_id"])
    print(f"Games with all three lines (2018-2021): {len(common21)}")
    for name, p in preds.items():
        q = p.filter(pl.col("game_id").is_in(list(common21)))
        by = "  ".join(f"{s}: {record(q.filter(pl.col('season') == s))}" for s in range(2018, 2022))
        print(f"  {name:28s} {record(q)}   [{by}]")
    a = preds["SBRO open (original test)"].filter(pl.col("game_id").is_in(list(common21)))
    b = preds["Rebuilt pool line"].filter(pl.col("game_id").is_in(list(common21)))
    j = a.join(b, on="game_id", suffix="_rb")
    print(f"  Picks that differ SBRO vs rebuilt: {j.filter(pl.col('pick') != pl.col('pick_rb')).height}")
    print(f"  Line differs: {j.filter(pl.col('line') != pl.col('line_rb')).height}")
    r22 = preds["Rebuilt pool line"].filter(pl.col("season") == 2022)
    print(f"Rebuilt pool line, 2022 (no SBRO): {record(r22)}")
    allp = preds["Rebuilt pool line"]
    print(f"Rebuilt pool line, all 2018-2022 games it covers ({len(allrb)}): {record(allp)}")


if __name__ == "__main__":
    main()
