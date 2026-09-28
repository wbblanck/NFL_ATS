"""Play-level efficiency ratings for proj-epa-v6 (docs/projection_v6_preregistration.md).

Per team-game metrics from play-by-play (offense view; defense = what it allowed):
  db_epa    mean EPA per dropback            (garbage time removed)
  rush_epa  mean EPA per designed rush       (garbage time removed)
  sr        success rate over counted plays  (garbage time removed)
  rz_td     TD share of red-zone drives      (drive outcome; no garbage-time filter)
Ratings before a game use only games that kicked off before it: values are centered by the previous season's
league mean, opponent-adjusted with the opponent's pre-game rating, combined by an exponentially weighted mean
(half-life h games, across seasons) and shrunk by (1 - s) at each new season.
"""
from __future__ import annotations

from collections import defaultdict

import polars as pl

from engine.models.projection import FRANCHISE

METRICS = ("db", "rush", "sr", "rz")
FEATURES = [f"off_{m}" for m in METRICS] + [f"def_{m}" for m in METRICS]
PBP_COLS = ["game_id", "season", "season_type", "posteam", "defteam", "pass", "rush", "qb_dropback", "qb_kneel",
            "qb_spike", "two_point_attempt", "epa", "success", "wp", "half_seconds_remaining", "fixed_drive",
            "fixed_drive_result", "drive_inside20"]


def _team(c: str) -> pl.Expr:
    return pl.col(c).replace(FRANCHISE)


def counted_plays(pbp: pl.DataFrame) -> pl.DataFrame:
    """Scrimmage plays that count, with the garbage-time flag (kept, so the removed share can be reported)."""
    p = pbp.filter(((pl.col("pass") == 1) | (pl.col("rush") == 1)), pl.col("qb_kneel").fill_null(0) == 0,
                   pl.col("qb_spike").fill_null(0) == 0, pl.col("two_point_attempt").fill_null(0) == 0,
                   pl.col("epa").is_not_null(), pl.col("posteam").is_not_null())
    return p.with_columns(
        (pl.col("wp").is_null() | (pl.col("wp") < 0.10) | (pl.col("wp") > 0.90)
         | (pl.col("half_seconds_remaining") <= 120)).alias("garbage"))


def game_metrics(pbp: pl.DataFrame) -> pl.DataFrame:
    """One row per (game_id, team) on offense: the four metrics and their counts (null when no such play)."""
    p = counted_plays(pbp).filter(~pl.col("garbage")).with_columns(_team("posteam").alias("team"))
    plays = p.group_by("game_id", "team").agg(
        pl.col("epa").filter(pl.col("qb_dropback") == 1).mean().alias("db"),
        (pl.col("qb_dropback") == 1).sum().alias("n_db"),
        pl.col("epa").filter((pl.col("rush") == 1) & (pl.col("qb_dropback") == 0)).mean().alias("rush"),
        ((pl.col("rush") == 1) & (pl.col("qb_dropback") == 0)).sum().alias("n_rush"),
        pl.col("success").mean().alias("sr"), pl.len().alias("n_plays"))
    drives = pbp.filter(pl.col("posteam").is_not_null(), pl.col("fixed_drive").is_not_null()) \
        .group_by("game_id", "fixed_drive").agg(_team("posteam").first().alias("team"),
                                                 pl.col("drive_inside20").max().alias("in20"),
                                                 pl.col("fixed_drive_result").first().alias("res"))
    rz = drives.filter(pl.col("in20") == 1).group_by("game_id", "team").agg(
        (pl.col("res") == "Touchdown").mean().alias("rz"), pl.len().alias("n_rz"))
    return plays.join(rz, on=["game_id", "team"], how="full", coalesce=True)


def with_order_time(sched: pl.DataFrame) -> pl.DataFrame:
    """kickoff_utc, filled from the game date (17:00 UTC) when the kickoff time is missing (all of 1999 in
    nflverse). Used both to order games and to cut data in the point-in-time check."""
    day = pl.col("gameday").str.strptime(pl.Datetime("us"), "%Y-%m-%d").dt.replace_time_zone("UTC") \
        + pl.duration(hours=17)
    return sched.with_columns(pl.coalesce(pl.col("kickoff_utc"), day).alias("kickoff_utc"))


