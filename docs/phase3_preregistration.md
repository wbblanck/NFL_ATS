# Phase 3 — Drift Model: Pre-registration

This file was written and committed **before** any Phase 3 result was computed.
The git history is the timestamp.

## Hypothesis

The league line is set once and frozen. The market keeps moving until kickoff.
If the market's movement carries information, then picking the side the market
moved toward will beat the frozen line more than 50% of the time.

## Data

- **Frozen line (proxy):** SBRO opening line, 2007–2021, regular season. The
  league line itself is CBS's Tuesday-noon number, which is not available
  historically (data audit 0.3).
- **Market at lock (proxy):** SBRO closing line for the same games. It reflects
  kickoff rather than kickoff −15 min, a small look-ahead gap. That gap will be
  measured from the live `market_captures.csv` once 2026 games accumulate.
- **Drift** = close home spread − open home spread. Negative means the market
  moved toward the home team.
- **Scores:** nflverse. Games with an unusable SBRO open or close are excluded
  and counted.
- **Pushes:** games landing exactly on a whole-number *open* are pushes. They
  are excluded from win rate and reported separately.

## Strategies

1. **Primary, D0: sign of drift.** Pick home if drift < 0, away if drift > 0.
   Games with drift = 0 have no signal. They are excluded from D0's win rate
   and counted.
2. **D0-full: every game picked.** Same as D0, but drift = 0 games take the
   Phase 2 bar strategy, *always away*. This is fixed now and not chosen after
   seeing results.
3. **D-k, secondary, walk-forward.** Follow drift only when |drift| ≥ k,
   otherwise pick away. For each test season, k ∈ {0.5, 1, 1.5, 2, 2.5, 3} is
   chosen to maximize the win rate on **all prior seasons only**. The first
   test season is 2010, trained on 2007–2009.

D0 and D0-full have no fitted parameters, so every season is out of sample
for them.

## Primary test and kill criterion

On SBRO open, 2007–2021, pooled:

- p = D0 win rate, SE = sqrt(p(1−p)/N).
- Bar = Phase 2 always-away: 0.5137, SE_bar 0.0082.
- **PASS** only if both of the following hold:
  - (p − 0.5) / SE ≥ 1.96, and
  - (p − 0.5137) / sqrt(SE² + SE_bar²) ≥ 1.96.
- **Otherwise Phase 3 FAILS.** The failure is reported plainly, and no more
  complex modeling is started to rescue it (spec rule 6).

## Secondary analyses

These are diagnostics only and do not decide the gate.

- **Monotonicity:** win rate by |drift| bucket, using fixed buckets
  {0.5}, {1}, {1.5}, {2, 2.5}, {3, 3.5, 4}, {≥ 4.5}. Plus a logistic
  regression of "picked side covered" on |drift|, reporting the slope and its
  SE.
- **Key numbers:** D0 split by whether the move crossed 3 or 7.
- **Per season:** every season is reported, with no filtering.
- **D0-full and D-k:** reported with SE, per season and pooled.

## Known threats, stated in advance

- **SBRO's open is earlier than CBS's Tuesday-noon line.** Some of the
  movement it captures happens before CBS posts, and CBS's line already
  reflects that part. So historical drift overstates the drift that is
  actually available against the league line. The size of that overstatement
  is unknown until the 2026 captures (CBS line plus market snapshots) exist.
- **Close vs lock:** the close includes the last 15 minutes of movement, which
  a lock-time pick could not see.
