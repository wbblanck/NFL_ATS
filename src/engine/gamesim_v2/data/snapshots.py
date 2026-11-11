"""Point-in-time pregame player snapshots (gamesim v2, sprint 1, task 4).

For every regular-season team-game, one row per player in that team's candidate pool, built only from information dated
before the cutoff (kickoff minus 20 minutes, the pick time):
  * pool: players with at least one offensive or defensive snap in the team's previous 4 regular-season games, plus players
    on this game's injury report whose entry was last modified before the cutoff. A player who has played no snap for the team
    in 4 games and is not on the report is not in the pool; `pool_recall()` measures how often that matters.
  * workload: mean offensive and defensive snap share over the previous 4 team games (snap counts, PFR), and games played.
  * availability: the injury report status on this game's report and its `date_modified`. `p_active` is the share of players
    with that status who played, estimated only from seasons before this game's season.
  * abilities: the walk-forward on-field effects (pressure, completion) as of this game's week, with standard errors.
Depth charts are not used: before 2025 they are weekly and untimestamped, so what they knew at the cutoff cannot be checked.
Injury `date_modified` exists for 2016-2024 but not for 2025+; 2025+ rows are flagged `injury_ts_verified` False.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

import numpy as np
import polars as pl

SNAPSHOT_VERSION = "snapshot-v1"
CUTOFF_MINUTES = 20
WINDOW = 4


def kickoffs(sched: pl.DataFrame) -> pl.DataFrame:
    s = sched.filter(pl.col("game_type") == "REG").select(
        "game_id", pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64), "home_team", "away_team", "gameday", "gametime")
    return s.with_columns(pl.concat_str(["gameday", "gametime"], separator=" ").str.to_datetime(
        "%Y-%m-%d %H:%M", time_zone="America/New_York", strict=False).dt.convert_time_zone("UTC").alias("kickoff_utc"))


def team_games(ko: pl.DataFrame, franchise: dict) -> pl.DataFrame:
    a = ko.select("game_id", "season", "week", "kickoff_utc", pl.col("home_team").replace(franchise).alias("team"),
                  pl.col("away_team").replace(franchise).alias("opp"), pl.lit(True).alias("home"))
    b = ko.select("game_id", "season", "week", "kickoff_utc", pl.col("away_team").replace(franchise).alias("team"),
                  pl.col("home_team").replace(franchise).alias("opp"), pl.lit(False).alias("home"))
    return pl.concat([a, b]).sort("team", "kickoff_utc")


def snap_table(snaps: pl.DataFrame, ident: pl.DataFrame, franchise: dict) -> pl.DataFrame:
    m = ident.filter(pl.col("pfr_id").is_not_null()).select(pl.col("pfr_id").alias("pfr_player_id"), "uid")
    return snaps.filter(pl.col("game_type") == "REG").join(m, on="pfr_player_id", how="inner").select(
        "game_id", pl.col("team").replace(franchise).alias("team"), "uid", "position",
        pl.col("offense_snaps").fill_null(0), pl.col("defense_snaps").fill_null(0), pl.col("st_snaps").fill_null(0),
        pl.col("offense_pct").fill_null(0), pl.col("defense_pct").fill_null(0))


def injury_table(inj: pl.DataFrame, ko: pl.DataFrame, franchise: dict) -> pl.DataFrame:
    """One row per (game, team, gsis) with the latest report entry modified at or before the cutoff when timestamps exist."""
    has_ts = "date_modified" in inj.columns
    i = inj.filter(pl.col("game_type") == "REG").with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64),
                                                              pl.col("team").replace(franchise))
    tg = ko.select("game_id", "season", "week", "kickoff_utc", pl.col("home_team").replace(franchise).alias("team")).vstack(
        ko.select("game_id", "season", "week", "kickoff_utc", pl.col("away_team").replace(franchise).alias("team")))
    i = i.join(tg, on=["season", "week", "team"], how="inner").with_columns(
        (pl.col("kickoff_utc") - pl.duration(minutes=CUTOFF_MINUTES)).alias("cutoff_utc"))
    if has_ts:
        i = i.with_columns(pl.col("date_modified").alias("injury_ts"))
        ok = i["injury_ts"].is_not_null()
        i = i.with_columns(pl.col("injury_ts").is_not_null().alias("injury_ts_verified"))
        i = i.filter(~pl.col("injury_ts_verified") | (pl.col("injury_ts") <= pl.col("cutoff_utc")))
        i = i.sort("injury_ts").unique(["game_id", "team", "gsis_id"], keep="last")
    else:
        i = i.with_columns(pl.lit(None, dtype=pl.Datetime("us", "UTC")).alias("injury_ts"), pl.lit(False).alias("injury_ts_verified"))
        i = i.unique(["game_id", "team", "gsis_id"], keep="last")
    return i.select("game_id", "team", "gsis_id", pl.col("report_status").fill_null("none").alias("status"),
                    pl.col("practice_status").fill_null("none").alias("practice"), "report_primary_injury", "injury_ts",
                    "injury_ts_verified", "cutoff_utc")


def build_pool(tg: pl.DataFrame, sn: pl.DataFrame, injt: pl.DataFrame, ident: pl.DataFrame) -> pl.DataFrame:
    """Candidate pool with workload features, status and (for past games) whether the player actually played."""
    g2 = ident.filter(pl.col("gsis_id").is_not_null()).select("gsis_id", "uid")
    inj = injt.join(g2, on="gsis_id", how="inner").select("game_id", "team", "uid", "status", "practice", "report_primary_injury",
                                                          "injury_ts", "injury_ts_verified")
    by_game = {}
    for g, t, u, p, o, d_, op, dp, st in zip(sn["game_id"], sn["team"], sn["uid"], sn["position"], sn["offense_snaps"],
                                             sn["defense_snaps"], sn["offense_pct"], sn["defense_pct"], sn["st_snaps"]):
        by_game.setdefault((g, t), {})[u] = (p, o, d_, op, dp, st)
    rows = []
    hist: dict = {}
    for r in tg.iter_rows(named=True):
        key = (r["game_id"], r["team"])
        prev = hist.setdefault(r["team"], [])[-WINDOW:]
        pool: dict = {}
        for gk in prev:
            for u, (p, o, d_, op, dp, st) in by_game.get(gk, {}).items():
                if o + d_ > 0:
                    e = pool.setdefault(u, {"position": p, "gp": 0, "off": 0.0, "def": 0.0, "off_snaps": 0.0, "def_snaps": 0.0})
                    e["position"] = p
                    e["gp"] += 1
                    e["off"] += op
                    e["def"] += dp
                    e["off_snaps"] += o
                    e["def_snaps"] += d_
        actual = by_game.get(key, {})
        n_prev = max(len(prev), 1)
        for u, e in pool.items():
            rows.append({"game_id": r["game_id"], "season": r["season"], "week": r["week"], "team": r["team"], "uid": u,
                         "position": e["position"], "prev_games": len(prev), "games_played_prev": e["gp"],
                         "off_share_prev": e["off"] / n_prev, "def_share_prev": e["def"] / n_prev,
                         "off_share_active": e["off"] / e["gp"], "def_share_active": e["def"] / e["gp"],
                         "off_snaps_prev": e["off_snaps"], "def_snaps_prev": e["def_snaps"], "in_prev_pool": True})
        hist[r["team"]].append(key)
    pool_df = pl.DataFrame(rows)
    # add this game's injury-report players who are not already in the pool (workload unknown = zero)
    base = pool_df.join(inj, on=["game_id", "team", "uid"], how="full", coalesce=True)
    meta = tg.select("game_id", "season", "week", "team")
    base = base.drop("season", "week").join(meta, on=["game_id", "team"], how="left").with_columns(
        pl.col("in_prev_pool").fill_null(False), pl.col("status").fill_null("no_report"), pl.col("practice").fill_null("no_report"),
        pl.col("injury_ts_verified").fill_null(False))
    for c in ("games_played_prev", "off_share_prev", "def_share_prev", "off_share_active", "def_share_active", "off_snaps_prev", "def_snaps_prev", "prev_games"):
        base = base.with_columns(pl.col(c).fill_null(0))
    # outcome: played any snap in this game (known only after the game; used for calibration, never as a feature)
    played = sn.group_by("game_id", "team", "uid").agg(((pl.col("offense_snaps") + pl.col("defense_snaps") + pl.col("st_snaps")) > 0).any().alias("played"))
    played_def = sn.group_by("game_id", "team", "uid").agg(((pl.col("offense_snaps") + pl.col("defense_snaps")) > 0).any().alias("played_scrimmage"))
    base = base.join(played, on=["game_id", "team", "uid"], how="left").join(played_def, on=["game_id", "team", "uid"], how="left").with_columns(
        pl.col("played").fill_null(False).alias("outcome_played"), pl.col("played_scrimmage").fill_null(False).alias("outcome_played_scrimmage")).drop("played", "played_scrimmage")
    pos_fill = ident.select("uid", pl.col("position").alias("pos_ident"))
    base = base.join(pos_fill, on="uid", how="left").with_columns(pl.coalesce("position", "pos_ident").alias("position")).drop("pos_ident")
    return base


def p_active_table(pool: pl.DataFrame) -> pl.DataFrame:
    """Share who played (any scrimmage snap) by (report status, games played in the previous 4), per season, estimated from all
    EARLIER seasons only. Players with no prior snaps (not in the previous-4 pool) use the one-game row."""
    seasons = sorted(pool["season"].unique().to_list())
    rows = []
    for s in seasons:
        prev = pool.filter(pl.col("season") < s, pl.col("in_prev_pool"))
        if prev.height == 0:
            continue
        t = prev.group_by("status", "games_played_prev").agg(
            pl.col("outcome_played_scrimmage").mean().alias("p_active"), pl.len().alias("n"))
        for st, gp, p, n in t.iter_rows():
            rows.append({"season": s, "status": st, "gp_key": int(gp), "p_active": p, "n_train": n})
    return pl.DataFrame(rows)


def finalize(pool: pl.DataFrame, pa: pl.DataFrame, ko: pl.DataFrame) -> pl.DataFrame:
    x = pool.with_columns(pl.max_horizontal(pl.col("games_played_prev"), pl.lit(1)).cast(pl.Int64).alias("gp_key"))
    x = x.join(pa, on=["season", "status", "gp_key"], how="left")
    cut = ko.select("game_id", (pl.col("kickoff_utc") - pl.duration(minutes=CUTOFF_MINUTES)).alias("data_cutoff"))
    x = x.join(cut, on="game_id", how="left").with_columns(
        pl.col("p_active").fill_null(0.0).alias("p_active"),
        pl.max_horizontal("off_share_prev", "def_share_prev").alias("snap_share_prev"),
        pl.max_horizontal("off_share_active", "def_share_active").alias("snap_share_when_active"),
        pl.lit(SNAPSHOT_VERSION).alias("snapshot_version"))
    return x.with_columns((pl.col("p_active") * pl.col("snap_share_when_active")).alias("expected_share"))


PFR_GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "WR", "TE": "TE", "T": "OL", "G": "OL", "C": "OL", "OL": "OL",
             "OT": "OL", "C/G": "OL", "G/T": "OL", "G/C": "OL", "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "LB": "LB", "ILB": "LB",
             "OLB": "LB", "MLB": "LB", "CB": "DB", "S": "DB", "SS": "DB", "FS": "DB", "DB": "DB", "SAF": "DB"}


def add_position_group(x: pl.DataFrame, lookup: pl.DataFrame, ident: pl.DataFrame) -> pl.DataFrame:
    """`pos_grp`: the position group the matchup models use (weekly-roster position that season); PFR snap-count position as fallback."""
    g = ident.filter(pl.col("gsis_id").is_not_null()).select("uid", "gsis_id")
    lk = lookup.join(g, on="gsis_id").select(pl.col("season").cast(pl.Int64), "uid", pl.col("grp").alias("grp_roster"))
    return x.join(lk, on=["season", "uid"], how="left").with_columns(
        pl.coalesce("grp_roster", pl.col("position").replace_strict(PFR_GROUP, default=None)).alias("pos_grp")).drop("grp_roster")


def checksum(df: pl.DataFrame) -> str:
    return hashlib.sha256(df.sort("game_id", "team", "uid").write_csv().encode()).hexdigest()


ABILITY_KEYS = {"pressure": {"OL": "OL", "DL": "DL", "LB": "LB", "QB": "QB"},
                "completion": {"WR": "R", "TE": "R", "RB": "R", "DB": "DB", "LB": "LB", "QB": "QB"}}


def add_abilities(x: pl.DataFrame, ab: dict) -> pl.DataFrame:
    """Join walk-forward effects as of each game's (season, week). ab: {'pressure': long frame, 'completion': long frame} with columns
    season, week, key ('OL:uid'), beta, se, n_eff, n_raw. A player gets an effect for a model only if his position group is one the model
    estimates; otherwise the columns stay null. Raw logit effects, sign convention in DATA_DICTIONARY.md."""
    for kind, keymap in ABILITY_KEYS.items():
        k = x.with_columns(pl.col("pos_grp").replace_strict(keymap, default=None).alias("_g")).with_columns(
            (pl.col("_g") + ":" + pl.col("uid")).alias("key"))
        a = ab[kind].filter(pl.col("key").str.contains(":")).select(
            "season", "week", "key", pl.col("beta").alias(f"ab_{kind}"), pl.col("se").alias(f"ab_{kind}_se"),
            pl.col("n_eff").alias(f"ab_{kind}_neff"), pl.col("n_raw").alias(f"ab_{kind}_n"))
        k = k.join(a.with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64)), on=["season", "week", "key"], how="left")
        x = k.drop("_g", "key")
    return x
