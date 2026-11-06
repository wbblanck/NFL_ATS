"""League tables for the game simulator, fitted from nflverse play-by-play of the fit seasons only
(nfl-betting-model docs/gamesim_preregistration.md). Every table is a plain numpy array or list so it can be saved as JSON.

Buckets are shared with the engine (`engine.py`) through the functions below, so fitting and simulating use the
same definitions.
"""
from __future__ import annotations

import numpy as np
import polars as pl

TOGO = np.array([1, 3, 6, 10])                    # togo buckets: 1 | 2-3 | 4-6 | 7-10 | 11+
SDIFF = np.array([-15, -8, -1, 0, 7, 14])         # <=-15 | -14..-8 | -7..-1 | 0 | 1..7 | 8..14 | 15+
YL4 = np.array([5, 10, 20, 30, 40, 50, 60, 70])   # 4th-down field position buckets (yardline_100)
YARD = np.array([5, 10, 15, 20])                  # yards-distribution buckets: 1-5 | 6-10 | 11-15 | 16-20 | 21+
FGD = np.arange(18, 70, 3)                        # field-goal distance bins
PUNTYL = np.array([45, 55, 65, 75, 85])           # punt field position buckets


def b_togo(t):
    return np.searchsorted(TOGO, t, side="left")


def b_sdiff(s):
    s = np.asarray(s)
    return np.searchsorted(SDIFF, s, side="left") + 0


def b_time(game_sec, half_sec, qtr):
    """0 normal, 1 Q4 last 5 minutes, 2 end of first half (last 2 minutes of Q2)."""
    game_sec, half_sec, qtr = map(np.asarray, (game_sec, half_sec, qtr))
    return np.where((qtr == 2) & (half_sec <= 120), 2, np.where((qtr >= 4) & (game_sec <= 300), 1, 0))


def b_yl4(y):
    return np.searchsorted(YL4, y, side="left")


def b_yard(y):
    return np.searchsorted(YARD, y, side="left")


def b_pool(y):
    """Yards-pool bucket: exact yard line 1-20 (0-19), 20 = beyond the 20 (pool built from plays at the 50 or deeper,
    where the goal line rarely cuts gains short)."""
    return np.clip(np.asarray(y).astype(int), 1, 21) - 1


def b_sit4(sdiff, game_sec, qtr):
    """4th-down situation: 0 normal, 1 Q4 <= 10 min trailing by 1-8, 2 Q4 <= 10 min trailing 9+, 3 Q4 <= 5 min leading."""
    sdiff, game_sec, qtr = map(np.asarray, (sdiff, game_sec, qtr))
    late = (qtr >= 4) & (game_sec <= 600)
    return np.where(late & (sdiff < 0) & (sdiff >= -8), 1, np.where(late & (sdiff < -8), 2,
                    np.where((qtr >= 4) & (game_sec <= 300) & (sdiff > 0), 3, 0)))


def _smooth(num, den, prior_num, prior_den, w):
    return (num + w * prior_num / np.maximum(prior_den, 1e-9)) / (den + w)


def scrimmage(p: pl.DataFrame) -> pl.DataFrame:
    """Regular-season scrimmage snaps (pass, run, accepted no-play penalties), no kneels or spikes."""
    p = p.filter(pl.col("season_type") == "REG", pl.col("down").is_not_null(), pl.col("yardline_100").is_not_null(),
                 pl.col("play_type").is_in(["pass", "run", "no_play"]),
                 ~((pl.col("play_type") == "no_play") & (pl.col("penalty").fill_null(0) == 0)),
                 pl.col("two_point_attempt").fill_null(0) == 0)
    return p.with_columns(
        (pl.col("play_type") == "no_play").alias("is_pen"),
        ((pl.col("qb_dropback").fill_null(0) == 1) & (pl.col("play_type") != "no_play")).alias("is_db"),
        ((pl.col("play_type") == "run") & (pl.col("qb_scramble").fill_null(0) == 0)).alias("is_run"))


TD_CODE = 999.0


