# Is there a 65% pattern in our picks? (exploratory, v2 with 2022-24, 2026-11-03)

Supersedes v1 (written before the 2022-24 file was available). Will asked for any subset of picks that has hit about 65%
against the spread, even if it might be noise. This is an exploratory search, not a pre-registered test. Nothing here
changes the official pick. Code: `scripts/pattern65_search.py`; numbers: `data/backtests/pattern65.json`.

## Short answer

65%+ subsets are easy to find, and most of them fall back to the base rate on new data. One family is the exception so
far: **weeks 10-14 combined with a market move of 2+ points since the pool line** (or the model-confidence 8+ version of
the same games). It was 65% and 69% in the two halves of 2007-21, then **55-23 (71%) on 2022-24, which was not used to
find it**, and searching 2022-25 and pooled 2007-25 puts the same slice at the top again (253-121, 67.6%, passes Holm). It is the best 65% candidate in the data. It is still one slice picked from thousands and the week 10-14 label has no football reason behind it. Against the other weeks' move picks (57.4%) it is about z 3.5, roughly p = 0.01-0.05 after allowing for the slices tried. Treat it as a strong lead, not a proven edge.

## What was searched

| Set | Picks | Graded against | Record |
|---|---|---|---|
| Backtest of the official model, 2007-2021 | 3,722 | SBRO open (proxy for the pool line); SBRO close = market at lock | 2,043-1,679 (54.9%) |
| Same model retrained per season, 2022-2024 | 798 | bet365 open (AusSportsBetting, personal use, not committed) | 449-349 (56.3%) |
| CBS-open holdout, 2025 | 267 | CBS open | 130-137 (48.7%) |
| Live official picks, 2026 weeks 3-8 | 78 | pool line | 42-36 (53.8%) |
| Market sides only, nflverse close, 1999-2025 | 13,556 side-rows | close | 50.0% by construction |

Features sliced (every 1-, 2- and 3-way combination, at least 30 picks per subset; team only 1-2 way): pick side, favorite
or dog, spread size, exactly 3 / exactly 7 / half-point line, week bucket, kickoff slot, division game, roof, rest edge,
game total, model confidence, market move since the pool line, pick team. That is 6,752 subsets in the backtest.

## The 65% subsets, and how much to trust them

**Backtest 2007-2021:** 302 of 6,752 subsets hit 65% or better (n at least 30). Shuffling the win/loss labels 500 times
gives 253 on average (95th percentile 326), so that count is not unusual (P = 0.14). The best single subset (weeks 10-14,
total 44.5-48, pick follows a 2+ point move) is 81-27 (75%, n = 108), p = 1.3e-5 against the 54.9% base. The Holm bar
for 6,752 tests is 7.4e-6, so even the best one misses it, and that is before counting that the feature list was chosen
after looking at data.

**Out of sample, frozen subsets.** Every 65% subset found in 2007-2014 (or 2015-2021) was frozen and scored later.

| Frozen from | Found | Other half of 2007-21 | 2022-24 | 2025 CBS | 2026 live |
|---|---|---|---|---|---|
| 2007-2014 | 378 | 57.5% pooled / 54.8% union | 60.6% pooled / 57.4% union (n 759) | 51.5% / 48.6% | 59.5% / 52.9% |
| 2015-2021 | 313 | 57.6% pooled / 56.0% union | 61.3% pooled / 57.0% union (n 697) | 53.9% / 49.3% | 53.1% / 55.1% |

"Pooled" counts a pick once per subset it belongs to (so overlapping subsets repeat the same games); "union" counts each
pick once. In 2022-24 the base rate of all picks was 56.3%, so the union at 57% is only a point above the base. Across the
whole set of found subsets there is no 65% that survives; on 2025 they are at or below 50%.

**Market-only sides (1999-2025, no model):** zero subsets reach 65% with n of at least 100. The best is 63.9%, which is
what shuffled data gives (median 64.0%). No betting angle on the closing line shows up in these features.

**2026 live only (78 picks):** 32 of 179 subsets hit 65% (n at least 12); shuffled data gives 18 on average (95th
percentile 32). Best: spread 3 or less, 21-8 (72%, n = 29), p = 0.013 against the 53.8% base (Holm bar 0.0003). The same
subset was 56% in 2007-21, 61% in 2022-24 and 52% in 2025. A 21-8 start is within luck.

