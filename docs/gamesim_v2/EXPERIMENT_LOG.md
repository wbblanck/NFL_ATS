# Generation 2 experiment log

Every experiment, including failures. Dates 2026-11-11 unless stated.

| # | What | Data | Result | Where |
|---|---|---|---|---|
| E0 | Freeze G1: hashes, constants, tests, reproduction | 2022-2025 weeks 2-18, seed 101, 1,000 sims | G3 margin MAE 9.9827 on 1,023 games (registered 9.983); Elo 9.9640; closing line 9.5367; 30 G1 tests pass | `manifests/g1_baseline_manifest.json` |
| E1 | Player data audit | nflverse, 2009-2026 | See `DATA_AUDIT.md`. Corrections to the 2026-09-24 audit: injury timestamps exist 2016-2024; participation ends 2025; pressure label breaks 2017/2018 | `manifests/data_audit.json` |
| E2 | Player identity | players, weekly rosters, snap counts | 26,551 people, 0 duplicate ids, 0 unmapped snap rows; 1 legacy id aliased; 2 PFR ids on two GSIS ids and 4 GSIS ids with two PFR ids left to `players`; 1 same-name-and-birthdate pair left flagged | `manifests/identity_diagnostics.json` |
| E3 | Pregame snapshots 2016-2021 | snap counts, injuries with timestamps | Pool recall of players who took a scrimmage snap 99.2-99.3%; `p_active` Brier 0.133-0.153 vs 0.200-0.221 for a constant (2016-2021). 2022 was also built once and inspected for availability only (disclosed in the preregistration) and then removed | `manifests/snapshot_manifest.json` |
| E4 | Development grid, 2020: ridge strength and half-life | 2020 dropbacks | Pressure: player best 0.61036 (lambda 100, half-life 730), team best 0.61173, ctx 0.61320. Completion: player 0.58602, team 0.58648, ctx 0.58703. A first timing run with lambda 100 gave the same 2020 player-vs-ctx gain (-0.0029) | `manifests/dev_grid_2020.json` |
| E5 | Preregistered validation, 2021 | 2021 | Pressure: player -0.0016 vs ctx (interval excludes 0), -0.0005 vs team (includes 0). Completion: -0.0019 vs ctx, -0.0011 vs team (both exclude 0). Individual OL and DB effects fail split-half repeat; receivers, QBs, rushers pass. V6 fails on monotonicity; V8 rush part fails | `VALIDATION_2021.md` |
| E6 | One-game demonstration | 2021 week 5 BUF at KC | Correlated pass-play trace works end to end (rushers, pressure, time to throw, decision, target, depth, completion, yards). Sanity only, no claim | `scripts/gamesim_v2/simulate_historical_game.py` |

Process notes: two bugs found and fixed before results were read (design reuse across the grid made the first grid run slow; the snapshot file lacked the position-group column the team-game check needs, so the first validation run stopped at V8 and was rerun reusing the same fitted predictions). One test failure showed that sharing one running generator per mechanism coupled draws across plays through conditional consumption; streams are now keyed per play.
