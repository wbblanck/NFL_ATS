# Tracked models: one Holm family against the Official pick

Registered 2026-11-26 on Will's approval (audit B, item 2). It replaces the single-model bar in `docs/hybrid_tracking.md`
(z at least 1.645 for Hybrid alone), which is tightened here. Nothing about any pick changes.

## Why

Four tracked comparators run beside the Official pick: the team-only projection (v1), the player projection (v3), Hybrid and
the key-number shadow. With four looks, one of them leading by a few games is expected by chance. On the 93 games where Official,
v1 and v3 all have a pick (2026, live, against the pool line), Official is 48-45 and v1 is 55-38; they differ on 37 games and v1
is right on 22 of them (z = +1.15). That lead is the kind this registration is meant to keep from being acted on.

## Family

H_v1, H_v3, H_hybrid, H_keynum: on the games where the model's pick differs from the Official pick, the model wins more than half.

## Test

- **Data:** live graded picks only, against the pool line frozen in each prediction. No backtest or reconstructed games.
  Counted: picks created at or after the start time below. Earlier games are reported but not counted.
- **Statistic:** per model, the number of differing games it won, k of n. P = P(X >= k), X ~ Binomial(n, 1/2), exact, one-sided.
- **Minimum:** 100 differing games for that model before its test counts.
- **Multiplicity:** Holm step-down over all four at 0.05 (the smallest p must be at most 0.0125, then 0.0167, 0.025, 0.05; a failure
  stops the step-down). With four models all four always count in the family, even if one has too few games.
- **Pass means:** that model beat the Official pick on differing games beyond chance for the family. It does not switch anything.
  Switching the live pick needs a pass, the owner's approval, and a fresh pre-registration of the switch.
- **Code:** `engine.backtest.tracked_family` (`python -m engine.backtest.tracked_family --since <UTC time>`), with tests in
  `tests/test_tracked_family.py`. It reads the same graded rows the live record uses.
- **Reviews:** at the end of each season and whenever a model reaches 100 differing games, never mid-stretch.
- **New tracked models:** adding a fifth model enlarges the family (Holm over 5) from its first counted game.

## Start time

Starts at the first lock run after this file is merged to main. The start time (UTC) is recorded in a one-line addendum commit
immediately after the merge, before that lock run.

**Recorded start: 2026-11-26T18:40:30Z** (PR #71 merged to main). Picks with `created_at` at or after this time count.

## Expected duration

About 30 games differ per season for Hybrid and similar models, so 100 differing games takes several seasons. That slow
pace is the point: a model that is not clearly better will not be promoted by a lucky stretch.
