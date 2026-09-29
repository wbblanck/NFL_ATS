import datetime as dt

from engine.picks import alerts as A

UTC = dt.timezone.utc


def _k(day, h, m=0):
    return dt.datetime(2026, 9, day, h, m, tzinfo=dt.timezone(dt.timedelta(hours=-4))).astimezone(UTC)


def _p(gid, away, home, pick, line, ko, created="2026-09-27T16:01:20+00:00", flags="", supersedes=""):
    return {"game_id": gid, "away_team": away, "home_team": home, "pick_team": pick, "league_line": str(line),
            "kickoff_utc": ko.isoformat(), "created_at": created, "flags": flags, "supersedes": supersedes}


def test_pool_spread_is_the_picked_teams_spread():
    assert A.pool_spread(_p("g", "PHI", "CHI", "PHI", 3.5, _k(28, 20, 15))) == -3.5      # away pick, home +3.5
    assert A.pool_spread(_p("g", "LAC", "BUF", "BUF", -7.5, _k(27, 13))) == -7.5
    assert A.pool_spread(_p("g", "LAC", "BUF", "LAC", -7.5, _k(27, 13))) == 7.5
    assert A.pool_spread({"pick_team": "X", "home_team": "Y", "league_line": ""}) is None


def test_message_lists_picks_with_true_minus_and_slot_label():
    rows = [_p("b", "CAR", "CLE", "CLE", 2.5, _k(27, 13)), _p("a", "LAC", "BUF", "LAC", -7.5, _k(27, 13))]
    m = A.message(rows)
    assert m == "Picks locked (Sun 1:00 PM): LAC +7.5 · CLE +2.5"
    assert A.message([_p("a", "PHI", "CHI", "PHI", 3.5, _k(28, 20, 15))]) == "Picks locked (Mon 8:15 PM): PHI −3.5"
    late = A.message([_p("a", "PHI", "CHI", "PHI", 3.5, _k(28, 20, 15), flags="LATE_AFTER_LOCK")])
    assert late.endswith("PHI −3.5 LATE")
    two = A.message([_p("a", "ARI", "SF", "ARI", -8.5, _k(27, 16, 5)), _p("b", "BAL", "DAL", "BAL", 2.5, _k(27, 16, 25))])
    assert "(Sun 4:05 & 4:25 PM)" in two


def test_message_fits_the_notification_limit_and_says_how_many_were_cut():
    rows = [_p(f"g{i}", f"AA{i}", f"BB{i}", f"AA{i}", -3.5, _k(27, 13)) for i in range(16)]
    m = A.message(rows)
    assert len(m) <= 200 and " more" in m and "\n" not in m
    assert A.message([]) == ""


def test_pick_without_a_team_is_called_out():
    r = _p("g", "AAA", "BBB", "", "", _k(27, 13))
    assert "AAA@BBB NO PICK" in A.message([r])


def test_new_rows_ignores_old_superseded_and_other_games():
    rows = [_p("a", "A", "B", "A", 1.5, _k(27, 13), created="2026-09-27T16:00:00+00:00"),
            _p("b", "C", "D", "C", 1.5, _k(27, 13), created="2026-09-27T16:10:00+00:00"),
            _p("c", "E", "F", "E", 1.5, _k(27, 13), created="2026-09-27T16:10:00+00:00", supersedes="x"),
            _p("d", "G", "H", "G", 1.5, _k(27, 13), created="2026-09-27T16:10:00+00:00")]
    got = A.new_rows(rows, "2026-09-27T16:05:00+00:00", ids={"a", "b", "c"})
    assert [r["game_id"] for r in got] == ["b"]


def _due(gid, away, home, lock):
    return {"game_id": gid, "away_team": away, "home_team": home, "lock_utc": lock}


def test_watch_step_alerts_once_per_group_and_finishes_when_all_are_picked():
    due = [_due("a", "A", "B", _k(27, 13)), _due("b", "C", "D", _k(27, 16))]
    now = _k(27, 11)
    warned: set = set()
    lines, since, done = A.watch_step([], "2026-09-27T00:00:00+00:00", due, warned, now)
    assert lines == [] and not done
    preds = [_p("a", "A", "B", "A", 1.5, _k(27, 13), created="2026-09-27T16:01:00+00:00")]
    lines, since, done = A.watch_step(preds, "2026-09-27T00:00:00+00:00", due, warned, now)
    assert len(lines) == 1 and lines[0].startswith("Picks locked") and not done and since == "2026-09-27T16:01:00+00:00"
    lines, since, done = A.watch_step(preds, since, due, warned, now)
    assert lines == []                                                                    # nothing new: no repeat
    preds.append(_p("b", "C", "D", "C", 2.5, _k(27, 16), created="2026-09-27T19:50:00+00:00"))
    lines, since, done = A.watch_step(preds, since, due, warned, now)
    assert len(lines) == 1 and done


def test_missing_pick_warning_is_sent_once_and_only_close_to_lock():
    lock = _k(27, 13)
    due = [_due("a", "AAA", "BBB", lock)]
    warned: set = set()
    assert A.watch_step([], "x", due, warned, lock - dt.timedelta(minutes=20))[0] == []          # far from lock
    lines, _, _ = A.watch_step([], "x", due, warned, lock - dt.timedelta(minutes=2))
    assert len(lines) == 1 and lines[0].startswith("PICK MISSING: AAA@BBB locks in 2 min")
    assert A.watch_step([], "x", due, warned, lock - dt.timedelta(minutes=1))[0] == []            # once only


def test_label_falls_back_to_a_count_across_days():
    m = A.message([_p("a", "A", "B", "A", 1.5, _k(27, 13)), _p("b", "C", "D", "C", 1.5, _k(28, 20, 15))])
    assert m.startswith("Picks locked (2 games): ")
