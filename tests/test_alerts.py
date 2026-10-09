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


def test_send_posts_the_text_to_the_topic_and_never_raises():
    seen = {}

    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def ok(req, timeout):
        seen.update(url=req.full_url, body=req.data, title=req.get_header("Title"))
        return R()

    assert A.send("Picks locked: LAC +7.5", "topic123", opener=ok) is True
    assert seen == {"url": "https://ntfy.sh/topic123", "body": b"Picks locked: LAC +7.5", "title": "NFL picks"}

    def boom(req, timeout):
        raise OSError("network down")

    assert A.send("x", "t", opener=boom) is False
    assert A.send("x", "", opener=ok) is False and A.send("", "t", opener=ok) is False


def test_send_uses_env_topic_and_skips_without_one(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert A.send("x", opener=lambda *a, **k: 1 / 0) is False           # no topic: nothing is attempted


def _row(gid, flags, mtl=5.0, books=14, ko="2026-09-27T17:00:00+00:00"):
    a, h = gid.split("_")[2:4]
    return {"game_id": gid, "away_team": a, "home_team": h, "kickoff_utc": ko, "flags": flags,
            "minutes_to_lock": str(mtl), "market_books": str(books)}


def test_warning_lists_flagged_picks_only():
    rows = [_row("2026_03_KC_MIA", "EARLY_PICK", mtl=43.7), _row("2026_03_ARI_SF", "FEW_BOOKS", books=4),
            _row("2026_03_NYJ_DET", "")]
    assert A.warning_message(rows) == ("CHECK PICKS: ARI@SF only 4 books"
                                       " · KC@MIA picked 44 min before lock (stale market)")
    assert A.warning_message([_row("2026_03_NYJ_DET", "")]) == ""


def test_warning_fits_the_limit():
    rows = [_row(f"2026_03_A{i}_B{i}", "EARLY_PICK;TOTAL_FROM_SCHEDULE", mtl=60) for i in range(9)]
    t = A.warning_message(rows)
    assert len(t) <= A.MAX_LEN and t.endswith("more")


def test_week3_replay_would_have_warned():
    from engine.data import store
    from engine.picks import final
    from engine import config
    p = config.ROOT / "data" / "predictions" / "predictions.csv"
    rows = [r for r in store.read_rows(p) if r["week"] == "3"]
    flagged = [r for r in rows if float(r["minutes_to_lock"]) > final.EARLY_PICK_MIN]
    assert len(flagged) == 14          # every week 3 pick except PHI@CHI (5 min)


def test_full_message_lists_every_model_and_marks_disagreements(monkeypatch):
    monkeypatch.setattr(A.strength, "table", lambda: {})            # no validated tiers: no strength tag
    r = _p("2026_04_NE_BUF", "NE", "BUF", "BUF", -6.5, _k(27, 13))
    r.update(drift="-0.5", p_home_cover="0.506", p_away_cover="0.494", shadow_pick_keynum="BUF")
    projs = {"2026_04_NE_BUF": {"proj-poisson-v1": "NE", "proj-players-v3": "NE"}}
    m = A.full_message([r], projs).split("\n")
    assert m[0] == "Picks locked (Sun 1:00 PM): BUF −6.5"
    assert m[1] == ("NE@BUF: Pick BUF −6.5 (moved ½ pt, 51%) | Hybrid NE +6.5 ≠ · v1 NE +6.5 ≠ · v3 NE +6.5 ≠"
                    " · Key BUF −6.5")


def test_full_message_tags_the_strength_tier_only_when_validated(monkeypatch):
    r = _p("2026_04_ARI_NYG", "ARI", "NYG", "ARI", 0.5, _k(27, 13))
    r.update(drift="3.0", p_home_cover="0.40", p_away_cover="0.60")
    monkeypatch.setattr(A.strength, "table", lambda: {"ok": True, "tiers": {}})
    assert "moved 3 pts, 60%, Max)" in A.full_message([r]).split("\n")[1]
    monkeypatch.setattr(A.strength, "table", lambda: {"ok": False, "tiers": {}})
    assert "Max" not in A.full_message([r]).split("\n")[1]


def test_full_message_big_move_keeps_hybrid_on_the_pick_and_handles_missing_models():
    r = _p("2026_04_ARI_NYG", "ARI", "NYG", "ARI", 0.5, _k(27, 13))
    r.update(drift="1.5", p_home_cover="0.433", p_away_cover="0.567")
    line = A.full_message([r], {"2026_04_ARI_NYG": {"proj-poisson-v1": "NYG"}}).split("\n")[1]
    assert "moved 1½ pts, 57%" in line and "Hybrid ARI −0.5 ·" in line and "v1 NYG +0.5 ≠" in line
    assert "v3 —" in line and "Key —" in line


def test_full_message_stays_under_ntfy_limit():
    rows = [_p(f"g{i}", f"AA{i}", f"BB{i}", f"AA{i}", -3.5, _k(27, 13)) for i in range(200)]
    assert len(A.full_message(rows).encode()) <= A.FULL_MAX_BYTES


def test_full_message_marks_v3_without_injury_report():
    r = _p("2026_04_ARI_NYG", "ARI", "NYG", "ARI", 0.5, _k(27, 13))
    r.update(drift="1.5", p_home_cover="0.433", p_away_cover="0.567")
    projs = {"2026_04_ARI_NYG": {"proj-players-v3": "NYG", "v3_no_injury_report": True}}
    assert "v3 NYG +0.5 ≠ (no injury report)" in A.full_message([r], projs)
    projs["2026_04_ARI_NYG"].pop("v3_no_injury_report")
    assert "no injury report" not in A.full_message([r], projs)