def team_games(sched: pl.DataFrame, metrics: pl.DataFrame) -> pl.DataFrame:
    """Team-game rows for every completed game (all game types) in kickoff order, with the team's offensive
    values and the values it allowed (its opponent's offensive values)."""
    if "gameday" in sched.columns:
        sched = with_order_time(sched)
    s = sched.filter(pl.col("home_score").is_not_null()).select(
        "game_id", "season", "game_type", "kickoff_utc", _team("home_team").alias("home"), _team("away_team").alias("away"))
    rows = pl.concat([s.select("game_id", "season", "game_type", "kickoff_utc", pl.col("home").alias("team"),
                               pl.col("away").alias("opp")),
                      s.select("game_id", "season", "game_type", "kickoff_utc", pl.col("away").alias("team"),
                               pl.col("home").alias("opp"))])
    off = metrics.select("game_id", "team", *[pl.col(m).alias(f"o_{m}") for m in METRICS])
    allowed = metrics.select("game_id", pl.col("team").alias("opp"), *[pl.col(m).alias(f"a_{m}") for m in METRICS])
    return rows.join(off, on=["game_id", "team"], how="left").join(allowed, on=["game_id", "opp"], how="left") \
        .sort("kickoff_utc", "game_id", "team")


def league_means(tg: pl.DataFrame) -> dict:
    """season -> metric -> league mean over that season's regular-season team-games (offense view)."""
    reg = tg.filter(pl.col("game_type") == "REG")
    out = {}
    for s, g in reg.group_by("season"):
        mm = {m: g[f"o_{m}"].drop_nulls().mean() for m in METRICS}
        if all(v is not None for v in mm.values()):      # a season with no played games yet has no mean (unused)
            out[int(s[0])] = {m: float(v) for m, v in mm.items()}
    return out


def ratings(tg: pl.DataFrame, half_life: float, shrink: float, means: dict | None = None,
            end_of_regular_season: dict | None = None) -> pl.DataFrame:
    """Pre-game ratings for every team-game in tg: off_<m> (above average = better offense) and def_<m>
    (above average = more allowed = worse defense). Uses only earlier games.
    If `end_of_regular_season` is a dict, it is filled with season -> team -> (off, def) as of the end of that
    season's regular season (for the validation check; not used by the model)."""
    means = means if means is not None else league_means(tg)
    first = min(means) if means else None
    alpha = 1 - 0.5 ** (1 / half_life)
    off, de = defaultdict(lambda: dict.fromkeys(METRICS, 0.0)), defaultdict(lambda: dict.fromkeys(METRICS, 0.0))
    seen: dict = {}
    out = []
    reg_open = None
    for gid, g in tg.group_by("game_id", maintain_order=True):
        rows = g.to_dicts()
        season = rows[0]["season"]
        if end_of_regular_season is not None:
            if reg_open is not None and (season != reg_open or rows[0]["game_type"] != "REG"):
                end_of_regular_season[reg_open] = {t: ({**off[t]}, {**de[t]}) for t in list(off)}
                reg_open = None
            if rows[0]["game_type"] == "REG":
                reg_open = season
        # previous season's league mean (the first season has none: its own mean, warm-up only; disclosed)
        c = means.get(season - 1) or (means[first] if first is not None else dict.fromkeys(METRICS, 0.0))
        for r in rows:
            t = r["team"]
            if seen.get(t) != season:
                if t in seen:
                    for m in METRICS:
                        off[t][m] *= (1 - shrink)
                        de[t][m] *= (1 - shrink)
                seen[t] = season
        pre = {r["team"]: ({**off[r["team"]]}, {**de[r["team"]]}) for r in rows}
        for r in rows:
            po, pd_ = pre[r["team"]]
            out.append({"game_id": gid[0], "team": r["team"], **{f"off_{m}": po[m] for m in METRICS},
                        **{f"defr_{m}": pd_[m] for m in METRICS}})
        for r in rows:
            t, o = r["team"], r["opp"]
            if o not in pre:
                continue
            for m in METRICS:
                v = r[f"o_{m}"]
                if v is not None:
                    off[t][m] += alpha * ((v - c[m]) - pre[o][1][m] - off[t][m])
                a = r[f"a_{m}"]
                if a is not None:
                    de[t][m] += alpha * ((a - c[m]) - pre[o][0][m] - de[t][m])
    if end_of_regular_season is not None and reg_open is not None:
        end_of_regular_season[reg_open] = {t: ({**off[t]}, {**de[t]}) for t in list(off)}
    return pl.DataFrame(out)


def features(tg: pl.DataFrame, rt: pl.DataFrame) -> pl.DataFrame:
    """Per team-game: the team's offensive ratings and the OPPONENT's defensive ratings (what it allows)."""
    own = rt.select("game_id", "team", *[f"off_{m}" for m in METRICS])
    opp = rt.select("game_id", pl.col("team").alias("opp"), *[pl.col(f"defr_{m}").alias(f"def_{m}") for m in METRICS])
    base = tg.select("game_id", "season", "game_type", "kickoff_utc", "team", "opp")
    return base.join(own, on=["game_id", "team"], how="left").join(opp, on=["game_id", "opp"], how="left")


def build(sched: pl.DataFrame, pbp_metrics: pl.DataFrame, half_life: float, shrink: float,
          means: dict | None = None) -> pl.DataFrame:
    tg = team_games(sched, pbp_metrics)
    return features(tg, ratings(tg, half_life, shrink, means))
