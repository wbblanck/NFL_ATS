# Live record vs the league line

Updated 2026-10-26T00:00:29+00:00 by `python -m engine grade`. Every final prediction is graded; nothing is filtered.

**36-27** (63 graded), win rate 0.571 ± 0.062 (SE). Pending: 1. Ungradable (no league line recorded): 0. Late picks included: 0.

No skill claim is made: fewer than 256 graded games (pre-registered).

Shadow key-number estimator (recorded, not used to pick): 35-19; it disagreed with the live pick 13 times and won 9 of those.

Score-projection models (tracked comparisons, not used to pick): proj-players-v3 30-23 (3 excluded: injury statuses not yet published); proj-poisson-v1 35-21.

Hybrid (tracked, docs/hybrid_tracking.md): 40-23; it picked differently from the live pick 14 times: hybrid right 9, live right 5.

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
| 2026 | 6 | 2026_06_HOU_JAX | HOU | -2.5 | 34-31 | W | JAX L |
| 2026 | 6 | 2026_06_CHI_ATL | CHI | +3.5 | 31-23 | W |   |
| 2026 | 6 | 2026_06_BAL_CLE | BAL | +4.5 | 10-13 | L |   |
| 2026 | 6 | 2026_06_TEN_IND | TEN | -6.5 | 26-20 | W |   |
| 2026 | 6 | 2026_06_NYJ_NE | NYJ | -7.5 | 19-26 | W |   |
| 2026 | 6 | 2026_06_NO_NYG | NO | -1.5 | 34-27 | W |   |
| 2026 | 6 | 2026_06_CAR_PHI | CAR | -1.5 | 25-14 | W |   |
| 2026 | 6 | 2026_06_PIT_TB | PIT | +2.5 | 26-19 | W |   |
| 2026 | 6 | 2026_06_LAC_KC | LAC | -8.5 | 6-22 | L |   |
| 2026 | 6 | 2026_06_BUF_LV | BUF | +5.5 | 33-30 | L |   |
| 2026 | 6 | 2026_06_DAL_GB | DAL | -1.5 | 13-23 | L | DAL L |
| 2026 | 6 | 2026_06_WAS_SF | WAS | -7.5 | 17-23 | W | WAS W |
| 2026 | 7 | 2026_07_NE_CHI | NE | -3.5 | 24-30 | L | NE L |
| 2026 | 7 | 2026_07_SF_ATL | ATL | +3.5 | 20-29 | W | ATL W |
| 2026 | 7 | 2026_07_CIN_BAL | CIN | -2.5 | 35-13 | W | CIN W |
| 2026 | 7 | 2026_07_TB_CAR | TB | -3.5 | 43-13 | W | TB W |
| 2026 | 7 | 2026_07_NYG_HOU | HOU | -9.5 | 27-21 | L | NYG W |
| 2026 | 7 | 2026_07_IND_MIN | MIN | -6.5 | 10-16 | L | IND W |
| 2026 | 7 | 2026_07_MIA_NYJ | MIA | -4.5 | 28-25 | W | MIA W |
| 2026 | 7 | 2026_07_CLE_TEN | CLE | +1.5 | 27-24 | W | CLE W |
| 2026 | 7 | 2026_07_DEN_ARI | DEN | +4.5 | 30-16 | W | ARI L |
