# Generation 2 implementation status (2026-11-11)

| Spec phase | Status |
|---|---|
| 0 Baseline freeze and source audit | Done: G1 hashes, G3 reproduction (MAE 9.9827), 30 G1 tests, manifest |
| 1 Data foundation | Done for ids, audit, snapshots 2016-2021, point-in-time and leakage tests. Not done: participation and rosters tables beyond dropbacks, Next Gen Stats and PFR features, weather, 2022+ snapshots (locked) |
| 2 Player ability engine | First version only: on-field ridge effects for pressure and completion (QB, OL, DL, LB, receivers, DB). Not done: position-specific ability sets in the spec (6.1-6.6), time-varying development, workload and fatigue |
| 3 Strategic engine | Not started (rushers are resampled from the league distribution) |
| 4 Matchup engine | Pass protection and coverage as unit-level on-field effects. Individual OL and DB effects do not validate. Not done: rushing matchup, tackling, separation, assignments |
| 5 Correlated play engine | One dropback with a trace, streams per play. Not done: rushing play, YAC, fumbles, penalties, latent game-level effects (set to zero until estimated) |
| 6 Complete game | Not started |
| 7 Calibration and validation | Play-level on 2021 done (`VALIDATION_2021.md`). Not done: dependency calibration on real data beyond unit tests, drive, game level |
| 8 CBS ATS challenger | Not started; design preregistered, nothing run |

Open items: the OL and DB repeat failures (V7) say individual line and coverage ratings need assignment data or a different identification strategy before the engine relies on them.
Locked: 2022-2025 plays and snapshots. No change to the live pipeline, G1, or recorded picks.

Update 2026-11-11: the game-level lineup test on 2021 failed its preregistered rule (`GAME_LEVEL_2021.md`); recommendation is not to build the drive and game engine on these inputs without a new reason.
Update 2026-11-11: 2019-2020 development diagnostics (`LINEUP_DEV_2019_2020.md`) point to noisy player estimates, not the snapshots or zero-imputation, as the main limit. Full engine stays on hold per Will.
Update 2026-11-11: estimation v2 development (`ESTIMATION_V2_DEV.md`): informative priors and an EPA outcome give no play-level gain; a first completion gain was a null-target leak and is withdrawn. Full engine stays on hold; 2022-2025 locked.
Update 2026-11-12: full-game development test (`FULL_GAME_DEV.md`), all players on passing and running plays, fails against the closing line (+0.31 points per SD, interval includes zero). Recommendation: close the lineup track for these inputs; 2022-2025 locked.
