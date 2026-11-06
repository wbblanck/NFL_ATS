"""Coverage layer for the game simulator: man vs zone (docs/gamesim_coverage_preregistration.md).

Recency weights for every rate here: a game g games ago (counting that team's or player's games) weighs 0.5**(g/8),
times 0.7 for each season back (the G3 half-life and season regression). Only games before the one simulated count.
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from . import league as L
from .teams import FRANCHISE

H, R, KG = 8.0, 0.7, 8.0
SPLITS = ("comp", "int", "sack", "ypc")
# split -> (success, trials) on labeled dropbacks; ypc is (yards, completions)
CNT = {"comp": ("cp", "natt"), "int": ("it", "att"), "sack": ("sk", "db"), "ypc": ("cy", "cp")}


def labeled(pbp: pl.DataFrame, part: pl.DataFrame) -> pl.DataFrame:
    """Dropbacks (no penalty plays) with a man / zone label: one row per play."""
    d = L.scrimmage(pbp).filter(~pl.col("is_pen"), pl.col("is_db")).with_columns(
        pl.col("posteam").replace(FRANCHISE), pl.col("defteam").replace(FRANCHISE))
    p = part.select(pl.col("nflverse_game_id").alias("game_id"), pl.col("play_id").cast(d["play_id"].dtype),
                    pl.col("defense_man_zone_type").alias("cov"))
    d = d.join(p, on=["game_id", "play_id"], how="left").filter(pl.col("cov").is_in(["MAN_COVERAGE", "ZONE_COVERAGE"]))
    sk = pl.col("sack").fill_null(0) == 1
    sc = (pl.col("qb_scramble").fill_null(0) == 1) & ~sk
    it = (pl.col("interception").fill_null(0) == 1) & ~sk & ~sc
    cp = (pl.col("complete_pass").fill_null(0) == 1) & ~sk & ~sc & ~it
    return d.with_columns((pl.col("cov") == "MAN_COVERAGE").alias("man"), sk.alias("sk"), sc.alias("sc"), it.alias("it"),
                          cp.alias("cp")).with_columns(
        (~pl.col("sk") & ~pl.col("sc")).alias("att"), (~pl.col("sk") & ~pl.col("sc") & ~pl.col("it")).alias("natt"),
        pl.lit(True).alias("db"), pl.when(pl.col("cp")).then(pl.col("yards_gained")).otherwise(0.0).alias("cy"))


def team_games(lab: pl.DataFrame) -> pl.DataFrame:
    """Per team-game (offense rows): counts by coverage and overall."""
    agg = []
    for c in ("cp", "natt", "it", "att", "sk", "db", "cy"):
        agg += [pl.col(c).cast(pl.Float64).filter(pl.col("man")).sum().alias(c + "_m"),
                pl.col(c).cast(pl.Float64).filter(~pl.col("man")).sum().alias(c + "_z")]
    return lab.group_by("season", "week", "game_id", "posteam", "defteam").agg(*agg).sort("season", "week")


def _w(seasons_back: np.ndarray, games_ago: np.ndarray) -> np.ndarray:
    return 0.5 ** (games_ago / H) * R ** seasons_back


def _lo(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def pregame(tg: pl.DataFrame, ks: list[float]) -> dict:
    """Pre-game defense man rate and offense man / zone splits for every team-game in tg, for each k_cov in ks.
    Returns {"man": {(game_id, defteam): m}, "split": {k: {(game_id, posteam): {split_man/zone: delta}}}}."""
    rows = tg.to_dicts()
    mean_db = np.mean([r["db_m"] + r["db_z"] for r in rows])
    att_db = sum(r["att_m"] + r["att_z"] for r in rows) / sum(r["db_m"] + r["db_z"] for r in rows)
    cp_db = sum(r["cp_m"] + r["cp_z"] for r in rows) / sum(r["db_m"] + r["db_z"] for r in rows)
    per_db = {"comp": att_db, "int": att_db, "sack": 1.0, "ypc": cp_db}     # pseudo-dropbacks -> pseudo-trials
    hist_d, hist_o = {}, {}
    out_m, out_s = {}, {k: {} for k in ks}
    by_season = {}
    for r in rows:
        a = by_season.setdefault(r["season"], [0.0, 0.0])
        a[0] += r["db_m"]
        a[1] += r["db_m"] + r["db_z"]
    first = min(by_season)
    seen = [0.0, 0.0]      # first labeled season only: league rate from its earlier weeks
    by_week = {}
    for r in rows:
        by_week.setdefault((r["season"], r["week"]), []).append(r)
    for (season, week) in sorted(by_week):
        grp = by_week[(season, week)]
        if season == first:
            lm = seen[0] / seen[1] if seen[1] else 0.5
        else:
            prev = [by_season[x] for x in by_season if x < season]
            lm = sum(a[0] for a in prev) / sum(a[1] for a in prev)
        for r in grp:
            hd = hist_d.get(r["defteam"], [])
            if hd:
                sb = np.array([season - h["season"] for h in hd], float)
                ga = np.arange(len(hd))[::-1].astype(float)
                w = _w(sb, ga)
                num = (w * np.array([h["db_m"] for h in hd])).sum()
                den = (w * np.array([h["db_m"] + h["db_z"] for h in hd])).sum()
            else:
                num = den = 0.0
            kn = KG * mean_db
            out_m[(r["game_id"], r["defteam"])] = (num + kn * lm) / (den + kn)
            ho = hist_o.get(r["posteam"], [])
            if ho:
                sb = np.array([season - h["season"] for h in ho], float)
                ga = np.arange(len(ho))[::-1].astype(float)
                w = _w(sb, ga)
            for k in ks:
                d = {}
                for f, (a, b) in CNT.items():
                    if not ho:
                        d[f + "_man"] = d[f + "_zone"] = 0.0
                        continue
                    nm = (w * np.array([h[a + "_m"] for h in ho])).sum()
                    dm = (w * np.array([h[b + "_m"] for h in ho])).sum()
                    nz = (w * np.array([h[a + "_z"] for h in ho])).sum()
                    dz = (w * np.array([h[b + "_z"] for h in ho])).sum()
                    if dm + dz <= 0:
                        d[f + "_man"] = d[f + "_zone"] = 0.0
                        continue
                    ov = (nm + nz) / (dm + dz)
                    kk = k * per_db[f]
                    rm, rz = (nm + kk * ov) / (dm + kk), (nz + kk * ov) / (dz + kk)
                    if f == "ypc":
                        d[f + "_man"], d[f + "_zone"] = math.log(max(rm, 1e-3) / max(ov, 1e-3)), math.log(max(rz, 1e-3) / max(ov, 1e-3))
                    else:
                        d[f + "_man"], d[f + "_zone"] = _lo(rm) - _lo(ov), _lo(rz) - _lo(ov)
                out_s[k][(r["game_id"], r["posteam"])] = d
        for r in grp:
            hist_d.setdefault(r["defteam"], []).append(r)
            hist_o.setdefault(r["posteam"], []).append(r)
            if season == first:
                seen[0] += r["db_m"]
                seen[1] += r["db_m"] + r["db_z"]
    return {"man": out_m, "split": out_s}


def overall_comp(tg: pl.DataFrame) -> dict:
    """Pre-game overall completion rate on labeled attempts per offense (same weights; k = 8 games prior to league)."""
    rows = tg.to_dicts()
    lg = sum(r["cp_m"] + r["cp_z"] for r in rows) / sum(r["natt_m"] + r["natt_z"] for r in rows)
    mean_n = np.mean([r["natt_m"] + r["natt_z"] for r in rows])
    hist, out = {}, {}
    by_week = {}
    for r in rows:
        by_week.setdefault((r["season"], r["week"]), []).append(r)
    for (season, week) in sorted(by_week):
        for r in by_week[(season, week)]:
            ho = hist.get(r["posteam"], [])
            num = den = 0.0
            if ho:
                w = _w(np.array([season - h["season"] for h in ho], float), np.arange(len(ho))[::-1].astype(float))
                num = (w * np.array([h["cp_m"] + h["cp_z"] for h in ho])).sum()
                den = (w * np.array([h["natt_m"] + h["natt_z"] for h in ho])).sum()
            out[(r["game_id"], r["posteam"])] = (num + KG * mean_n * lg) / (den + KG * mean_n)
        for r in by_week[(season, week)]:
            hist.setdefault(r["posteam"], []).append(r)
    return out


# --------------------------------------------------------------------------------------------- receivers

def receiver_games(lab: pl.DataFrame) -> pl.DataFrame:
    """Per player-game on labeled targeted passes: targets, catches and yards by coverage, and team targets by coverage."""
    t = lab.filter(pl.col("receiver_player_id").is_not_null(), pl.col("att"))
    team = t.group_by("game_id", "posteam").agg(pl.col("man").sum().alias("tt_m"), (~pl.col("man")).sum().alias("tt_z"))
    pg = t.group_by("season", "week", "game_id", "posteam", pl.col("receiver_player_id").alias("player_id")).agg(
        pl.col("man").sum().alias("t_m"), (~pl.col("man")).sum().alias("t_z"),
        (pl.col("cp") & pl.col("man")).sum().alias("c_m"), (pl.col("cp") & ~pl.col("man")).sum().alias("c_z"),
        pl.col("cy").filter(pl.col("man")).sum().alias("y_m"), pl.col("cy").filter(~pl.col("man")).sum().alias("y_z"))
    return pg.join(team, on=["game_id", "posteam"], how="left").sort("season", "week")


def receiver_splits(rg: pl.DataFrame, ks: list[float], n_games: int = 16) -> dict:
    """{k: {(season, week, player_id): (share_mult_man, share_mult_zone, ypr_mult_man, ypr_mult_zone)}} from the
    player's previous n_games labeled games. Multipliers are relative to his overall share / yards per catch."""
    out = {k: {} for k in ks}
    hist: dict = {}
    by_week = {}
    for r in rg.to_dicts():
        by_week.setdefault((r["season"], r["week"]), []).append(r)
    weeks = sorted(by_week)
    players_seen: set = set()
    for (season, week) in weeks:
        for pid in list(players_seen | {r["player_id"] for r in by_week[(season, week)]}):
            h = hist.get(pid, [])[-n_games:]
            if not h:
                continue
            tm, tz = sum(x["t_m"] for x in h), sum(x["t_z"] for x in h)
            Tm, Tz = sum(x["tt_m"] for x in h), sum(x["tt_z"] for x in h)
            cm, cz = sum(x["c_m"] for x in h), sum(x["c_z"] for x in h)
            ym, yz = sum(x["y_m"] for x in h), sum(x["y_z"] for x in h)
            if Tm + Tz <= 0 or tm + tz <= 0:
                continue
            s = (tm + tz) / (Tm + Tz)
            catch = (cm + cz) / (tm + tz)
            ypr = (ym + yz) / max(cm + cz, 1)
            for k in ks:
                sm, sz = (tm + k * s) / (Tm + k), (tz + k * s) / (Tz + k)
                kc = k * catch
                if cm + cz > 0 and ypr > 0:
                    ypm, ypz = (ym + kc * ypr) / (cm + kc), (yz + kc * ypr) / (cz + kc)
                    yr = (max(ypm, 0.5) / ypr, max(ypz, 0.5) / ypr)
                else:
                    yr = (1.0, 1.0)
                out[k][(season, week, pid)] = (sm / s, sz / s, *yr)
        for r in by_week[(season, week)]:
            hist.setdefault(r["player_id"], []).append(r)
            players_seen.add(r["player_id"])
    return out


