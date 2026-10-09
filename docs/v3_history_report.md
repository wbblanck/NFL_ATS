# v3 History: Report

Rules: `docs/v3_history_preregistration.md` (committed before any grading, `5d4b346`). Numbers:
`data/backtests/v3_history.csv`, `data/backtests/v3_history_checks.json`, `data/backtests/bettable.json`; code
`engine/backtest/v3_history.py` (`python -m engine v3-history`).

## The rebuild reproduces the published run

815 scored games in Test A (2022-2024), 272 in Test B (2025), and the 2025 half-point-open records (v3 104 wins, v1 107
wins of 210) all match `data/backtests/players_v3.json` exactly. (D, k) = (365, 500). The 1,065 games scored here are
those also in the live-model backtest set.

## Result: v3 is not profitable, and it trails the live model in the pool

| Same 1,065 games | Pool line (stale) | Bet at the closing line (-110) |
|---|---|---|
| v3 | 51.2% (545-520) | 48.7% (506-533), return **-7.0%** |
| v1 | 52.4% (558-507) | 50.6% (526-513), -3.4% |
| Live (official) | 54.4% (579-486) | 49.1% (510-529), -6.3% |

- **v3 against break-even:** 48.7% [45.7, 51.7] on 1,039 bets, z = -2.38; it does not clear Holm over the five models.
- By period at the close: 2022-2024 47.9% (370-403), 2025 51.1% (136-130).
- **In the pool v3 is worse than the live model on identical games** (51.2% vs 54.4%), and no better than v1.
- The strong 2026 live numbers for v3 (21-8 against the pool line, 19-9 against the line at the pick) have no
  historical support in this rebuild; 29 games say little.

## Limits

- About 1,000 games, so this can show v3 is clearly not an improvement; it cannot rule out a small real edge.
- v3 was not refit year by year, as registered.
