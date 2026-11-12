"""Run the game simulator over a set of games (nfl-betting-model docs/gamesim_preregistration.md)."""
from __future__ import annotations

import numpy as np
import polars as pl

from . import engine as E
from . import league as L
from .teams import FRANCHISE

OFF = ["sack", "scr", "int", "comp", "ypc", "ypr", "proe"]


def kick_pools(pbp: pl.DataFrame) -> pl.DataFrame:
    """Kickoff start positions and extra-point results tagged with season and week, for season-to-date pools."""
    p = pbp.filter(pl.col("season_type") == "REG").sort("game_id", "play_id").with_columns(
        pl.col("yardline_100").shift(-1).over("game_id").alias("y1"), pl.col("posteam").shift(-1).over("game_id").alias("pt1"),
        pl.col("down").shift(-1).over("game_id").alias("d1"))
    k = p.filter(pl.col("play_type") == "kickoff", pl.col("return_touchdown").fill_null(0) == 0, pl.col("d1") == 1,
                 pl.col("pt1") == pl.col("posteam")).select("season", "week", pl.col("y1").alias("y"))
    x = p.filter(pl.col("play_type") == "extra_point").select("season", "week", (pl.col("extra_point_result") == "good").alias("good"))
    return k.drop_nulls(), x


def pools_for(games: pl.DataFrame, kicks: pl.DataFrame, xps: pl.DataFrame):
    """For each game: index into a list of kickoff pools (season to date, weeks before the game's week; the previous
    season if fewer than 100 kickoffs) and the season-to-date extra-point rate (same rule)."""
    pools, idx, xp, cache = [], [], [], {}
    for s, w in zip(games["season"].to_list(), games["week"].to_list()):
        if (s, w) not in cache:
            k = kicks.filter(pl.col("season") == s, pl.col("week") < w)
            x = xps.filter(pl.col("season") == s, pl.col("week") < w)
            if k.height < 100:
                k = kicks.filter(pl.col("season") == s - 1)
                x = xps.filter(pl.col("season") == s - 1)
            pools.append(k["y"].to_numpy().astype(float))
            cache[(s, w)] = (len(pools) - 1, float(x["good"].mean()))
        i, r = cache[(s, w)]
        idx.append(i)
        xp.append(r)
    return pools, np.array(idx), np.array(xp)


def prep(games: pl.DataFrame, fac: pl.DataFrame, kicks, xps):
    """Games joined to both teams' factors (h_o*, h_d*, a_o*, a_d*), plus kickoff pools and extra-point rates."""
    g = games.with_columns(pl.col("home_team").replace(FRANCHISE), pl.col("away_team").replace(FRANCHISE))
    cols = [f"o{f}" for f in OFF] + [f"d{f}" for f in OFF]
    fh = fac.select("game_id", pl.col("team").alias("home_team"), *[pl.col(c).alias("h_" + c) for c in cols])
    fa = fac.select("game_id", pl.col("team").alias("away_team"), *[pl.col(c).alias("a_" + c) for c in cols])
    g = g.join(fh, on=["game_id", "home_team"], how="left").join(fa, on=["game_id", "away_team"], how="left").fill_null(0.0)
    pools, pidx, xp = pools_for(g, kicks, xps)
    return g, pools, pidx, xp


def chunk_inputs(gg: pl.DataFrame, sims: int, shift: dict | None):
    """Per-element offense / defense factor arrays (N, 2) for a chunk of prepared games, personnel shifts applied."""
    rep = lambda a: np.repeat(np.asarray(a, float), sims)  # noqa: E731
    off = {f: np.c_[rep(gg["h_o" + f]), rep(gg["a_o" + f])] for f in OFF}
    dfn = {f: np.c_[rep(gg["h_d" + f]), rep(gg["a_d" + f])] for f in OFF}
    if shift:
        for j, (gid, ht, at) in enumerate(zip(gg["game_id"], gg["home_team"], gg["away_team"])):
            for side, t in ((0, ht), (1, at)):
                for f, v in shift.get((gid, t), {}).items():
                    off[f][j * sims:(j + 1) * sims, side] += v
    return off, dfn


