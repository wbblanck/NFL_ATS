# Team ATS Form: Pre-registration

Committed 2026-11-02 before any result was computed. Asked for by the owner after looking at each team's 2026
record against the pool line ("can we test a model that takes this history into consideration?").

Question: does a team's against-the-spread record **so far this season** predict whether it covers its next
game, beyond what the live model already says? The open-search study (docs/mining_preregistration.md) only had
3-game cover streaks and last-game cover flags; the season-to-date record itself was never tested.

## Data

- Games: 2008–2021 and 2025 regular season. Pool-line proxy ("line") = SBRO open 2008–2021, CBS open 2025.
  (The book open for 2014–2024 is not in this container, so SBRO open is used through 2021, and 2022–2024 is
  left out.) Market = nflverse close and total. Pushes against the line excluded.
- Cover probability p = the live model (`TotalDist("shifted_total")`, fit on earlier seasons only), the same as
  `adaptive_eval.dataset` but with the line source above.
- **Form**: for each team, net ATS = covers − non-covers in its earlier regular-season games of the same season,
  graded against the nflverse close (pushes skipped). D = home net ATS − away net ATS. Known before kickoff.
- 2026 forward check: the 2026 pool lines (`data/lines/league_lines.csv`) and official picks
  (`data/predictions/predictions.csv`), with form graded against the pool line. Descriptive only.

## Tests (3, fixed now)

Score for a side S over a set of games: z = (wins − Σ p_S) / sqrt(Σ p_S(1 − p_S)), two-sided (a "hot team"
edge and a "fade the hot team" edge both count).

1. **form_side**: weeks 4+, |D| ≥ 2, S = the team with the better net ATS.
2. **form_strong**: weeks 4+, |D| ≥ 4, S = the team with the better net ATS.
3. **form_variant**: a model variant p' = logistic(logit(p) + β·D), β fitted by maximum likelihood on
   2008–2016 only, frozen, then scored on the holdout 2017–2021 + 2025: (a) the variant's picks against the
   official picks on games where they differ (sign test), (b) log-loss of p' vs p.

Tests 1–2 are scored on all seasons, and also reported separately for 2008–2016 and the holdout.
Holm over the 3 tests at 0.05 (two-sided). Test 3 decides on (a).

## Decision rule

A test that passes Holm is a lead only. Nothing changes the official pick without a separate live test and the
owner's approval, and the 256-graded-game rule still applies. If none passes, the idea is closed and goes on the
list of tested ideas. The 2026 numbers are reported but cannot decide anything (about 100 games).
