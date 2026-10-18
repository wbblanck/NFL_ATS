# OddsLink NFL probe 20261018T231335Z

GET /sports {} -> HTTP 200, 24941 bytes; headers {'X-Ratelimit-Limit': '2', 'X-Ratelimit-Remaining': '1', 'X-Ratelimit-Reset': '1', 'X-Request-Id': 'req_YpQQhHtYqoIG3MpT', 'X-Requests-Last': '0', 'X-Requests-Remaining': '1000', 'X-Requests-Used': '0'}
sports rows 174; NFL-like: [{"key": "nfl", "group": "American Football", "title": "NFL", "description": "US Football", "active": true, "has_outrights": false}]
using sport key 'nfl'
GET /sports/nfl/odds {'markets': 'spreads', 'oddsFormat': 'decimal', 'bookmakers': 'pinnacle'} -> HTTP 200, 7166 bytes; headers {'X-Ratelimit-Limit': '2', 'X-Ratelimit-Remaining': '1', 'X-Ratelimit-Reset': '0', 'X-Request-Id': 'req_IwbsQZBo7PUFwWVQ', 'X-Requests-Last': '1', 'X-Requests-Remaining': '999', 'X-Requests-Used': '1'}
  pinnacle: 2 fixtures; books ['pinnacle']
    Dallas Cowboys @ Green Bay Packers 2026-10-19T00:20:00.000Z pinnacle main [('Dallas Cowboys', -1.0, 1.98, True), ('Green Bay Packers', 1.0, 1.93, True)] last_update ['2026-10-18T23:13:32.041Z']
    Washington Commanders @ San Francisco 49ers 2026-10-20T00:15:00.000Z pinnacle main [('Washington Commanders', 7.5, 1.93, True), ('San Francisco 49ers', -7.5, 1.96, True)] last_update ['2026-10-18T23:13:32.041Z']
GET /sports/nfl/odds {'markets': 'spreads', 'oddsFormat': 'decimal'} -> HTTP 200, 680256 bytes; headers {'X-Ratelimit-Limit': '2', 'X-Ratelimit-Remaining': '1', 'X-Ratelimit-Reset': '0', 'X-Request-Id': 'req_x416ovSDIjSHF3iq', 'X-Requests-Last': '1', 'X-Requests-Remaining': '998', 'X-Requests-Used': '2'}
  all: 16 fixtures; books ['1xbet', '4casters', '888sport', 'ballybet', 'bet105', 'bet365', 'betano', 'betfair', 'betmgm', 'betonline', 'betr', 'betrivers', 'betus', 'betway', 'bovada', 'bwin', 'caesars', 'circa', 'cloudbet', 'draftkings', 'fanaticsmarkets', 'fanduel', 'fliff', 'hardrock', 'kalshi', 'ladbrokes', 'lowvig', 'matchbook', 'novig', 'pinnacle', 'polymarket', 'prophetx', 'rebet', 'sbobet', 'shuffle', 'skybet', 'sportbet', 'stake', 'sxbet', 'thescore', 'thunderpick', 'unibet', 'williamhill']
    Dallas Cowboys @ Green Bay Packers 2026-10-19T00:20:00.000Z pinnacle main [('Dallas Cowboys', -1.0, 1.98, True), ('Green Bay Packers', 1.0, 1.93, True)] last_update ['2026-10-18T23:13:38.522Z']
    Washington Commanders @ San Francisco 49ers 2026-10-20T00:15:00.000Z pinnacle main [('Washington Commanders', 7.5, 1.93, True), ('San Francisco 49ers', -7.5, 1.96, True)] last_update ['2026-10-18T23:13:38.522Z']
    New England Patriots @ Chicago Bears 2026-10-23T00:15:00.000Z pinnacle main [] last_update []
