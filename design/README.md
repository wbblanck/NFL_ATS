# Scoreboard dashboard (design)

A redesign of the NFL_ATS dashboard in the **dark-tech** style pack
(`.claude/skills/dark-tech`, on top of the core `design-taste` skill), read as a
stadium scoreboard. Chosen by the owner from three hero options on 2026-10-21;
the other style packs were removed.

| File | What it is |
|---|---|
| `dashboard.template.html` | The page. Reads the same `const D=__DATA__` payload that `engine.picks.dashboard` already builds. |
| `build_dashboard.py` | Copies the payload out of `site/dashboard.html` into the template, writing `dashboard.html`. |
| `dashboard.html` | Built page on the 2026-10-20 data (week 7). Open in a browser. |
| `hero-1.html` | The chosen hero. `hero-2/3.html` are the rejected options, kept for reference. |

Rebuild after a new `site/dashboard.html`: `python design/build_dashboard.py`.
Nothing here is wired into the pick pipeline or `publish-dashboard.yml`.

Team logos are nflverse's squared logos (128px copies in `design/logos`, embedded into
the built page so they show even with no network). They are cropped to a square
by their source; a full uncropped set needs a host the build environment can't
reach. Team logos are trademarks of their teams; this repo is private and for
personal use.
Team colors come from nflverse `teams_colors_logos.csv`.

## Motion and live scores (2026-10-21)

- **Season path:** a chip per tracked model turns its line on or off (choice kept in this browser), plus the 200 coin-flip ghosts (simulated, labeled). Lines draw in left to right.
- **Airport boards:** the hero record and the model tally flip only the digits that changed since your last visit (all roll in from 0 on a first look). What you have seen is stored in this browser only.
- **Result cascade:** after the hero flips, new results grow up from their base in game order (gray, then green or red) on a spring with no overshoot, the week's record counting up as each lands, then the lines draw.
- **Flip banner:** when `D.flips` has a game, a highlight sits on the old pick, a line strikes it, then the highlight stretches over to the new pick (leading edge on a quicker spring) and fades, once per flip.
- **Live pulse and settled check:** the page can't fetch scores itself (its viewer blocks outside requests). `streamlit_app/live.py` `page_data` / `inject_data` put ESPN scores for games in progress or just finished into `<script id="live-data">` when the page is opened; the card then breathes while the game is on and draws a check when it ends. Display only, never graded. Scores are as of the last page load.
- Everything respects `prefers-reduced-motion`. Animations wait until the section is on screen.

## Restored from the old dashboard (2026-10-21)

- **Always the underdog** is on the season path (on by default) with a note that it is a no-skill rule.
- **Finals** have a Replay button: the whole week on one clock, skipping idle hours, with a scrubber.
- **Why we lost** (every official loss, play by play, with turnovers, the last 5:00, tags, other models) needs `D.loss_review`. It was blank on main since week 4 because picks made with no market have `UNAVAILABLE` cover chances; fixed in `loss_review._num`.
- **Model picks** (official, hybrid, projection) on every card, a "Models disagree" filter, a line sparkline on the card and every book's line in the details.
- Build from a fresh dashboard: `python -m engine dashboard --season 2026 --out /tmp/d.html && python design/build_dashboard.py /tmp/d.html`.

## Sections

Scoreboard (live record, win rate ± SE, graded / 256, last week, live
countdown to the next pick) · lock schedule rail · week board (filter, team
search, sort by kickoff / cover chance / line gap; each game opens to the
reasons, market-median line movement, books at pick time vs the pool line, and
the player-projection breakdown) · season drive (cumulative net wins against
the coin-flip luck band, backtest weeks shaded) · official pick by week ·
model standings · last week's finals with each pick's cover margin through the
game.

## Pre-launch check (design-taste §7 + dark-tech §6), 2026-10-21

| Check | Result |
|---|---|
| Could be made without the skill / generic template | Pass: scoreboard identity, football-specific charts (season drive, cover-margin flow) |
| Centered badge + heading + 2 buttons + screenshot hero | Pass: split hero, the scoreboard is the visual |
| Emoji as UI | Pass: none |
| Three identical cards from habit | Pass: game cards are a data grid, one per game |
| Single neutral sans | Pass: Big Shoulders Display + IBM Plex Mono + Public Sans |
| More than ~2 colors carry meaning | Known exception (owner asked for more color, 2026-10-21): navy ground, team colors and logos on game tiles, blue for the hybrid line and luck band; amber stays the one accent for the pick and next lock; green/red only for cover/miss |
| Body text column too wide | Pass: hero copy capped at 44ch |
| Accent more than ~4 times per viewport | Fixed: amber removed from pool line, cover gauge, move tag and bullets; on the board it marks only the picked team (one per card) |
| Light surfaces / gradients | Pass: none |
| Headline above 4rem or serif | Pass: clamp max 4rem, grotesk |
| Radius above 10px panels / 6px buttons | Pass: 6–10px panels, 6px controls |
| Text contrast | Fixed: muted label color raised from 4.06:1 to 5.14:1 on panels |
| Reduced motion, keyboard | Pass: the pulse and transitions are off under reduced motion; native buttons, select and details/summary with focus rings |
| No horizontal scroll at 390px | Pass (checked in headless Chromium) |

## Publishing (2026-10-21)

`publish-dashboard.yml` builds the engine's data page, renders it through `design/build_dashboard.py`, and commits the result as `site/dashboard.html`. If the design step fails, the data page is published unchanged and the run shows a warning.

## Spring motion (2026-10-22)

Easing for the cascade, flip banner, model chips and live marker is a closed-form spring sampled into CSS `linear()`
(`--sp-crit`, `--sp-lead`, `--sp-trail` in `:root`). Browsers without `linear()` fall back to a plain ease-out.
- **Model chips:** the fill grows from the left edge on a spring instead of swapping in place.
- **Live strip:** a marker shows how far the pick is from covering (about ±14 points fills the track). It springs from where you last saw it, kept in this browser as `lm:<game id>`. Scores only arrive when the page opens, so nothing moves while you watch.
- **Next-pick countdown:** airport-board tiles ticking by the second (days and hours appear only while not zero), with a row of 60 ticks that fills each minute. Tiles turn amber inside 5 minutes, the clock thumps once a second in the last 10 seconds, and the label reads "Picking now" for 90 seconds after the pick time. Screen readers hear the time once a minute.
