"""Personnel layer for the game simulator (nfl-betting-model docs/gamesim_preregistration.md, step 3).

Inputs per team-game, built only from information dated before the game:
  qb_delta  starting QB's shrunk EPA per dropback minus the dropback-weighted rating of the QBs who took the team's
            dropbacks in its previous 4 games (ratings as of the game). Recorded starter from nflverse schedules
            (known at inactives; disclosed hindsight). Plays weighted 0.5^(days / D), shrunk by KQ dropbacks toward a
            replacement level (mean EPA of QBs' first 100 dropbacks, debuts in the fit seasons).
  ol, skill players listed Out or Doubtful on the week's final nflverse injury report x their offensive snap share in
            the team's previous 4 games, summed by group.
  dl, lb, db the same for the team's defense (applied to the opponent's offense).
Coefficients: weighted least squares of each team-game's rate residual (observed minus the pre-game factor
prediction) on the six inputs, fit seasons only. Constants D and KQ are fixed here, not tuned.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

from .teams import FRANCHISE

D_DAYS, KQ, WINDOW = 365.0, 200.0, 4
INPUTS = ["qb_delta", "ol", "skill", "opp_dl", "opp_lb", "opp_db"]
GROUPS = {"ol": {"T", "G", "C", "OT", "OG", "OL"}, "skill": {"WR", "TE", "RB", "FB", "HB"},
          "dl": {"DE", "DT", "NT", "DL"}, "lb": {"LB", "ILB", "OLB", "MLB"}, "db": {"CB", "S", "SS", "FS", "DB"}}
RATES = ["comp", "ypc", "int", "sack", "ypr"]


def _day(s) -> int:
    return (dt.date.fromisoformat(str(s)[:10]) - dt.date(1970, 1, 1)).days


def qb_games(pbp: pl.DataFrame) -> pl.DataFrame:
    d = pbp.filter(pl.col("season_type") == "REG", pl.col("qb_dropback") == 1, pl.col("qb_epa").is_not_null()) \
        .with_columns(pl.coalesce("passer_player_id", "rusher_player_id").alias("qb"), pl.col("posteam").replace(FRANCHISE).alias("team"))
    g = d.filter(pl.col("qb").is_not_null()).group_by("qb", "game_id", "game_date", "season", "week", "team") \
        .agg(pl.len().alias("n"), pl.col("qb_epa").sum().alias("s"))
    return g.with_columns(pl.col("game_date").map_elements(_day, return_dtype=pl.Int64).alias("day")).sort("day")


def replacement(qg: pl.DataFrame, pbp: pl.DataFrame, fit: list[int], first_n: int = 100) -> float:
    d = pbp.filter(pl.col("season_type") == "REG", pl.col("qb_dropback") == 1, pl.col("qb_epa").is_not_null()) \
        .with_columns(pl.coalesce("passer_player_id", "rusher_player_id").alias("qb")).filter(pl.col("qb").is_not_null()) \
        .sort("game_id", "play_id").with_row_index("ord")
    debut = d.group_by("qb").agg(pl.col("season").min().alias("debut"))
    first = int(d["season"].min())
    d = d.join(debut, on="qb").filter(pl.col("debut") > first, pl.col("debut").is_in(fit))
    d = d.with_columns(pl.int_range(pl.len()).over("qb").alias("k")).filter(pl.col("k") < first_n)
    return float(d["qb_epa"].mean())


class QBRater:
    def __init__(self, qg: pl.DataFrame, prior: float):
        self.prior = prior
        self.by = {}
        for q, n, s, day in zip(qg["qb"], qg["n"], qg["s"], qg["day"]):
            self.by.setdefault(q, []).append((day, n, s))

    def rating(self, qb, day: int) -> float:
        xs = [x for x in self.by.get(qb, []) if x[0] < day]
        if not xs:
            return self.prior
        w = np.array([0.5 ** ((day - x[0]) / D_DAYS) for x in xs])
        n = np.array([x[1] for x in xs], float)
        s = np.array([x[2] for x in xs], float)
        return float((w @ s + KQ * self.prior) / (w @ n + KQ))


def qb_delta(sched: pl.DataFrame, qg: pl.DataFrame, rater: QBRater) -> pl.DataFrame:
    """Per team-game qb_delta. sched: nflverse schedules (gameday, home/away team and starting QB ids)."""
    rows = []
    s = sched.filter(pl.col("game_type") == "REG")
    by_team = {}
    for t, gid, day, q, n in zip(qg["team"], qg["game_id"], qg["day"], qg["qb"], qg["n"]):
        by_team.setdefault(t, {}).setdefault((day, gid), []).append((q, n))
    for r in s.iter_rows(named=True):
        day = _day(r["gameday"])
        for side in ("home", "away"):
            team = FRANCHISE.get(r[f"{side}_team"], r[f"{side}_team"])
            starter = r[f"{side}_qb_id"]
            prev = sorted(k for k in by_team.get(team, {}) if k[0] < day)[-WINDOW:]
            plays = [x for k in prev for x in by_team[team][k]]
            if plays and starter:
                base = sum(rater.rating(q, day) * n for q, n in plays) / sum(n for _, n in plays)
                val = rater.rating(starter, day) - base
            else:
                val = 0.0
            rows.append({"game_id": r["game_id"], "team": team, "qb_delta": val})
    return pl.DataFrame(rows)


def injury_loss(inj: pl.DataFrame, snaps: pl.DataFrame, ids: pl.DataFrame, sched: pl.DataFrame) -> pl.DataFrame:
    """Per team-game: summed previous-4-game snap share of players Out or Doubtful, by group."""
    out = inj.filter(pl.col("game_type") == "REG", pl.col("report_status").is_in(["Out", "Doubtful"])) \
        .join(ids.select("gsis_id", "pfr_id").drop_nulls(), on="gsis_id", how="left") \
        .select("season", "week", pl.col("team").replace(FRANCHISE), "pfr_id", "position")
    sn = snaps.filter(pl.col("game_type") == "REG").with_columns(pl.col("team").replace(FRANCHISE)).select(
        "season", "week", "team", pl.col("pfr_player_id").alias("pfr_id"), "position",
        pl.max_horizontal(pl.col("offense_pct").fill_null(0), pl.col("defense_pct").fill_null(0)).alias("pct"))
    games = sched.filter(pl.col("game_type") == "REG").select("season", "week", "game_id", "home_team", "away_team")
    tg = pl.concat([games.select("season", "week", "game_id", pl.col("home_team").replace(FRANCHISE).alias("team")),
                    games.select("season", "week", "game_id", pl.col("away_team").replace(FRANCHISE).alias("team"))])
    tg = tg.with_columns((pl.col("season") * 100 + pl.col("week")).alias("sw"))
    sn = sn.with_columns((pl.col("season") * 100 + pl.col("week")).alias("sw"))
    rows = []
    team_weeks = {t: sorted(set(v)) for t, v in sn.group_by("team").agg(pl.col("sw")).iter_rows()}
    pct = {(t, w, p): c for t, w, p, c in zip(sn["team"], sn["sw"], sn["pfr_id"], sn["pct"])}
    out_by = {}
    for s, w, t, p, pos in out.iter_rows():
        out_by.setdefault((t, s * 100 + w), []).append((p, pos))
    for gid, t, sw in zip(tg["game_id"], tg["team"], tg["sw"]):
        prev = [x for x in team_weeks.get(t, []) if x < sw][-WINDOW:]
        acc = {g: 0.0 for g in GROUPS}
        for p, pos in out_by.get((t, sw), []):
            grp = next((g for g, ps in GROUPS.items() if pos in ps), None)
            if grp is None or p is None or not prev:
                continue
            acc[grp] += sum(pct.get((t, x, p), 0.0) for x in prev) / len(prev)
        rows.append({"game_id": gid, "team": t, **acc})
    return pl.DataFrame(rows)


def inputs(qbd: pl.DataFrame, inj: pl.DataFrame, sched: pl.DataFrame) -> pl.DataFrame:
    """Per team-game the six inputs (opponent's defensive losses attached to this team's offense)."""
    g = sched.filter(pl.col("game_type") == "REG")
    pairs = pl.concat([g.select("game_id", pl.col("home_team").replace(FRANCHISE).alias("team"), pl.col("away_team").replace(FRANCHISE).alias("opp")),
                       g.select("game_id", pl.col("away_team").replace(FRANCHISE).alias("team"), pl.col("home_team").replace(FRANCHISE).alias("opp"))])
    x = pairs.join(qbd, on=["game_id", "team"], how="left").join(inj.select("game_id", "team", "ol", "skill"), on=["game_id", "team"], how="left")
    o = inj.select("game_id", pl.col("team").alias("opp"), pl.col("dl").alias("opp_dl"), pl.col("lb").alias("opp_lb"), pl.col("db").alias("opp_db"))
    return x.join(o, on=["game_id", "opp"], how="left").fill_null(0.0)


def residuals(gs: pl.DataFrame, fac: pl.DataFrame, lg: dict) -> pl.DataFrame:
    """Per team-game rate residuals (observed minus pre-game prediction) and their weights."""
    f_o = fac.select("game_id", "team", *[pl.col("o" + r) for r in RATES])
    f_d = fac.select("game_id", pl.col("team").alias("opp"), *[pl.col("d" + r) for r in RATES])
    x = gs.join(f_o, on=["game_id", "team"]).join(f_d, on=["game_id", "opp"])
    lo = lambda p: np.log(p / (1 - p))  # noqa: E731
    out = x.select("game_id", "team", "season")
    for r, (succ, n) in {"comp": ("comp", "natt"), "int": ("int", "att"), "sack": ("sack", "db")}.items():
        obs = lo((x[succ].to_numpy() + 0.5) / (x[n].to_numpy() + 1))
        pred = lo(lg[r]) + x["o" + r].to_numpy() + x["d" + r].to_numpy()
        out = out.with_columns(pl.Series("y_" + r, obs - pred), pl.Series("w_" + r, x[n].to_numpy().astype(float)))
    for r, (yd, n) in {"ypc": ("comp_y", "comp"), "ypr": ("run_y", "run")}.items():
        cnt = x[n].to_numpy().astype(float)
        obs = np.log(np.clip(x[yd].to_numpy() / np.maximum(cnt, 1), 0.5, None))
        pred = np.log(lg[r]) + x["o" + r].to_numpy() + x["d" + r].to_numpy()
        out = out.with_columns(pl.Series("y_" + r, np.where(cnt > 0, obs - pred, 0.0)), pl.Series("w_" + r, cnt))
    return out


def fit_coefs(res: pl.DataFrame, inp: pl.DataFrame) -> dict:
    x = res.join(inp, on=["game_id", "team"])
    X = x.select(INPUTS).to_numpy()
    coefs = {}
    for r in RATES:
        w = x["w_" + r].to_numpy()
        y = x["y_" + r].to_numpy()
        Xc = np.c_[np.ones(len(y)), X]
        W = np.sqrt(w)[:, None]
        b = np.linalg.lstsq(Xc * W, y * W[:, 0], rcond=None)[0]
        coefs[r] = dict(zip(["const", *INPUTS], map(float, b)))
    return coefs


def shifts(inp: pl.DataFrame, coefs: dict) -> dict:
    """{(game_id, team): {rate: shift}} for the engine's offense factors (constant term not applied)."""
    out = {}
    for row in inp.iter_rows(named=True):
        out[(row["game_id"], row["team"])] = {r: sum(coefs[r][i] * row[i] for i in INPUTS) for r in RATES}
    return out
