# Market-disagreement model: pre-registration and development-tier result

Registered 2026-11-26 on Will's approval (audit B, item 5). Research only. Nothing about any pick changes, and no capture
workflow is touched.

## What is tested

Does any information beyond the lock-time market predict the final margin? Target: the residual r = margin + c (c = home
spread at lock, negative = home favored). Every model predicts a shift in r, orthogonalised to c, with a ridge penalty. The
shift is scored by log score of P(home covers) against the same quantity with no shift, so a model only earns credit for
information the market does not already carry. A shift of 0.86 points (signal SD 3.45 times a disagreement weight of 0.25)
is the smallest useful effect: it is worth about +0.9 percentage points of win rate.

Blocks (each is a feature set, fit separately and then combined):

| Block | Inputs |
|---|---|
| Q | QB delta (starter vs team QB baseline) |
| I | injury loads by position group |
| X | rest, bye, short week, travel |
| M | Pinnacle open-to-lock move, Pinnacle minus median gap, total move, number of books |

## Tiers

- Development: nflverse 2013-2021, rolling origin, test seasons 2016-2021 (1,552 games), blocks Q, I, X. Holm over 3 blocks.
- Burned: 2022-2025. Used by earlier audits, so it cannot confirm anything. It is a consistency check only.
- Forward: 2026 weeks 3-18 live games with captures. Block M can only be tested here, because history has no timestamped
  Pinnacle lines. Fewer than 256 games exist this season, so a 2026 forward test can only rule large effects out. A confirming
  result needs 2027 as well (about 1,360 games for w = 0.25; this is a power calculation, not a plan to run it).

## Development-tier result (run 2026-11-26)

Script `scripts/audit_B/followup_F_devtier.py`. Mean log-score gain per game against the no-shift model, one-sided p
for gain > 0, and the effective shift in points (slope of r on the model's shift, times its SD).

| Block | Mean gain | One-sided p | Effective shift (95% bound) |
|---|---|---|---|
| Q | -0.00016 | 0.56 | 0.21 +/- 0.34 (upper 0.77) |
| I | -0.00048 | 0.74 | -0.07 +/- 0.37 (upper 0.53) |
| X | +0.00028 | 0.115 | 0.45 +/- 0.33 (upper 0.99) |
| Q+I+X combined | -0.00010 | 0.57 | 0.09 +/- 0.34 (upper 0.65) |

No block passes Holm over 3 (smallest p is 0.115). Q, I and the combined model rule out the 0.86-point effect at about the
95% bound. X does not: it is neither shown nor excluded. These are bounds on a linear shift only; they say nothing about
interactions I did not try.

## Block M: what can be measured today

From `data/lines/market_captures.csv` with captures at or before kickoff minus 15 minutes (`scripts/block_m_features.py`):
126 games have a Pinnacle line before lock. 100 of them span at least 24 hours (weeks 3-9). Weeks 10-11 have only the
lock-time row, week 12 has none, and the total's open-to-lock move is not captured at all. So block M is unusable for
a test as things stand. The move feature is also the pick itself in most games, which must be separated before any claim.

## Decision for Will (not made here)

Block M needs Pinnacle history that the capture jobs do not keep. Options, neither implemented:
1. Daily Pinnacle snapshot for NFL from OddsPapi, about 30 of the 250 monthly requests. Touches live capture.
2. One-off pull from OddsPapi's free `/historical-odds` (history from January 2026 only, works only from GitHub Actions).
3. Do nothing: block M stays untested and the other blocks stay at no evidence.

## Rules for any later test

One run per tier, parameters frozen before looking, Holm across blocks, game-clustered bootstrap, no re-use of the burned
tier for confirmation, and any positive result must beat the plain follow-the-move rule on the same games before it
changes anything. A change to a pick needs Will's approval.
