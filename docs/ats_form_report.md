# Team ATS Form: Report

Pre-registration: docs/ats_form_preregistration.md (committed before any result). Code:
`src/engine/backtest/ats_form.py`. Per-test numbers: `data/backtests/ats_form.json`. Run 2026-11-02.

**Verdict: no test passed Holm. The idea is closed as a pick rule.** One thing is worth knowing, though. A team
with the better ATS record so far has covered its next game *less* often than the model expected, not more.
This held in both halves of the history and in 2026, but it was just short of the pre-registered bar.

## History (2008–2021, 2025; line = SBRO open, CBS open 2025; 3,745 games)

| Test | Games | Hot-ATS side won | Model expected | z | p (two-sided) | Holm bar | Pass |
|---|---|---|---|---|---|---|---|
| 1. form_side (wk 4+, gap ≥ 2) | 2,162 | 1,032 (47.7%) | 1,086.9 | −2.38 | 0.017 | 0.0167 | no |
| 2. form_strong (wk 4+, gap ≥ 4) | 1,096 | 519 (47.4%) | 550.2 | −1.90 | 0.057 | 0.025 | no |
| 3. form_variant (holdout, differing games) | 66 | variant 38, official 28 | — | 1.23 | 0.22 | 0.05 | no |

Split for tests 1–2 (same direction in both):

| Test | 2008–2016 | Holdout 2017–2021, 2025 |
|---|---|---|
| form_side | 629 / 1,311 (exp 654.5, z −1.42) | 403 / 851 (exp 432.4, z −2.04) |
| form_strong | 330 / 682 (exp 341.0, z −0.85) | 189 / 414 (exp 209.2, z −2.01) |

Test 3 detail: β fitted on 2008–2016 = −0.019 per net ATS game (a fade, worth about 0.5 points of cover
probability per game of gap). On the 1,508 holdout games the variant went 818-690 vs official 808-700. It
changes only 66 picks (4%), and its log-loss is 0.6846 against 0.6862.

## 2026 (pool lines, form graded against the pool line, 119 graded games)

- Test 1 situation: 49 games; the team with the better ATS record covered 22, lost 27.
- Variant on the 68 official picks that have a model probability: it flips **one** pick (week 4 NE@BUF, to NE),
  and that flip won. That makes the variant 36-32 and official 35-33 on those 68 games. Too few games to mean anything.

## What this means

- A team's ATS record is not a reason to back it. If anything, the market overrates hot ATS teams slightly. The
  hot side covered about 2.5 points less often than the model expected.
- As a tweak to the official model it does almost nothing: β is small, so it only flips coin-flip games.
- The direction (fade) was not chosen in advance, so a later "fade" test would need fresh data: the rest of 2026
  forward, or 2022–2024 book opens if that file is uploaded again. Nothing changes the official pick.
