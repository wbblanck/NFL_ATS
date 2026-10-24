# Key-Number Pick in No-Move and Straddle Games: Report

Rules: `docs/keynum_combo_preregistration.md` (committed before any result). Numbers:
`data/backtests/keynum_combo.json`, aggregate only, from `python -m engine.backtest.keynum_combo`. The
AusSportsBetting file stays out of git.

## Result: fail

**Primary (AusSportsBetting 2022-2024, 453 games).** KN picked differently from the official pick in 78 games:
KN won 38, official won 40 (one-sided p = 0.63; the pass mark was 0.05). Over all 453 games KN went 256-197
and official 258-195. KN's mean cover margin was 0.78 points worse (95% week-clustered interval −2.01 to +0.33).
The lead from `docs/variants2026_report.md` is closed.

## Secondary

| Set | Games | Official | KN | Differ: KN-official | No-move half | Straddle half |
|---|---|---|---|---|---|---|
| ASB 2022-2024 (primary) | 453 | 258-195 | 256-197 | 38-40 | 36-36 | 2-4 |
| ASB 2014-2021 (same games as the SBRO lead) | 971 | 518-453 | 524-447 | 104-98 (p = 0.36) | 97-90 | 7-8 |
| 2025 CBS open | 210 | 108-102 | 109-101 | 21-20 | 19-17 | 2-3 |
| 2026 (94 games) | 94 | 54-40 | 56-38 | 8-6 | 8-6 | none |

- On the 2014-2021 SBRO lines the same rule looked strong (no-move 74-49, straddle 33-13). On those same games
  with the AusSportsBetting lines it is 104-98, and the straddle half shrinks from 46 differing games to 15. The
  SBRO result came from that line source (how its opens sit next to the key numbers), not from a real edge.
- `keynum` used everywhere (the original key-number study's candidate): 44-49 on 2022-2024, 120-126 on
  2014-2021, 34-21 on 2025 (p = 0.05, one of many looks, and it had no part in this decision).

## What this means

No change. The official pick stays as it is, and KN is not proposed for tracking. As stated in advance, the test
could detect only a large edge (about 60% on the differing games), so this is "no evidence", not proof that no
edge exists.
