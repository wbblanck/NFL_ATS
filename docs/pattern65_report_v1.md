# Is there a 65% pattern in our picks? (exploratory, 2026-11-03)

Will asked for any subset of picks that has hit about 65% against the spread, even if it might be noise. This is an
exploratory search, not a pre-registered test. Nothing here changes the official pick. Code: `scripts/pattern65_search.py`;
numbers: `data/backtests/pattern65.json`.

## Short answer

Yes, 65%+ subsets exist. Hundreds of them. They are what a search this wide produces from a ~55% pick stream, and none of
them has held up on data it was not found in. The one thing that is real is already known: picks that follow a market move
of 2+ points after the pool line was set win about 60%, not 65%.

## What was searched

| Set | Picks | Graded against | Record |
|---|---|---|---|
| Backtest of the official model, 2007-2021 | 3,722 | SBRO open (proxy for the pool line); model sees the close | 2,043-1,679 (54.9%) |
| CBS-open holdout, 2025 | 267 | CBS open | 130-137 (48.7%) |
| Live official picks, 2026 weeks 3-8 | 78 | pool line | 42-36 (53.8%) |
| Market sides only, nflverse close, 1999-2025 | 13,556 side-rows | close | 50.0% by construction |

Not available in this container: the 2022-2024 AusSportsBetting file (gitignored, never committed). 2022-24 is therefore
missing from every number below.

Features sliced (every 1-, 2- and 3-way combination, at least 30 picks per subset; team only 1-2 way): pick side, favorite
or dog, spread size, exactly 3 / exactly 7 / half-point line, week bucket, kickoff slot, division game, roof, rest edge,
game total, model confidence, market move since the pool line, pick team. That is 6,752 subsets in the backtest.

## The 65% subsets, and how much to trust them

**Backtest 2007-2021:** 302 of 6,752 subsets hit 65% or better (n at least 30). Shuffling the win/loss labels 500 times
gives 253 on average (95th percentile 326), so the real count is not unusual (shuffle P = 0.14). The best single subset
(Weeks 10-14, total 44.5-48, pick follows a 2+ point move) is 81-27 (75%, n = 108) with p = 1.3e-5 against the 54.9% base.
The Holm bar for 6,752 tests is 7.4e-6, so even the best one misses it, before counting that the feature list itself was
chosen after looking at data.

**Out of sample (the check that matters).** Freeze every 65% subset found in 2007-2014, score it on 2015-2021, then on
2025 and 2026. And the reverse.

| Subsets frozen from | Found | Later half of backtest | 2025 CBS | 2026 live |
|---|---|---|---|---|
| 2007-2014 | 378 | 57.5% pooled, 54.8% as one union (n 1,630) | 51.5% / 48.6% union | 59.5% / 52.9% union (n 68) |
| 2015-2021 | 313 | 57.6% pooled, 56.0% union (n 1,749) | 53.9% / 49.3% union | 53.1% / 55.1% union (n 49) |

A rule found at 65%+ and tested later runs 55-58%, which is about the base rate of this pick stream. The 2025 result is
at or below 50%. That is the usual shrinkage from picking the best of many.

**Market-only sides (1999-2025, no model):** zero subsets reach 65% with n of at least 100. The best is 63.9% (n 100+),
which is what shuffled data gives (median 64.0%). No betting angle on the closing line shows up in these features.

**2026 live only (78 picks):** 32 of 179 subsets hit 65% (n at least 12); shuffled data gives 18 on average (95th
percentile 32). Best: spread 3 or less, 21-8 (72%, n = 29), p = 0.013 against the 53.8% base, versus a Holm bar of 0.0003.
In earlier years that same subset was 55.9% (773-611, 2007-21) and 52.5% in 2025 (53-48). A 21-8 start is within what
luck produces, and it has no history behind it.

## Named candidates, tracked across every window

Selected after seeing the data, so the 2007-2021 columns are in-sample. Only the 2025 and 2026 columns are fresh.

