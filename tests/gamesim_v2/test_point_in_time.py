from datetime import datetime, timezone

import polars as pl

from engine.gamesim_v2.data import snapshots as S


def _frames():
    ko = [datetime(2020, 9, 13 + 7 * i, 17, 0, tzinfo=timezone.utc) for i in range(3)] + [datetime(2021, 9, 12 + 7 * i, 17, 0, tzinfo=timezone.utc) for i in range(3)]
    gid = [f"g{i}" for i in range(6)]
    tg = pl.DataFrame({"game_id": gid, "season": [2020] * 3 + [2021] * 3, "week": [1, 2, 3, 1, 2, 3], "kickoff_utc": ko,
                       "team": ["A"] * 6, "opp": ["B"] * 6, "home": [True] * 6}).with_columns(pl.col("kickoff_utc").dt.convert_time_zone("UTC"))
    rows = []
    for g in gid[:5]:
        rows.append(("g" + g[1:], g, "A", "X", "QB", 60.0, 0.0, 0.0, 1.0, 0.0))
    rows.append(("y", "g4", "A", "Y", "WR", 30.0, 0.0, 0.0, 0.5, 0.0))     # Y first plays in g4, so is unknown before it
    sn = pl.DataFrame([dict(zip(["_", "game_id", "team", "uid", "position", "offense_snaps", "defense_snaps", "st_snaps", "offense_pct", "defense_pct"], r)) for r in rows]).drop("_")
    inj = pl.DataFrame(schema={"game_id": pl.String, "team": pl.String, "uid": pl.String, "status": pl.String, "practice": pl.String,
                               "report_primary_injury": pl.String, "injury_ts": pl.Datetime("us", "UTC"), "injury_ts_verified": pl.Boolean})
    ident = pl.DataFrame({"uid": ["X", "Y"], "gsis_id": ["X", "Y"], "position": ["QB", "WR"]})
    return tg, sn, inj, ident


def test_pool_uses_only_earlier_games_and_players_unknown_before_debut_are_missing():
    tg, sn, inj, ident = _frames()
    inj = inj.rename({"uid": "gsis_id"})
    pool = S.build_pool(tg, sn, inj, ident)
    g4 = pool.filter(pl.col("game_id") == "g4")
    assert set(g4["uid"]) == {"X"}                                   # Y played g4 itself: not known before kickoff
    assert g4["games_played_prev"][0] == 4 and g4["prev_games"][0] == 4
    assert pool.filter(pl.col("uid") == "Y")["game_id"].to_list() == ["g5"]   # known only from the game after his debut
    g0 = pool.filter(pl.col("game_id") == "g0")
    assert g0.height == 0                                            # no earlier games, no pool


def test_active_probabilities_use_only_earlier_seasons():
    tg, sn, inj, ident = _frames()
    pool = S.build_pool(tg, sn, inj.rename({"uid": "gsis_id"}), ident)
    pa = S.p_active_table(pool)
    assert pa["season"].min() == 2021                                # nothing before 2020 to learn from, 2020 learns from nothing
    n2020 = pool.filter(pl.col("season") == 2020, pl.col("in_prev_pool")).height
    assert pa.filter(pl.col("season") == 2021)["n_train"].sum() == n2020


def test_injury_rows_modified_after_cutoff_are_dropped():
    ko = pl.DataFrame({"game_id": ["g"], "season": [2020], "week": [1], "home_team": ["A"], "away_team": ["B"],
                       "kickoff_utc": [datetime(2020, 9, 13, 17, 0, tzinfo=timezone.utc)]}).with_columns(pl.col("kickoff_utc").dt.convert_time_zone("UTC"))
    inj = pl.DataFrame({"season": [2020] * 3, "week": [1] * 3, "game_type": ["REG"] * 3, "team": ["A"] * 3, "gsis_id": ["P1", "P2", "P3"],
                        "report_status": ["Out", "Questionable", "Out"], "practice_status": ["DNP"] * 3, "report_primary_injury": ["knee"] * 3,
                        "date_modified": [datetime(2020, 9, 11, 20, 0, tzinfo=timezone.utc), datetime(2020, 9, 13, 16, 30, tzinfo=timezone.utc),
                                          datetime(2020, 9, 13, 16, 55, tzinfo=timezone.utc)]})
    out = S.injury_table(inj, ko, {})
    assert set(out["gsis_id"]) == {"P1", "P2"}                       # P3 edited 5 minutes before kickoff, after the 20-minute cutoff
