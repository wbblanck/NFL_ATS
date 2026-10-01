# Predicting the Line Move, Betting the Opener: Pre-registration

Committed before any bet was graded. Code: `engine/backtest/alt_markets.py` (`run_move`, `ratings_before`),
checks in `tests/test_alt_markets.py` (ratings recover known strengths; synthetic informative ratings are found,
uninformative ones are not). Output: `data/backtests/alt_markets.json`.

Question: can a rating built from information available before the opening line predict which way the line
moves, well enough to make the opener profitable? The pool result (docs/phase3_report.md: the side the market
moves toward beats the open, 54.84%) says moves carry information; every earlier fundamentals test targeted the
final margin, none the move.

## Seen before this was written (disclosed)

Line-only: SBRO open-to-close moves, 4,008 games, mean |move| 1.36 points, 740 no-move games. Phase 3 (move →
cover) is known. No rating-versus-open result has been computed.

## Data and models (constants fixed here, not tuned)

- SBRO opening spread (book and time UNVERIFIED), nflverse closing spread and final score, regular season
  2007–2021 (4,010 games with an open). Ratings use only games in the 16 played weeks before the game's week.
- **A, market memory:** ridge least squares of prior games' closing lines (expected margin = HFA + r_home −
  r_away), λ = 1.
- **B, margin rating:** the same on prior games' actual margins, λ = 20.
- D = rating's home spread − open. Bet home at the open when D ≤ −1, away when D ≥ +1. Graded against the open,
  pushes dropped, −110 assumed (break-even 52.38%).

## Tests (family of 2, Bonferroni: one-sided 2.5% each), all 2007–2021 (no constant was fitted)

**PASS** (per model) if the week-clustered 95% interval of the win rate at the open has its lower end above
52.38%.

Reported, not deciding: the coefficient on the rating in OLS close = a + b·open + c·rating (c > 0 means the
rating knows something about the close beyond the open; a regression of (close − open) on (rating − open) is NOT
used, because the shared open term biases it upward); share of bets where the close moved toward the bet.