| Candidate | 2007-21 | 2007-14 | 2015-21 | 2025 CBS | 2026 live |
|---|---|---|---|---|---|
| Pick follows a 2+ pt move (all weeks) | 662-447 (60%) | 59% | 60% | 28-21 (57%) | 4-3 |
| Weeks 10-14 and 2+ pt move | 193-94 (67%) | 65% | 69% | 5-4 | none yet |
| Weeks 10-14 and model confidence 8+ pts | 120-55 (69%) | 69% | 69% | 3-3 | none yet |
| Half-point line, outdoors, confidence 8+ | 133-60 (69%) | 72% | 67% | 13-8 (62%) | 2-2 |
| Half-point line, outdoors, 2+ pt move | 194-101 (66%) | 67% | 65% | 16-11 (59%) | 4-3 |
| Favorite on exactly 3, small move | 93-56 (62%) | 72% | 47% | 4-4 | none yet |
| Spread 3 or less | 773-611 (56%) | 57% | 54% | 53-48 (52%) | 21-8 (72%) |

The two week 10-14 rows and the half-point/outdoor rows replicate across the two halves of 2007-21, which is the best
thing in the search. They also point the same way in 2025, but on 8-21 games that proves nothing. Two reasons to stay
skeptical. First, they are overlapping slices of the same effect: "confidence 8+" and "move 2+" are the same games
(every confidence 8+ pick is a 2+ move pick). Second, the week 10-14 flag is one of four week buckets, chosen after seeing
that it was the best; confidence 8+ picks win 58.1% in weeks 1-4, 54.6% in weeks 5-9, 68.6% in weeks 10-14, 58.8% in weeks 15+.
There is no football reason for November to differ, and 2007-2021 is the only sample behind it.

A harder test of "replicates in both halves": 96 subsets hit 65% in both 2007-14 and 2015-21 (at least 15 picks each). Shuffled
labels give 63 on average (95th percentile 90, P = 0.03). That is mildly above luck, but it is explained by the real 2+ pt
move effect (those subsets are almost all move/confidence slices), not by anything independent of it.

## What is real

Following a move of 2+ points since the pool line is set has won 59.7% of 1,109 picks (2007-21), with no season near 50%
(season rates 55-70%). The size of the move matters: under 0.5 pts 51.6%, 0.5-1.5 pts 52.2%, 1.5-2.5 pts 57.9%, 2.5+ pts 60.2%.
That is the market-move signal docs/mining_report.md already named as the only thing beyond chance. It is 60%, not 65%, it
is already in the official pick, and in 2025 (57% on 49) and 2026 (4-3) it is too thin to tell.

## Other tracked 2026 comparisons (live, n small)

- Official pick when it agrees with the shadow key-number estimator: 32-23 (58%); when they disagree, 10-13. All three
  tracked models (key-number, v1, v3) agree with the official pick: 17-11 (61%, n = 28).
- Shadow key-number estimator on its own: 42-27 (61%). It is closed as a lead: it failed out of sample on 2022-24 (38-40).
- 9 of the 78 official picks were fallback picks with no model input (forced away); they went 6-3. Treat as noise.

## Caveats

- Backtest picks are graded against the SBRO open, not the CBS line, and the the SBRO close stands in for the market at lock.
- Spread, week and slot cuts are not independent, so the 6,752 tests count fewer independent hypotheses than the Holm bar
  assumes; the bar is conservative in that direction, but the choice of features was not blind.
- 2026 is 78 picks. One more win or loss moves any subset by 3-8 points.
- This search used 2007-21 as discovery for the 2025/2026 checks. 2022-2024 is unused here and could serve as one more
  out-of-sample check if the AusSportsBetting file is re-uploaded (personal use only; never committed).

## Bottom line

- 65% is a number you can find; it is not a number that has held. Every 65%+ pattern found in one window fell to 55-58%
  or below in the next, which is the shrinkage this search design predicts.
- Best candidate to watch, labeled as a guess: weeks 10-14 plus a 2+ pt move (or model confidence 8+). Current record
  193-94 in-sample, 5-4 outside. A pre-registered forward test needs roughly 300 qualifying picks to separate 65%
  from 58%. This pattern produced about 19 a season, so that is around 15 seasons; it cannot pay off in the 2026 pool.
- The official pick is unchanged. Nothing merged.
