# Hybrid rule with the simulator: Report (2026-11-09)

Rules: `docs/hybrid_sim_preregistration.md` (commit 7e9e5fc, made before the simulator output was joined to any line
data). Code: `scripts/hybrid_sim.py`. Numbers: `data/backtests/hybrid_sim.json`. Run once.

**Result: FAIL.** On 2022-2024, using the simulator's side on games where the line moved ½ point or less did slightly
worse than the live model, not better.

## Known answer first
`scripts/gamesim_reproduce.py` reproduced G3's margin MAE on today's nflverse files: 9.9827 on 1,023 games
(registered 9.983). Elo 9.9640, close 9.5367.

## Test: 2022-2024 (pre-registered)
Sample: 426 games, regular season weeks 2-18, with a half-point bet365 open, a close and a simulator row. 157 of them
moved ½ point or less from open to close; on the other 269 the hybrid keeps the live pick.

| On the 157 ½/no-move games | Record vs the open |
|---|---|
| Live model | 84-73 (53.5%) |
| Simulator | 81-76 (51.6%) |

- Picks differ on 81 games: simulator right on 39, live model right on 42. **Net −3, z −0.33, p 0.63** (pass needed
  z ≥ 1.645).
- Whole hybrid on all 426 games: 239-187 (56.1%), live model 242-184 (56.8%).
- By season (net on differing games): 2022 +6 (15-9), 2023 −12 (8-20), 2024 +3 (16-13).
- The pre-registered guesses held: 157 low-move games (guessed about 175), 81 differing (guessed about 85).

## Descriptive only
- **Plain Elo** in the same rule, 2022-2024: differs on 78, net +2 (40-38), z 0.23. Elo on the 157 games: 86-71.
  Hybrid with Elo on all 426: 244-182 vs live 242-184.
- **2025** (194 games, 54 ½/no-move): simulator net +9 (23-14 on 37 differing), z 1.48; simulator 35-19 on the 54,
  live 26-28; hybrid 112-82 vs live 103-91. Elo: net +3 (15-12). Not evidence: 2025 was not the test season, the
  simulator's 2025 opener bets were already seen in nfl-betting-model, and 2023 alone shows a −12 swing of the same size.

## Reading
The simulator adds nothing to the live model on the games where the market did not move, the same result as v1
(hybrid test, +8, p 0.26) and the key-number lead (38-40). As stated in advance, power was low (about 55% for a true
60% rate on the differing games), so this is "no evidence", not proof of no effect. Nothing changes in the pick
pipeline or the tracked hybrid.
