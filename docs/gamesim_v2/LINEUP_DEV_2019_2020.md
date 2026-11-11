# Lineup diagnostics on 2019-2020 (development, not confirmation)

Run 2026-11-11 per `PREREGISTRATION_lineup_dev_2019_2020.md` (committed before scoring). Script `scripts/gamesim_v2/lineup_dev_2019_2020.py`, numbers in `data/gamesim_v2/manifests/lineup_dev_2019_2020.json`.
1,024 team-games (512 per season). 2021 not reopened and not pooled; 2022-2025 not loaded. 2020 is not clean for the player effects (it tuned the ridge settings); 2019 is cleaner. Standard errors are two-way clustered by offense team and week (only 32 teams and 17 weeks, so they are themselves rough). Holm correction over the 18 pooled coefficient tests.

## Headline

**Nothing clears multiple-testing correction, and the lineup score still adds nothing to out-of-sample error.** The pooled pass-offense estimate is the same size as in 2021 (+0.014 EPA per dropback per standard deviation of combined lineup shift, z 1.1; 2021 was +0.026), so the extra two seasons did not resolve the question.
What they did show is why: the player estimates are mostly shrinkage and noise, while the snapshot lineups and the zero-for-unseen rule are not the problem.

## Which problem is it?

| Candidate cause | Evidence | Verdict |
|---|---|---|
| Snapshot lineups wrong | The expected-lineup components correlate 0.84 to 0.95 with the same components computed from who actually played (OL 0.90, rush 0.86, QB 0.88, coverage 0.84, receivers 0.95). Using the actual lineup (D10) gives +0.025 per SD (z 1.79, error change -0.00017, interval spans zero) against +0.014 for the expected lineup | Small loss at most; not the main cause |
| Zero for unseen players hides signal | Only 0.07% of 31,570 lineup slots have no effect in that week's table. Zeroing the thin and unseen slots (D5) gives +0.012 against +0.014 | Not the cause |
| Estimates too noisy | Per slot, the median standard error is 0.067 to 0.096 on the logit scale against a ridge prior with standard deviation 0.1, so estimates are largely the prior. 34% of slots are thin (under 300 pressure or 150 completion plays): receivers 70%, OL 15%, rushers about 25%, QB 6%, DB 4%. Lineup-score reliability (variance of the score over variance plus summed squared standard error) is 0.34 for the completion shift and 0.37 for the pressure shift | **Main cause**: roughly two thirds of the variance in the scores is estimation noise by the model's own standard errors |
| Uncertainty weighting helps | D4 (shifts divided by their own standard error) +0.015 against +0.014 | No |
| More evidence, more signal | Team-games with an above-median share of evidenced slots: +0.021 per SD (z 1.43, 535 games); below median: +0.005 (z 0.25, 489 games). The gap is in the hoped-for direction but not itself significant | Suggestive, untested |
| Effects genuinely small | Best case one standard deviation of lineup shift is about 0.01 to 0.03 EPA per dropback, 0.4 to 1.0 points per team-game. Interval widths here cannot exclude zero or one point | Cannot be separated from "noisy" with this data |

## Pooled results (calibrated form; per standard deviation of the predictor; expected signs: positive for EPA and completion, negative for pressure)

| ID | Predictor | Outcome | Coefficient | z | Holm p | Error change vs form only |
|---|---|---|---|---|---|---|
| D1 | Combined S | EPA per dropback | +0.0137 | 1.10 | 1.00 | +0.00010 (interval -0.00028 to +0.00049) |
| D2 | Completion shift | EPA / completion rate | +0.0092 / +0.0075 | 0.55 / 1.47 | 1.00 | +0.00024 / -0.00001 |
| D3 | Pressure shift | EPA / pressure rate | +0.0082 / -0.0045 | 0.80 / -1.20 | 1.00 | +0.00012 / +0.00001 |
| D4 | S uncertainty-weighted | EPA | +0.0149 | 1.22 | 1.00 | +0.00007 |
| D5 | S evidenced-only | EPA | +0.0123 | 1.19 | 1.00 | +0.00007 |
| D6 | OL only | pressure rate / EPA | +0.0013 / -0.0011 | 0.27 / -0.11 | 1.00 | pressure +0.00002, EPA +0.00015 (both intervals above zero: worse) |
| D7 | QB only | completion rate / EPA | +0.0085 / +0.0128 | 1.78 / 0.83 | 1.00 | -0.00001 / +0.00018 |
| D8 | Receivers only | completion rate / EPA | +0.0069 / +0.0174 | 2.07 / 1.62 | 0.69 | -0.00001 / -0.00004 |
| D9a | Opponent rush only | pressure rate / EPA | -0.0067 / +0.0119 | -1.51 / 1.14 | 1.00 | 0.00000 / +0.00011 |
| D9b | Opponent coverage only | completion rate / EPA | +0.0016 / +0.0000 | 0.40 / 0.00 | 1.00 | +0.00001 / +0.00017 (interval above zero) |
| D10 | S from the actual lineup | EPA | +0.0254 | 1.79 | 1.00 | -0.00017 (interval -0.00085 to +0.00060) |

Error change is the leave-one-week-out weighted squared error with the predictor minus without; negative is better. Pooled intervals are game-cluster bootstrap (300 resamples).

By season, D1: 2019 +0.0142 (z 0.69), 2020 +0.0120 (z 0.71). D10: 2019 +0.020 (1.03), 2020 +0.031 (1.40). D8 on completion rate: 2019 +0.002 (0.24), 2020 +0.009 (2.51), so the one nominal result is unstable across seasons.
Calibrated form chose half-life 6 games and 2 pseudo-games for EPA (3 and 8 for pressure rate, 12 and 8 for completion rate); the a priori form used in 2021 gives almost identical lineup coefficients (D1 +0.0136).

## What stands out

- **The strongest directional hints are the ones the play-level test found reliable**: receivers (D8) and the quarterback (D7) on completion rate, and the actual lineup (D10) on EPA. Offensive line only (D6, wrong sign on pressure) and opponent coverage only (D9b, zero on EPA) show nothing, which matches the play-level finding that individual OL and DB effects do not repeat.
- **Adding OL-only or coverage-only scores makes out-of-sample error worse** with intervals above zero: unreliable components subtract value.
- Player effects number 1,265 (2019) and 1,505 (2020) with at least the thin-evidence threshold, out of about 2,000 players seen in lineups each season.

## What I would do next (not started)

1. The noise is the first problem, not the engine. Give player effects better information before testing again: informative priors from position and other available data (for receivers, Next Gen Stats separation and PFR targets; draft round and experience), more history (completion from 2016, pressure label breaks 2017/2018), and a richer outcome than a binary completion (EPA or yards per target).
2. Carry uncertainty into the lineup prediction by drawing player effects from their posteriors rather than using means. With 1/3 reliability, the posterior-mean score already shrinks; draws would show how often a lineup advantage is distinguishable from none.
3. Judge a refit on data not yet scored: 2022-2025 are reserved and need a fresh preregistration; the 2021 test is spent.
4. Keep the full drive and game engine on hold.

Limits: two seasons, the effective sample is smaller than 1,024 because teams and weeks repeat; 18 tests with several correlated; effects set to the ridge mean (zero) for players with no plays; passing offense only (nothing on running, tackling or special teams); expected lineups from the pregame snapshot.
