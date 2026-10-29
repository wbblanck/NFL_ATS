"""Known-answer checks for engine.backtest.alt_markets (run before any real result was graded)."""
import numpy as np
import polars as pl
import pytest

from engine.backtest import alt_markets as A
from engine import config


def test_teaser_breakeven():
    assert A.teaser_breakeven(-110) == pytest.approx((110 / 210) ** 0.5)
    assert A.teaser_breakeven(-120) == pytest.approx((120 / 220) ** 0.5)
    assert A.teaser_breakeven(160, legs=3) == pytest.approx((1 / 2.6) ** (1 / 3))


def _games(rows):
    return pl.DataFrame(rows, schema={"game_id": pl.Utf8, "season": pl.Int64, "week": pl.Int64,
                                      "close": pl.Float64, "margin": pl.Int64, "total": pl.Float64}, orient="row")


def test_teaser_legs_hand_cases():
    g = _games([
        ("a", 2020, 1, -2.5, -8, 44.0),   # away +2.5 dog wins by 8 -> teased +8.5 covers (8 > -8.5... away margin 8)
        ("b", 2020, 1, -7.5, 2, 41.0),    # home -7.5 fav wins by 2 -> teased -1.5 covers
        ("c", 2020, 1, -8.0, 2, 41.0),    # home -8 fav wins by 2 -> teased -2 pushes
        ("d", 2020, 1, 2.5, 9, 47.0),     # home +2.5 dog loses... home wins by 9 -> covers easily
        ("e", 2020, 1, -3.0, 3, 47.0),    # outside the window: no leg
        ("f", 2020, 1, 8.5, -9, 47.0),    # home +8.5 dog loses by 9: AWAY is -8.5 fav, wins by 9 -> teased -2.5 covers
        ("g", 2020, 1, -1.5, 9, 47.0),    # away +1.5 dog loses by 9 -> teased +7.5 loses
    ])
    legs = A.teaser_legs(g)
    got = {r["game_id"]: (r["side"], r["teased"], r["result"]) for r in legs.iter_rows(named=True)}
    assert got == {"a": ("away", 8.5, "W"), "b": ("home", 4.5 - 6.0, "W"), "c": ("home", -2.0, "P"),
                   "d": ("home", 8.5, "W"), "f": ("away", -2.5, "W"), "g": ("away", 7.5, "L")}


def test_split_2h():
    assert A._split_2h("27.5", "3") == (1, 3.0, 27.5, "ok")
    assert A._split_2h("pk", "21") == (0, 0.0, 21.0, "ok")
    assert A._split_2h("3", "3")[3] == "ambiguous"
    assert A._split_2h("x", "3")[3] == "unparsable"


def test_sbro_full_known_game():
    """2015 opener PIT @ NE (raw row: PIT 0,3,8,10 = 21; NE 0,14,7,7 = 28; 2H column PIT 27.5, NE 3)."""
    html = (config.ROOT / "data" / "raw" / "sbro" / "nfl-odds-2015-16.html").read_text()
    rec = A.parse_page_full(html, 2015)[0]
    assert (rec["h1_team1"], rec["h1_team2"]) == (3, 14)
    assert (rec["ot_team1"], rec["ot_team2"]) == (0, 0)
    assert rec["h2_team1_spread"] == 3.0 and rec["h2_total"] == 27.5      # team1 (PIT) gets +3 in the 2H
    assert (rec["ml1"], rec["ml2"]) == (300.0, -365.0)


def test_ratings_recover_known_strengths():
    rng = np.random.default_rng(1)
    teams = [f"T{i}" for i in range(8)]
    strength = dict(zip(teams, rng.normal(0, 4, 8)))
    rows = []
    for wk in range(1, 17):
        order = rng.permutation(teams)
        for h, a in zip(order[0::2], order[1::2]):
            exp = 2.0 + strength[h] - strength[a]
            rows.append({"game_id": f"{wk}{h}{a}", "season": 2020, "week": wk, "home_team": h, "away_team": a,
                         "close": -exp, "margin": int(round(exp))})
    g = pl.DataFrame(rows)
    r, hfa = A.ratings_before(g, 2020, 17, "line", lam=1e-6)
    assert hfa == pytest.approx(2.0, abs=1e-4)
    est = np.array([r[t] for t in teams]); true = np.array([strength[t] for t in teams])
    assert np.allclose(est - est.mean(), true - true.mean(), atol=1e-4)


