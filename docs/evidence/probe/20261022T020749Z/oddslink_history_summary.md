# OddsLink history probe 20261022T020749Z

GET /openapi.json -> HTTP 200, 200822 bytes, application/json
  POST /v1/contact :: Submit a contact request :: []
  GET /v1/tryit/run :: Run a public read request as a guest :: [None]
  GET /v1/sports :: List sports :: []
  GET /v1/bookmakers :: List bookmakers :: []
  GET /v1/markets :: List markets :: []
  GET /v1/sports/{sport}/events :: List a sport's fixtures, no prices :: [None, None, None, None, None, None]
  GET /v1/sports/{sport}/events/live :: List fixtures in play, no prices :: [None, None, None, None, None, None]
  GET /v1/sports/{sport}/odds :: List a sport's fixtures with prices :: [None, None, None, None, None, None, None, None, None, None, None]
  GET /v1/sports/{sport}/odds/live :: List fixtures in play with prices :: [None, None, None, None, None, None, None, None, None, None, None]
  GET /v1/sports/{sport}/events/{id}/odds :: One fixture's prices, including periods and full-game ladders :: [None, None, None, None, None, None, None, None, None]
  GET /v1/public/board/sports :: Board sports with fixture counts :: []
  GET /v1/public/board/{sport} :: The public board for one sport :: ['sport']
  GET /v1/public/featured :: The homepage's featured games :: []
  GET /v1/sports/{sport}/props :: Player props across a sport's fixtures :: [None, None, None, None, None, None, None, None, None]
  GET /v1/sports/{sport}/props/live :: Player props for fixtures in play :: [None, None, None, None, None, None, None, None, None]
  GET /v1/sports/{sport}/events/{id}/props :: Player props for one fixture :: [None, None, None, None, None, None, None, None, None]
  GET /v1/historical/sports/{sport}/events :: Discover archived fixture IDs :: [None, None, 'commenceTimeFrom', 'commenceTimeTo', 'limit', 'cursor']
  GET /v1/historical/sports/{sport}/events/{id}/odds :: The full recorded price series for one fixture :: [None, None, None, None, None, None, None, None]
  GET /v1/historical/sports/{sport}/events/{id}/openers :: Each book's opening line for one fixture :: [None, None, None, None, None, None, None, None]
  GET /v1/historical/sports/{sport}/events/{id}/closing :: Each book's closing line for one fixture :: [None, None, None, None, None, None, None, None]
  GET /v1/historical/sports/{sport}/events/{id}/props :: Recorded full-game prop checkpoints for one fixture :: [None, None, None, None, None, None, None]
  GET /v1/historical/sports/{sport}/events/{id}/props/movement :: Recorded full-game prop price changes for one fixture :: [None, None, None, None, None, None, None]
  GET /v1/historical/sports/{sport}/events/{id}/props/openers :: Each prop selection first observed by each book :: [None, None, None, None, None, None, None]
  GET /v1/historical/sports/{sport}/events/{id}/props/closing :: Each prop selection last observed before kickoff :: [None, None, None, None, None, None, None]
  GET /v1/account/usage :: This key's plan, allowance and usage :: []
  GET /v1/account/usage/session :: This account's plan, allowance and usage (signed-in session) :: []
  GET /v1/account/usage/history/session :: Daily usage and per-key totals in this billing period :: []
  GET /v1/account/plan :: This account's plan, allowance, billing period and launch price :: []
  GET /v1/account/keys :: List this account's API keys :: []
  POST /v1/account/keys :: Create a new API key :: []
  DELETE /v1/account/keys/{keyId} :: Revoke an API key :: [None]
  POST /v1/billing/checkout :: Start a checkout for a paid plan :: []
  POST /v1/billing/card :: Replace the saved card :: []
  GET /v1/billing/subscription :: This account's subscription :: []
  POST /v1/billing/change :: Change plan, interval or add-on :: []
  POST /v1/billing/cancel :: Cancel at the end of the paid period :: []
  POST /v1/billing/resume :: Undo a cancellation :: []
GET /docs/guides/history/ -> HTTP 200, 237636 bytes, text/html; charset=utf-8
  guide mentions /v1/historical/sports/
  guide mentions /v1/sports/
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
  guide mentions /v1/historical/sports/nfl/events/nfl
GET /v1/account/usage -> HTTP 200, 209 bytes; headers {'X-Ratelimit-Remaining': '1', 'X-Requests-Remaining': '998', 'X-Requests-Used': '2'}
  body: {"plan":"free","requests_allowance":1000,"requests_used_this_period":2,"period_resets_at":"2026-11-18T20:16:29.342684Z","speed_limit_per_second":2,"requests_last_second":0,"measured_at":"2026-10-22T02:07:49Z"}
GET /v1/historical/sports/nfl/events -> HTTP 403, 231 bytes; headers {'X-Ratelimit-Remaining': '1', 'X-Requests-Remaining': '998', 'X-Requests-Used': '2'}
  body: {"error":{"code":"PLAN_REQUIRED","message":"History requires the Scale plan or above.","docs_url":"https://oddslink.app/docs/errors/#plan-required","request_id":"req_DnE2i2EOcThEj1od","current_plan":"free","required_plan":"scale"}}
