# Preregistration: do pregame lineups (passing and running, both sides) predict the final margin beyond the closing line? (development, 2019-2021)

Written 2026-11-12 before any rushing model is fit or any margin is scored. Will said "go" to testing the whole picture after the passing-only work. Research only; no change to the live pipeline, G1, or picks. Seasons after 2021 are not loaded.

## Status of the data

2019-2021 have already been used for the passing work (design choices, 2021 validation), so this is a development check. A pass justifies a proper confirmation on unused data; it is not evidence of an edge by itself. A fail closes the lineup track for these inputs.

## Ratings (fixed here, not tuned)

Two on-field ridge models in expected points added (EPA), fitted walk-forward by week exactly as before (a week is rated from plays dated before it; exponential decay half-life 730 days; ridge strength 100 for every player group; training from 2016; ratings recorded for 2019-2021):

- **Dropbacks**: every regular-season dropback with participation (pass attempts including throwaways and no-target throws, sacks, scrambles; penalty plays excluded). Outcome: EPA of the play. No target is used anywhere.
- **Designed runs**: regular-season `play_type == "run"` with `qb_dropback == 0` (scrambles are dropbacks), no kneel-downs, no two-point tries, no penalty plays, not aborted, with participation. Outcome: EPA.
- Columns: one per player on the field, grouped by side and position from weekly rosters: offense QB, RB, WR, TE, OL; defense DL, LB, DB. A player's column is 1 when he is on the field. Players with no roster position are left out of the design (count reported). Defensive effects carry their own sign (a good defender lowers offensive EPA).
- Context, pre-snap only: down (2, 3, 4), yards to go (4-6, 7-10, 11+), yard line (inside 10, 11-20, 21-50, beyond 50 from the goal), shotgun, no huddle, score differential (down 14+, down 4-13, up 4-13, up 14+). Nothing from after the snap.
- No draft or experience priors (they did not help in estimation v2).

## Pregame lineup shift per game (points, home perspective)

From the frozen pregame snapshots (cutoff kickoff minus 20 minutes): for each team, every player in the snapshot with weight `expected_share` = probability active times snap share when active. Players with no rating in that week's table count as zero (league average); no rescaling.

- Team pass offense = sum of weight times dropback rating over its offensive players; team pass defense = the same over its defensive players (defense columns of the dropback model). Run offense and run defense likewise with the run model.
- Expected plays per team-game: the 2016-2018 league means of dropbacks and designed runs per team-game in these tables (computed once, recorded in the manifest).
- Shift S = n_pass x (home pass offense + away pass defense) + n_run x (home run offense + away run defense), minus the same for the away team's offense against the home defense. Units: points of margin.

## Primary test (pass requires all three)

Games: 2019-2021 regular season with a snapshot for both teams and a closing line (784 games before exclusions). Home margin M = home score minus away score; closing expected margin C = nflverse `spread_line` (positive = home favored).

1. Regress R = M - C on z(S) (S divided by its standard deviation in these games) with an intercept. The coefficient must be at least +0.5 points per SD.
2. Its 95% interval must exclude zero under both a game bootstrap and a week-block bootstrap (10,000 draws each).
3. Out of sample: leave-one-week-out squared error of M against C + a + b z(S) must be lower than against C + a (point estimate; interval reported).

## Reported without a pass rule

- Raw coefficient on S (1.0 would mean the shift is calibrated in points).
- The same with team form instead of the closing line: M on an exponentially weighted margin form (half-life 6 games, prior weight 2, from 2016, walk-forward) plus z(S).
- Components alone: passing shift, running shift.
- Actual-lineup upper bound: S rebuilt from who actually played (each player's share of his team's plays in that game). Not usable before kickoff.
- By season.
- Evidence: players with a rating per season, share of expected snaps on unrated players, distribution of rating standard errors, play counts and players left out for missing position.
- Play-level check: walk-forward EPA squared error of each model against context only, 2019-2021, with game-cluster bootstrap.

## What is not done

No ATS pick simulation, no comparison with the pool line (the margin test against the closing line comes first), no tuning of any setting after results are seen. Any deviation will be listed in the report.
