# Pick-Model Variants on the 2026 Season: Report

Rules: `docs/variants2026_preregistration.md` (committed before any result). Numbers and per-game rows:
`data/backtests/variants2026.json`, from `python -m engine.backtest.variants2026`. Research only: the official
pick, the live record and every workflow are unchanged.

## Bottom line

**No variant beats the official pick.** None of the 13 tests passed Holm, and none got near the unadjusted
p ≤ 0.10 needed to qualify for live tracking (the best was 0.26). Every record, including the five models
already tracked, sits inside the range coin flips produce on 94 games (38 to 56 wins). Nothing qualifies for
live tracking under the pre-registered rule.

One lead is worth writing down for next season. On older lines, the key-number estimator did well in exactly
two kinds of games: no-move games and games where the line crossed 3 or 7. That data overlaps with the
key-number study that already failed overall, so this is a lead, not a finding (see "Leads" below).

## Data

94 graded 2026 games: 32 in weeks 1-2 (market = nflverse close), 46 live picks with a market at lock, and 16
rebuilt missed games. Method check: re-running the official estimator reproduced the official pick in 94 of 94
games and its cover probability to within 0.005 in 94 of 94. The rebuilt lock-time snapshot matched the
recorded Pinnacle line in 18 of 18 games and the recorded all-book median in 26 of 26. Two live games used
OddsPapi's Pinnacle, which isn't in the snapshot, so they keep the official market.

One fix was made before any result was computed. Week 3 and the first two week-4 picks used the all-book median
(Pinnacle became the input on 2026-10-04), so the market source is read from `feature_version`, not from the
flag.

## Primary test (pooled 2026, games where the candidate picks differently from official)

| # | Candidate | Games differing | Candidate won / official won | One-sided p | Holm |
|---|---|---|---|---|---|
| C1 | Fresh-quote consensus | 0 | n/a | n/a | fail |
| C2 | Price-adjusted line | 12 | 6 / 6 | 0.61 | fail |
| C3 | Momentum to the close | 0 | n/a | n/a | fail |
| C4 | Hybrid + book-agreement gate | 22 | 12 / 10 | 0.42 | fail |
| C5a | Blend with v1 | 0 (w = 0) | n/a | n/a | fail |
| C5b | Blend with v3 | 0 (w = 0) | n/a | n/a | fail |
| C5c | Blend with v1+v3 | 0 (w = 0) | n/a | n/a | fail |
| C6a | Hybrid, v3 fill | 22 | 13 / 9 | 0.26 | fail |
| C6b | Hybrid, v1+v3 average fill | 24 | 14 / 10 | 0.27 | fail |
| C6c | Hybrid, key-number fill | 14 | 8 / 6 | 0.40 | fail |
| C7 | Switch when v1 and v3 both disagree | 29 | 15 / 14 | 0.50 | fail |
| C8 | Five-model majority vote | 22 | 13 / 9 | 0.26 | fail |
| C9 | Key-number pick when the line straddles 3/6/7/10 | 1 | 1 / 0 | 0.50 | fail |

Why several candidates never differ:
- **C1:** at lock, 562 of 579 book quotes were less than 10 minutes old (Pinnacle was stale once), so dropping
  stale books changed the market in one game and the pick in none.
- **C3:** the momentum weight k came out at 0.08 to 0.33. Moving the market a little further in the direction
  it was already going never flips a pick.
- **C4:** in no game did fewer than 60% of books agree with a 1+ point move, so the gate never fired and C4 is
  just the hybrid.
- **C5:** the blend weight fitted on 2007-2013 (686 games, v1 refit weekly) came out at −0.15, clipped to 0. So
  once the closing line is known, the team projection adds nothing on average. The blends are therefore the
  official pick. That fits the hybrid report: v1's help, if any, is limited to no-move games.

## Records against the pool line (2026, all 94 games)

| Model | All | Weeks 1-2 | Live | Rebuilt |
|---|---|---|---|---|
| Official | 54-40 | 18-14 | 24-22 | 12-4 |
| Key-number shadow | 57-37 | 19-13 | 28-18 | 10-6 |
| v1 | 52-42 | 16-16 | 28-18 | 8-8 |
| v3 | 54-40 | 18-14 | 27-19 | 9-7 |
| Hybrid | 56-38 | 20-12 | 26-20 | 10-6 |
| C6a / C6b / C8 (best) | 58-36 | 20-12 / 21-11 / 20-12 | 26-20 / 26-20 / 27-19 | 12-4 / 11-5 / 11-5 |

The best is 4 wins ahead of official over 94 games. The coin-flip band is 38 to 56 wins.

Cover margin (how many points the pick beat the pool line by, candidate minus official, 95% interval from
resampling whole weeks): every interval contains 0. For example, C6b gives −0.06 (−2.0 to +1.8) and C8 gives
−0.30 (−1.8 to +1.7). With only 7 weeks to resample, these intervals are rough. Brier score: 0.244 for official
and for every candidate that has a probability.

## History check (sanity only, cannot promote anything)

| Candidate | SBRO 2014-2021 (825 games, open = pool proxy) | 2025 CBS open (210 games) |
|---|---|---|
| C5a blend with v1 | w = 0: no games differ | w = 0: no games differ |
| C6c hybrid, key-number fill | 123 differ, 74-49 (net +25, p = 0.015) | 36 differ, 19-17 (net +2) |
| C9 key-number on straddles | 46 differ, 33-13 (net +20, p = 0.002) | 12 differ, 7-5 (net +2) |

Official on the same sets: 446-379 (SBRO), 108-102 (2025).

## Leads (not findings)

The SBRO numbers for C6c and C9 look strong, but they are not independent evidence:
- **Same data as the key-number study.** That study's primary test was the same SBRO 2007-2021 set. It failed
  overall, and its report already noted that `keynum` "gained 13 games next to 3 and 7 but lost more
  elsewhere". C9 is a slice chosen after reading that, so its 33-13 is partly a re-discovery of a known pattern.
- **The clean seasons are weak.** In 2025 (CBS open) both are only +2. In 2026, C9 changed one pick and C6c went
  8-6.

Follow-up done: `docs/keynum_combo_report.md` (failed on AusSportsBetting 2022-2024, 38-40). The original next step was a new pre-registration that combines the two ideas (key-number pick in no-move
and straddle games, official elsewhere). It would be tested on a line source the key-number study never used:
the AusSportsBetting 2014-2024 opens, which need the `nfl.xlsx` file back on this machine. From then on it would
be tracked live like the hybrid, never as the pick.

## Not testable

- **Pool contrarian strategy:** CBS shows the pool's pick percentages only for the current week, so there is no
  history. It would need a weekly capture from now on.
- **Candidate 10 (total-conditioned spread):** void. The official estimator already does it.