## Named candidates, every window

Chosen after seeing 2007-21. 2022-24 is the first fresh test for all of them; 2025 and 2026 are the second.

| Candidate | 2007-14 | 2015-21 | 2022-24 | 2025 CBS | 2026 live |
|---|---|---|---|---|---|
| Pick follows a 2+ pt move (all weeks) | 317-218 (59%) | 345-229 (60%) | 175-107 (62%) | 28-21 (57%) | 4-3 |
| **Weeks 10-14 and 2+ pt move** | 86-46 (65%) | 107-48 (69%) | **55-23 (71%)** | 5-4 | none yet |
| **Weeks 10-14 and model confidence 8+** | 48-22 (69%) | 72-33 (69%) | **48-16 (75%)** | 3-3 | none yet |
| Half-point line, outdoors, confidence 8+ | 57-22 (72%) | 76-38 (67%) | 45-28 (62%) | 13-8 (62%) | 2-2 |
| Half-point line, outdoors, 2+ pt move | 87-43 (67%) | 107-58 (65%) | 61-40 (60%) | 16-11 (59%) | 4-3 |
| Division game, outdoors, 2+ pt move | 112-60 (65%) | 102-73 (58%) | 46-26 (64%) | 8-5 | 4-0 |
| Favorite on exactly 3, small move | 66-26 (72%) | 27-30 (47%) | 13-11 (54%) | 4-4 | none yet |
| Spread 3 or less | 414-310 (57%) | 359-301 (54%) | 216-140 (61%) | 53-48 (52%) | 21-8 (72%) |

Fresh-data scorecard for the week 10-14 family: 2022-24 plus 2025 is 60-27 (69%) on 87 picks, p = 0.0003 against 50%.
Against the plain 2+ move rate (62% in 2022-24, 60% for 2025) it is p = 0.08 in 2022-24 and p = 0.05 on the 87 combined.
Versus the other weeks' 2+ move picks in 2022-24 (120-84, 59%) it is z = 1.8, p = 0.035, one-sided, uncorrected for the
nine candidates tried. Taken honestly: promising and replicated across three windows, not proven.

Why still skeptical: "confidence 8+" and "2+ move" are the same games (every confidence 8+ pick is a 2+ move pick), so
the two rows are one finding, not two. Week 10-14 is one of four week buckets, kept because it was the best in 2007-21.
There is no football reason for mid-season to differ. 2025 is 8 games, so it says nothing either way.

A harder test of "replicates in both halves of 2007-21": 96 subsets hit 65% in both halves (at least 15 picks each);
shuffled labels give 62 on average (95th percentile 90, P = 0.03). That is mildly above luck and is explained mostly by
the real move effect below, not by anything independent of it.

## Searching 2022-25 as well (added after Will asked why they were not searched)

They were held out on purpose: a search needs untouched data to be checked against, and once a year is in the search it
cannot also be the check. Both views are useful, so here is the second one.

| Search set | Picks | Subsets | Hit 65%+ (n at least 25-30) | Shuffled labels (mean / 95th) | P(shuffle at least as many) |
|---|---|---|---|---|---|
| 2022-24 plus 2025 only | 1,065 | 3,692 | 323 | 222 / 287 | 0.01 |
| Pooled 2007-25 | 4,787 | 7,404 | 367 | 239 / 310 | 0.004 |

- **2022-25 on their own** point to the same area again: weeks 10-14 and model confidence 8+ is 51-19 (73%, n = 70);
  underdogs in weeks 10-14 are 91-43 (68%, n = 134); home picks with confidence 8+ are 76-31 (71%, n = 107). Best subsets
  there miss the Holm bar (best p = 2.3e-4 against 1.4e-5), and with 1,065 picks any subset under about 80 picks is
  fragile.
- **Pooled 2007-25**: weeks 10-14 and a 2+ pt move is **253-121 (67.6%, n = 374), p = 2.6e-7, which passes the Holm bar
  (6.8e-6 for 7,404 subsets)**. The confidence 8+ version is 171-74 (69.8%, p = 1.1e-6, also passes). Both include the
  data they were found in, so this is the same evidence as above, restated; the new part is that 2022-25 gave the
  same answer without being used to pick the week.
