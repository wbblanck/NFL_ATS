# Player Projection Model for Props: Declaration

Committed 2026-10-01 before the model was built or run on any prop line.

- Model: each player's expected stat from information known before kickoff (recent usage, team scoring
  environment from the closing spread and total, opponent's yards allowed to the position). Bet the under (or
  over) when the projection sits far enough from the line.
- **Built and tuned on 2024 and 2025 only** (both already exploration seasons for props). 2024 fits the
  constants, 2025 checks them; anything chosen there is a hypothesis.
- **2026 is the test.** `data/props/an_props_2026.csv` exists for the separately registered selective rules
  (docs/selective_props_confirm.md); it is not read for this model, and no 2026 player stat enters any fit, until
  `docs/projection_props_confirm.md` (at most 3 rules, Bonferroni, pass criteria) is committed. Decision after
  the 2026 regular season.
