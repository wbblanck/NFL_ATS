"""Features for proj-players-v3 (docs/players_v3_preregistration.md).

Every feature for a game is built only from information dated before that game:
plays from earlier games, injury reports filed before lock, snap counts from the
team's earlier games, depth-chart snapshots taken before lock. `build` takes the
raw tables as arguments so the point-in-time property can be tested by deleting
everything at or after a game and checking the features do not change.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from engine.models.projection import FRANCHISE

H_V1 = 8.0                         # v1 game-weight half-life (weeks), frozen
EPOCH = dt.date(1970, 1, 1)
STATUSES = ("Out", "Doubtful", "Questionable")
GROUPS = {
    "ol": {"T", "G", "C", "OT", "OG", "OL"},
    "skill": {"WR", "TE", "RB", "FB", "HB"},
    "dl": {"DE", "DT", "NT", "DL"},
    "lb": {"LB", "ILB", "OLB", "MLB"},
    "db": {"CB", "S", "SS", "FS", "DB"},
}
OFF_GROUPS, DEF_GROUPS = ("ol", "skill"), ("dl", "lb", "db")
# Standard time zone of each home stadium: 0 = Eastern, 1 = Central, 2 = Mountain, 3 = Pacific.
# Keyed by the schedule's own team code, so relocated franchises keep their old zone (STL = Central).
TZ = {**{t: 0 for t in ("ATL", "BAL", "BUF", "CAR", "CIN", "CLE", "DET", "IND", "JAX", "MIA", "NE", "NYG",
                        "NYJ", "PHI", "PIT", "TB", "WAS")},
      **{t: 1 for t in ("CHI", "DAL", "GB", "HOU", "KC", "MIN", "NO", "TEN", "STL")},
      **{t: 2 for t in ("DEN", "ARI")},
      **{t: 3 for t in ("LA", "LAC", "LV", "OAK", "SD", "SEA", "SF")}}
# Neutral-site games played in the US; every other neutral site is international (tz_shift = 5).
# nflverse lists wrong home-stadium ids for several 2021/2025 international games, so these are named explicitly.
DOMESTIC_NEUTRAL = {"DET00": 0, "PHO00": 2, "PHO99": 2}
INTERNATIONAL = 5
CONTEXT = ["rest_diff", "short_week", "off_bye", "tz_shift", "division", "dome"]
FEATURES = ["qb_delta", "ol", "skill", "opp_dl", "opp_lb", "opp_db", *CONTEXT]


def _fr(c: str) -> pl.Expr:
    return pl.col(c).replace(FRANCHISE)


def _day(d) -> int:
    if isinstance(d, str):
        d = dt.date.fromisoformat(d[:10])
    return (d - EPOCH).days


# ---------------------------------------------------------------- QB ratings

def qb_games(dropbacks: pl.DataFrame) -> pl.DataFrame:
    """Per QB per game: dropbacks n and summed qb_epa. The QB is the passer, or the rusher on scrambles."""
    d = dropbacks.filter(pl.col("qb_dropback") == 1, pl.col("qb_epa").is_not_null()).with_columns(
        pl.coalesce("passer_player_id", "rusher_player_id").alias("qb"), _fr("posteam").alias("team"))
    return d.filter(pl.col("qb").is_not_null()).group_by("qb", "game_id", "game_date", "season", "season_type", "week", "team") \
        .agg(pl.len().alias("n"), pl.col("qb_epa").sum().alias("s")) \
        .with_columns(pl.col("game_date").map_elements(_day, return_dtype=pl.Int64).alias("day"))


def replacement_prior(dropbacks: pl.DataFrame, train_seasons: tuple[int, int], first_n: int = 100) -> dict:
    """Mean EPA/dropback over QBs' first `first_n` career dropbacks. Only QBs whose first dropback in the
    data is after its first season (so the start is a real career start) and whose first `first_n` dropbacks
    all fall in the training seasons."""
    d = dropbacks.filter(pl.col("qb_dropback") == 1, pl.col("qb_epa").is_not_null()).with_row_index("ord") \
        .with_columns(pl.coalesce("passer_player_id", "rusher_player_id").alias("qb")) \
        .sort("game_date", "ord")
    first_season = int(d["season"].min())
    d = d.with_columns(pl.int_range(pl.len()).over("qb").alias("k"),
                       pl.col("season").min().over("qb").alias("debut"))
    lo, hi = train_seasons
    e = d.filter(pl.col("debut") > first_season, pl.col("debut") >= lo, pl.col("k") < first_n)
    ok = e.group_by("qb").agg(pl.col("season").max().alias("last")).filter(pl.col("last") <= hi)["qb"]
    e = e.filter(pl.col("qb").is_in(ok.implode()))
    return {"prior": float(e["qb_epa"].mean()), "n_qbs": int(ok.len()), "n_plays": int(e.height)}


@dataclass
class QBRater:
    games: pl.DataFrame
    D: float
    k: float
    prior: float
    _idx: dict = field(default_factory=dict)

    def __post_init__(self):
        for (qb,), g in self.games.sort("day").group_by(["qb"]):
            self._idx[qb] = (g["day"].to_numpy(), g["n"].to_numpy().astype(float), g["s"].to_numpy())

    def rating(self, qb: str | None, day: int) -> tuple[float, float]:
        """(rating, weighted dropbacks) from games strictly before `day`."""
        if qb is None or qb not in self._idx:
            return self.prior, 0.0
        days, n, s = self._idx[qb]
        m = days < day
        if not m.any():
            return self.prior, 0.0
        w = 0.5 ** ((day - days[m]) / self.D)
        wn = float(w @ n[m])
        return (float(w @ s[m]) + self.k * self.prior) / (wn + self.k), wn


# ---------------------------------------------------------------- team-game frame

def team_game_frame(sched: pl.DataFrame) -> pl.DataFrame:
    """One row per REG team-game with the context variables (all known before kickoff)."""
    s = sched.filter(pl.col("game_type") == "REG")
    neutral = pl.col("location") == "Neutral"
    site = (pl.when(neutral & pl.col("stadium_id").is_in(list(DOMESTIC_NEUTRAL)))
            .then(pl.col("stadium_id").replace_strict(DOMESTIC_NEUTRAL, default=None))
            .when(neutral).then(pl.lit(INTERNATIONAL))
            .otherwise(pl.col("home_team").replace_strict(TZ, default=None)))
    s = s.with_columns(site.alias("site_tz"), neutral.alias("neutral"),
                       (pl.col("roof").is_in(["dome", "closed"])).cast(pl.Int8).alias("dome"),
                       pl.col("div_game").fill_null(0).cast(pl.Int8).alias("division"))
    cols = ["game_id", "season", "week", "gameday", "site_tz", "neutral", "dome", "division"]
    if "kickoff_utc" in s.columns:
        cols += ["kickoff_utc", "lock_utc"]
    h = s.select(*cols, pl.col("home_team").alias("raw"), _fr("home_team").alias("team"), _fr("away_team").alias("opp"),
                 pl.lit(1).alias("home"), pl.col("home_rest").alias("rest"), pl.col("away_rest").alias("opp_rest"),
                 pl.col("home_qb_id").alias("qb_recorded"))
    a = s.select(*cols, pl.col("away_team").alias("raw"), _fr("away_team").alias("team"), _fr("home_team").alias("opp"),
                 pl.lit(0).alias("home"), pl.col("away_rest").alias("rest"), pl.col("home_rest").alias("opp_rest"),
                 pl.col("away_qb_id").alias("qb_recorded"))
    g = pl.concat([h, a])
    own_tz = pl.col("raw").replace_strict(TZ, default=None)
    tz = (pl.when(pl.col("site_tz") == INTERNATIONAL).then(pl.lit(INTERNATIONAL))
          .when((pl.col("home") == 1) & ~pl.col("neutral")).then(pl.lit(0))
          .otherwise((own_tz - pl.col("site_tz")).abs()))
    return g.with_columns(
        (pl.col("season") * 25 + pl.col("week")).alias("t"),
        pl.col("gameday").map_elements(_day, return_dtype=pl.Int64).alias("day"),
        (pl.col("rest") - pl.col("opp_rest")).clip(-7, 7).alias("rest_diff"),
        (pl.col("rest") <= 5).cast(pl.Int8).alias("short_week"),
        (pl.col("rest") >= 13).cast(pl.Int8).alias("off_bye"),
        tz.alias("tz_shift"),
    ).sort("team", "t")


# ---------------------------------------------------------------- starters

def starters_from_depth(tg: pl.DataFrame, depth: pl.DataFrame, injuries: pl.DataFrame, season: int) -> pl.DataFrame:
    """QB1 on the team's last depth-chart snapshot before lock; QB2 if QB1 is Out that week."""
    d = depth.filter(pl.col("pos_abb") == "QB").with_columns(_fr("team").alias("team"))
    out = injuries.filter(pl.col("report_status") == "Out").with_columns(
        _fr("team").alias("team"), pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32))
    rows = []
    for r in tg.filter(pl.col("season") == season).select("game_id", "team", "season", "week", "lock_utc").to_dicts():
        lock = r["lock_utc"].strftime("%Y-%m-%dT%H:%M:%SZ")
        snap = d.filter((pl.col("team") == r["team"]) & (pl.col("dt") < lock))
        if snap.height == 0:
            rows.append({"game_id": r["game_id"], "team": r["team"], "qb_depth": None, "qb1_out": None, "snapshot": None})
            continue
        last = snap["dt"].max()
        s = snap.filter(pl.col("dt") == last).sort("pos_rank")
        ids = [x for x in s["gsis_id"].to_list()]
        outs = set(out.filter((pl.col("season") == r["season"]) & (pl.col("week") == r["week"])
                              & (pl.col("team") == r["team"]))["gsis_id"].to_list())
        qb1_out = bool(ids and ids[0] in outs)
        pick = ids[1] if qb1_out and len(ids) > 1 else (ids[0] if ids else None)
        rows.append({"game_id": r["game_id"], "team": r["team"], "qb_depth": pick, "qb1_out": qb1_out, "snapshot": last})
    return pl.DataFrame(rows, schema={"game_id": pl.Utf8, "team": pl.Utf8, "qb_depth": pl.Utf8,
                                      "qb1_out": pl.Boolean, "snapshot": pl.Utf8})


