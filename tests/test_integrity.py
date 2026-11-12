"""Prediction and grading integrity: per-row line validation, frozen-line grading, one prediction per game."""
import csv
import datetime as dt
import json

import polars as pl

from engine.data import league_lines as LL
from engine.data import store
from engine.picks import final, live
from tests.conftest import FIX
from tests.test_final_picks import LOCK, _league, _with_history

EVENTS = json.loads((FIX / "parlay_nfl_spreads_trimmed.json").read_text())
HDR = "game_id,season,week,home_team,away_team,spread,favorite,source,recorded_at\n"
GB = "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n"
JAX = "2026_03_NE_JAX,2026,3,JAX,NE,-3.5,JAX,test,x\n"
CLE = "2026_03_CAR_CLE,2026,3,CLE,CAR,2.5,CAR,test,x\n"
MIA = "2026_03_KC_MIA,2026,3,MIA,KC,-1.5,MIA,test,x\n"
NOON_LOCK = dt.datetime(2026, 9, 27, 16, 45, tzinfo=dt.timezone.utc)   # 1:00 PM ET games, lock = kickoff - 15 min


def _lines(root, rows):
    p = root / "data" / "lines" / "league_lines.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(HDR + rows)


# ---- league line validation, row by row -------------------------------------------------------------

def test_one_malformed_row_does_not_invalidate_the_others(tmp_root):
    _lines(tmp_root, GB + "2026_03_NE_JAX,2026,3,JAX,NE,abc,JAX,test,x\n" + CLE)
    ls = LL.load_checked()
    assert set(ls.valid) == {"2026_03_ATL_GB", "2026_03_CAR_CLE"}
    assert ls.status("2026_03_NE_JAX") == LL.INVALID
    assert [i["kind"] for i in ls.problems()] == [LL.INVALID_ROW] and ls.problems()[0]["line"] == 3
    assert [r["game_id"] for r in LL.load()] == ["2026_03_ATL_GB", "2026_03_CAR_CLE"]


def test_invalid_favorite_whole_number_and_missing_spread(tmp_root):
    _lines(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,ATL,test,x\n"           # favorite is the wrong side
                     "2026_03_NE_JAX,2026,3,JAX,NE,-3.0,JAX,test,x\n"           # whole number
                     "2026_03_CAR_CLE,2026,3,CLE,CAR,,CAR,test,x\n" + MIA)      # missing spread
    ls = LL.load_checked()
    assert set(ls.valid) == {"2026_03_KC_MIA"}
    msgs = {i["game_id"]: i["message"] for i in ls.problems()}
    assert "inconsistent" in msgs["2026_03_ATL_GB"] and "whole-number" in msgs["2026_03_NE_JAX"] \
        and "missing spread" in msgs["2026_03_CAR_CLE"]


def test_unknown_team_and_blank_game_id_are_rejected(tmp_root):
    _lines(tmp_root, "2026_03_ATL_GB,2026,3,GB,Nowhere,-6.5,GB,test,x\n,2026,3,JAX,NE,-3.5,JAX,test,x\n" + MIA)
    ls = LL.load_checked()
    assert set(ls.valid) == {"2026_03_KC_MIA"} and len(ls.problems()) == 2


def test_identical_duplicate_keeps_first_row_deterministically(tmp_root):
    _lines(tmp_root, GB + "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,second source,y\n")
    ls = LL.load_checked()
    assert ls.valid["2026_03_ATL_GB"]["source"] == "test" and ls.status("2026_03_ATL_GB") == LL.VALID
    assert [i["kind"] for i in ls.issues] == [LL.DUPLICATE_IDENTICAL] and ls.problems() == []


def test_conflicting_duplicate_quarantines_only_that_game(tmp_root):
    _lines(tmp_root, GB + "2026_03_ATL_GB,2026,3,GB,ATL,-3.5,GB,later,y\n" + JAX)
    ls = LL.load_checked()
    assert ls.status("2026_03_ATL_GB") == LL.CONFLICTING and "2026_03_ATL_GB" not in ls.valid
    assert "-6.5" in ls.problems()[0]["message"] and "-3.5" in ls.problems()[0]["message"]
    assert ls.status("2026_03_NE_JAX") == LL.VALID


