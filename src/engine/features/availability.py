"""Player-availability features for proj-players-v1 (docs/players_preregistration.md)."""
from __future__ import annotations

import polars as pl

from engine.models.projection import FRANCHISE

OFF_POS_2025 = {"RB", "WR", "TE", "LT", "LG", "C", "RG", "RT"}
DEF_POS_2025 = {"LDE", "RDE", "LDT", "RDT", "NT", "LILB", "RILB", "MLB", "SLB", "WLB", "LCB", "RCB", "NB", "FS", "SS"}
OFF_POS_OLD = {"RB", "WR", "TE", "T", "G", "C"}
OUT = {"Out", "Doubtful"}


def _fr(c):
    return pl.col(c).replace(FRANCHISE)


def starters_by_game(sched: pl.DataFrame) -> pl.DataFrame:
    """Per team-game: actual starting QB and the established starter (mode of previous 4 REG starts)."""
    reg = sched.filter(pl.col("game_type") == "REG").sort("gameday", "gametime")
    long = pl.concat([
        reg.select("game_id", "season", "week", "gameday", "gametime", _fr("home_team").alias("team"),
                   pl.col("home_qb_id").alias("qb")),
        reg.select("game_id", "season", "week", "gameday", "gametime", _fr("away_team").alias("team"),
                   pl.col("away_qb_id").alias("qb")),
    ]).sort("team", "gameday", "gametime")
    rows = []
    for (team,), grp in long.group_by(["team"], maintain_order=True):
        prev = []
        for r in grp.to_dicts():
            est = max(set(prev[-4:]), key=prev[-4:].count) if prev else None
            rows.append({"game_id": r["game_id"], "team": team, "qb_actual": r["qb"], "qb_established": est})
            if r["qb"]:
                prev.append(r["qb"])
    return pl.DataFrame(rows)


def injuries_out(injuries: pl.DataFrame) -> pl.DataFrame:
    return injuries.filter(pl.col("report_status").is_in(list(OUT))).select(
        pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32), _fr("team").alias("team"), "gsis_id").unique()


def train_features(sched, depth_old, injuries) -> pl.DataFrame:
    """2012-2024: weekly depth charts (depth_team '1') + weekly injury reports."""
    st = starters_by_game(sched)
    reg = sched.filter(pl.col("game_type") == "REG").select("game_id", pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32),
                                                            _fr("home_team").alias("home"), _fr("away_team").alias("away"))
    d1 = depth_old.filter(pl.col("depth_team") == "1", pl.col("game_type") == "REG").with_columns(
        _fr("club_code").alias("team"), pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32))
    off = d1.filter(pl.col("formation") == "Offense", pl.col("position").is_in(list(OFF_POS_OLD))) \
        .select("season", "week", "team", "gsis_id").unique()
    de = d1.filter(pl.col("formation") == "Defense").select("season", "week", "team", "gsis_id").unique()
    out = injuries_out(injuries)
    off_out = off.join(out, on=["season", "week", "team", "gsis_id"]).group_by("season", "week", "team").len() \
        .rename({"len": "off_out"})
    def_out = de.join(out, on=["season", "week", "team", "gsis_id"]).group_by("season", "week", "team").len() \
        .rename({"len": "def_out"})
    tg = pl.concat([reg.select("game_id", "season", "week", pl.col("home").alias("team"), pl.col("away").alias("opp")),
                    reg.select("game_id", "season", "week", pl.col("away").alias("team"), pl.col("home").alias("opp"))])
    f = tg.join(st, on=["game_id", "team"], how="left") \
        .join(off_out, on=["season", "week", "team"], how="left") \
        .join(def_out.rename({"team": "opp", "def_out": "opp_def_out"}), on=["season", "week", "opp"], how="left")
    return f.with_columns(
        ((pl.col("qb_actual") != pl.col("qb_established")) & pl.col("qb_established").is_not_null())
        .fill_null(False).cast(pl.Int8).alias("qb_backup"),
        pl.col("off_out").fill_null(0).clip(0, 5), pl.col("opp_def_out").fill_null(0).clip(0, 5),
    ).select("game_id", "team", "qb_backup", "off_out", "opp_def_out")


def features_2025(sched, depth25, injuries, locks: pl.DataFrame) -> pl.DataFrame:
    """2025: last depth-chart snapshot strictly before each game's lock (point-in-time)."""
    st = starters_by_game(sched)
    out = injuries_out(injuries)
    d = depth25.with_columns(_fr("team").alias("team"), pl.col("pos_rank").cast(pl.Int32))
    snaps = d.select("team", "dt").unique()
    rows = []
    for g in locks.to_dicts():
        lock_iso = g["lock_utc"].strftime("%Y-%m-%dT%H:%M:%SZ")
        for team, opp in ((g["home"], g["away"]), (g["away"], g["home"])):
            rec = {"game_id": g["game_id"], "team": team}
            for side, who in (("own", team), ("opp", opp)):
                s = snaps.filter((pl.col("team") == who) & (pl.col("dt") < lock_iso))
                if s.height == 0:
                    rec[side] = None
                    continue
                dt_ = s["dt"].max()
                rec[side] = d.filter((pl.col("team") == who) & (pl.col("dt") == dt_) & (pl.col("pos_rank") == 1))
            own, oppd = rec.pop("own"), rec.pop("opp")
            wk_out = set(out.filter((pl.col("season") == g["season"]) & (pl.col("week") == g["week"])
                                    & (pl.col("team") == team))["gsis_id"].to_list())
            opp_out = set(out.filter((pl.col("season") == g["season"]) & (pl.col("week") == g["week"])
                                     & (pl.col("team") == opp))["gsis_id"].to_list())
            est = st.filter((pl.col("game_id") == g["game_id"]) & (pl.col("team") == team))["qb_established"]
            est = est[0] if est.len() else None
            qb1 = None if own is None else own.filter(pl.col("pos_abb") == "QB")["gsis_id"]
            qb1 = qb1[0] if qb1 is not None and qb1.len() else None
            rec["qb_backup"] = int(est is not None and ((qb1 is not None and qb1 != est) or est in wk_out))
            rec["off_out"] = 0 if own is None else min(5, len(set(own.filter(pl.col("pos_abb").is_in(list(OFF_POS_2025)))["gsis_id"].to_list()) & wk_out))
            rec["opp_def_out"] = 0 if oppd is None else min(5, len(set(oppd.filter(pl.col("pos_abb").is_in(list(DEF_POS_2025)))["gsis_id"].to_list()) & opp_out))
            rec["qb1"], rec["qb_established"] = qb1, est
            rows.append(rec)
    return pl.DataFrame(rows)