- **Is it an artifact of where the week bucket ends?** Among 2+ pt move picks, 2007-25 pooled, weeks 10-14 are 67.6%
  against 57.4% for all other weeks. Moving the edges barely changes it: weeks 9-13 64.0%, 10-15 65.5%, 9-14 64.9%,
  11-14 67.8%, 10-13 67.2%. Week 9 itself is 51%, so the bump starts at week 10. By season, 15 of 19 seasons are 60% or
  better and only one (2014 at 47%) is under 50%.
- **Caveat that remains:** the comparison is against the other weeks' move picks (57.4%), not against 50%. The difference
  is 10 points on 374 against 1,066 picks (z about 3.5). After allowing for four week buckets and the other features that
  could have been sliced, that is roughly p = 0.01 to 0.05. A real but not conclusive result, and no football story explains it.

## What is real

Following a move of 2+ points since the pool line is set has won 59.7% of 1,109 picks (2007-21) and **62.0% of 282 in
2022-24** (175-107). Bigger moves do better in every window:

| Move toward the pick | 2007-21 | 2022-24 | 2025 | 2026 |
|---|---|---|---|---|
| under 0.5 pts | 361-338 (52%) | 57-64 (47%) | 42-40 (51%) | 8-10 |
| 0.5-1.5 | 780-714 (52%) | 159-143 (53%) | 52-68 (43%) | 21-17 |
| 1.5-2.5 | 467-340 (58%) | 101-68 (60%) | 15-13 (54%) | 4-4 |
| 2.5 and up | 435-287 (60%) | 132-74 (64%) | 21-16 (57%) | 3-2 |

This is the market-move signal docs/mining_report.md already named as the one thing beyond chance. It is 60-64%, not 65%
across the board, it is already in the official pick, and 2025 (57% on 49) and 2026 (4-3) are too thin to tell. Notice that
the 2.5+ bucket reaches 64% in 2022-24, which is as close to a clean 65% as the data gets without slicing by week.

## Other tracked 2026 comparisons (live, n small)

- Official pick when it agrees with the shadow key-number estimator: 32-23 (58%); when they disagree, 10-13. All three
  tracked models (key-number, v1, v3) agree with the official pick: 17-11 (61%, n = 28).
- Shadow key-number estimator alone: 42-27 (61%). Closed as a lead: it failed out of sample on 2022-24 (38-40).
- 9 of the 78 official picks were fallback picks with no model input (forced away); they went 6-3. Treat as noise.

## Caveats

- The 2007-21 backtest grades against the SBRO open; 2022-24 against the bet365 open (a proxy that gap2022 checked);
  the 2022-24 model is retrained each season and is not the live engine run. Real pool lines differ from both.
- The 2022-24 rows were not used to find any candidate, but they were used by the earlier gap2022 test (which only checked
  the overall rate), so they are fresh for this question, not for the model in general.
- Spread, week and slot cuts are not independent, so 6,752 tests are fewer independent hypotheses than the Holm bar assumes.
  The feature list itself was not blind.
- 2026 is 78 picks. One win or loss moves any subset by 3-8 points.

## Bottom line

- 65% is findable in-sample and almost always shrinks. Frozen 65%+ subsets as a group do not beat the base rate by more
  than a point or two on new data.
- The one exception worth watching is weeks 10-14 with a 2+ pt move: 65%, 69%, 71% across three windows, 5-4 on 2025.
  My guess is that part of it is real (the move effect is) and part is the week label picked from many. A fair estimate
  going forward is somewhere around 62-65%, not 70%.
- No pipeline change is needed to check it. Predictions already record the pool line and the market at lock, so the
  2026 weeks 10-14 picks (Nov 15 onward) can be scored after the fact against this definition: pick side matches the
  direction of `market_at_lock - league_line` and the move is 2 or more. Expect about 10-15 qualifying picks in those
  weeks, which cannot settle anything alone. Whether to track it is Will's call.
- The official pick is unchanged. Nothing merged.
