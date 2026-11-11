# Generation 2 data dictionary (sprint 1)

All paths under `data/gamesim_v2/`. Parquet under `features/` and `snapshots/` is re-derivable and not committed (hash in the manifests). Manifests and
`processed/player_identity.parquet`, `processed/player_team_history.parquet` are committed (public nflverse data only; no AusSportsBetting data).

## processed/player_identity.parquet (`identity-v1`, one row per person)

| Column | Meaning |
|---|---|
| `uid` | Internal id. The nflverse GSIS id (`00-0034796`, or a 9-character legacy id for pre-GSIS players) when there is one; otherwise `pfr:<pfr_id>`. Stable and public |
| `canonical_uid` | Same as `uid`, except a legacy id that matches exactly one GSIS id on name and birth date points to it (1 case in the 2026-11-11 build) |
| `gsis_id`, `pfr_id`, `esb_id`, `pff_id`, `espn_id`, `nfl_id`, `smart_id` | Source ids. A weekly-roster id fills a gap only if no other person in `players` already owns it |
| `source` | `players` (24,867), `roster_only` (1,656, on weekly rosters but not in `players`), `pfr_only` (28, snap counts only) |
| attributes | name, birth date, position, rookie season, draft, size |

Known unresolved: 4 GSIS ids carry two PFR ids in the roster rows and 2 PFR ids sit on two GSIS ids (the `players` table decides); two GSIS ids share the name Kevin White and birth date 1992-06-25.
Joins always use ids; 905 display names are shared by different people. Details: `manifests/identity_diagnostics.json`.

## processed/player_team_history.parquet

One row per (`uid`, `season`, `week`, `team`) from weekly rosters, 702,029 rows, franchise names unified (OAK/LV, SD/LAC, STL/LA).

## features/dropbacks.parquet (not committed)

One row per regular-season dropback 2016-2025, `play_type == pass`, no penalty. Play facts from pbp plus participation: `offense_players`, `defense_players` (`;`-joined GSIS ids),
`was_pressure`, `time_to_throw`, `number_of_pass_rushers`, `defenders_in_box`, `route`, man/zone and coverage type, `has_part` (99.999% true).
`features/position_lookup.parquet`: (season, gsis_id) to position group, from weekly rosters.

## snapshots/pregame_players_<season>.parquet (`snapshot-v1`, one row per team-game-player, 2016-2021 built so far)

Cutoff `data_cutoff` = kickoff minus 20 minutes. Built only from earlier games, injury rows last modified at or before the cutoff, and availability rates from earlier seasons.

| Column | Meaning |
|---|---|
| `game_id`, `team`, `uid`, `season`, `week` | Key |
| `position`, `pos_grp` | PFR position string; model position group (QB RB WR TE OL DL LB DB) |
| `prev_games`, `games_played_prev` | Team games in the window (up to 4) and games in which the player took a scrimmage snap |
| `off_share_prev`, `def_share_prev` | Mean snap share over the window (missed games count as zero) |
| `off_share_active`, `def_share_active`, `snap_share_when_active` | Mean share over games he played |
| `in_prev_pool` | True if he had a scrimmage snap in the window; False if he is here only through the injury report |
| `status`, `practice`, `report_primary_injury`, `injury_ts`, `injury_ts_verified` | Injury report entry (`no_report` if none); last-modified time (2016-2024 only) and whether one exists |
| `p_active` | Share of players with this status and `games_played_prev` who played a scrimmage snap, from earlier seasons only (`manifests/p_active_by_status.csv`) |
| `expected_share` | `p_active * snap_share_when_active` |
| `outcome_played`, `outcome_played_scrimmage` | Whether he played, known after the game. For calibration only, never a feature |
| `ab_pressure*`, `ab_completion*` | Walk-forward on-field effects as of this game's week (see below), when built |
| `snapshot_version`, `data_cutoff` | Version and cutoff |

## features/abilities_pressure.parquet, abilities_completion.parquet (not committed)

Long table written by `validate_plays.py`: `season`, `week`, `key` (`GROUP:uid`, or `intercept` / context term), `beta` (logit effect), `se` (diagonal Laplace), `n_eff` (decay-weighted plays on the field), `n_raw`.
Model `g2-onfield-ridge-v1`; effective cutoff is the first game of that (season, week) block.

Sign conventions (raw logit effects): pressure model, `OL` positive = more pressure allowed (worse protection), `DL`/`LB` positive = more pressure created, `QB` positive = more often pressured.
Completion model, `R` and `QB` positive = more completions, `DB`/`LB` positive = more completions allowed (worse coverage).
These are effects of being on the field, not assigned matchups.
