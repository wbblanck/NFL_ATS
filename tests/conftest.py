import shutil
from pathlib import Path

import polars as pl
import pytest

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    """Isolated repo root: real config, empty data dir."""
    shutil.copytree(REPO / "config", tmp_path / "config")
    monkeypatch.setenv("NFL_ATS_ROOT", str(tmp_path))
    import engine.config as c
    monkeypatch.setattr(c, "ROOT", tmp_path)
    c.data.cache_clear(); c.league.cache_clear(); c.model.cache_clear()
    yield tmp_path
    c.data.cache_clear(); c.league.cache_clear(); c.model.cache_clear()


@pytest.fixture(autouse=True)
def no_pinnacle_retry_wait(monkeypatch):
    """The pick path waits once before a Pinnacle retry. Tests use fake market events, so do not sleep."""
    from engine.picks import final
    monkeypatch.setattr(final, "PINNACLE_RETRY_WAIT_S", 0)


@pytest.fixture
def week3_schedule():
    """Subset of the real 2026 week-3 schedule (nflverse, pulled 2026-09-24)."""
    from engine.data.nflverse import with_kickoff
    rows = [
        ("2026_03_ATL_GB", "ATL", "GB", "2026-09-24", "20:15"),
        ("2026_03_NE_JAX", "NE", "JAX", "2026-09-27", "13:00"),
        ("2026_03_CAR_CLE", "CAR", "CLE", "2026-09-27", "13:00"),
        ("2026_03_KC_MIA", "KC", "MIA", "2026-09-27", "13:00"),
        ("2026_03_LA_DEN", "LA", "DEN", "2026-09-27", "16:25"),
    ]
    df = pl.DataFrame(rows, schema=["game_id", "away_team", "home_team", "gameday", "gametime"], orient="row")
    df = df.with_columns(pl.lit(2026).alias("season"), pl.lit(3).alias("week"), pl.lit("REG").alias("game_type"))
    return with_kickoff(df)
