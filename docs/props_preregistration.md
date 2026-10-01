# NFL Player Props: Exploration Declaration (step 1 of 2)

Committed before any player-prop line was fetched for analysis (only the coverage probes in
`docs/props_data_audit.md` exist, which read no outcomes).

- **2024 is the exploration season.** Its Action Network props (`data/props/an_props_2024.csv`, fetched by
  `scripts/fetch/an_props.py`) and nflverse player stats may be explored freely. Anything found there is a
  hypothesis, not a result.
- **2025 and 2026 are held out.** Their props are not fetched until step 2, a confirmation pre-registration
  (`docs/props_confirm_preregistration.md`: the hypotheses taken forward, the bet rules, sample rules and pass
  criteria, Bonferroni over every hypothesis taken forward), is committed. The fetch script refuses any season but
  2024 while that file is absent.
- A hypothesis is never added because a held-out result looked interesting. "Nothing survives" is a valid result.
- Pass criterion for any confirmed bet rule (fixed now): win rate at the recorded price with a player-clustered or
  week-clustered 95% interval whose lower end clears that price's break-even; minimum n = 30 per rule.
