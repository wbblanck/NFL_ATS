import polars as pl

from engine.gamesim_v2.data import identity as ID


def _players():
    return pl.DataFrame({
        "gsis_id": ["00-0000001", "00-0000002", "ABB498348", ""],
        "display_name": ["A One", "A Two", "Old Timer", "Nobody"],
        "pfr_id": ["OneA00", None, "OldTi00", None], "esb_id": ["ONE1", "TWO2", "ABB498348", None],
        "pff_id": ["1", "2", None, None], "espn_id": ["1", "2", None, None], "nfl_id": [None] * 4,
        "smart_id": ["s1", "s2", None, None], "birth_date": ["1990-01-01", "1991-02-02", "1960-03-03", None],
        "position_group": ["QB", "WR", "QB", None], "position": ["QB", "WR", "QB", None],
        "rookie_season": [2012, 2013, 1982, None], "last_season": [2020, 2024, 1988, None],
        "draft_year": [None] * 4, "draft_round": [None] * 4, "draft_pick": [None] * 4,
        "height": [75, 72, 74, None], "weight": [220, 200, 210, None], "college_name": [None] * 4})


def _rosters():
    return pl.DataFrame({
        "gsis_id": ["00-0000001", "00-0000002", "00-0000003", "00-0000002"], "pfr_id": ["OneA00", "TwoA00", "ThreA00", "OneA00"],
        "esb_id": ["ONE1", "TWO2", "THR3", "TWO2"], "pff_id": ["1", "2", "3", "2"], "espn_id": ["1", "2", "3", "2"],
        "smart_id": ["s1", "s2", "s3", "s2"], "full_name": ["A One", "A Two", "A Three", "A Two"],
        "birth_date": [None] * 4, "position": ["QB", "WR", "TE", "WR"], "rookie_year": [2012, 2013, 2020, 2013],
        "season": [2020] * 4, "week": [1, 1, 1, 2], "team": ["OAK", "SD", "KC", "SD"], "game_type": ["REG"] * 4, "status": ["ACT"] * 4})


def _snaps():
    return pl.DataFrame({"pfr_player_id": ["OneA00", "NewG00", "OldTi00"], "player": ["A One", "New Guy", "Old Timer"],
                         "position": ["QB", "RB", "QB"], "season": [2020, 2021, 2020]})


def test_one_uid_per_person_and_ids_never_stolen():
    ident = ID.build_identity(_players(), _rosters(), _snaps())
    assert ident["uid"].n_unique() == ident.height
    # roster says A Two owns pfr id OneA00, but `players` gives it to A One: players wins, the id is not reassigned
    assert ident.filter(pl.col("uid") == "00-0000001")["pfr_id"][0] == "OneA00"
    assert ident.filter(pl.col("uid") == "00-0000002")["pfr_id"][0] is None or ident.filter(pl.col("uid") == "00-0000002")["pfr_id"][0] == "TwoA00"
    assert ident["pfr_id"].drop_nulls().is_duplicated().sum() == 0


def test_sources_and_pfr_only_and_legacy_ids():
    ident = ID.build_identity(_players(), _rosters(), _snaps())
    src = dict(zip(ident["uid"], ident["source"]))
    assert src["00-0000003"] == "roster_only"       # on a roster, missing from players
    assert src["pfr:NewG00"] == "pfr_only"          # snap counts only
    assert src["ABB498348"] == "players"            # legacy 9-character id is a valid key
    assert "" not in src                            # empty gsis_id is not an id and has no other id to key on


def test_team_history_unifies_franchises():
    ident = ID.build_identity(_players(), _rosters(), _snaps())
    h = ID.team_history(_rosters(), ident)
    assert set(h["team"]) == {"LV", "LAC", "KC"}
    assert h.height == 4


def test_diagnostics_flag_conflicts():
    ident = ID.build_identity(_players(), _rosters(), _snaps())
    d = ID.diagnostics(ident, _rosters(), _snaps())
    assert d["duplicate_uid"] == 0
    assert d["pfr_id_on_multiple_uids"] == []
    assert d["snap_rows_unmapped"] == 0
    assert len(d["gsis_with_multiple_pfr_in_rosters"]) == 1   # 00-0000002 has TwoA00 and OneA00 in the roster rows
    assert len(d["pfr_with_multiple_gsis_in_rosters"]) == 1   # OneA00 is on two gsis ids in the roster rows


def test_legacy_id_merged_into_gsis_when_name_and_birthdate_match():
    pl_ = _players().vstack(pl.DataFrame({
        "gsis_id": ["00-0000009", "ABC123456"], "display_name": ["Same Guy", "Same Guy"], "pfr_id": [None, None],
        "esb_id": [None, None], "pff_id": [None, None], "espn_id": [None, None], "nfl_id": [None, None], "smart_id": [None, None],
        "birth_date": ["2000-01-01", "2000-01-01"], "position_group": ["WR", "WR"], "position": ["WR", "WR"],
        "rookie_season": [2022, 2022], "last_season": [2024, 2024], "draft_year": [None] * 2, "draft_round": [None] * 2,
        "draft_pick": [None] * 2, "height": [72, 72], "weight": [200, 200], "college_name": [None] * 2}, schema=_players().schema))
    ident = ID.build_identity(pl_, _rosters(), _snaps())
    c = dict(zip(ident["uid"], ident["canonical_uid"]))
    assert c["ABC123456"] == "00-0000009" and c["00-0000009"] == "00-0000009"
    assert ID.diagnostics(ident, _rosters(), _snaps())["same_name_birthdate_multiple_uids"] == []
