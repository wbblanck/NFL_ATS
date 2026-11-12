# Game simulator refit: plan and V0 baseline (Sprint 1)

Research only. Nothing here touches the live pick pipeline. Branch `claude/project-thread-bxmkrr`, no PR, no merge until the owner says "merge".
Written before any refit version (V1 and later) has been run or scored.

## Goal
Make the simulator's outcome distributions more accurate and find out whether that improves anything against the market.
Three separate questions, each with its own evidence: (1) realism (does it reproduce NFL games), (2) predictive accuracy
(is it better than its previous version out of sample), (3) betting value (does it beat the market after vig).
Improving (1) does not imply (2) or (3).

## V0 baseline (reproduced 2026-11-11, distribution figures corrected 2026-11-12)
Correction 2026-11-12: the first version of this table used `g3_2022_2025.parquet` as written by the ported
`scripts/gamesim_reproduce.py`, whose margin-distribution columns (m_-60..m_60) were attached after a join that reordered
the rows, so each game carried another game's distribution (correlation of the distribution mean with the game's own fair
margin was 0.15). The script is fixed and the file regenerated (correlation 1.0). Figures that pool over all games
(margin MAE, records, key-margin frequencies) were unaffected; log loss, ATS Brier and calibration changed (first version:
4.064, 0.289, ECE 0.168). Only the m_* columns were wrong: sim_fair and elo_fair, which batch 2 and the hybrid-with-simulator
test use, were correct.
`scripts/gamesim_reproduce.py` reproduces the registered G3 margin MAE (9.9827 vs registered 9.983, 1,023 games, 2022-2025
regular season, weeks 2-18). Diagnostics: `scripts/sim_baseline_v0.py` -> `data/gamesim/v0_baseline.json`.

| Metric (2022-2025 pooled, 1,023 games) | Simulator V0 | Elo | Closing spread |
|---|---|---|---|
| Margin MAE | 9.983 | 9.964 | 9.537 |
| Margin bias (forecast minus actual home margin, points) | +0.27 | -0.90 | -0.64 |

Per season margin MAE, simulator / Elo / close: 2022 9.06 / 8.99 / 8.72; 2023 10.32 / 10.46 / 9.82; 2024 10.17 / 10.07 / 9.65; 2025 10.38 / 10.33 / 9.96.

| Distribution and betting diagnostics | Simulator V0 |
|---|---|
| Margin-distribution log loss (smoothed, 121 integer cells) | 3.904, versus 3.936 for a plain normal centred on the close with sd 12.38 |
| ATS Brier of the simulator's cover probability vs the close (994 non-push games) | 0.261, versus 0.250 for always saying 50% |
| ATS record picking the simulator's side vs the close | 495-499 (all), 330-335 when it disagrees by 1.5+ points |
| Elo, same | 484-510 (all), 293-319 at 1.5+ |
| Calibration error (ECE, 6 bins) | 0.088 |
| 3-point margins | 11.5% simulated vs 15.2% actual (every season 11.2-11.7% vs 14.1-16.9%) |

Reading: the simulator's raw cover probabilities are overconfident against the market. Games it rates at 65%+ to cover
(126 games) covered 50.0%, games at 55-65% (298) covered 50.7%, and games under 35% (54) covered 44.4%. They cannot be used
as bet probabilities without calibration against the line. Its margin distribution shape scores better than a plain normal
on the close (3.904 vs 3.936), mostly because it puts extra mass on 3 and 7. The benchmark sd was fit on the same games, so its log loss is slightly flattering;
a normal centred on the close is a hard benchmark because the close already contains most of the information.

Other margin frequencies (actual vs simulated): 1: 5.0 vs 4.7; 2: 5.1 vs 4.2; 4: 5.4 vs 6.5; 6: 6.6 vs 4.8; 7: 8.1 vs 10.2; 8: 4.5 vs 3.6; 10: 4.7 vs 6.0; 14: 4.6 vs 4.3 (%). The simulator over-produces 7s and 4s and under-produces 3s and 6s.
The handoff note says 12.0% simulated vs 14.2% actual for equal teams; the table above is all games, so the two are not the same measure.

