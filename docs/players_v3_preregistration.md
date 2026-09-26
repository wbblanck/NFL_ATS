# Player Model v3 (`proj-players-v3`): Pre-registration

Committed **before** any v3 feature was computed or any result seen. It
replaces the invalid v2 (see the correction in `docs/players_report.md`).

The user's standard for this model is "thorough, never crude". Every variable
below states exactly how it is built. Every variable uses only information
available before the game's lock. The validation checks at the end must pass
**before** any result is read.

## Base

- The v3 base is `proj-poisson-v1`: time-decayed Poisson ratings for TDs and
  FGs (H = 8 weeks, λ = 5, frozen).
- v3 multiplies each team's expected TDs and FGs by exp(β·x), using the
  features x below.
- β is estimated on training seasons only, by Poisson regression with
  log λ_v1 as an offset. λ_v1 comes from the walk-forward fit that uses games
  before each game only.

## Variables

### 1. QB quality: `qb_delta`

- **QB rating.** For each quarterback, EPA per dropback (`qb_epa`, plays with
  `qb_dropback == 1`). The QB on a play is `passer_player_id`, or
  `rusher_player_id` on scrambles.
  - It uses **only plays from games before the game being rated**, regular
    season and postseason, since 2006.
  - Weighting: each play gets weight 0.5^(days_ago / D).
  - Shrinkage: rating = (Σ w·epa + k·prior) / (Σ w + k).
  - The prior is the replacement level: the mean EPA/dropback over QBs'
    first 100 career dropbacks, estimated on training seasons only.
- **Starting QB.**
  - 2025: the QB1 on the team's **last depth-chart snapshot before lock**.
    If that player is Out on the week's injury report, the QB2 is used. If
    there is no snapshot, the recorded starter is used and flagged.
  - 2013–2024: the recorded starter (`home_qb_id` / `away_qb_id`). Starters
    are normally known by inactives, 90 minutes before kickoff, which is
    before lock. The residual look-ahead risk is disclosed.
- **Team baseline.** The rating a team's rating already "contains": the
  dropback-weighted mean, as of this game, of the ratings of every QB who
  took the team's dropbacks in the games behind the team rating. The weights
  are the v1 game weights × each QB's dropbacks in those games.
- **Feature:** `qb_delta` = rating(starter) − team baseline, in EPA per
  dropback.
  - It is 0 when the usual starter plays, including new or returning
    starters who were already in the baseline.
  - It is negative for a worse replacement and **positive for an upgrade**,
    e.g. a starter returning from injury.

### 2. Injuries, snap-weighted with play probabilities (non-QB)

- **Who counts:** players on that week's official injury report with status
  Out, Doubtful or Questionable. The final game-status report is published
  before the game.
- **Snap share:** the player's share of team offensive or defensive snaps
  over the team's previous 4 regular-season games, from nflverse
  `snap_counts`, which start in 2013.
  - `pfr_player_id` is mapped to `gsis_id` through `load_players`.
  - Players with no snaps in that window have share 0, because the team
    rating already reflects their absence.
- **Probability of playing** for each status: the share of reported players
  with that status who took more than 0 snaps in that game, **estimated on
  training seasons only**.
- **Expected missing share** = (1 − p_play(status)) × snap share, summed by
  position group:
  - `ol` (T, G, C),
  - `skill` (WR, TE, RB, FB),
  - `dl` (DE, DT, NT),
  - `lb` (LB, ILB, OLB, MLB),
  - `db` (CB, S, SS, FS, DB).
- **Features:** a team's own `ol` and `skill`, which affect its offense, and
  the **opponent's** `dl`, `lb` and `db`, which affect this team's offense.

### 3. Context (known in advance)

- `rest_diff`: team rest minus opponent rest, clipped to ±7 days.
- `short_week`: rest ≤ 5.
- `off_bye`: rest ≥ 13.
- `tz_shift`: the number of time zones between the team's home stadium and
  the game site. It is 0 for the home team, and international games count
  as 5.
- `division`: both teams are in the same division.
- `dome`: roof is dome or closed.
- Home-stadium time zones are a fixed table of the 32 franchises; neutral
  sites come from `location == "Neutral"`.

### Not used, and why

- **Weather.** nflverse temp/wind are observed at the game, not forecast. No
  verified point-in-time historical forecast source has been ingested.
- **Betting market inputs.** v3 is a pure football model by design. The
  market is the benchmark.

## Hyperparameters

- The QB-rating half-life is D ∈ {180, 365, 730} days and the shrinkage is
  k ∈ {100, 250, 500} dropbacks.
- The combination is chosen on the **training seasons only** (2013–2021), by
  the log-likelihood of the actual margin under v3.
- It is then frozen.

## Training and testing

- **Train:** 2013–2021 regular season, 9 seasons.
- **Test A: 2022–2024,** about 815 games.
  - Point-in-time weekly depth charts and injury reports.
  - No verified opening-line source exists for these seasons, so the
    metrics are about projection accuracy:
    - log-likelihood of the actual margin,
    - margin MAE,
    - P(home wins) log loss,
    - ATS against the **closing line**.
  - Each is reported for v3, v1 and the market close, where applicable.
- **Test B: 2025,** using the exact pre-lock depth-chart snapshots.
  - The same metrics as Test A.
  - Plus ATS against the CBS open (half-point) and the live model.

## Validation checks (must pass before results are read; failures are fixed and disclosed)

1. **Point-in-time.** A unit test shows that no feature for a game changes
   when every later game, play and report is deleted.
2. **QB ratings are sensible:**
   - the top 10 by rating at the end of 2023 are listed in the report;
   - QBs with fewer than 100 career dropbacks sit near the prior.
3. **Known cases:**
   - Brock Purdy returning in 2025 week 4 has `qb_delta` > 0;
   - Cam Ward in 2025 week 1 is not treated as a backup of himself, and his
     delta is measured against TEN's 2024 baseline;
   - a clear backup start is negative, and one is listed in the report.
4. **Play probabilities are ordered** Out < Doubtful < Questionable.
5. **Coverage.** The share of team-games with a QB rating, a snap share and
   an injury match is reported, including any gaps.

## Decision rules (fixed in advance)

- **v3 replaces v1 as the tracked projection** if its margin log-likelihood
  on Test A is higher than v1's.
- **The live pick switches to v3 only if**, on Test B plus live 2026 games,
  v3's ATS against the league line or CBS open beats the live model by
  z ≥ 1.96 **and** has lower log loss.
- Every number above is reported, including failures.
