# Edge Search With the AusSportsBetting Data: Report

Rules: `docs/edge2_preregistration.md` (commit `1dea397`, before any result). Numbers: `data/backtests/edge2.json`
from `engine.backtest.edge2.run()`.

## Bottom line

**No new edge.** None of the 7 pre-registered ideas beat the live model on the 2020–2024 confirmation seasons
(Holm-corrected; the best was p = 0.08 against a required 0.007). The live model is unchanged. The data did
confirm the existing signal once more on clean, single-book lines.

## Verification of the file

| Era | Source (per file notes) | Finding |
|---|---|---|
| 2006–2012 | footballlocks | One line per game, 0.2–0.3 pt from the close on average: **not an opener**, unusable for move tests. |
| 2013 | mixed | Partly an opener (0.58 pt from the close). Not used. |
| 2014–Feb 2018 | Pinnacle | Clean. Every close within ½ pt of nflverse in 97–100% of games; open and close inside the week's min/max for every game; 2.5% margin on every price. |
| Sep 2018–Feb 2025 | bet365 | Clean. Closes within ½ pt of nflverse in 84–97%; open/close inside min/max everywhere; ~5% margin. Open-to-close gaps (1.1–1.8 pt) match SBRO's openers. |
| Sep 2025 on | betr | **Failed.** 2025 weeks 1–5 have no close. In 2026 weeks 1–3 its closes match our own live captures in only 11 of 15 games, and some opens sit up to 9 points from every book we captured. Not used. |

No duplicate rows; every 2014–2024 regular-season game matched to nflverse. This also corrects one row of the gap
test report (its 2025 "betr open" comparison).

Also found: bet365 prices both sides of the spread identically in 54–64% of games (Pinnacle: 9–13%), which limits
how much price information that era carries.

## Tests (proxy pool line = the book's half-point open; 1,424 games)

Live model (baseline): discovery 2014–2019 381-338 (53.0%); confirmation 2020–2024 395-310 (56.0%, week-clustered
bootstrap 52.8%–59.1%).

| Idea | Fitted on 2014–19 | 2020–24: games picked differently | Rule won / live model won | One-sided p |
|---|---|---|---|---|
| H1 Closing price breaks no-move ties | — | 27 | 14 / 13 | 0.42 |
| H2 Market adjusted by closing price | b = 1.75 | 18 | 11 / 7 | 0.17 |
| H3 Market adjusted by the moneyline | c = 0 (no information) | 0 | — | 1.00 |
| H4a v1 team projection as the pick | — | 354 | 163 / 191 | 0.93 |
| H4b v1 breaks no-move ties | — | 61 | 36 / 25 | 0.08 |
| H5a v3 player projection as the pick (2022–24) | — | 164 | 76 / 88 | 0.83 |
| H5b v3 breaks no-move ties (2022–24) | — | 37 | 20 / 17 | 0.31 |

- **Price and moneyline (H1–H3):** the close already carries what the prices and moneyline know. H3's best weight
  on the moneyline was exactly zero.
- **Projections as the pick (H4a, H5a):** both lose to the market-move model, as in every earlier test.
- **v1 as a no-move tie-break (H4b):** +11 over five seasons, but discovery showed nothing (+1), and it misses the
  corrected threshold by a factor of 11. Recorded as a lead only; it would need its own pre-registered live test.
- The 2025 CBS check was only required for candidates; there were none.

## The existing signal, by size of move (live model, book open vs book close)

| Move off the open | 2014–2019 | 2020–2024 |
|---|---|---|
| None | 51-60 (45.9%) | 52-61 (46.0%) |
| ½ point | 127-132 (49.0%) | 98-82 (54.4%) |
| 1+ point | 203-146 (58.2%) | 245-167 (59.5%) |

All the edge is in games the market moves a point or more. No-move games are slightly below a coin flip in both
periods (they are the games where the model has nothing to go on).

## Season simulation (272 games, 100,000 seasons)

| Win rate | Average wins | 90% range | P(≥141, the user's 2025 pace) | P(≥150) | Weeks with 12+ right per season |
|---|---|---|---|---|---|
| 51.4% (2025 vs CBS line) | 139.8 | 126–153 | 47% | 12% | 0.8 |
| 54.9% (2007–2021 history) | 149.3 | 136–163 | 86% | 49% | 1.4 |
| 56.0% (2020–2024 vs bet365 open) | 152.3 | 139–166 | 93% | 64% | 1.7 |

What the season looks like depends almost entirely on which of those win rates holds against the CBS line, which
this data cannot settle (see docs/gap2022_report.md).
