# Handoff: play-by-play game simulator (ported from nfl-betting-model)

Built and tested in `wbblanck/nfl-betting-model` (PRs #10 and #11, merged 2026-11-05). Ported here so the hybrid rule
can be tested with the simulator in place of v1. **Research only: nothing here touches the live pick pipeline.**

## What was ported
| Here | From nfl-betting-model | What it is |
|---|---|---|
| `src/engine/gamesim/engine.py` | `src/nflbet/gamesim/engine.py` | Vectorized snap-by-snap engine: down, distance, field position, clock, 4th-down and 2-point decisions, kicks, overtime |
| `league.py`, `teams.py`, `run.py` | same names | League tables fit on 2016-2020; per-team offense/defense factors from earlier games only; runner over a schedule |
| `personnel.py` | same | Starting-QB and injury layer (G3) |
| `coverage.py` | same | Man/zone layer (did not help; kept for completeness, off by default) |
| `elo.py` | `src/nflbet/ats/elo.py` | Elo + Poisson/negative binomial baseline |
| `data/gamesim/*.json` | `data/backtests/gamesim_constants.json`, `gamesim_league.json`, `elo_constants.json` | Frozen constants. Do not refit them on 2022+ data. |
| `scripts/gamesim_reproduce.py` | `scripts/gamesim_confirm.py` (G3 part) | Regenerates the 2022-2025 output and checks it against the registered MAE |
| `tests/test_gamesim.py`, `tests/test_gamesim_elo.py` | same tests | Known-answer checks |

Not ported: the player/prop layer and the props-mix tracker (props only).

## Sign conventions
The simulator works in nflverse's sign: `fair` = mean simulated **home margin** (positive = home wins by that much).
This repo's spread is negative when the home team is favored, so the simulator's fair spread here is `-fair`, and the
home team covers a spread `s` when `margin > -s`. `scripts/gamesim_reproduce.py` writes `close_spread` already in
this repo's sign.

## Seasons: what is clean
- Fit 2016-2020, explore 2021, confirm once on 2022-2025. **Only 2022-2025 are out of sample for the simulator.**
  Any simulator test on 2014-2021 here would be in-sample and cannot be used as evidence.
- The 2022-2025 per-game output is fixed by seed 101 and 1000 runs per game. `scripts/gamesim_reproduce.py` refuses
  to write it unless G3's margin MAE reproduces 9.983.

## What it showed (nfl-betting-model docs, 2022-2025, 1023 games, weeks 2-18)
- Margin MAE: simulator G3 9.983, plain Elo 9.964, closing spread 9.537. Elo and the simulator are not
  distinguishable (Elo − G3 −0.019, interval −0.288 to +0.246).
- No information beyond the closing spread; betting its 1.5+ point disagreements at the close: 49.6% covers, ROI −4.7%.
- Line movement: from bet365's opener the line moves about 30% of the gap toward the simulator by the close (Elo: 23%).
- Bet at the opener, 2025 only (174 bets): 53.4% covers, ROI −0.8%, beat the close by 0.84 points: failed.
- Cover probabilities near 3 and 7 are not trustworthy (equal teams land on 3 12.0% of the time vs 14.2% actual).
  Use the mean margin, not the cover probability, to pick a side.

## How to run
```
pip install -e .
python scripts/gamesim_reproduce.py /tmp/gamesim_cache   # downloads nflverse files on first use; about 6 min on 4 cores after that
pytest tests/test_gamesim.py tests/test_gamesim_elo.py
```
Output: `data/gamesim/g3_2022_2025.parquet` (sim_fair, elo_fair, margin, close_spread, and the simulator's margin
distribution m_-60 .. m_60).

## Next step: hybrid with the simulator (not yet pre-registered)
Will wants the hybrid rule (`docs/hybrid_preregistration.md`, `docs/hybrid_tracking.md`) tried with the simulator.
Suggested design, to be written up and committed as `docs/hybrid_sim_preregistration.md` **before** joining the
simulator output to any line data:
- Same structure as the hybrid: 1+ point move off the proxy line keeps the live pick; on ½/no-move games use the
  simulator's side against the proxy line (sim fair margin vs the line; a tie keeps the live pick).
- No selection step: one candidate, tested once on 2022-2024 (AusSportsBetting open/close, as edge2), net vs the
  live model with the one-sided z already used for the hybrid. 2025 CBS opens reported, not tested.
- State the power in advance: roughly 175 ½/no-move games in three seasons is far too few to detect a 3-point gain,
  so a fail says "no evidence", not "no effect".
- Plain Elo as a second, descriptive candidate, since it matched the simulator on margin.
AusSportsBetting data stays local; never commit it.
