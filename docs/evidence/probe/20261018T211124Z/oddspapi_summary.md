# OddsPapi NFL probe 20261018T211124Z

requests before: 26 of 250

## 1. ids
sports -> HTTP 200, 70 rows
  sportName matching ('american',): [(14, 'American Football')]
tournaments?sportId=14 -> HTTP 200, 34 rows
  tournamentName matching ('nfl',): [(31, 'NFL'), (233, 'NFL Preseason'), (458, 'NFL Europe'), (1010, 'NFL Pro Bowl'), (14872, 'NFLPA Collegiate Bowl'), (38947, 'NFL Draft')]

## 2. markets
markets?sportId=14 -> HTTP 200, 4751 market ids
marketTypes: {'1x2': 7, 'exactfieldgoals': 1, 'exacttd': 1, 'moneyline': 9, 'oddeven': 3, 'oddeven-team1': 3, 'oddeven-team2': 3, 'overtime': 1, 'players-assists': 1, 'players-fieldgoals': 1, 'players-firsttd': 1, 'players-kickingpoints': 1, 'players-passyards': 1, 'players-rushattempts': 1, 'players-rushtd': 1, 'players-rushyards': 1, 'players-sacks': 1, 'players-secondtd': 1, 'players-tacass': 1, 'players-td': 5, 'players-td-other': 4, 'players-thirdtd': 1, 'playertotals-assists': 15, 'playertotals-fieldgoals': 10, 'playertotals-interceptions': 3, 'playertotals-kickingpoints': 20, 'playertotals-longestpasscomp': 91, 'playertotals-longestrushyards': 50, 'playertotals-passattempts': 70, 'playertotals-passcompletions': 70, 'playertotals-passyards': 300, 'playertotals-receivingyards': 300, 'playertotals-receptions': 10, 'playertotals-rushattempts': 50, 'playertotals-rushtd': 4, 'playertotals-rushyards': 191, 'playertotals-sacks': 5, 'playertotals-tacass': 25, 'playertotals-td': 5, 'playertotals-tdpasses': 3, 'spreads': 1049, 'teamtotals-team1': 690, 'teamtotals-team2': 690, 'totals': 961, 'totals-fieldgoals': 40, 'totals-touchdowns': 50}
  id 14186 spreads 'Handicap (incl. overtime)' handicap -25.0 period result outcomes [(14186, '1'), (14187, '2')]
  id 14188 spreads 'Handicap (incl. overtime)' handicap -24.5 period result outcomes [(14188, '1'), (14189, '2')]
  id 14190 spreads 'Handicap (incl. overtime)' handicap -24.0 period result outcomes [(14191, '2'), (14190, '1')]
  id 14192 spreads 'Handicap (incl. overtime)' handicap -23.5 period result outcomes [(14193, '2'), (14192, '1')]
  id 14194 spreads 'Handicap (incl. overtime)' handicap -23.0 period result outcomes [(14195, '2'), (14194, '1')]
  id 14196 spreads 'Handicap (incl. overtime)' handicap -22.5 period result outcomes [(14197, '2'), (14196, '1')]
  id 14198 spreads 'Handicap (incl. overtime)' handicap -22.0 period result outcomes [(14199, '2'), (14198, '1')]
  id 14200 spreads 'Handicap (incl. overtime)' handicap -21.5 period result outcomes [(14200, '1'), (14201, '2')]
  id 14202 spreads 'Handicap (incl. overtime)' handicap -21.0 period result outcomes [(14202, '1'), (14203, '2')]
  id 14204 spreads 'Handicap (incl. overtime)' handicap -20.5 period result outcomes [(14205, '2'), (14204, '1')]
  id 14206 spreads 'Handicap (incl. overtime)' handicap -20.0 period result outcomes [(14206, '1'), (14207, '2')]
  id 14208 spreads 'Handicap (incl. overtime)' handicap -19.5 period result outcomes [(14209, '2'), (14208, '1')]

## 3. live odds (odds-by-tournaments)
pinnacle: HTTP 200, 2 fixtures, 2 with a spread market
draftkings: HTTP 200, 16 fixtures, 16 with a spread market
fanduel: HTTP 200, 16 fixtures, 16 with a spread market
sample spread quotes: ["pinnacle", "id1400003171515922", null, null, {"14272": {"14273": {"active": true, "betslip": null, "bookmakerOutcomeId": "-3.5/away", "bookmakerChangedAt": "2026-10-18T21:03:24.310Z", "changedAt": "2026-10-18T21:03:24.568Z", "limit": 139664.0, "playerName": null, "price": 1.537, "priceAmerican": "-186", "priceFractional": "29/54", "mainLine": false, "exchangeMeta": null}, "14272": {"active": true, "betslip": null, "bookmakerOutcomeId": "-3.5/home", "bookmakerChangedAt": "2026-10-18T21:03:24.310Z", "changedAt": "2026-10-18T21:03:24.568Z", "limit": 75000.0, "playerName": null, "price": 2.61, "priceAmerican": "161", "priceFractional": "161/100", "mainLine": false, "exchangeMeta": null}}, "14300": {"14301": {"active": true, "betslip": null, "bookmakerOutcomeId": "3.5/away", "bookmakerChangedAt": "2026-10-18T21:03:24.310Z", "changedAt": "2026-10-18T21:03:24.568Z", "limit": 75000.0, "playerName": null, "price": 2.78, "priceAmerican": "178", "priceFractional": "89/50", "mainLine": false, "exchangeMeta": null}, "14300": {"active": true, "betslip": null, "bookmakerOutcomeId": "3.5/home", "bookmakerChangedAt": "2026-10-18T21:03:24.310Z", "changedAt": "2026-10-18T21:03:24.568Z", "limit": 156250.0, "playerName": null, "price": 1.48, "priceAmerican": "-208", "priceFractional": "12/25", "mainLine": false, "exchangeMeta": null}}, "142383": {"142384": {"active": true, "betslip": null, "bookmakerOutcomeId": "-0.5/away", "bookmakerChangedAt": "2026-10-18T21:03:24.437Z", "changedAt": "2026-10
fixture keys (first live fixture): ['bookmakerOdds', 'fixtureId', 'hasOdds', 'participant1Id', 'participant2Id', 'seasonId', 'sportId', 'startTime', 'statusId', 'tournamentId', 'trueEndTime', 'trueStartTime', 'updatedAt']

## 4. history (historical-odds, free)
fixtures last 8 days -> HTTP 200, 15 rows
  using fixture id1400003171488624 Jacksonville Jaguars v Philadelphia Eagles start 2026-10-11T13:30:00.000Z
  draftkings: 861 markets, 150 spread markets, 96217 spread snapshots
  fanduel: 825 markets, 124 spread markets, 58435 spread snapshots
  pinnacle: 256 markets, 79 spread markets, 16410 spread snapshots

done. requests after: 33 of 250 (this probe 7)
