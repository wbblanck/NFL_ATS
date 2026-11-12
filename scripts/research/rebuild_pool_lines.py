"""Rebuild 2018-2022 pool lines from ESPN's Tuesday-noon market (research only).

Inputs (data/raw/espn_history/): games, spread_movements, moneyline_movements (2018-2022).
Output: data/raw/espn_history/rebuilt_pool_lines_2018_2022.csv

Line at Tuesday 12:00 ET (last move at or before). Home spread S, negative = home favored.
- S on a half point: kept.
- S whole, spread prices uneven: half point toward the pricier side (the registered juice rule).
- S whole, spread prices even: use the moneyline. The no-vig home win probability is compared with
  the median for games at the same S (all 2018-2022 Tuesday-noon lines); a stronger home team than
  usual at S means the fair line is below S, so S - 0.5, otherwise S + 0.5.
The moneyline rule is also scored where the juice rule decides, as an agreement check.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "raw" / "espn_history"
ET = "America/New_York"
KNOWN_POOL = {"2021_07_HOU_ARI": -16.5, "2021_07_IND_SF": -3.5, "2021_07_NO_SEA": 5.5,
              "2021_18_KC_DEN": 10.5, "2021_18_DAL_PHI": 7.5, "2021_18_CHI_MIN": -2.5}


def implied(american: pd.Series) -> pd.Series:
    a = american.astype(float)
    return np.where(a < 0, -a / (-a + 100), 100 / (a + 100))


def at_noon(moves: pd.DataFrame, noon: pd.Series) -> pd.DataFrame:
    x = moves.merge(noon.rename("noon"), left_on="game_id", right_index=True)
    x = x[x.t <= x.noon].sort_values("t")
    return x.groupby("game_id").last()


def main() -> None:
    g = pd.read_csv(D / "games_2018_2022.csv")
    g["kick"] = pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize(ET)
    noon = (g.kick.dt.normalize() - pd.to_timedelta((g.kick.dt.dayofweek - 1) % 7, unit="D")
            + pd.Timedelta(hours=12))
    noon.index = g.game_id
    sp = pd.read_csv(D / "spread_movements_2018_2022.csv")
    ml = pd.read_csv(D / "moneyline_movements_2018_2022.csv")
    for m in (sp, ml):
        m["t"] = pd.to_datetime(m.line_date_utc, utc=True)
    sp = at_noon(sp.dropna(subset=["home_spread"]), noon)
    ml = at_noon(ml.dropna(subset=["home_odds", "away_odds"]), noon)
    ml = ml[(ml.home_odds != 0) & (ml.away_odds != 0)]
    ph, pa = implied(ml.home_odds), implied(ml.away_odds)
    ml["p_home"] = ph / (ph + pa)
    t = sp[["home_spread", "home_odds", "away_odds"]].join(ml[["p_home"]], how="left")
    t = t.rename(columns={"home_odds": "spread_home_odds", "away_odds": "spread_away_odds"})
    med = t.groupby("home_spread").p_home.median()
    t["p_median_at_S"] = t.home_spread.map(med)
    whole = t.home_spread * 2 % 2 == 0
    juice = np.where(t.spread_home_odds < t.spread_away_odds, -0.5,
                     np.where(t.spread_home_odds > t.spread_away_odds, 0.5, np.nan))
    mlr = np.where(t.p_home > t.p_median_at_S, -0.5,
                   np.where(t.p_home < t.p_median_at_S, 0.5, np.nan))
    t["juice_dir"] = np.where(whole, juice, np.nan)
    t["ml_dir"] = np.where(whole, mlr, np.nan)
    t["method"] = np.where(~whole, "half", np.where(~np.isnan(t.juice_dir), "juice",
                           np.where(~np.isnan(t.ml_dir), "moneyline", "undecided")))
    adj = np.where(t.method == "juice", t.juice_dir, np.where(t.method == "moneyline", t.ml_dir, 0.0))
    t["rebuilt_pool"] = np.where(t.method == "undecided", np.nan, t.home_spread + adj)
    t = t.join(g.set_index("game_id")[["season", "week"]])
    t.reset_index().to_csv(D / "rebuilt_pool_lines_2018_2022.csv", index=False)

    print("Methods:", t.method.value_counts().to_dict())
    both = t[(t.method == "juice") & t.ml_dir.notna()]
    agree = (both.ml_dir == both.juice_dir)
    print(f"Moneyline vs juice rule where juice decides: agree {int(agree.sum())}/{len(both)} "
          f"({agree.mean():.0%})")
    for s in sorted(both.season.unique()):
        b = both[both.season == s]
        print(f"  {s}: {int((b.ml_dir == b.juice_dir).sum())}/{len(b)}")
    print("Known 2021 pool lines:")
    for gid, p in KNOWN_POOL.items():
        r = t.loc[gid]
        print(f"  {gid}: noon {r.home_spread:+.1f} ({r.method}) -> rebuilt {r.rebuilt_pool:+.1f}, pool {p:+.1f}"
              f"{'  MATCH' if r.rebuilt_pool == p else ''}")


if __name__ == "__main__":
    main()
