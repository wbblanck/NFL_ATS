# Live record vs the league line

Updated 2026-10-01T23:55:11+00:00 by `python -m engine grade`. Every final prediction is graded; nothing is filtered.

**9-6** (15 graded), win rate 0.600 ± 0.126 (SE). Pending: 1. Ungradable (no league line recorded): 0. Late picks included: 0.

No skill claim is made: fewer than 256 graded games (pre-registered).

Shadow key-number estimator (recorded, not used to pick): 10-5; it disagreed with the live pick 3 times and won 2 of those.

Score-projection models (tracked comparisons, not used to pick): proj-players-v3 8-7; proj-poisson-v1 9-6.

Hybrid (tracked, docs/hybrid_tracking.md): 10-5; it picked differently from the live pick 5 times: hybrid right 3, live right 2.

| Season | Week | Game | Pick | League line (home) | Score (away-home) | Result | Shadow pick |
|---|---|---|---|---|---|---|---|
| 2026 | 3 | 2026_03_LAC_BUF | LAC | -7.5 | 16-24 | L | LAC L |
| 2026 | 3 | 2026_03_CAR_CLE | CLE | +2.5 | 18-21 | W | CAR L |
| 2026 | 3 | 2026_03_NYJ_DET | NYJ | -6.5 | 24-31 | L | NYJ L |
| 2026 | 3 | 2026_03_HOU_IND | IND | +2.5 | 17-19 | W | IND W |
| 2026 | 3 | 2026_03_NE_JAX | JAX | -2.5 | 6-35 | W | JAX W |
| 2026 | 3 | 2026_03_KC_MIA | MIA | +11.5 | 24-10 | L | MIA L |
| 2026 | 3 | 2026_03_TEN_NYG | TEN | -3.5 | 7-12 | L | TEN L |
| 2026 | 3 | 2026_03_CIN_PIT | PIT | +3.5 | 27-30 | W | PIT W |
| 2026 | 3 | 2026_03_SEA_WAS | SEA | +7.5 | 31-33 | L | WAS W |
| 2026 | 3 | 2026_03_ARI_SF | ARI | -8.5 | 30-36 | W | ARI W |
| 2026 | 3 | 2026_03_MIN_TB | MIN | +1.5 | 23-16 | W | MIN W |
| 2026 | 3 | 2026_03_BAL_DAL | BAL | +2.5 | 34-31 | W | BAL W |
| 2026 | 3 | 2026_03_LV_NO | LV | -3.5 | 35-27 | W | LV W |
| 2026 | 3 | 2026_03_LA_DEN | DEN | +2.5 | 26-30 | W | DEN W |
| 2026 | 3 | 2026_03_PHI_CHI | PHI | +3.5 | 7-27 | L | CHI W |
