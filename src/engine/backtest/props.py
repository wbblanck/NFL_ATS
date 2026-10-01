"""NFL player props: join Action Network lines to nflverse outcomes, and grade bets.

Plan and rules: docs/props_preregistration.md (2024 = exploration; 2025-2026 held out until
docs/props_confirm_preregistration.md is committed).

Joining: Action Network player ids are not nflverse ids, so a prop is matched to the nflverse player-game with
the same week and team by normalized full name (accents, punctuation and Jr/Sr/II-V suffixes removed), else by a
last name + first initial that is unique on that team that week. Unmatched props are kept and counted, never guessed.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import polars as pl

from engine import config

NON_BOOKS = {"15", "30"}                    # Action Network "Consensus" and "Open"
STAT = {                                    # market -> nflverse expression for the graded quantity
    "pass_yds": pl.col("passing_yards"), "pass_att": pl.col("attempts"), "pass_cmp": pl.col("completions"),
    "pass_td": pl.col("passing_tds"), "pass_int": pl.col("passing_interceptions"),
    "rush_yds": pl.col("rushing_yards"), "rush_att": pl.col("carries"), "rec": pl.col("receptions"),
    "rec_yds": pl.col("receiving_yards"), "rush_rec_yds": pl.col("rushing_yards") + pl.col("receiving_yards"),
    "pass_rush_yds": pl.col("passing_yards") + pl.col("rushing_yards"),
    "anytime_td": pl.col("rushing_tds") + pl.col("receiving_tds") + pl.col("special_teams_tds")
    + pl.col("fumble_recovery_tds"),
}
# Action Network abbreviations that differ from nflverse
TEAM_FIX = {"JAC": "JAX", "LAR": "LA", "WSH": "WAS"}


def norm_name(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'`\-]", " ", s)
    parts = [p for p in s.split() if p not in ("jr", "sr", "ii", "iii", "iv", "v")]
    out: list[str] = []
    for p in parts:                          # "d j moore" -> "dj moore", so D.J. and DJ agree
        if len(p) == 1 and out and len(out[-1]) >= 1 and out[-1].isalpha() and len(out[-1]) <= 2 \
                and all(len(x) == 1 for x in out[-1]):
            out[-1] += p
        else:
            out.append(p)
    return " ".join(out)


def last_name(s: str) -> str:
    """Last name plus first initial ("garrett wilson" -> "wilson g"), so a fallback never pairs M. Wilson
    with Garrett Wilson."""
    p = norm_name(s).split()
    return f"{p[-1]} {p[0][0]}" if len(p) >= 2 else (p[0] if p else "")


def american_to_decimal(a: float) -> float:
    return 1 + (a / 100 if a > 0 else 100 / -a)


def load_lines(season: int, path: Path | None = None) -> pl.DataFrame:
    path = path or config.ROOT / "data" / "props" / f"an_props_{season}.csv"
    d = pl.read_csv(path, infer_schema_length=0)
    return (d.with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64),
                           pl.col("line").cast(pl.Float64),
                           *(pl.col(c).replace("", None).cast(pl.Float64) for c in ("over_odds", "under_odds", "yes_odds")),
                           pl.col("player_team").replace(TEAM_FIX).alias("team"))
            .filter(~pl.col("book_id").is_in(list(NON_BOOKS))))


def load_stats(season: int) -> pl.DataFrame:
    import nflreadpy as nfl

    s = nfl.load_player_stats(seasons=[season]).filter(pl.col("season_type") == "REG")
    return s.select("player_id", "player_display_name", "position", "week", "team", "game_id",
                    *[e.alias(m) for m, e in STAT.items()])


def join(lines: pl.DataFrame, stats: pl.DataFrame) -> pl.DataFrame:
    """Attach nflverse player_id and the graded stat to every prop row; `match` says how (full/last/none)."""
    st = stats.with_columns(pl.col("player_display_name").map_elements(norm_name, return_dtype=pl.Utf8).alias("nkey"),
                            pl.col("player_display_name").map_elements(last_name, return_dtype=pl.Utf8).alias("lkey"))
    full = {(r["week"], r["team"], r["nkey"]): r["player_id"] for r in st.iter_rows(named=True)}
    lk = {}
    for r in st.iter_rows(named=True):
        lk.setdefault((r["week"], r["team"], r["lkey"]), set()).add(r["player_id"])
    ids, how = [], []
    for w, t, p in zip(lines["week"].to_list(), lines["team"].to_list(), lines["player"].to_list()):
        k = (w, t, norm_name(p))
        if k in full:
            ids.append(full[k]); how.append("full")
            continue
        c = lk.get((w, t, last_name(p)), set())
        if len(c) == 1:
            ids.append(next(iter(c))); how.append("last")
        else:
            ids.append(None); how.append("none" if not c else "ambiguous")
    out = lines.with_columns(pl.Series("player_id", ids, dtype=pl.Utf8), pl.Series("match", how))
    long = stats.unpivot(index=["player_id", "week", "position"], on=list(STAT), variable_name="market",
                         value_name="actual")
    return out.join(long, on=["player_id", "week", "market"], how="left")


def graded(d: pl.DataFrame) -> pl.DataFrame:
    """Over/under rows with both prices and a matched actual: de-vigged P(over), hold, result (W/L/P for over)."""
    ou = d.filter(pl.col("market") != "anytime_td", pl.col("over_odds").is_not_null(),
                  pl.col("under_odds").is_not_null(), pl.col("actual").is_not_null())
    io = 1 / ou["over_odds"].map_elements(american_to_decimal, return_dtype=pl.Float64)
    iu = 1 / ou["under_odds"].map_elements(american_to_decimal, return_dtype=pl.Float64)
    return ou.with_columns((io / (io + iu)).alias("p_over"), (io + iu - 1).alias("hold"),
                           pl.when(pl.col("actual") > pl.col("line")).then(pl.lit("over"))
                           .when(pl.col("actual") < pl.col("line")).then(pl.lit("under"))
                           .otherwise(pl.lit("push")).alias("result"))


def profit(odds: np.ndarray, won: np.ndarray) -> np.ndarray:
    """Profit per 1 unit staked at American odds; won is 1 (win), 0 (loss) or nan (push -> 0)."""
    dec = np.where(odds > 0, 1 + odds / 100, 1 + 100 / -odds)
    return np.where(np.isnan(won), 0.0, np.where(won == 1, dec - 1, -1.0))