def test_missing_game_has_no_line_status(tmp_root):
    _lines(tmp_root, GB)
    assert LL.load_checked().status("2026_03_NE_JAX") == LL.NO_LINE


def test_schedule_mismatch_is_rejected(tmp_root, week3_schedule):
    _lines(tmp_root, GB + "2026_03_KC_MIA,2026,3,KC,MIA,-1.5,KC,test,x\n"        # home/away swapped
                     "2026_03_DAL_NYG,2026,3,NYG,DAL,-1.5,NYG,test,x\n")           # not in the schedule
    ls = LL.load_checked(week3_schedule)
    assert set(ls.valid) == {"2026_03_ATL_GB"}
    assert {i["kind"] for i in ls.problems()} == {LL.SCHEDULE_MISMATCH}
    assert ls.status("2026_03_KC_MIA") == LL.INVALID


def test_line_id_is_stable_and_changes_with_the_line():
    r = {"game_id": "g", "spread": "-6.5", "source": "s", "recorded_at": "t"}
    assert LL.line_id(r) == LL.line_id(dict(r)) and LL.line_id(r) != LL.line_id(dict(r, spread="-7.5"))


# ---- lock run: a bad row never stops the slate; line provenance is recorded --------------------------

def test_lock_run_survives_bad_and_conflicting_rows_and_flags_them(tmp_root, week3_schedule):
    _lines(tmp_root, JAX + "2026_03_CAR_CLE,2026,3,CLE,CAR,2.0,CAR,test,x\n" + MIA
           + "2026_03_KC_MIA,2026,3,MIA,KC,-2.5,MIA,later,y\n")
    sched = _with_history(week3_schedule)
    out = {r["game_id"]: r for r in final.run(sched, now=NOON_LOCK - dt.timedelta(minutes=20), events=EVENTS)}
    assert set(out) == {"2026_03_NE_JAX", "2026_03_CAR_CLE", "2026_03_KC_MIA"}
    assert out["2026_03_NE_JAX"]["league_line"] == -3.5 and "LEAGUE_LINE" not in out["2026_03_NE_JAX"]["flags"]
    bad, conf = out["2026_03_CAR_CLE"], out["2026_03_KC_MIA"]
    assert bad["league_line"] is None and "LEAGUE_LINE_INVALID" in bad["flags"] and "NO_LEAGUE_LINE" in bad["flags"]
    assert conf["league_line"] is None and "LEAGUE_LINE_CONFLICT" in conf["flags"]
    assert bad["data_status"] == conf["data_status"] == "incomplete"
    frz = {r["game_id"]: r for r in store.read_rows(final.line_freeze_path())}
    assert frz["2026_03_NE_JAX"]["line_id"].startswith("LL-") and frz["2026_03_NE_JAX"]["line_status"] == "VALID"
    assert frz["2026_03_CAR_CLE"]["line_status"] == "INVALID" and frz["2026_03_CAR_CLE"]["line_id"] == ""
    assert frz["2026_03_KC_MIA"]["line_status"] == "CONFLICT"
    assert frz["2026_03_NE_JAX"]["prediction_id"] == out["2026_03_NE_JAX"]["prediction_id"]


# ---- one official prediction per game ---------------------------------------------------------------

def test_append_unique_rejects_existing_and_in_batch_duplicates(tmp_path):
    p = tmp_path / "x.csv"
    rows = [{"k": "a", "v": 1}, {"k": "a", "v": 2}, {"k": "b", "v": 3}]
    done, rej = store.append_unique(p, ["k", "v"], rows, key="k")
    assert [r["v"] for r in done] == [1, 3] and [r["v"] for r in rej] == [2]
    done, rej = store.append_unique(p, ["k", "v"], [{"k": "b", "v": 9}, {"k": "c", "v": 4}], key="k")
    assert [r["k"] for r in done] == ["c"] and [r["k"] for r in rej] == ["b"]
    assert [r["k"] for r in csv.DictReader(open(p))] == ["a", "b", "c"]