def starters_weekly(depth_old: pl.DataFrame) -> pl.DataFrame:
    """2001-2024 weekly depth charts: QB1 per team-week. These releases carry no timestamp, so this is a
    sensitivity check on the recorded starter, not a verified pre-lock source."""
    d = depth_old.filter(pl.col("game_type") == "REG", pl.col("position") == "QB", pl.col("depth_team") == "1",
                         pl.col("gsis_id").is_not_null())
    return d.with_columns(_fr("club_code").alias("team"), pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32)) \
        .group_by("season", "week", "team").agg(pl.col("gsis_id").first().alias("qb_weekly"), pl.len().alias("n_qb1"))


# ---------------------------------------------------------------- QB delta

def qb_features(tg: pl.DataFrame, qbg: pl.DataFrame, rater: QBRater, starter_col: str = "starter") -> pl.DataFrame:
    """qb_delta = rating(starter) - dropback-weighted rating of the QBs behind the team rating (v1 weights)."""
    reg = qbg.filter(pl.col("season_type") == "REG")
    per_game = {}
    for (gid, team), g in reg.group_by(["game_id", "team"]):
        per_game[(gid, team)] = list(zip(g["qb"].to_list(), g["n"].to_list()))
    rows = []
    for (team,), grp in tg.sort("t").group_by(["team"], maintain_order=True):
        hist = grp.select("game_id", "t", "season").to_dicts()
        for i, r in enumerate(grp.to_dicts()):
            W = {}
            for h in hist[:i]:
                if h["t"] >= r["t"]:
                    continue
                w = 0.5 ** ((r["t"] - h["t"]) / H_V1) * 0.5 ** (r["season"] - h["season"])
                if w <= 1e-3:
                    continue
                for qb, n in per_game.get((h["game_id"], team), []):
                    W[qb] = W.get(qb, 0.0) + w * n
            tot = sum(W.values())
            base = sum(wq * rater.rating(qb, r["day"])[0] for qb, wq in W.items()) / tot if tot > 0 else rater.prior
            rs, wn = rater.rating(r[starter_col], r["day"])
            rows.append({"game_id": r["game_id"], "team": team, "qb_rating": rs, "qb_wdropbacks": wn,
                         "qb_baseline": base, "qb_delta": rs - base})
    return pl.DataFrame(rows)


