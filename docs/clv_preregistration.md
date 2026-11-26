# Closing-line value (CLV): definition and one pre-registered test

Registered 2026-11-26 on Will's approval (audit B, item 1). Descriptive reporting starts as soon as this file is merged; the
test counts picks created at or after the time recorded in "Window" below.

## Definition

For each graded pick, in points, from the pick's side:

    CLV = +(pool line - reference line)   for a home pick
    CLV = -(pool line - reference line)   for an away pick

All lines are home spreads (negative = home favored). Positive means the pool line was better for the pick than the reference.
Two references are reported, never mixed:

- **Close**: the nflverse closing spread (`spread_line`, sign flipped), available once the game is final.
- **Lock**: the market line the pick used (`market_at_lock`). Because the pick follows the move, this equals the size of the
  move, and it is reported only to show the lock-time line was not stale. It is not evidence of skill.

Code: `engine.picks.live.clv_points` and `_clv_summary`. They write one paragraph in `data/predictions/live_record.md`. No
win-loss grade, pick, flag or dashboard record changes.

## Why

Win-loss is the noisiest possible measure of a small edge: at 256 games its standard error is 3.1 points of win rate, and
2026 has only 240 games in weeks 3-18 (`docs/audit_2026-11_B_model_math.md`, issue 2). CLV measures the same thing
(did we get a better number than the market ended at) without the 13-point margin noise.

## First reading (2026-11-26, 117 graded games, live picks only, no backtest or reconstructed games)

- Official record: 64-53 against the frozen pool line.
- CLV against the nflverse close: **+0.75 points, SE 0.10**, over 117 games (74 positive, 36 zero, 7 negative).
- Against the lock-time market the pick used: **+0.84 points** over 108 games (the 9 blind away picks have no lock market).

## The one test

- **Hypothesis:** mean CLV against the nflverse close is above zero.
- **Test:** one-sided, mean over SE (t with n - 1 degrees of freedom), alpha 0.05, no multiplicity correction (a single test).
- **Minimum games:** 100 graded picks in the window.
- **Pass:** the lower one-sided 95% bound on the mean is above 0.
- **A pass means** the pool line is better than where the market closes, on average. It does not mean a win-rate edge. At the
  current mix of move sizes the out-of-sample table predicts a 53.6% win rate (interval 52.7% to 54.4%) if the market is
  unbiased (`docs/audit_2026-11_B2_followups.md`, section 1).
- **A fail means** the lock-time line is stale or biased relative to the close. Then the move rule gives up its edge, and the
  market input (`docs/market_input.md`) is the first thing to check.

## Window

Starts at the first lock run after this file is merged to main. The start time (UTC) is written in a one-line addendum commit
immediately after the merge. Games picked before it are reported in the descriptive paragraph but do not count toward the test.

## Limits

- The nflverse close is not Pinnacle's own close. On 70 live Pinnacle picks the lock line minus the nflverse close had mean
  -0.05 and SD 0.33 points (one game off by a point or more).
- Zero-CLV games (36 of 117) are not wasted data: they are the zero-move coin flips.
