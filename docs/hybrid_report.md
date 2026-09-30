# Hybrid Rule: Report

Rules: `docs/hybrid_preregistration.md` (committed before these results). Numbers: `data/backtests/hybrid.json`.

**Result: fail.** Keeping the market-move pick for 1+ point moves and switching the ½/no-move games to another
signal did not beat the live model outside the seasons it was chosen on.

| Candidate on ½/no-move games | 2014–19 (selection): record on those games | Net vs live | 2020–24 (test): record | Net vs live | p |
|---|---|---|---|---|---|
| Live model (reference) | 178-192 (48.1%) | — | 150-143 (51.2%) | — | — |
| **v1 projection (selected)** | 200-170 (54.1%) | +22 | 158-135 (53.9%) | +8 | 0.26 |
| Closing price side | 175-195 | −3 | 157-136 | +7 | 0.20 |
| v1 where price agrees | 187-183 | +9 | 157-136 | +7 | 0.14 |

- v1 was chosen on 2014–2019 (+22, p = 0.048 there) and shrank to +8 on 2020–2024 (p = 0.26): the usual sign of a
  selection effect.
- 2025, CBS open: the hybrid went 106-104 vs the live model's 108-102 (v1 45-53 on the 98 low-move games, live 47-51).
- As stated in advance, the test had low power (about 1 in 4 to detect a true 3-point gain), so this is "no
  evidence", not proof of no effect. Across 2014–2025, v1 on these games is 403-358 (52.9%), live 375-386; the
  2025 CBS games go the other way.