# ---------------------------------------------------------------- injuries

def injury_reports(injuries: pl.DataFrame, tg: pl.DataFrame) -> pl.DataFrame:
    """Non-QB O/D/Q entries, using the latest report row filed before the game's lock.
    Rows without a timestamp (2025 release) are kept; that is disclosed in the report."""
    if "date_modified" not in injuries.columns:          # the 2026 release has no timestamp column
        injuries = injuries.with_columns(pl.lit(None, pl.Datetime("us", "UTC")).alias("date_modified"))
    i = injuries.filter(pl.col("game_type") == "REG", pl.col("report_status").is_in(list(STATUSES)),
                        pl.col("position") != "QB", pl.col("gsis_id").is_not_null()).with_columns(
        _fr("team").alias("team"), pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32))
    locks = tg.select("season", "week", "team", "game_id", "lock_utc")
    i = i.join(locks, on=["season", "week", "team"], how="inner")
    i = i.filter(pl.col("date_modified").is_null() | (pl.col("date_modified") < pl.col("lock_utc")))
    grp = pl.col("position").replace_strict({p: g for g, ps in GROUPS.items() for p in ps}, default=None)
    return i.sort("date_modified", nulls_last=False).group_by("game_id", "team", "gsis_id").last() \
        .with_columns(grp.alias("group")).filter(pl.col("group").is_not_null()) \
        .select("game_id", "season", "week", "team", "gsis_id", "position", "group", "report_status")


