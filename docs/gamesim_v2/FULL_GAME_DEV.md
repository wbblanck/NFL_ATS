# Full-game test: pregame lineups, passing and running, both sides, against the closing line (development, 2019-2021)

Status: development only. Plan: `PREREGISTRATION_full_game_dev.md` and `PREREGISTRATION_full_game_dev_AMENDMENT1.md`, both committed before any margin was scored. Seasons after 2021 were not loaded. No change to the live pipeline, G1, or picks. Every number below is generated from the manifests named at the end.

## Headline

**Fail.** Player ratings built from every player on the field, for passing and running plays on both sides, predict game margins well: the pregame lineup shift correlates 0.87 with the closing line and has a +2.38 points per SD coefficient beyond team form (interval +0.12 to +4.66; its out-of-sample error gain over team form, -0.40, is not distinguishable from zero, interval -2.11 to +1.30). But they add nothing beyond the closing line: +0.31 points per SD (interval -0.60 to +1.24), and out-of-sample squared error is +0.30 worse (interval -0.22 to +0.87). The market already prices what the lineups carry. The preregistered pass rule (at least +0.5 per SD, intervals excluding zero, lower out-of-sample error) is not met on any part.

## What was built

- Two on-field ratings in expected points added: dropbacks (113,670 plays 2016-2021, including sacks, scrambles and throwaways; no target used) and designed runs (73,217 plays). One column per player on the field: offense QB, RB, WR, TE, OL; defense DL, LB, DB. Pre-snap context only. Walk-forward by week, half-life 730 days, training from 2016, ratings for 2019-2021.
- Pregame lineup shift per game, in points of home margin, from the frozen pregame snapshots (expected snap share times rating, summed over every player of both teams), with 36.6 dropbacks and 23.5 designed runs per team-game (2016-2018 means). 784 games, none excluded.

## Amendment before scoring

The preregistered ridge strength (100) overfit on the expected-points scale: play-level error versus context only was worse for dropbacks by +0.0316 (interval +0.0241 to +0.0388) and for runs by +0.0090. Before any margin was looked at, the ridge was chosen on 2018 only from 100 to 30,000: 3,000 for both play types (2018 play-level error versus context: dropbacks -0.0069, runs -0.0020). With 3,000 the ratings beat context only in every season 2019-2021: dropbacks -0.0066 (interval -0.0088 to -0.0046), runs -0.0025 (interval -0.0033 to -0.0017). The original ridge-100 version is reported below as secondary; it also fails.

## Primary result (ridge 3,000), 784 games

| Measure | Value | 95% interval |
|---|---|---|
| Residual margin (actual minus closing line) on lineup shift, points per SD | +0.31 | game bootstrap -0.60 to +1.24; week bootstrap -0.55 to +1.19 |
| Out-of-sample squared error change (leave one week out; negative is better) | +0.30 | -0.22 to +0.87 |
| Raw coefficient on the shift in points (1.0 = calibrated, 0 = adds nothing) | +0.06 | -0.14 to +0.26 |
| Pass rule | fail | |

Shift standard deviation 4.85 points; correlation with closing line 0.87, with team form 0.92.

## Reported without a pass rule

| Test | Points per SD | Interval | Out-of-sample error change | Interval |
|---|---|---|---|---|
| Against team form instead of the closing line | +2.38 | +0.12 to +4.66 | -0.40 | -2.11 to +1.30 |
| Passing shift alone, vs close | +0.05 | -0.85 to +0.97 | +0.35 | +0.20 to +0.51 |
| Running shift alone, vs close | +0.97 | -0.00 to +1.94 | -0.45 | -2.35 to +1.59 |
| Actual lineup (who played; upper bound), vs close | +0.18 | -0.72 to +1.10 | +0.34 | +0.04 to +0.69 |
| 2019 only, vs close | +0.62 | -0.97 to +2.16 | | |
| 2020 only, vs close | +0.35 | -1.14 to +1.98 | | |
| 2021 only, vs close | +0.00 | -1.74 to +1.70 | | |
| Ridge 100 (original setting), vs close | +0.18 | -0.76 to +1.13 | +0.34 | -0.02 to +0.76 |

Out-of-sample error is in squared points of margin; the closing line alone has a mean squared residual of 173.5.

The running shift alone (+0.97, interval touching zero) is one of eight secondary numbers, its out-of-sample error interval spans zero widely, and it is the same size in the ridge-100 version (+0.92). It is not a finding and should not be chased without fresh data. Even the actual-lineup version, which knows who played, adds nothing beyond the closing line.

## Evidence behind the ratings

| Season | Share of expected snaps on unrated players | Rating SE, 10th / 50th / 90th percentile (EPA per play) | Players with a rating available (dropbacks / runs) |
|---|---|---|---|
| 2019 | 0.14% | 0.016 / 0.024 / 0.028 | 3,019 / 3,029 |
| 2020 | 0.12% | 0.016 / 0.023 / 0.028 | 3,436 / 3,443 |
| 2021 | 0.16% | 0.016 / 0.017 / 0.028 | 3,863 / 3,878 |

Players with a rating available counts everyone seen on the field since 2016 up to that season. On-field slots dropped from the design for missing position: dropbacks 3,550 of 2,500,662; runs 2,850 of 1,610,644.

## What this means

Testing the whole game confirms the earlier verdict instead of reversing it. The full player-aware ratings do contain real information about team strength (correlation 0.87 with the closing line, and a significant coefficient beyond team form, though their out-of-sample gain over team form is not distinguishable from zero), but the closing line already contains all of it. For the pool, where the bar is the pool line set from the market, there is nothing here to use. Recommendation: close the lineup track for these inputs; keep 2022-2025 locked.

## Caveats

- 2019-2021 had been used for earlier passing work, so this is a development check; a fail here is still informative because the closing line baseline was never used for tuning.
- The ridge was amended before scoring (disclosed above); both versions fail.
- The closing line is nflverse `spread_line`, a consensus close, not the Pinnacle close or the pool line.

Files: `scripts/gamesim_v2/build_runs.py`, `full_game_ratings.py`, `full_game_lambda_2018.py`, `full_game_margin_test.py`; `src/engine/gamesim_v2/players/abilities_full.py`; manifests `full_game_ratings.json`, `full_game_ratings_lam100.json`, `full_game_lambda_2018.json`, `full_game_margin_test.json`, `full_game_margin_test_lam100.json`, `runs_build.json`.
