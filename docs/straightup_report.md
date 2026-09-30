# Picking Winners (Straight Up): Report

Rules: `docs/straightup_preregistration.md` (committed before any result). Numbers: `data/backtests/straightup.json`;
code `engine/backtest/straightup_eval.py` (test) and `engine/picks/straightup.py` (tracker).

## Close-game test: fail (the market favorite stays the pick)

| Closing spread 2.5 or less | Games | Projection | Market favorite | Games that differ: projection / market won |
|---|---|---|---|---|
| v1, 2010–2025 (primary) | 943 | 467 (49.5%) | 499 (52.9%) | 185 / 217, z = −1.60 |
| v1, 2010–2017 | 464 | 235 | 245 | 90 / 100 |
| v1, 2018–2025 | 479 | 232 | 254 | 95 / 117 |
| v3, 2022–2024 | 204 | 102 | 116 | 37 / 51 |

On all games the gap is larger: v1 2,658 vs the market's 2,767 of 4,162 (66.5%); v3 520 vs 557 of 813.

The market's win probabilities are well calibrated: it expected 2,722 wins and got 2,767.

## Tracker: removed

A tracker panel was built, then removed at the user's request (2026-09-30): a winner-picking model that cannot beat
the market favorite (about 66%) adds nothing. The close-game test above is kept as the record.