def snap_table(snaps: pl.DataFrame, players: pl.DataFrame) -> pl.DataFrame:
    idmap = players.filter(pl.col("pfr_id").is_not_null(), pl.col("gsis_id").is_not_null()) \
        .select(pl.col("pfr_id").alias("pfr_player_id"), "gsis_id").unique("pfr_player_id")
    return snaps.filter(pl.col("game_type") == "REG").with_columns(_fr("team").alias("team")) \
        .join(idmap, on="pfr_player_id", how="left") \
        .select("game_id", "team", "gsis_id", "offense_pct", "defense_pct",
                (pl.col("offense_snaps") + pl.col("defense_snaps") + pl.col("st_snaps")).alias("snaps"))


def play_probabilities(reports: pl.DataFrame, snaps: pl.DataFrame) -> dict:
    """P(took > 0 snaps | status), on the given (training) reports. Only players known to the snap data
    (mapped id, at least one snap row anywhere) count, so an id-mapping gap is not read as 'did not play'."""
    known = snaps.filter(pl.col("gsis_id").is_not_null())["gsis_id"].unique().implode()
    r = reports.filter(pl.col("gsis_id").is_in(known))
    played = snaps.filter(pl.col("snaps") > 0).select("game_id", "team", "gsis_id").unique().with_columns(pl.lit(1).alias("played"))
    r = r.join(played, on=["game_id", "team", "gsis_id"], how="left").with_columns(pl.col("played").fill_null(0))
    out = {}
    for s in STATUSES:
        x = r.filter(pl.col("report_status") == s)["played"]
        p = float(x.mean()) if x.len() else float("nan")
        out[s] = {"p_play": p, "n": int(x.len()), "se": float(np.sqrt(p * (1 - p) / max(x.len(), 1)))}
    return out


