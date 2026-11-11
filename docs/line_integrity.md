# Pool-line and prediction integrity (2026-11-11)

Prediction and grading integrity fixes from the external audit (findings B1-B3). No model, pick rule or
methodology changed; the live record on current data is identical before and after (checked row by row: 48-46 over 94 games on
the 2026-11-11 schedule, same picks, results and lines).

- **Per-row line validation** (`league_lines.load_checked`). One bad row no longer stops the lock run, the grade or the
  dashboard. Each row is checked on its own (spread present and a half-point, favorite matches the sign, known teams,
  and, when a schedule is given, game_id and home/away match). Per game the status is `VALID`, `NO_LINE`, `INVALID` or
  `CONFLICT`. Rejected rows are printed to stderr by every caller and listed by `python -m engine check-league-lines`
  (exit 1 on any problem) and in `live_record.md`.
- **Duplicates.** Identical duplicate rows: the first row is kept (information only). Rows for one game with different
  spreads: all of them are quarantined and the game is `CONFLICT` until the file is fixed in a reviewed commit. This
  replaces "the last row wins". (Batch 6's "latest recorded line per game" rule is separate and unchanged.)
- **A pick without a usable pool line** is still made (the pool needs a pick for every game), flagged
  `NO_LEAGUE_LINE` plus `LEAGUE_LINE_INVALID` or `LEAGUE_LINE_CONFLICT`, status `incomplete`.
- **Frozen-line provenance.** Every prediction gets a row in `data/predictions/line_freeze.csv` (append-only):
  `prediction_id`, `game_id`, `line_status`, `line_id` (a hash of the recorded row's game, spread, source and time),
  `spread`, `line_source`, `line_recorded_at`. `predictions.csv` keeps its columns, so nothing in the pick history was
  rewritten. Predictions made before this change have no freeze row; their stored `league_line` is their frozen line.
- **Grading uses the frozen line.** `live.compute` grades each prediction on the `league_line` stored in it. If
  `league_lines.csv` later shows a different valid line, or the game is now in conflict, the game is still graded on the
  frozen line and reported as `frozen_vs_file_mismatches` (and a `LINE MISMATCH` line in `live_record.md`). A prediction made
  with no pool line is graded on the line recorded afterwards, labelled `file_after_pick`; if none is usable it is
  ungradable, with the reason (`no_line`, `invalid_line`, `conflicting_lines`).
- **One official prediction per game.** `store.append_unique` re-reads the file under an exclusive file lock at write
  time and rejects a second row for a game_id (also within a batch); the lock run prints the rejection and returns only
  what it wrote. The grader keeps the earliest row per game_id, lists the rest as `duplicate_predictions`, and counts
  unique games toward the 256-game threshold.
- **`supersedes`** is unchanged: it is still always empty and ten places treat a non-empty value as "skip this row".
  Defining a correction workflow or removing the column is an owner decision and is not part of this change.
