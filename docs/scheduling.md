# Scheduling final picks (external timer → GitHub)

GitHub's built-in cron started 2.7–5.7 h late in 31 measured runs (audit
0.10). Runs started through the **workflow_dispatch API** were prompt. In the
one measurement so far (2026-09-25), the request was sent at 03:41:46Z, the
job started at 03:41:54Z, and the market capture ran at 03:42:14Z. So an
external timer calls the API, and `lock-run.yml` does the work.

## Waiting mode (used from week 3's Monday game on)

Measured in week 3: the old immediate mode picked games 58–79 minutes before kickoff, because a run fired an hour
early picked every game in its window at once. That discarded the last ~45 minutes of line movement, which is the
signal the model uses.

- **Change:** dispatch `lock-run.yml` with `wait: "true"` about 45 minutes before a slot's first lock.
- **What the job does:** it finds the next lock group in its window and sleeps until **lead_minutes (5) before that
  lock**, i.e. kickoff − 20 min. Then it captures the market, picks, commits and pushes, and repeats for the next
  lock group until the window is empty.
- **Result:** every game is picked about 5 minutes before its lock. That is 20 minutes before kickoff, so the
  `minutes_to_lock` column should read about 5.
- **If a pass fails,** the next pass retries the same game while it is still before lock. The `game_id` manual
  fallback still works.
- **Cost:** one job per slot, up to about 3 hours for the Sunday afternoon slot, i.e. billed Actions minutes for the
  wait.

The six slot jobs on cron-job.org (below) dispatch these runs. The earlier weekly Claude routine that created one
timer per slot no longer exists (checked 2026-10-15); do not recreate it.

## Pick alerts (ntfy)

`lock-run.yml` sends one alert per group of picks to the ntfy topic in the `NTFY_TOPIC` GitHub secret, right after
it commits them. It does not depend on any Claude session. Without the secret it does nothing.

- **Setup:** install the ntfy app, subscribe to the topic, and add the same topic as a repository secret named
  `NTFY_TOPIC`. Run the **Phone alert test** workflow once to confirm a message arrives. The topic is the only
  protection on ntfy.sh (anyone who knows it can read the alerts), so it is a random string and never committed.
- **Command:** `python -m engine alert --local --send --since <ISO time>` prints the line for the picks created
  since then in the working tree and posts it. A failed post is reported but never fails the lock run.
- **The text:** one line of at most 200 characters listing each pick with its spread on the pool line, for example
  `Picks locked (Sun 1:00 PM): CLE +2.5 · PIT +3.5 · JAX −2.5 · SEA −7.5`. A pick made after its lock ends with
  `LATE`. If more picks do not fit, it ends with `· +N more`.
- **Not covered:** the "PICK MISSING" warning exists only in `alert --watch` (prints from a Claude session,
  which cannot reach a phone). A game that gets no pick sends nothing.

## Immediate mode (retired)

Without `wait`, a call picks at once every game whose lock is within `window_minutes` (default 25). It was run from
a timer every 10 minutes until week 3. It is retired: do not create every-10-minute jobs, and do not dispatch with
the bare body `{"ref":"main"}`, which runs in this mode. Two jobs covering the same game can pick it twice.

## Timer jobs (cron-job.org, set up by the repo owner)

Six recurring jobs, time zone **America/New_York**, each dispatching `lock-run.yml` in waiting mode:

| Fires (ET) | Covers | `window_minutes` |
|---|---|---|
| Thu 7:15 PM | 8:15 PM kickoff | 55 |
| Sun 8:30 AM | 9:30 AM (international) | 55 |
| Sun 12:00 PM | 1:00 PM games | 55 |
| Sun 3:05 PM | 4:05 / 4:25 PM games | 75 |
| Sun 7:20 PM | 8:20 PM kickoff | 55 |
| Mon 7:15 PM | 8:15 PM kickoff | 55 |

A job covers a game only if it fires before that game's pick time (kickoff − 20 min) and the game's lock is inside
its window. Any other kickoff needs a **one-off job**: Saturday, Thanksgiving afternoon, Christmas, Friday games, an
earlier Monday doubleheader game, an international game not at 9:30 AM Sunday. Check each week's kickoffs against
the table. Never add a job for a game a recurring job already covers.

**Request** (same for recurring and one-off jobs):
- **URL:** `https://api.github.com/repos/wbblanck/NFL_ATS/actions/workflows/lock-run.yml/dispatches`
- **Method:** `POST`
- **Headers:** `Accept: application/vnd.github+json`, `Authorization: Bearer <token>`,
  `X-GitHub-Api-Version: 2022-11-28`
- **Body:**
  `{"ref":"main","inputs":{"wait":"true","lead_minutes":"5","window_minutes":"55"}}`
  (fire about 45 minutes before the first kickoff; widen `window_minutes` if the slot has several kickoff times)
- **Success response:** HTTP **204**.

**Token:** a fine-grained personal access token limited to `wbblanck/NFL_ATS`, with only **Actions: Read and
write**. When it expires, every job stops, so note the date. It lives only in cron-job.org.

**Verify:** after a slot, `data/predictions/predictions.csv` has a row per game with `minutes_to_lock` about 5.

## Missed locks

A missed lock stays missed. Never pick a game after its lock, and never write or edit a pick after the fact.

The `game_id` input (Actions → **Lock run (final picks)** → Run workflow) and `python -m engine run --game <id>`
pick one game immediately. Use them only **before** that game's lock, for example when its slot job failed to
start. After lock the engine would still write the pick (flagged `LATE_AFTER_LOCK`); do not run them then.

## Dashboard (private, on Streamlit)

`publish-dashboard.yml` rebuilds the dashboard (`python -m engine dashboard`, current week chosen automatically) and
commits it as `site/dashboard.html`. The Streamlit Community Cloud app `streamlit_app/app.py` displays that file;
the app is deployed from this private repo, so only invited viewers can open it.

- **After every group of picks:** the lock run dispatches it from its `notify` step.
- **For final scores:** crons on Sunday evening, after the Sunday/Monday/Thursday night games, and Tuesday morning.
  GitHub's cron can start late (audit 0.10), so scores may appear later than the cron time.
- **Any time:** dispatch it manually.