# ------------------------------------------------------------------------------------------- engine inputs

def arrays(gg: pl.DataFrame, sims: int, cov: dict, k: float) -> dict:
    """Engine `cover` arrays for a chunk of prepared games (home side 0, away side 1)."""
    mdef = float(np.mean(list(cov["man"].values())))
    sp_k = cov["split"][k]
    G = gg.height
    m = np.zeros((G, 2))
    sp = np.zeros((G, 2, 2, 4))
    for j, (gid, ht, at) in enumerate(zip(gg["game_id"], gg["home_team"], gg["away_team"])):
        for side, t in ((0, ht), (1, at)):
            m[j, side] = cov["man"].get((gid, t), mdef)
            d = sp_k.get((gid, t))
            if d:
                for ci, c in enumerate(("man", "zone")):
                    sp[j, side, ci] = [d[f"{f}_{c}"] for f in SPLITS]
    return {"m": np.repeat(m, sims, axis=0), "sp": np.repeat(sp, sims, axis=0)}


def attach_receivers(ros: dict, rs: dict) -> dict:
    """Copy of the player-engine rosters with tmul / ymul (K, 2) from receiver_splits output for one k_rec."""
    out = {}
    for (s, w, t), r in ros.items():
        mult = np.array([rs.get((s, w, pid), (1.0, 1.0, 1.0, 1.0)) for pid in r["rec_ids"]], float)
        out[(s, w, t)] = dict(r, tmul=mult[:, :2], ymul=mult[:, 2:])
    return out