def _coded(x: pl.DataFrame, bucket: np.ndarray) -> np.ndarray:
    """Yards gained; inside the 20 (buckets 0-3) an offensive touchdown is coded TD_CODE and other gains are kept
    below the goal line, so a draw from the bucket keeps that bucket's touchdown rate."""
    y = x["yards_gained"].fill_null(0).to_numpy().astype(float)
    td = ((x["touchdown"].fill_null(0) == 1) & (x["td_team"] == x["posteam"])).to_numpy()
    return np.where((bucket < 20) & td, TD_CODE, y)


def fit(pbp: pl.DataFrame) -> dict:
    """All league tables from the fit seasons' play-by-play."""
    T: dict = {}
    s = scrimmage(pbp)
    sn = s.filter(~pl.col("is_pen"))
    # ---- pass probability by down (1-3), togo, score diff, time; 4th-down go plays use the down-3 row
    d = sn.filter(pl.col("down") <= 3)
    dn = d["down"].to_numpy().astype(int) - 1
    tg, sd = b_togo(d["ydstogo"].to_numpy()), b_sdiff(d["score_differential"].to_numpy())
    tm = b_time(d["game_seconds_remaining"].to_numpy(), d["half_seconds_remaining"].to_numpy(), d["qtr"].to_numpy())
    y = d["is_db"].to_numpy().astype(float)
    shape = (3, 5, 7, 3)
    num, den = np.zeros(shape), np.zeros(shape)
    np.add.at(num, (dn, tg, sd, tm), y)
    np.add.at(den, (dn, tg, sd, tm), 1)
    mnum, mden = num.sum(axis=(2, 3), keepdims=True), den.sum(axis=(2, 3), keepdims=True)
    T["pass_prob"] = _smooth(num, den, mnum, mden, 30).tolist()
    # field-position shift (log-odds) by down and yard bucket: teams run more near the goal line
    yb_ = b_yard(d["yardline_100"].to_numpy())
    sh = np.zeros((3, 5))
    for a in range(3):
        base = y[dn == a].mean()
        for b in range(5):
            m = (dn == a) & (yb_ == b)
            r = (y[m].sum() + 20 * base) / (m.sum() + 20)
            sh[a, b] = np.log(r / (1 - r)) - np.log(base / (1 - base))
    T["pass_yl_shift"] = sh.tolist()
    # ---- penalties (no-play): rate per snap, share on the defense, yards, first down
    pen = s.filter(pl.col("is_pen"))
    T["pen_rate"] = pen.height / s.height
    on_def = (pen["penalty_team"] != pen["posteam"]).to_numpy()
    T["pen_def_share"] = float(on_def.mean())
    T["pen_def_yards"] = pen.filter(pl.col("penalty_team") != pl.col("posteam"))["penalty_yards"].fill_null(5).to_numpy().tolist()
    T["pen_def_first"] = float(pen.filter(pl.col("penalty_team") != pl.col("posteam"))["first_down_penalty"].fill_null(0).mean())
    T["pen_off_yards"] = pen.filter(pl.col("penalty_team") == pl.col("posteam"))["penalty_yards"].fill_null(10).to_numpy().tolist()
    # ---- dropback outcomes by field position bucket: sack, scramble, interception, complete, incomplete
    db = sn.filter(pl.col("is_db"))
    yb = b_yard(db["yardline_100"].to_numpy())
    sack = db["sack"].fill_null(0).to_numpy() == 1
    scr = (db["qb_scramble"].fill_null(0).to_numpy() == 1) & ~sack
    intc = (db["interception"].fill_null(0).to_numpy() == 1) & ~sack & ~scr
    comp = (db["complete_pass"].fill_null(0).to_numpy() == 1) & ~sack & ~scr & ~intc
    cat = np.select([sack, scr, intc, comp], [0, 1, 2, 3], 4)
    cnt = np.zeros((5, 5))
    np.add.at(cnt, (yb, cat), 1)
    T["db_outcome"] = (cnt / cnt.sum(1, keepdims=True)).tolist()
    # yards samples by bucket (censored at the goal line, so reaching it is a TD)
    pb_ = b_pool(db["yardline_100"].to_numpy())
    deep = db["yardline_100"].to_numpy() >= 50
    ygain = _coded(db, pb_)
    T["comp_yards"] = [ygain[comp & (pb_ == b) & ((b < 20) | deep)].tolist() for b in range(21)]
    T["scr_yards"] = [ygain[scr & (pb_ == b) & ((b < 20) | deep)].tolist() for b in range(21)]
    T["sack_yards"] = ygain[sack].tolist()
    ii = intc
    air = db["air_yards"].fill_null(0).to_numpy()[ii]
    ret = db["return_yards"].fill_null(0).to_numpy()[ii]
    T["int_net"] = (air - ret).tolist()        # spot of the defense's possession = offense spot moved by this
    T["int_td"] = float(db["return_touchdown"].fill_null(0).to_numpy()[ii].mean())
    T["fumble_comp"] = float(db["fumble_lost"].fill_null(0).to_numpy()[comp].mean())
    T["fumble_sack"] = float(db["fumble_lost"].fill_null(0).to_numpy()[sack].mean())
    run = sn.filter(pl.col("is_run"))
    rb = b_yard(run["yardline_100"].to_numpy())
    rp = b_pool(run["yardline_100"].to_numpy())
    rdeep = run["yardline_100"].to_numpy() >= 50
    ry = _coded(run, rp)
    T["run_yards"] = [ry[(rp == b) & ((b < 20) | rdeep)].tolist() for b in range(21)]
    T["fumble_run"] = float(run["fumble_lost"].fill_null(0).mean())
    fl = sn.filter(pl.col("fumble_lost").fill_null(0) == 1)
    T["fumble_td"] = float(fl["return_touchdown"].fill_null(0).mean())
    ko = pbp.filter(pl.col("season_type") == "REG", pl.col("play_type") == "kickoff")
    T["kick_td"] = float(((ko["return_touchdown"].fill_null(0) == 1) & (ko["td_team"] != ko["posteam"])).mean())
    # ---- 4th-down decisions: go / punt / field goal by field position, togo, situation
    f4 = pbp.filter(pl.col("season_type") == "REG", pl.col("down") == 4, pl.col("yardline_100").is_not_null(),
                    pl.col("play_type").is_in(["pass", "run", "punt", "field_goal"]))
    ch = f4["play_type"].replace_strict({"pass": 0, "run": 0, "punt": 1, "field_goal": 2}).to_numpy()
    yl, tg4 = b_yl4(f4["yardline_100"].to_numpy()), b_togo(f4["ydstogo"].to_numpy())
    st = b_sit4(f4["score_differential"].to_numpy(), f4["game_seconds_remaining"].to_numpy(), f4["qtr"].to_numpy())
    c4 = np.zeros((9, 5, 4, 3))
    np.add.at(c4, (yl, tg4, st, ch), 1)
    marg = c4.sum(axis=2, keepdims=True)
    tot, mtot = c4.sum(-1, keepdims=True), marg.sum(-1, keepdims=True)
    T["fourth"] = ((c4 + 5 * marg / np.maximum(mtot, 1)) / (tot + 5)).tolist()
    # ---- field goals by distance
    fg = pbp.filter(pl.col("season_type") == "REG", pl.col("play_type") == "field_goal")
    dist = fg["kick_distance"].fill_null(0).to_numpy()
    made = (fg["field_goal_result"] == "made").to_numpy()
    fb = np.clip(np.searchsorted(FGD, dist), 0, len(FGD))
    m, n = np.zeros(len(FGD) + 1), np.zeros(len(FGD) + 1)
    np.add.at(m, fb, made)
    np.add.at(n, fb, 1)
    T["fg_make"] = ((m + 1) / (n + 2)).tolist()
    # ---- punts: receiving team's yardline_100 at its first snap, by punting team's field position
    pu = pbp.filter(pl.col("season_type") == "REG", pl.col("play_type") == "punt")
    py = pu["yardline_100"].to_numpy()
    tb = pu["touchback"].fill_null(0).to_numpy() == 1
    land = py - pu["kick_distance"].fill_null(40).to_numpy() + pu["return_yards"].fill_null(0).to_numpy()
    recv = np.where(tb, 80, 100 - land)
    recv = np.clip(recv, 1, 99)
    pb = np.searchsorted(PUNTYL, py)
    T["punt_recv"] = [recv[(pb == b) & (pu["return_touchdown"].fill_null(0).to_numpy() == 0)].tolist() for b in range(len(PUNTYL) + 1)]
    T["punt_td"] = float(pu["return_touchdown"].fill_null(0).mean())
    # ---- two-point tries and conversion
    two = pbp.filter(pl.col("season_type") == "REG", pl.col("two_point_attempt").fill_null(0) == 1)
    T["two_success"] = float((two["two_point_conv_result"] == "success").mean())
    T.update(clock(pbp))
    T.update(two_point_decision(pbp))
    return T


