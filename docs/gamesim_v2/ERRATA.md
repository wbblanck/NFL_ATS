# Errata and audit log (Generation 2 research), 2026-11-12

Will asked for a full accuracy check. Frozen preregistrations are not edited; corrections are recorded here and in the reports they affect. Every item below was verified by running code or reading the saved manifests, not by memory.

## Errors in what was reported (all development or reporting; no live file, G1 constant or pick changed)

| # | What was wrong | Correct | Where fixed |
|---|---|---|---|
| 1 | First estimation-v2 completion gain (-0.0050 log loss) reported as a result | A leak: 2,018 no-target attempts (all incomplete) were flagged by the receiver prior columns. Withdrawn; clean run flat (-0.00025, interval -0.00063 to +0.00011) | `ESTIMATION_V2_DEV.md` |
| 2 | Said drafted receivers complete about 5 points more often than raw rates imply (unexplained) | The effect existed only in the leaked fit. Clean: +0.02 logit (about 0.5 points), as raw rates | `RECEIVER_AND_D5_DIAGNOSIS.md` |
| 3 | Frozen completion results (dev grid 2020, 2021 validation, 2019-2020 lineup work) used attempts that include no-target throws; the preregistration said "with a target" (2021: 18,489 attempts, of which 558 have no target) | Pressure and the gate are unaffected. Completion player-vs-team shrinks on the clean population: 2019-2020 walk-forward -0.00079 (interval -0.00139 to -0.00019) with them, -0.00043 (-0.00103 to +0.00016) without; vs context -0.00144 vs -0.00109 (both exclude 0). Saved 2021 predictions on the 17,931 attempts with a target: vs context -0.00163 (-0.00262 to -0.00059), vs team -0.00081 (-0.00165 to +0.00001). The 2021 statement that completion beats team factors with an interval excluding zero does not survive | `VALIDATION_2021.md` erratum; `null_target_sensitivity.json`, `audit_2021_completion_target_subset.json` |
| 4 | D5 z of 6.9 and D1 z of 2.46 reported from the two-way cluster standard error | The two-way formula (team + week - observation level) is unstable for the v2 scores. Game-cluster bootstrap, v2 EPA table: D1 z 1.57, D4 1.74, D5 1.49, D10 2.88. For v1 tables the two methods agree (D1 1.10 vs 1.11) | `RECEIVER_AND_D5_DIAGNOSIS.md`, `robust_se_all_*.json` |
| 5 | Described the EPA lineup score as the lead and said nothing in the v2 work cleared correction. Calling any of this a "lead" overstated it: the completion-rate tests are association results (QB and receiver completion rates repeat), with out-of-sample error change -0.000067 (interval -0.000145 to +0.000026) for the QB shift and -0.000073 (-0.000182 to +0.000039) for the receiver shift | With the bootstrap, three v2-completion-table tests on completion rate clear Holm over 18 (D2 comp coef +0.0119 z 3.20 Holm 0.02; D7 comp +0.0119 z 3.21 Holm 0.02; D8 comp +0.0112 z 3.53 Holm 0.01; two-way z were 2.32, 2.70, 2.73). The EPA score does not. These three are one family of related scores, on development data, and 54 tests were examined across three variants | `ESTIMATION_V2_DEV.md` |
| 6 | "About 1,300 team-games for 80% power" and "about 2,150 team-games in 2022-2025" | 2022-2025 weeks 2-18 is 2,046 team-games; power at +0.020 per SD is roughly 60% to 80% depending on the SE method, about 35% at +0.014 | `RECEIVER_AND_D5_DIAGNOSIS.md`, draft preregistration |
| 7 | Slot standard-error range "0.05-0.12" mixed logit units (pressure, completion table) with EPA-per-attempt units | Quoted by table and unit | `ESTIMATION_V2_DEV.md` |
| 8 | Pressure M1 interval compared priors with the frozen v1 prediction file; completion and EPA used a no-prior control | Pressure rerun with the control: +0.000127 (-0.00040 to +0.00065); split-half numbers identical | `ESTIMATION_V2_DEV.md` |
| 9 | Receiver 0.24 to 0.39 split-half rise described as a pedigree effect | Within noise (41 players, overlapping intervals) and the clean prior terms are tiny | `ESTIMATION_V2_DEV.md` |
| 10 | Leak ablation numbers came from a scratch script outside the repo | Reproduced by `scripts/gamesim_v2/prior_ablation.py` (same numbers) | this file |
| 12 | Said every out-of-sample error interval in the 2019-2020 lineup tests includes zero | Of the 54 pooled error tests (3 variants x 18), none is significantly better and 5 are significantly worse (v1 D6 pressure, v1 D6 EPA, v1 D9b EPA, v2-completion D3 EPA, v2-EPA D3 EPA; the last two are the same pressure table). Found by the independent review, verified against the manifests | this file |
| 13 | Draft confirmation preregistration quoted about 60% power | That figure is for the coefficient; for its pass rule 1 (out-of-sample error difference) power is roughly 20-30% at +0.020 per SD and about 5% at +0.014 (rough) | draft marked withdrawn |
| 11 | Commit messages on this branch carry a model-named `Co-Authored-By` line, against the repo rule | Not fixed: removing it needs a history rewrite and force-push, which was blocked and needs Will's say-so. New commits carry only `Claude-Session:` | open |

## Verified correct

- G1 files, `final.py` and the live pipeline: no file outside the Gen 2 directories differs from `main`; full test suite 285 passed.
- v1 lineup results reproduce exactly with the edited script (all 18 pooled tests, maximum difference 0.0 in coefficient and z).
- Estimation-v2 M1, M2, M3, M4, M5 numbers match the manifests (checked line by line); pipeline control (no priors) equals the frozen v1 player model to 0.0000011 log loss.
- No-target attempts by season: 199, 226, 403, 607, 583, 558, 666, 716, 701, 699 (2016-2025); none completed.
- Pressure results do not use the target, so V1, V2, V5 and the gate stand as reported.
- Leak ablation reproduces from the repo script.

## Not checked

- 2022-2025 and 2026 data remain unloaded.
- The effect of removing no-target attempts on the 2019-2020 lineup tests with v1 tables (the v1 table would need refitting without them).
- Whether the v2 completion table's gain on completion rate comes from the clean population or the priors (the no-prior table was not saved).