def test_race_between_check_and_write_cannot_duplicate_a_prediction(tmp_root, week3_schedule, monkeypatch, capsys):
    _lines(tmp_root, GB)
    sched = _with_history(week3_schedule)
    now = LOCK - dt.timedelta(minutes=20)
    assert len(final.run(sched, now=now, events=EVENTS)) == 1
    monkeypatch.setattr(final, "existing_game_ids", lambda: set())        # a second run that checked too early
    assert final.run(sched, now=now + dt.timedelta(minutes=1), events=EVENTS) == []
    assert len(store.read_rows(final.predictions_path())) == 1 and len(store.read_rows(final.line_freeze_path())) == 1
    assert "DUPLICATE PREDICTION REJECTED" in capsys.readouterr().err


# ---- grading: one result per game, frozen line ------------------------------------------------------

def _played(sched):
    """ATL@GB final 21-24: GB won by 3, so ATL covers -6.5 and GB covers... only with a line below -3."""
    g = pl.col("game_id") == "2026_03_ATL_GB"
    return sched.with_columns(pl.when(g).then(3).otherwise(pl.col("result")).alias("result"),
                              pl.when(g).then(24).otherwise(None).alias("home_score"),
                              pl.when(g).then(21).otherwise(None).alias("away_score"))


def _one_pick(tmp_root, week3_schedule, lines=GB):
    _lines(tmp_root, lines)
    sched = _with_history(week3_schedule)
    final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS)
    return _played(sched)


def _dup_prediction(tmp_root):
    rows = store.read_rows(final.predictions_path())
    d = dict(rows[0], prediction_id="dup-id", created_at="2026-09-24T23:59:00+00:00")
    with open(final.predictions_path(), "a", newline="") as f:
        csv.DictWriter(f, fieldnames=final.FIELDS).writerow(d)


def test_duplicate_prediction_rows_are_graded_once(tmp_root, week3_schedule):
    played = _one_pick(tmp_root, week3_schedule)
    _dup_prediction(tmp_root)
    s = live.compute(played)[0]
    assert (s["W"], s["L"], s["N"]) == (1, 0, 1)
    assert len(s["duplicate_predictions"]) == 1 and s["duplicate_predictions"][0]["ignored"] == "dup-id"
    live.grade(played)
    assert "DUPLICATE PREDICTIONS" in (tmp_root / "data/predictions/live_record.md").read_text()


def test_256_game_threshold_counts_unique_games(tmp_root):
    preds = [{"game_id": f"g{i % 3}", "prediction_id": f"p{i}", "created_at": f"2026-01-01T00:00:{i % 60:02d}"}
             for i in range(300)]
    kept, dups = live.unique_predictions(preds)
    assert len(kept) == 3 and len(dups) == 297 and len(kept) < live.MIN_GAMES_FOR_CLAIM