def injury_features(tg: pl.DataFrame, reports: pl.DataFrame, snaps: pl.DataFrame, p_play: dict) -> pl.DataFrame:
    """Expected missing snap share by group: sum over reported players of (1 - p_play(status)) x share,
    share = mean snap pct over the team's previous 4 REG games (0 where the player did not appear)."""
    prev = {}
    for (team,), grp in tg.sort("t").group_by(["team"], maintain_order=True):
        ids = grp["game_id"].to_list()
        for i, g in enumerate(ids):
            prev[(g, team)] = ids[max(0, i - 4):i]
    pct = {}
    for r in snaps.filter(pl.col("gsis_id").is_not_null()).iter_rows(named=True):
        pct[(r["game_id"], r["team"], r["gsis_id"])] = (r["offense_pct"] or 0.0, r["defense_pct"] or 0.0)
    acc: dict = {}
    for r in reports.iter_rows(named=True):
        games = prev.get((r["game_id"], r["team"]), [])
        if not games:
            continue
        off = r["group"] in OFF_GROUPS
        share = sum(pct.get((g, r["team"], r["gsis_id"]), (0.0, 0.0))[0 if off else 1] for g in games) / len(games)
        key = (r["game_id"], r["team"])
        acc.setdefault(key, {g: 0.0 for g in GROUPS})
        acc[key][r["group"]] += (1 - p_play[r["report_status"]]["p_play"]) * share
    rows = [{"game_id": g, "team": t, **v} for (g, t), v in acc.items()]
    f = pl.DataFrame(rows, schema={"game_id": pl.Utf8, "team": pl.Utf8, **{g: pl.Float64 for g in GROUPS}})
    base = tg.select("game_id", "team", "opp")
    own = base.join(f.select("game_id", "team", *OFF_GROUPS), on=["game_id", "team"], how="left")
    opp = f.select("game_id", pl.col("team").alias("opp"), *[pl.col(g).alias(f"opp_{g}") for g in DEF_GROUPS])
    return own.join(opp, on=["game_id", "opp"], how="left").fill_null(0.0).drop("opp")


# ---------------------------------------------------------------- assemble

def build(sched, dropbacks, injuries, snaps, players, depth25, D, k, prior, p_play,
          targets: list[str] | None = None, depth_old: pl.DataFrame | None = None,
          depth_season: int = 2025) -> pl.DataFrame:
    """All v3 features per REG team-game. Starter: the `depth_season` depth chart (point-in-time snapshots;
    2025 in evaluation, the current season live), else the recorded starter, or (sensitivity check, when
    `depth_old` is given) the weekly depth-chart QB1 where one exists."""
    tg = team_game_frame(sched)
    if depth25 is not None and tg.filter(pl.col("season") == depth_season).height:
        st = starters_from_depth(tg, depth25, injuries, depth_season)
        tg = tg.join(st, on=["game_id", "team"], how="left")
    else:
        tg = tg.with_columns(pl.lit(None, pl.Utf8).alias("qb_depth"), pl.lit(None, pl.Boolean).alias("qb1_out"),
                             pl.lit(None, pl.Utf8).alias("snapshot"))
    tg = tg.with_columns(pl.when(pl.col("season") == depth_season).then(pl.coalesce("qb_depth", "qb_recorded"))
                         .otherwise(pl.col("qb_recorded")).alias("starter"))
    if depth_old is not None:
        tg = tg.join(starters_weekly(depth_old), on=["season", "week", "team"], how="left").with_columns(
            pl.when(pl.col("season") < depth_season).then(pl.coalesce("qb_weekly", "qb_recorded"))
            .otherwise(pl.col("starter")).alias("starter"))
    qbg = qb_games(dropbacks)
    rater = QBRater(qbg, D, k, prior)
    st_tab = snap_table(snaps, players)
    reps = injury_reports(injuries, tg)
    q = qb_features(tg, qbg, rater)
    inj = injury_features(tg, reps, st_tab, p_play)
    out = tg.join(q, on=["game_id", "team"], how="left").join(inj, on=["game_id", "team"], how="left")
    out = out.with_columns([pl.col(c).fill_null(0.0) for c in ("ol", "skill", "opp_dl", "opp_lb", "opp_db")])
    if targets is not None:
        out = out.filter(pl.col("game_id").is_in(targets))
    return out
