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
