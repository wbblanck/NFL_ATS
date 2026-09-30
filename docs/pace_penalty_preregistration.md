# Pace and Penalties: Pre-registration

Committed before any result. Suggested by r/sportsanalytics comments ("pace of play", "penalties/discipline of the
teams matters a lot"). Neither has been tested in this project. Everything else used here was already seen
(docs/adaptive_report.md, the live model's history).

## Team traits (before each game, from earlier games only)

From nflverse team game stats (all game types, 1999 onward):
- **Discipline:** net penalty yards per game = penalty yards committed − penalty yards drawn (the opponent's
  committed).
- **Pace:** offensive plays per game = pass attempts + carries + sacks taken.

Each is an exponentially weighted mean of the team's earlier games (half-life 8 games), shrunk 35% toward the
league mean at each new season. Fixed in advance, not tuned.

## Inputs to the pick model

1. logit of the live model's cover probability (as in the adaptive test);
2. **penalty edge** = (away net penalty yards − home net penalty yards) / 10: positive when home is more
   disciplined;
3. **pace × favorite** = (combined pace of the two teams, standardized on earlier seasons) × (+1 if the home team
   is favored on the line, −1 if the away team is): positive when a faster game favors the favorite covering.

Logistic regression re-fit before every week on all earlier games since 2008, the same procedure and grid as the
adaptive test (age half-life H in {2, 4, 8, none}, L2 penalty lambda in {0.1, 1, 10}, chosen by log loss on
2016–2019).

## Data and decision

Same as docs/adaptive_preregistration.md: proxy line SBRO open 2008–2013, book open 2014–2024, CBS open 2025;
market = nflverse close and total; pushes excluded. **Pass** only if on 2020–2024 half-point book opens (a) it beats
the live model on games where the picks differ with one-sided z >= 1.645, (b) its log loss is lower, and (c) its
2025 CBS-open record on differing games is not negative. Reported, deciding nothing: each input's fitted weight and
its standard error on 2008–2019, and results by move size.