Not yet in the baseline (gaps to close in Sprint 1b): total MAE and total distribution (the saved output has margins only, not
totals), moneyline probabilities, closing-line value (needs the opening line), player and prop projections (not ported here),
and 3-point frequency split by game state.

## Input timing audit (look-ahead check)
Checked in `src/engine/gamesim/personnel.py` and `teams.py`:
- Team factors use only earlier games (documented, not opponent-adjusted).
- QB layer uses the starter recorded in the nflverse schedule (`home_qb_id`/`away_qb_id`), which is the QB who actually started. In live use the starter is known only at inactives (about 90 minutes before kickoff) and earlier is a projection. This is a look-ahead for any backtest of pick-time use.
- Injury layer uses the week's final nflverse injury report (Out/Doubtful). The final report is Friday for most teams, but the file does not carry timestamps, so "as of pick time" is not verified.
- Weather: no weather file is in `main` (`data/weather/game_wind.csv` does not exist here), so weather cannot be tested until it is found or rebuilt.
Consequence: backtest accuracy of V0 and later versions is an upper bound for pick-time use until QB and injury inputs are rebuilt as of pick time.

## Evaluation design
The 2022-2025 seasons are development data, not a clean test: the V0 constants were fit on 2016-2020, explored on 2021 and
confirmed on 2022-2025, and any choice made while looking at them uses them up.
- Development: rolling origin, expanding window from 2016, test 2021 onward one season at a time (train through t-1, test t). Used for debugging and for choosing between variants.
- Adoption evidence: frozen forward predictions only. Every prediction is written before kickoff with model version, game id, timestamp, input snapshot, full margin distribution, market line and source, never edited after. 2026 weeks already played are not described as an untouched test.
- Overlap with `docs/batch6_preregistration.md` (2026 weeks 10-18, Elo+QB and XGBoost vs the pool line, Holm 0.05): any refit scored on those same weeks joins that Holm family or starts after week 18.
- One change at a time against V0, versions in this order: V1 opponent-adjusted team factors; V2 + weather and roof; V3 + team pace; V4 + 4th-down behavior and kicker accuracy; V5 + endgame engine; V6 + player layer; V7 + selected FTN/NGS features. Each stage is compared with V0 and with the previous stage.

## Acceptance criteria (set now, applied per stage)
A stage is kept only if, on the development folds, all of these hold, and then it is confirmed on frozen forward data:
1. Out-of-sample margin MAE and margin-distribution log loss both improve versus the previous stage, with a paired game-by-game interval that excludes zero, in at least 3 of the 4 development seasons.
2. No metric in the baseline table gets materially worse (more than 0.1 MAE, or ATS Brier up more than 0.005).
3. For stages that target a diagnosed problem (3-point frequency, 7-point frequency, pace), the targeted frequency moves toward actual without forcing it.
4. Betting value is assessed last and only through calibration against the line, closing-line value and a paired comparison with the live pick, not raw ATS win percentage.
A stage that improves realism but not prediction is parked as "investigate", not deployed.
Power warning: roughly 256 games a season cannot show a 1-point MAE gain reliably, and any ATS test of the stage is far too small to detect a small edge. A fail means no evidence, not no effect.

## Benchmark to keep in view
Whether the play-level simulator adds anything over a simple calibrated model of margin and total centred on the market (normal on the close
above is the crude version). If V1 and later stages do not beat that on margin log loss, the simulation is not adding predictive value.

## Next steps
Sprint 1b: save totals from the simulator, add total and moneyline diagnostics, split 3-point frequency by game state, build the
chronological harness (expanding fit from 2016), and find or rebuild the weather file. Then V1.
