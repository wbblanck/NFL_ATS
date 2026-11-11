# Generation 2 architecture (as built in sprint 1)

Research namespace `src/engine/gamesim_v2/`, scripts in `scripts/gamesim_v2/`, tests in `tests/gamesim_v2/`. Nothing here is imported by the pick pipeline or by G1
(`src/engine/gamesim/`, frozen; hashes in `data/gamesim_v2/manifests/g1_baseline_manifest.json`). Modules are created when their phase starts; the full layout in the spec is the target, not the present state.

| Module | Built | Does |
|---|---|---|
| `data/loaders.py` | yes | Cached `nflreadpy` pulls, one parquet per dataset and season |
| `data/identity.py` | yes | Canonical player ids, legacy-id aliasing, team history, duplicate diagnostics |
| `data/plays.py` | yes | Dropback table: pbp joined to participation, positions from weekly rosters |
| `data/snapshots.py` | yes | Point-in-time pregame player snapshots (pool, workload, availability, abilities) |
| `players/abilities.py` | yes | Ridge-logit on-field player effects with per-group penalties and Laplace standard errors |
| `players/lineups.py` | yes | Expected lineups from a snapshot, availability sampled from `p_active` |
| `matchups/protection.py`, `matchups/coverage.py` | yes | Pressure and completion models over the units on the field |
| `plays/passing.py` | yes | One correlated dropback with a trace: rushers, pressure, time to throw, sack/scramble/throw, target, depth, completion, interception, yards |
| `probability/random_streams.py` | yes | Five independent streams per play, keyed by (seed, play index) |
| `validation/play_validation.py` | yes | Walk-forward harness, paired game-cluster bootstrap |
| strategy, run game, special teams, clock, game state | no | Phases 3, 6 of the spec; G1's rules remain the reference until then |

Flow of a dropback: calls (rushers) -> protection vs rush -> pressure -> time to throw -> sack, scramble or throw -> target and depth -> completion (receiver, QB, coverage, pressure, depth) -> interception -> yards.
Each mechanism has its own random stream; stream state is per play so one play's draw count never moves the next play.

Data limits that shape the design are in `DATA_AUDIT.md`: players on the field are known, who blocked or covered whom is not.
