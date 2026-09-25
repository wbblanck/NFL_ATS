# Scheduling final picks (external timer → GitHub)

GitHub's built-in cron started 2.7–5.7 h late in 31 measured runs (audit
0.10). Runs started through the **workflow_dispatch API** were prompt. In the
one measurement so far (2026-09-25), the request was sent at 03:41:46Z, the
job started at 03:41:54Z, and the market capture ran at 03:42:14Z. So an
external timer calls the API, and `lock-run.yml` does the work.

## How the lock run behaves

Each call picks every game whose lock (kickoff − 15 min) is **within the next
25 minutes** and that has no prediction yet.

With the timer firing **every 10 minutes**, each game is picked 15–25 minutes
before its lock. If one run fails, the next run 10 minutes later still lands
before lock. A game already picked is never touched again, because
predictions are immutable.

A run with no games due does nothing and costs about 1 billed Actions minute.

## One-time setup (done by the repo owner)

### 1. Create a GitHub token that can only start workflows in this repo

GitHub → Settings → Developer settings → **Fine-grained personal access
tokens** → Generate new token:
- **Repository access:** Only select repositories → `wbblanck/NFL_ATS`.
- **Permissions:** Repository permissions → **Actions: Read and write**.
  Nothing else is needed.
- **Expiration:** your choice. When it expires, the timer stops working, so
  note the date.

### 2. Create the timer job

Use any service that can send a scheduled HTTP POST with custom headers, for
example cron-job.org. That service's features and terms are **UNVERIFIED**
here; check them yourself.

- **URL:** `https://api.github.com/repos/wbblanck/NFL_ATS/actions/workflows/lock-run.yml/dispatches`
- **Method:** `POST`
- **Headers:**
  - `Accept: application/vnd.github+json`
  - `Authorization: Bearer <the token from step 1>`
  - `X-GitHub-Api-Version: 2022-11-28`
- **Body:** `{"ref":"main"}`
- **Success response:** HTTP **204**.
- **Schedule** (time zone **America/New_York**), every 10 minutes during:
  - Thursday 19:00–20:50
  - Sunday 08:30–20:50
  - Monday 18:30–20:50
  - **Add as the season requires:** Saturday games (usually December),
    Thanksgiving Thursday afternoon, Christmas and other special dates. Cover
    from 30 minutes before the earliest lock to the latest lock that day.

   As cron expressions (America/New_York):
   ```
   */10 19-20 * * 4
   */10 8-20  * * 0     # set the first hour to start at :30 if the service allows
   */10 18-20 * * 1
   ```

   The budget is about 100 runs a week, roughly 450 billed Actions minutes a
   month.

### 3. Verify

- Trigger the timer job once by hand. It should return 204, and a "Lock run"
  run should appear under the repo's **Actions** tab within seconds.
- On a game day, `data/predictions/predictions.csv` gains a row for each game
  15–25 minutes before its lock. `minutes_to_lock` in each row records the
  real margin.

## Manual fallback

- **Actions tab:** Actions → **Lock run (final picks)** → Run workflow. Set
  `game_id` (e.g. `2026_04_KC_BUF`) to pick one game right now.
- **Locally:** `python -m engine run --game <game_id>`.
- A pick made after lock is still written, but it is flagged
  `LATE_AFTER_LOCK`.
