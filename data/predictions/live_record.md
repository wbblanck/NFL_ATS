# Live record vs the league line

Updated 2026-10-18T16:41:06+00:00 by `python -m engine grade`. Every final prediction is graded; nothing is filtered.

**22-20** (42 graded), win rate 0.524 ± 0.077 (SE). Pending: 8. Ungradable (no league line recorded): 0. Late picks included: 0.

No skill claim is made: fewer than 256 graded games (pre-registered).

Shadow key-number estimator (recorded, not used to pick): 27-15; it disagreed with the live pick 9 times and won 7 of those.

Score-projection models (tracked comparisons, not used to pick): proj-players-v3 24-16 (2 excluded: injury statuses not yet published); proj-poisson-v1 27-15.

Hybrid (tracked, docs/hybrid_tracking.md): 26-16; it picked differently from the live pick 10 times: hybrid right 7, live right 3.

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
| 2026 | 4 | 2026_04_PIT_CLE | PIT | +2.5 | 24-27 | L | PIT L |
| 2026 | 4 | 2026_04_IND_WAS | IND | +3.5 | 30-13 | W | IND W |
| 2026 | 4 | 2026_04_TEN_BAL | TEN | -11.5 | 18-24 | W | TEN W |
| 2026 | 4 | 2026_04_NE_BUF | BUF | -6.5 | 29-26 | L | NE W |
| 2026 | 4 | 2026_04_NYJ_CHI | NYJ | -3.5 | 12-23 | L | NYJ L |
| 2026 | 4 | 2026_04_JAX_CIN | JAX | -2.5 | 22-17 | W | CIN L |
| 2026 | 4 | 2026_04_DAL_HOU | HOU | -2.5 | 34-30 | L | HOU L |
| 2026 | 4 | 2026_04_ARI_NYG | ARI | +0.5 | 24-36 | L | ARI L |
| 2026 | 4 | 2026_04_LA_PHI | LA | +2.5 | 24-20 | W | LA W |
| 2026 | 4 | 2026_04_GB_TB | TB | +3.5 | 17-14 | W | TB W |
| 2026 | 4 | 2026_04_MIA_MIN | MIA | -11.5 | 10-15 | W | MIA W |
| 2026 | 4 | 2026_04_KC_LV | KC | +4.5 | 30-27 | L | LV W |
| 2026 | 4 | 2026_04_LAC_SEA | LAC | -7.5 | 23-30 | W | LAC W |
| 2026 | 4 | 2026_04_DEN_SF | SF | -2.5 | 14-24 | W | SF W |
| 2026 | 4 | 2026_04_DET_CAR | DET | +3.5 | 26-32 | L | CAR W |
| 2026 | 5 | 2026_05_TB_DAL | DAL | -8.5 | 24-16 | L | TB W |
| 2026 | 5 | 2026_05_PHI_JAX | JAX | -6.5 | 17-19 | L | JAX L |
| 2026 | 5 | 2026_05_CHI_GB | GB | +2.5 | 7-31 | W | GB W |
| 2026 | 5 | 2026_05_CIN_MIA | MIA | +7.5 | 31-24 | W | MIA W |
| 2026 | 5 | 2026_05_LV_NE | LV | -3.5 | 17-45 | L | LV L |
| 2026 | 5 | 2026_05_MIN_NO | MIN | +1.5 | 23-13 | W | MIN W |
| 2026 | 5 | 2026_05_CLE_NYJ | CLE | -2.5 | 12-17 | L | NYJ W |
| 2026 | 5 | 2026_05_IND_PIT | PIT | -2.5 | 22-34 | W | PIT W |
| 2026 | 5 | 2026_05_HOU_TEN | TEN | +7.5 | 26-3 | L | TEN L |
| 2026 | 5 | 2026_05_NYG_WAS | NYG | -3.5 | 27-27 | W | NYG W |
| 2026 | 5 | 2026_05_BUF_LA | LA | -2.5 | 37-34 | L | LA L |
| 2026 | 6 | 2026_06_SEA_DEN | SEA | +2.5 | 14-17 | L | SEA L |
