# Selective Rules: Declaration (step 1)

Committed 2026-10-01 before any slicing below was computed. Goal: bet only the strongest cases instead of every
qualifying one, choosing the slices on data that is then not used to judge them.

## Player props
- **2025 becomes an exploration season** for selective versions of the disagreement rule
  (docs/props_confirm_report.md already graded the unselective rule on it). Slices may be explored freely on
  2025 (and 2024).
- **2026 is the confirmation season.** No 2026 prop line is fetched until `docs/selective_props_confirm.md`
  (at most 3 rules, Bonferroni over them, pass criteria) is committed. Decision at the end of the 2026 regular
  season; interim numbers are descriptive only.

## Line-move predictor (bet the opener)
- Cutoffs and model choice are explored on **2007–2014 only**; the chosen rule is confirmed once on
  **2015–2021**. Disclosed: the unselective rule's pooled 2007–2021 result (51.7% at |D| ≥ 1) is already known,
  so 2015–2021 is not perfectly clean; no per-season or per-cutoff result on 2015–2021 has been computed.
- At most 2 rules taken forward; pass = week-clustered 95% interval of the win rate at the open above 52.38%
  (Bonferroni across the rules taken forward), n ≥ 30.
