# Generation 2 data audit (sprint 1, task 2)

Audit date 2026-11-11. Source: `nflreadpy` 0.1.5 (nflverse releases), pulled by `scripts/gamesim_v2/audit_inputs.py`; full schemas,
row counts per season and null shares are in `data/gamesim_v2/manifests/data_audit.json`. This supersedes the player-data rows of
`docs/data_audit.md` (2026-09-24) where they differ; the differences are listed at the end.

## What exists, by dataset

| Dataset | Seasons with rows | Key | What it tells Gen 2 | Limit |
|---|---|---|---|---|
| Participation | 2016-2025 (loader refuses 2026) | `nflverse_game_id` + `play_id` | Who was on the field every play (`offense_players`, `defense_players`, GSIS ids); `was_pressure`, `time_to_throw`, `number_of_pass_rushers`, `defenders_in_box`, `route`, man/zone and coverage type, formation, personnel | No assignments (who blocked or covered whom), no separation, no positions or names before 2023 |
| FTN charting | 2022-2026 | `nflverse_game_id` + `nflverse_play_id` | Motion, play action, RPO, screen, `n_blitzers`, `n_pass_rushers`, `read_thrown`, drops, catchable and contested ball, QB-fault sack | 2022+ only; nothing about blocking |
| Next Gen Stats | 2016-2026 | `player_gsis_id`, week (0 = season total) | Per-player weekly aggregates: average separation, cushion, time to throw, completion above expected, rush yards over expected | Aggregates only, not play level; ~600 passers, ~1,400 receivers, ~600 rushers a season |
| PFR advanced | 2018-2026 | `pfr_player_id`, `pfr_game_id` | Per player-game: pressures, hurries, hits, blitzes, times pressured (QB); defender targets, completions allowed, passer rating allowed, missed tackles | No offensive-line blocking data; `pfr_player_id` only |
| Snap counts | 2013-2026 (2012 returns 0 rows) | `pfr_player_id` | Offensive, defensive and special-teams snaps and shares per player-game | PFR id only; every row maps to a person through the identity table (0 unmapped) |
| Weekly rosters | 2009-2026 | `gsis_id` | Team, position, status by week | Week-level, no timestamp |
| Depth charts | 2009-2024 weekly; 2025-2026 timestamped snapshots (`dt`) | `gsis_id` | Expected roles | Schema changed in 2025 (221 snapshots in 2025, 290 so far in 2026). Before 2025 untimestamped, so what it knew at a cutoff cannot be checked: not used in snapshots |
| Injuries | 2009-2026 | `gsis_id` | Report and practice status per player-week | `date_modified` exists for 2016-2024 only, missing in 2025 and 2026 files |
| Players | 24,867 people | `gsis_id` | Id crosswalk (PFR, ESB, PFF, ESPN, NFL, smart), birth date, draft | 6,079 of the GSIS keys are 9-character legacy ids from before GSIS |

## Findings that change the design

1. **Participation joins to every dropback.** Dropbacks = regular-season `qb_dropback` pass plays without a penalty: 189,708 plays 2016-2025, 99.999% matched
   (the earlier 89% figure came from counting non-pass rows). 2026 participation is not published, so any 2026 use needs another source.
2. **Use `offense_players` and `defense_players`, not `players_on_play`.** In 2016-2022 `players_on_play` holds a different numeric id (NFL internal);
   the two side-specific columns are GSIS ids in every season. Position and name columns exist only from 2023, so positions come from weekly rosters.
3. **The pressure label changes definition between 2017 and 2018.** Share of dropbacks with `was_pressure`:
   2016 24.8%, 2017 24.4%, 2018 30.9%, 2019 29.1%, 2020 29.0%, 2021 28.3%, 2022 28.9%, 2023 28.3%, 2024 29.9%, 2025 29.2%. The pressure model trains from 2018 on.
   (`defense_coverage_type` and man/zone labels also start in 2018.)
4. **Injury timestamps exist for 2016-2024 and are before kickoff.** The 2026-09-24 audit said "report-date only, no timestamps". Now `date_modified` is populated
   on every 2016-2024 row, and 99.8-100% of rows in 2016, 2020 and 2024 were last modified before kickoff (median 47-54 hours before). The 2025 and 2026 files have no such column,
   so those seasons cannot be checked and are flagged `injury_ts_verified = False`. This is not a Tuesday-state reconstruction: a row shows the last edit, not each earlier status.
5. **No public source has assignments.** Nothing in the nflverse sets says which lineman blocked which rusher, which defender covered which receiver, or the separation on a play.
   Player effects therefore have to be on-field effects shared by everyone in the unit on that play. Individual matchup assignment stays an unmodelled uncertainty (spec 8.2).
6. **Participation covers the 22 players, not the scheme.** Formation is present on 80% of 2023+ participation rows (72% before). Time to throw is present on ~88-91% of dropbacks.

## Differences from `docs/data_audit.md` (2026-09-24)

| Earlier statement | Now |
|---|---|
| Injuries: report-date only, no timestamps | `date_modified` present for 2016-2024, not 2025-2026 |
| Snap counts: first season unverified | 2013 is the first season with rows |
| Participation: "last updated Feb 2026" | Loader accepts 2016-2025 only |

## Not verified

- Whether `date_modified` is the time of the player's last status change or of a later bulk refresh. The kickoff comparison says it is never after the game, not that it equals the Friday status time.
- Whether participation's `was_pressure` and `time_to_throw` come from one tracking vendor across 2018-2025 (the 2018 break suggests a source change; 2023 shows no break in the pressure rate).
- Completeness of the 2026 in-season files (injuries to week 10, snap counts and PFR to date); not used yet.