def simulate_games(games: pl.DataFrame, fac: pl.DataFrame, tb: E.Tables, kicks, xps, hfa: float, sims: int = 400,
                   seed: int = 0, chunk: int = 60000, shift: dict | None = None,
                   want_counts: bool = False, cover: tuple | None = None, return_totals: bool = False,
                   return_regscore: bool = False):
    """games: season, week, game_id, home_team, away_team, neutral. fac: per team-game factors (o*/d*).
    shift: optional extra per-team-game factor shifts {(game_id, team): {factor: value}} (personnel layer).
    cover: optional (coverage dict from engine.gamesim.coverage.pregame, k_cov) for the coverage layer.
    Returns per game: mean home margin (fair), mean total, P(margin > x) is left to the caller via `margins`."""
    g, pools, pidx, xp = prep(games, fac, kicks, xps)
    G = g.height
    margins = np.zeros((G, sims), dtype=np.float32)
    totals = np.zeros((G, sims), dtype=np.float32)
    per = max(1, chunk // sims)
    att = np.zeros((G, sims, 2), np.int16) if want_counts else None
    reg = np.zeros((G, sims, 2), np.int16) if return_regscore else None
    car = np.zeros((G, sims, 2), np.int16) if want_counts else None
    for c0 in range(0, G, per):
        sl = slice(c0, min(G, c0 + per))
        gg = g[sl]
        off, dfn = chunk_inputs(gg, sims, shift)
        neutral = np.repeat(gg["neutral"].to_numpy(), sims)
        # home-field: engine applies +hfa to home offense yards and -hfa to away; neutral sites get none
        h = np.where(neutral, 0.0, hfa)
        cnt = {} if (want_counts or return_regscore) else None
        cv = None
        if cover is not None:
            from . import coverage as CV
            cv = CV.arrays(gg, sims, cover[0], cover[1])
        hh, aa = _sim_hfa(tb, off, dfn, (pools, np.repeat(pidx[sl], sims)), np.repeat(xp[sl], sims),
                          np.repeat(gg["season"].to_numpy(), sims), h, seed + c0, cnt, cv)
        if return_regscore:
            reg[sl] = cnt["qscore"][:, 3, :].reshape(-1, sims, 2)
        if want_counts:
            att[sl] = cnt["att"].reshape(-1, sims, 2)
            car[sl] = cnt["car"].reshape(-1, sims, 2)
        margins[sl] = (hh - aa).reshape(-1, sims)
        totals[sl] = (hh + aa).reshape(-1, sims)
    out = g.select("season", "week", "game_id", "home_team", "away_team").with_columns(
        pl.Series("fair", margins.mean(1).astype(float)), pl.Series("sim_total", totals.mean(1).astype(float)))
    if want_counts:
        return out, margins, att, car
    if return_totals and return_regscore:
        return out, margins, totals, reg
    if return_totals:
        return out, margins, totals
    return out, margins


def _sim_hfa(tb, off, dfn, kick, xp, season, h, seed, cnt=None, cv=None):
    """Per-element home-field: the engine takes one scalar; split elements by their h value."""
    N = len(xp)
    hh, aa = np.zeros(N), np.zeros(N)
    if cnt is not None:
        cnt["att"], cnt["car"] = np.zeros((N, 2), np.int16), np.zeros((N, 2), np.int16)
        cnt["qscore"] = np.zeros((N, 4, 2), np.int16)
    for v in np.unique(h):
        m = h == v
        o = {f: a[m] for f, a in off.items()}
        d = {f: a[m] for f, a in dfn.items()}
        c = {} if cnt is not None else None
        a1, a2 = E.simulate(tb, o, d, (kick[0], kick[1][m]), xp[m], season[m], float(v), seed=seed + int(v * 1000), counts=c,
                            cover=None if cv is None else {kk: a[m] for kk, a in cv.items()})
        hh[m], aa[m] = a1, a2
        if cnt is not None:
            cnt["att"][m], cnt["car"][m] = c["att"], c["car"]
            cnt["qscore"][m] = c["qscore"]
    return hh, aa
