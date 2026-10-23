# Key-Number Pick in No-Move and Straddle Games: Pre-registration

Committed before any result of this rule on the data below was computed. Follow-up to the lead in
`docs/variants2026_report.md`. Research only: no change to the official pick.

## Why, and what has already been seen

`docs/variants2026_report.md` found, on SBRO opens 2014-2021, that the key-number estimator (`keynum`) beat
the official pick in no-move games (C6c: 74-49) and in games where the line straddled 3, 6, 7 or 10 (C9:
33-13). Those games overlap the key-number study's data, so they are not evidence. Also seen: both rules on
2025 CBS opens (+2 each) and on 2026 (C6c 8-6, C9 1-0). Not seen: `keynum` against any AusSportsBetting line.

## Rule (KN)

Proxy pool line L = the book's half-point open, market m = the book's close (as in edge2 and the hybrid study).
- If |m − L| < 1 (no move by the hybrid's definition), or a key number (±3, ±6, ±7, ±10) lies between L and m
  (inclusive of m): the `keynum` pick.
- Otherwise: the official pick.

Official = the total-conditioned shifted estimator (`TotalDist("shifted_total")`); `keynum` = `MarginDist("keynum")`.
Both are fitted on nflverse closes and margins from seasons before the test season, exactly as in `edge2.dists`.

## Primary test (decides)

**AusSportsBetting 2022-2024** (bet365 lines; these games come after SBRO ends in 2021, so no earlier key-number
result touched them). On the games where KN and official differ: KN wins vs official wins, one-sided exact
binomial, **pass at p ≤ 0.05**. This is one test, so there is no correction.

## Secondary (reported, do not decide)

- The same comparison on AusSportsBetting 2014-2021. These are the same games as the SBRO lead with different
  lines, so not independent.
- The two halves of the rule separately (no-move only, straddle only) on each set.
- 2025 CBS opens and 2026 (94 games, `data/backtests/variants2026.json`), for reference.
- Records against L for official, `keynum` and KN; mean cover margin difference with a week-clustered 95%
  interval.

## What a result means

- **Pass:** propose KN to the user as a tracked comparison, like the hybrid (shown on the dashboard, never the
  pick), judged by the hybrid's rule (z ≥ 1.645 on differing games). Switching the official pick would still need
  the user's approval and the 256-game rule.
- **Fail:** the lead is closed. It was a re-slice of data that had already been seen.

## Power, stated in advance

On SBRO about 20% of games changed (169 of 825), so roughly 90 of the ~450 games in 2022-2024 should differ.
With 90 differing games, p ≤ 0.05 needs about 54 wins (60%). A true 55% edge on those games would pass only
about 1 time in 4, so a fail means "no evidence", not "no effect".
