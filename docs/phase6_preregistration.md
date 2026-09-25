# Phase 6 — Residual Features: Pre-registration

Committed **before** any Phase 6 result was computed.

## Framework

- **Base:** the Phase 4 raw out-of-sample P(home covers the frozen line), from
  the shifted-empirical estimator with the market at lock.
- **Feature group model:** logit(p) = a + b·logit(p_raw) + γ·features.
  - Fit walk-forward: for test season s, it uses only games from seasons
    before s.
  - Test seasons 2010–2021. Frozen line = SBRO open; market = nflverse close
    (the same proxies as Phases 3–5).
- **Comparators:**
  - **raw**: the base with no refit;
  - **platt**: the same model with no features. This isolates the value of
    the features from the value of re-fitting a and b.
- **Groups are tested one at a time, in the spec's order.**
- **Kept groups:** a group is kept only if its pooled out-of-sample log loss
  is lower than **both** raw and platt, **and** its ATS win rate (pick P > 0.5)
  is at least raw's on the same games. Kept groups are then evaluated
  together. A group that fails is removed and not tuned further.

## Groups and written rationale

### 1. QB availability / change

- **Rationale:** a backup or new starting QB is the largest single
  personnel shock. If the market adjusts late or too little, the change is
  residual signal.
- **Features:** `qb_change_home` and `qb_change_away`. Each is 1 when the
  game's starting QB differs from that team's starter in its previous
  regular-season game.
- **Point-in-time note:** nflverse records the actual starter. Starters are
  normally known by inactives, about 90 minutes before kickoff, which is
  before lock. Rare late or in-game changes are a small look-ahead risk,
  disclosed here. The feature compares against the *previous game's*
  starter, which is fully known.
- **Probability weighting:** probability-weighted status (the spec's
  "unresolved availability") needs point-in-time injury reports, which do
  not exist historically (audit 0.8). It is not tested.

### 2. Rest and schedule

- **Rationale:** rest differentials and bye weeks are scheduled far in
  advance. The market prices them, but possibly imperfectly.
- **Features** (from nflverse `home_rest`/`away_rest`, known in advance):
  - `rest_diff` = home − away, clipped to ±7,
  - `home_short` and `away_short`: rest ≤ 5 days,
  - `home_bye` and `away_bye`: rest ≥ 13 days.

### 3. Opponent-adjusted efficiency

- **Rationale:** recent play efficiency may carry information that the
  market underweights, or overweights through recency bias.
- **Data:** nflverse `team_stats` per game. Offensive EPA/play =
  (passing_epa + rushing_epa) / (attempts + carries + sacks_suffered).
  Defensive EPA/play allowed = the opponent's offensive EPA/play in that
  game.
- **Ratings before each game use only earlier games.**
  - Each game value is opponent-adjusted by subtracting the opponent's
    *pre-game* rating on the other side of the ball.
  - Values are combined with an exponentially weighted mean: half-life 6
    games, across seasons.
  - Ratings shrink 50% toward 0 at each new season.
- **Feature:** `net_eff_diff` = (home_off − home_def) − (away_off − away_def)
  ratings.

### 4. Weather: not testable without look-ahead

- nflverse `temp`/`wind` are observed at the game, not forecast before lock
  (audit 0.8).
- The historical point-in-time forecast source's start date is unverified
  (audit 0.9), and it is not ingested.
- **No weather result is reported.** Weather is deferred until 2026+
  forecast captures exist.

### 5. OL / pass-rush matchup: not tested

- The pressure and participation data covers only 2016+ and has no
  in-season 2026 data (audit 0.1).
- Too few seasons for a walk-forward test with this many parameters.

## Report

- For each group, give its out-of-sample log loss, Brier, ECE, and ATS with
  SE, against raw and platt.
- Report the fitted γ per test season.
- State plainly which groups were kept.