def test_week_boot_and_record():
    s = np.repeat(np.arange(2010, 2020), 100); w = np.tile(np.repeat(np.arange(1, 11), 10), 10)
    won = np.ones(1000, dtype=bool)
    r = A.record(won, s, w, 0.5238)
    assert r["rate"] == 1.0 and r["ci95"] == [1.0, 1.0] and r["pass"]
    rng = np.random.default_rng(3)
    noise = rng.random(1000) < 0.5
    assert not A.record(noise, s, w, 0.5238)["pass"]


def _synthetic_league(seed, informative):
    """Three seasons, 8 teams. informative: fixed team strengths (prior ratings know the close);
    otherwise strengths are redrawn every week (prior ratings know nothing). The open is the close
    plus noise; margins are drawn around the close."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(8)]
    fixed = dict(zip(teams, rng.normal(0, 5, 8)))
    g, sb = [], []
    for season in (2007, 2008, 2009):
        for wk in range(1, 17):
            st = fixed if informative else dict(zip(teams, rng.normal(0, 5, 8)))
            order = rng.permutation(teams)
            for h, a in zip(order[0::2], order[1::2]):
                close = -(2.0 + st[h] - st[a])
                gid = f"{season}{wk:02d}{h}{a}"
                g.append({"game_id": gid, "season": season, "week": wk, "home_team": h, "away_team": a,
                          "close": close, "margin": int(round(-close + rng.normal(0, 13)))})
                sb.append({"game_id": gid, "season": season, "week": wk,
                           "open": round(2 * (close + rng.normal(0, 2.0))) / 2})
    return pl.DataFrame(g), pl.DataFrame(sb)


def test_move_signal_found_noise_not():
    g, sb = _synthetic_league(5, informative=True)
    r = A.run_move(g, sb, seasons=(2008, 2009))["A_market_memory"]
    assert r["pred_coef_ci95"][0] > 0.3                              # ratings carry the close
    assert r["bet_at_open_|D|>=1"]["rate"] > 0.53
    g, sb = _synthetic_league(6, informative=False)
    r = A.run_move(g, sb, seasons=(2008, 2009))["A_market_memory"]
    lo, hi = r["pred_coef_ci95"]
    assert lo < 0 < hi                                               # no information: coefficient ~0


def _synthetic_halftime(seed, overreact):
    """2007-2021, 200 games a season. True 2H expectation = 0.5 * pregame expectation. The 2H line adds
    `overreact` times the first-half margin (0 = an unbiased line)."""
    rng = np.random.default_rng(seed)
    g, sb = [], []
    for season in range(2007, 2022):
        for i in range(200):
            gid, wk = f"{season}_{i}", i // 12 + 1
            c = rng.normal(2, 6)                          # pregame expected home margin
            h1 = int(round(0.5 * c + rng.normal(0, 9)))
            true2 = 0.5 * c
            line = -(round(2 * (true2 + overreact * h1)) / 2 + 0.25)   # quarter point: no pushes on the line
            h2 = int(round(true2 + rng.normal(0, 9)))
            g.append({"game_id": gid, "close": -c})
            sb.append({"game_id": gid, "season": season, "week": wk, "h2_status": "ok", "quarters_status": "ok",
                       "h2_spread": line, "h1_margin": h1, "h2_margin": h2})
    return pl.DataFrame(g), pl.DataFrame(sb)


def test_halftime_signal_found_noise_not():
    g, sb = _synthetic_halftime(1, overreact=0.25)
    r = A.run_halftime(g, sb)
    assert r["H1_back_halftime_trailer"]["ci95"][0] > 0.5 and r["H2_regression_side"]["ci95"][0] > 0.5
    g, sb = _synthetic_halftime(2, overreact=0.0)
    r = A.run_halftime(g, sb)
    for k in ("H1_back_halftime_trailer", "H2_regression_side"):
        lo, hi = r[k]["ci95"]
        assert lo < 0.5 < hi and not r[k]["pass"]
