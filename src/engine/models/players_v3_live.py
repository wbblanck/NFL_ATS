"""proj-players-v3 at lock time (docs/players_v3_report.md, decision 1: v3 replaces v1 as the tracked projection).

Frozen from the evaluation, never refit live:
  data/processed/players_v3_model.json      D, k, replacement prior, play probabilities, beta (fit on 2013-2021)
  data/processed/qb_games_2006_2025.parquet per-QB per-game dropbacks and summed EPA, 2006-2025
The current season's plays, snaps, injury reports and depth-chart snapshots are downloaded at the run.
Every feature is built from data dated before the game's lock (same code as the evaluation).
"""
from __future__ import annotations

import json
import math

import polars as pl

from engine import config
from engine.features import players_v3 as V

VERSION = "proj-players-v3"


def model_path():
    return config.path("processed") / "players_v3_model.json"


def qb_hist_path():
    return config.path("processed") / "qb_games_2006_2025.parquet"


def freeze(results_json: str, dropbacks: pl.DataFrame, const: dict) -> dict:
    """Write the frozen artifacts from an evaluation run (python -m engine players-v3)."""
    j = json.load(open(results_json))
    beta = {r["feature"]: {"td": r["td_b"], "fg": r["fg_b"]} for r in j["test"]["beta"]}
    m = {"version": VERSION, "D": j["tuning"]["D"], "k": j["tuning"]["k"], "prior": const["prior"]["prior"],
         "p_play": {s: {"p_play": v["p_play"]} for s, v in const["p_play"].items()},
         "features": V.FEATURES, "beta": beta, "trained_on": "2013-2021 REG",
         "source": "docs/players_v3_results.md"}
    model_path().write_text(json.dumps(m, indent=1))
    V.qb_games(dropbacks.filter(pl.col("season") <= 2025)).write_parquet(qb_hist_path())
    return m


def load_model() -> dict:
    return json.loads(model_path().read_text())


def live_inputs(season: int) -> dict:
    """Download the current season's inputs. Snaps include the previous season for week 1-4 windows."""
    import nflreadpy as nfl
    cols = ["game_id", "season", "season_type", "week", "game_date", "posteam", "qb_dropback", "qb_epa",
            "passer_player_id", "rusher_player_id"]
    try:
        cur = V.qb_games(nfl.load_pbp(seasons=[season]).filter(pl.col("qb_dropback") == 1).select(cols))
    except Exception:
        cur = None                                     # before the season's first game
    hist = pl.read_parquet(qb_hist_path())
    qbg = pl.concat([hist, cur.select(hist.columns)]) if cur is not None and cur.height else hist
    return {"qb_games": qbg,
            "injuries": nfl.load_injuries(seasons=[season]),
            "snaps": nfl.load_snap_counts(seasons=[season - 1, season]),
            "players": nfl.load_players(),
            "depth": nfl.load_depth_charts(seasons=[season])}