def test_grading_uses_the_frozen_line_not_a_later_file_edit(tmp_root, week3_schedule):
    played = _one_pick(tmp_root, week3_schedule)                     # picked and graded against GB -6.5
    base = live.compute(played)[0]
    assert (base["W"], base["N"]) == (1, 1) and base["line_reconciliation"]["graded_on_frozen_line"] == 1
    # a later row for the same game with a different line: quarantined as a conflict, grade unchanged
    with open(tmp_root / "data/lines/league_lines.csv", "a") as f:
        f.write("2026_03_ATL_GB,2026,3,GB,ATL,-1.5,GB,correction?,z\n")
    s, rows = live.compute(played)
    assert (s["W"], s["L"], s["N"]) == (1, 0, 1) and rows[0]["league_line"] == -6.5 and rows[0]["line_source"] == "frozen"
    assert s["line_reconciliation"]["frozen_vs_file_mismatches"][0]["file_line_id"] == "CONFLICT"
    assert any("CONFLICT" in p for p in s["league_line_problems"])
    # the file rewritten to a single different line: still graded on the frozen line, mismatch is reported
    _lines(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-1.5,GB,edited,z\n")
    s, rows = live.compute(played)
    assert rows[0]["league_line"] == -6.5 and (s["W"], s["N"]) == (1, 1)
    mm = s["line_reconciliation"]["frozen_vs_file_mismatches"]
    assert mm[0]["frozen"] == -6.5 and mm[0]["file"] == -1.5
    live.grade(played)
    assert "LINE MISMATCH" in (tmp_root / "data/predictions/live_record.md").read_text()


def test_prediction_made_without_a_line_uses_the_line_recorded_afterwards(tmp_root, week3_schedule):
    played = _one_pick(tmp_root, week3_schedule, lines="")
    s, _ = live.compute(played)
    assert s["N"] == 0 and s["ungradable_by_reason"] == {"no_line": ["2026_03_ATL_GB"]}
    _lines(tmp_root, GB)
    s, rows = live.compute(played)
    assert s["N"] == 1 and rows[0]["line_source"] == "file_after_pick"
    assert s["line_reconciliation"]["graded_on_line_recorded_after_pick"] == 1


def test_game_with_only_an_invalid_line_is_ungradable_with_a_reason(tmp_root, week3_schedule):
    played = _one_pick(tmp_root, week3_schedule, lines="")
    _lines(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.0,GB,test,x\n")
    s, _ = live.compute(played)
    assert s["N"] == 0 and s["ungradable_by_reason"] == {"invalid_line": ["2026_03_ATL_GB"]}
    assert len(s["league_line_problems"]) == 1


def test_row_with_an_unquoted_comma_is_quarantined_not_silently_shifted(tmp_root):
    # an unquoted comma in `source` pushes recorded_at into an extra field (audit 2026-11-09, finding L1)
    bad = "2026_03_NE_JAX,2026,3,JAX,NE,-3.5,JAX,screenshot (sent 2:16 PM ET, phone clock not visible),2026-11-03T19:16:00Z\n"
    quoted = '2026_03_CAR_CLE,2026,3,CLE,CAR,2.5,CAR,"screenshot (sent 2:16 PM ET, phone clock not visible)",2026-11-03T19:16:00Z\n'
    _lines(tmp_root, GB + bad + quoted)
    ls = LL.load_checked()
    assert set(ls.valid) == {"2026_03_ATL_GB", "2026_03_CAR_CLE"}
    assert ls.status("2026_03_NE_JAX") == LL.INVALID
    assert ls.valid["2026_03_CAR_CLE"]["recorded_at"] == "2026-11-03T19:16:00Z"


def test_committed_league_lines_file_has_no_malformed_rows():
    import csv
    from pathlib import Path
    with open(Path(__file__).resolve().parents[1] / "data" / "lines" / "league_lines.csv", newline="") as f:
        rows = list(csv.reader(f))
    assert {len(r) for r in rows} == {len(rows[0])}


def test_record_splits_blind_no_market_picks_from_market_picks(tmp_root, week3_schedule):
    played = _one_pick(tmp_root, week3_schedule)
    s = live.compute(played)[0]
    assert s["by_market"] == {"no_market": {"W": 0, "N": 0}, "with_market": {"W": s["W"], "N": 1}}
    live.grade(played)
    assert "picked with no market line" not in (tmp_root / "data/predictions/live_record.md").read_text()
    rows = store.read_rows(final.predictions_path())
    rows[0]["flags"] = "NO_MARKET;TOTAL_FROM_SCHEDULE"
    with open(final.predictions_path(), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=final.FIELDS)
        w.writeheader()
        w.writerows(rows)
    s = live.compute(played)[0]
    assert (s["W"] + s["L"], s["by_market"]["no_market"]["N"], s["by_market"]["with_market"]["N"]) == (1, 1, 0)
    live.grade(played)
    assert "1 were picked with no market line" in (tmp_root / "data/predictions/live_record.md").read_text()
