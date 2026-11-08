"""Known-answer checks for the XGBoost margin model (nfl-betting-model docs/batch4_preregistration.md, checks 1-4)."""
import numpy as np
import polars as pl

from engine.gamesim import xgb as X


def test_planted_interaction_beats_linear():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, (4000, 5))
    y = 8 * x[:, 0] * (x[:, 1] > 0) + rng.normal(0, 13, 4000)
    m = X.model(400).fit(x[:3000], y[:3000])
    A = np.c_[np.ones(3000), x[:3000]]
    beta = np.linalg.lstsq(A, y[:3000], rcond=None)[0]
    lin = np.c_[np.ones(1000), x[3000:]] @ beta
    assert np.abs(m.predict(x[3000:]) - y[3000:]).mean() < np.abs(lin - y[3000:]).mean()


def test_noise_not_better_than_mean():
    rng = np.random.default_rng(2)
    x, y = rng.normal(0, 1, (2500, 17)), rng.normal(0, 13, 2500)
    m = X.model(400).fit(x[:1500], y[:1500])
    xg = np.abs(m.predict(x[1500:]) - y[1500:]).mean()
    base = np.abs(y[:1500].mean() - y[1500:]).mean()
    assert xg > base * 0.99


def fake_pbp(n_games):
    rows = []
    for g in range(n_games):
        for t, o in (("AAA", "BBB"), ("BBB", "AAA")):
            for k in range(3):
                rows.append({"season_type": "REG", "epa": float(g + k), "play_type": "pass", "posteam": t, "defteam": o,
                             "game_id": f"g{g:02d}", "game_date": f"2020-01-{g + 1:02d}"})
    return pl.DataFrame(rows)


def test_rolling_no_lookahead():
    full = X.rolling_epa(fake_pbp(12))
    part = X.rolling_epa(fake_pbp(6))
    j = part.join(full, on=["game_id", "team"], suffix="_f").drop_nulls("off8")
    assert j.height > 0 and np.allclose(j["off8"], j["off8_f"]) and np.allclose(j["def8"], j["def8_f"])
    first = full.filter(pl.col("game_id") == "g00")
    assert first["off8"].is_null().all()
    g9 = full.filter(pl.col("game_id") == "g09", pl.col("team") == "AAA")["off8"][0]
    assert abs(g9 - np.mean([g + k for g in range(1, 9) for k in range(3)])) < 1e-9  # games 1-8 only


def test_same_seed_same_output():
    rng = np.random.default_rng(3)
    x, y = rng.normal(0, 1, (500, 4)), rng.normal(0, 1, 500)
    assert np.array_equal(X.model(100).fit(x, y).predict(x), X.model(100).fit(x, y).predict(x))
