"""Team EPA by component, season to date (descriptive; shown on the game page, never used by the pick).

Components, from nflverse play-by-play (regular season, games before the given week):
  pass_off / rush_off   EPA on the team's own pass / designed-run plays (no turnover, penalty or special-teams play)
  pass_def / run_def    minus the EPA opponents gained on those plays (positive = good defense)
  turnovers             net EPA on every play with an interception or lost fumble (giveaways and takeaways)
  penalties             EPA on accepted-penalty plays, charged to the penalized team (for) or its opponent (against)
  special_teams         net EPA on kicks, punts, field goals and extra points
Values are per game played; ranks are 1 = best of 32. The split follows the @SamHoppen chart (nflfastR); pass,
rush, defense and turnovers reproduce it to within a point or two, penalties and special teams differ by definition.
"""
from __future__ import annotations

import polars as pl

COMPONENTS = [("pass_off", "Pass offense"), ("rush_off", "Rush offense"), ("pass_def", "Pass defense"),
              ("run_def", "Run defense"), ("turnovers", "Turnovers"), ("penalties", "Penalties"),
              ("special_teams", "Special teams")]


def _side(p: pl.DataFrame, mask: pl.Expr, team_col: str, sign: float) -> pl.DataFrame:
    return p.filter(mask).group_by(team_col).agg((pl.col("epa").sum() * sign).alias("v")).rename({team_col: "team"})


def _net(a: pl.DataFrame, b: pl.DataFrame) -> pl.DataFrame:
    return a.join(b, on="team", how="full", coalesce=True).select(
        "team", (pl.col("v").fill_null(0) + pl.col("v_right").fill_null(0)).alias("v"))


def compute(pbp: pl.DataFrame, before_week: int) -> dict:
    """{'through_week': int, 'teams': {team: {'games': n, comp: [per_game, rank], ...}}}."""
    p = pbp.filter(pl.col("season_type") == "REG", pl.col("week") < before_week, pl.col("epa").is_not_null(),
                   pl.col("posteam").is_not_null())
    if p.height == 0:
        return {"through_week": before_week - 1, "teams": {}}
    to = (pl.col("interception").fill_null(0) == 1) | (pl.col("fumble_lost").fill_null(0) == 1)
    pen = pl.col("penalty").fill_null(0) == 1
    st = pl.col("special_teams_play").fill_null(0) == 1 if "special_teams_play" in p.columns else \
        pl.col("play_type").is_in(["kickoff", "punt", "field_goal", "extra_point"])
    p = p.with_columns(to.alias("_to"), pen.alias("_pen"), st.alias("_st"))
    base = ~pl.col("_to") & ~pl.col("_pen") & ~pl.col("_st")
    pas, run = base & (pl.col("pass") == 1), base & (pl.col("rush") == 1)
    comp = {"pass_off": _side(p, pas, "posteam", 1), "rush_off": _side(p, run, "posteam", 1),
            "pass_def": _side(p, pas, "defteam", -1), "run_def": _side(p, run, "defteam", -1),
            "turnovers": _net(_side(p, pl.col("_to"), "posteam", 1), _side(p, pl.col("_to"), "defteam", -1)),
            "special_teams": _net(_side(p, pl.col("_st") & ~pl.col("_pen") & ~pl.col("_to"), "posteam", 1),
                                  _side(p, pl.col("_st") & ~pl.col("_pen") & ~pl.col("_to"), "defteam", -1))}
    pp = p.filter(pl.col("_pen") & ~pl.col("_to") & pl.col("penalty_team").is_not_null()).with_columns(
        pl.when(pl.col("penalty_team") == pl.col("posteam")).then(pl.col("epa")).otherwise(-pl.col("epa")).alias("v"))
    comp["penalties"] = pp.group_by("penalty_team").agg(pl.col("v").sum()).rename({"penalty_team": "team"})
    games = pl.concat([p.select("game_id", pl.col("posteam").alias("team")),
                       p.select("game_id", pl.col("defteam").alias("team"))]).unique() \
        .group_by("team").len().rename({"len": "games"})
    out: dict = {}
    for r in games.iter_rows(named=True):
        out[r["team"]] = {"games": int(r["games"])}
    for key, _ in COMPONENTS:
        d = comp[key].join(games, on="team").with_columns((pl.col("v") / pl.col("games")).alias("pg")) \
            .with_columns(pl.col("pg").rank("ordinal", descending=True).cast(pl.Int32).alias("rank"))
        for r in d.iter_rows(named=True):
            out.setdefault(r["team"], {"games": r["games"]})[key] = [round(float(r["pg"]), 2), int(r["rank"])]
    return {"through_week": int(p["week"].max()), "teams": out}