def two_point_decision(pbp: pl.DataFrame) -> dict:
    """P(go for two) after a TD by the scoring team's margin after the six points (-15..+15) and Q4 or not."""
    tries = pbp.filter(pl.col("season_type") == "REG",
                       (pl.col("play_type") == "extra_point") | (pl.col("two_point_attempt").fill_null(0) == 1))
    sd = np.clip(tries["score_differential"].fill_null(0).to_numpy().astype(int), -15, 15) + 15
    q4 = (tries["qtr"].to_numpy() >= 4).astype(int)
    go = tries["two_point_attempt"].fill_null(0).to_numpy()
    g, n = np.zeros((31, 2)), np.zeros((31, 2))
    np.add.at(g, (sd, q4), go)
    np.add.at(n, (sd, q4), 1)
    base = g.sum() / n.sum()
    return {"two_go": ((g + 5 * base) / (n + 5)).tolist()}


def clock(pbp: pl.DataFrame) -> dict:
    """Mean seconds off the game clock per scrimmage snap, by whether the clock stops (incomplete pass,
    score, turnover, penalty) and by situation: 0 normal, 1 Q4 <= 5 min offense trailing, 2 Q4 <= 5 min offense
    leading or tied, 3 last 2 minutes of the first half."""
    p = pbp.filter(pl.col("season_type") == "REG").sort("game_id", "play_id").with_columns(
        (pl.col("game_seconds_remaining") - pl.col("game_seconds_remaining").shift(-1).over("game_id")).alias("dt"),
        pl.col("qtr").shift(-1).over("game_id").alias("qn"))
    p = scrimmage(p).filter(pl.col("qn") == pl.col("qtr"), pl.col("dt").is_between(0, 60))
    stop = ((p["incomplete_pass"].fill_null(0) == 1)
            | (p["touchdown"].fill_null(0) == 1) | (p["interception"].fill_null(0) == 1)
            | (p["fumble_lost"].fill_null(0) == 1) | p["is_pen"]).to_numpy()
    g, hs, q, sd = (p[c].to_numpy() for c in ("game_seconds_remaining", "half_seconds_remaining", "qtr", "score_differential"))
    sit = np.where((q == 2) & (hs <= 120), 3, np.where((q >= 4) & (g <= 300), np.where(sd < 0, 1, 2), 0))
    dt = p["dt"].to_numpy()
    out = np.zeros((2, 4))
    for a in range(2):
        for b in range(4):
            m = (stop == bool(a)) & (sit == b)
            out[a, b] = float(dt[m].mean()) if m.any() else 30.0
    return {"secs": out.tolist()}


def kick_start(pbp: pl.DataFrame) -> list:
    """Receiving team's yardline_100 at its first snap after a kickoff (no return TDs, no onside recoveries)."""
    p = pbp.filter(pl.col("season_type") == "REG").sort("game_id", "play_id")
    p = p.with_columns(pl.col("yardline_100").shift(-1).over("game_id").alias("y1"),
                       pl.col("posteam").shift(-1).over("game_id").alias("pt1"),
                       pl.col("down").shift(-1).over("game_id").alias("d1"))
    k = p.filter(pl.col("play_type") == "kickoff", pl.col("return_touchdown").fill_null(0) == 0,
                 pl.col("d1") == 1, pl.col("pt1") == pl.col("posteam"))
    return k["y1"].drop_nulls().to_numpy().tolist()


def xp_rate(pbp: pl.DataFrame) -> float:
    x = pbp.filter(pl.col("season_type") == "REG", pl.col("play_type") == "extra_point")
    return float((x["extra_point_result"] == "good").mean())