def features(sched_all: pl.DataFrame, inputs: dict, season: int, game_ids: list[str], m: dict) -> pl.DataFrame:
    """v3 features for the given games (sched_all: nflverse schedule with kickoff_utc/lock_utc)."""
    sched = sched_all.filter(pl.col("season").is_between(season - 4, season))
    tg = V.team_game_frame(sched)
    st = V.starters_from_depth(tg.filter(pl.col("game_id").is_in(game_ids)), inputs["depth"], inputs["injuries"], season)
    tg = tg.join(st, on=["game_id", "team"], how="left").with_columns(
        pl.when(pl.col("season") == season).then(pl.col("qb_depth")).otherwise(pl.col("qb_recorded")).alias("starter"))
    rater = V.QBRater(inputs["qb_games"], m["D"], m["k"], m["prior"])
    q = V.qb_features(tg, inputs["qb_games"], rater)
    reps = V.injury_reports(inputs["injuries"], tg)
    inj = V.injury_features(tg, reps, V.snap_table(inputs["snaps"], inputs["players"]), m["p_play"])
    out = tg.join(q, on=["game_id", "team"], how="left").join(inj, on=["game_id", "team"], how="left") \
        .with_columns([pl.col(c).fill_null(0.0) for c in ("ol", "skill", "opp_dl", "opp_lb", "opp_db")])
    out = _fill_roof(out, sched_all)
    n_rep = reps.group_by("game_id", "team").len()
    # Was the team's game-status report (Out/Doubtful/Questionable) published when this ran? Practice-only
    # rows mean it was not yet, and the injury features would read "nobody hurt". Such rows are flagged
    # INJ_STATUS_MISSING and excluded from v3's live score (docs/players_v3_report.md).
    inj = inputs["injuries"].with_columns(V._fr("team").alias("team"), pl.col("season").cast(pl.Int32),
                                          pl.col("week").cast(pl.Int32))
    pub = inj.filter(pl.col("season") == season).group_by("week", "team").agg(
        pl.col("report_status").is_not_null().any().alias("injury_status_published"))
    return out.filter(pl.col("game_id").is_in(game_ids)).join(n_rep, on=["game_id", "team"], how="left") \
        .with_columns(pl.col("len").fill_null(0).alias("n_injury_rows")).drop("len") \
        .join(pub, on=["week", "team"], how="left") \
        .with_columns(pl.col("injury_status_published").fill_null(False))


def _fill_roof(f: pl.DataFrame, sched_all: pl.DataFrame) -> pl.DataFrame:
    """nflverse leaves `roof` empty for future games at retractable-roof stadiums: open/closed is decided on game
    day. Training used the observed value, which is not known at lock, so the live value is that stadium's share
    of dome/closed games among its earlier games (0 for a stadium with no history, e.g. a new open-air site)."""
    if not f["dome"].is_null().any():
        return f.with_columns(pl.lit(False).alias("dome_estimated"))
    past = sched_all.filter(pl.col("roof").is_not_null())
    rows = []
    for r in f.filter(pl.col("dome").is_null()).select("game_id", "kickoff_utc").unique().iter_rows(named=True):
        sid = sched_all.filter(pl.col("game_id") == r["game_id"])["stadium_id"][0]
        h = past.filter((pl.col("stadium_id") == sid) & (pl.col("kickoff_utc") < r["kickoff_utc"]))
        rows.append({"game_id": r["game_id"],
                     "dome_hat": float(h["roof"].is_in(["dome", "closed"]).mean()) if h.height else 0.0})
    est = pl.DataFrame(rows, schema={"game_id": pl.Utf8, "dome_hat": pl.Float64})
    return f.join(est, on="game_id", how="left").with_columns(
        pl.col("dome").is_null().alias("dome_estimated"),
        pl.coalesce(pl.col("dome").cast(pl.Float64), pl.col("dome_hat")).alias("dome")).drop("dome_hat")


def loader(sched_rs: pl.DataFrame, sched_all: pl.DataFrame | None):
    """Callable(game_ids) -> {"model", "features"}, for final.run / preview.build (built lazily, only if needed).
    sched_rs: the regular-season schedule used for picks; sched_all: the full nflverse schedule, if loaded."""
    def load(game_ids):
        from engine.data import nflverse
        m = load_model()
        season = int(sched_rs.filter(pl.col("game_id").is_in(game_ids))["season"].max())
        full = nflverse.with_kickoff(sched_all if sched_all is not None else nflverse.pull("schedules", save=False)[0])
        return {"model": m, "features": features(full, live_inputs(season), season, game_ids, m)}
    return load


def multiplier(row: dict, m: dict, kind: str) -> float:
    """exp(intercept + beta . x) for kind 'td' or 'fg'."""
    b = m["beta"]
    return math.exp(b["intercept"][kind] + sum(b[f][kind] * float(row[f]) for f in m["features"]))
