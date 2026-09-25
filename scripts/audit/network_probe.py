"""Phase 0 network probe.

Runs on a GitHub-hosted runner (open internet) and records exactly what each
candidate data source returns. Raw responses are saved under
docs/evidence/probe/<UTC timestamp>/ so the audit can cite them. Nothing here
is interpreted; interpretation lives in docs/data_audit.md.

Secrets are read from the environment and scrubbed from anything written.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "probe" / STAMP
OUT.mkdir(parents=True, exist_ok=True)
SECRETS = [v for k, v in os.environ.items() if k.endswith("_API_KEY") and v]
SUMMARY: list[dict] = []


def scrub(text: str) -> str:
    for s in SECRETS:
        text = text.replace(s, "***")
    return text


def fetch(name: str, url: str, save_as: str | None = None, max_save: int = 3_000_000,
          headers: dict | None = None) -> requests.Response | None:
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    rec = {"name": name, "url": scrub(url)}
    try:
        r = requests.get(url, headers=h, timeout=45)
        rec.update(status=r.status_code, bytes=len(r.content),
                   content_type=r.headers.get("content-type"),
                   final_url=scrub(r.url),
                   last_modified=r.headers.get("last-modified"))
        if save_as:
            body = r.content[:max_save]
            if save_as.endswith((".html", ".json", ".txt", ".csv")):
                (OUT / save_as).write_text(scrub(body.decode("utf-8", "replace")))
            else:
                (OUT / save_as).write_bytes(body)
            rec["saved"] = save_as
        print(f"[{name}] {r.status_code} {len(r.content)}B {rec['content_type']}")
        SUMMARY.append(rec)
        return r
    except Exception as e:  # record the failure, never hide it
        rec["error"] = repr(e)
        print(f"[{name}] ERROR {e!r}")
        SUMMARY.append(rec)
        return None


def html_notes(name: str, r: requests.Response | None) -> None:
    if r is None or not r.ok:
        return
    t = r.text
    notes = {
        "title": (re.search(r"<title>(.*?)</title>", t, re.S) or [None, None])[1],
        "count_open_word": len(re.findall(r"\bopen(ing)?\b", t, re.I)),
        "count_consensus": len(re.findall(r"consensus", t, re.I)),
        "script_json_ids": re.findall(r'<script[^>]+id="([^"]+)"[^>]*type="application/json"', t),
        "has_next_data": "__NEXT_DATA__" in t,
        "spread_like_tokens": re.findall(r"[+-]\d{1,2}\.5|[+-]\d{1,2}(?=\D)", t)[:40],
        "snippets_open": [re.sub(r"\s+", " ", t[max(0, m.start() - 150): m.end() + 150])
                          for m in list(re.finditer(r"[Oo]pen(ing)?", t))[:8]],
    }
    (OUT / f"{name}_notes.json").write_text(json.dumps(notes, indent=2))
    print(json.dumps({k: notes[k] for k in ("title", "count_open_word", "count_consensus",
                                            "script_json_ids", "has_next_data")}, indent=1))


def main() -> int:
    print("probe start UTC", dt.datetime.now(dt.timezone.utc).isoformat())
    print("GITHUB_EVENT_NAME", os.environ.get("GITHUB_EVENT_NAME"))

    # --- CBS Sports ---------------------------------------------------------
    r = fetch("cbs_nfl_odds", "https://www.cbssports.com/nfl/odds/", "cbs_nfl_odds.html")
    html_notes("cbs_nfl_odds", r)
    r = fetch("cbs_nfl_odds_spread", "https://www.cbssports.com/nfl/odds/spread/",
              "cbs_nfl_odds_spread.html")
    html_notes("cbs_nfl_odds_spread", r)
    r = fetch("cbs_pickem", "https://picks.cbssports.com/football/pickem/", "cbs_pickem.html")
    html_notes("cbs_pickem", r)
    r = fetch("cbs_ats_experts", "https://www.cbssports.com/nfl/picks/experts/against-the-spread/",
              "cbs_ats_experts.html")
    html_notes("cbs_ats_experts", r)

    # Round 3 (2026-09-25): all 2025 regular-season CBS week pages for the
    # pre-registered 2025 holdout (docs/holdout2025_preregistration.md).
    for season, week in [(2025, w) for w in range(1, 19)]:
        name = f"cbs_odds_{season}_w{week}"
        r = fetch(name, f"https://www.cbssports.com/nfl/odds/{season}/regular/week-{week}/", f"{name}.html")
        html_notes(name, r)
    # CBS Pick'em rules / help (league line posting + half-point policy, audit 0.3)
    for name, url in [
        ("cbs_pickem_rules", "https://www.cbssports.com/fantasy/football/games/pickem/rules"),
        ("cbs_opm_help", "https://help.opm.cbssports.com/s/topic/0TO8b000000knCKGAY/how-to-play-and-rules"),
        ("cbs_pickem_lobby", "https://picks.cbssports.com/football/lobby"),
    ]:
        html_notes(name, fetch(name, url, f"{name}.html"))
    # SBRO season page format (historical open/close, audit 0.4/0.6)
    html_notes("sbro_2021_22", fetch("sbro_2021_22",
               "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nfl-odds-2021-22", "sbro_2021_22.html"))
    # NFL inactives timing (audit 0.7)
    html_notes("nfl_injuries", fetch("nfl_injuries", "https://www.nfl.com/injuries/", "nfl_injuries.html"))

    # --- ESPN public JSON (odds with open/current where present) -------------
    r = fetch("espn_scoreboard",
              "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
              "espn_scoreboard.json")
    event_id = None
    if r is not None and r.ok:
        try:
            ev = r.json().get("events", [])
            if ev:
                event_id = ev[0]["id"]
        except Exception as e:
            print("espn parse", e)
    if event_id:
        fetch("espn_summary", f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event_id}",
              "espn_summary.json")
        fetch("espn_core_odds",
              f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{event_id}/competitions/{event_id}/odds",
              "espn_core_odds.json")

    # --- Parlay API (key already used by this repo for MLB) -------------------
    key = os.environ.get("PARLAY_API_KEY")
    if key:
        fetch("parlay_sports", f"https://parlay-api.com/v1/sports?apiKey={key}", "parlay_sports.json")
        fetch("parlay_nfl_spreads",
              f"https://parlay-api.com/v1/sports/americanfootball_nfl/odds?apiKey={key}&markets=spreads&regions=us",
              "parlay_nfl_spreads.json")
    else:
        print("PARLAY_API_KEY not set; skipped")

    # --- The Odds API (no key: records the auth response only) ---------------
    fetch("the_odds_api_nokey", "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds?regions=us&markets=spreads",
          "the_odds_api_nokey.json")

    # --- Historical opening/closing line archives ----------------------------
    fetch("aussportsbetting_nfl_xlsx", "https://www.aussportsbetting.com/historical_data/nfl.xlsx",
          "aussportsbetting_nfl.xlsx", max_save=20_000_000)
    fetch("aussportsbetting_page", "https://www.aussportsbetting.com/data/historical-nfl-results-and-odds-data/",
          "aussportsbetting_page.html")
    fetch("sbro_archive_page", "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nfl/nfloddsarchives.htm",
          "sbro_archive_page.html")

    # --- Weather --------------------------------------------------------------
    fetch("open_meteo_forecast",
          "https://api.open-meteo.com/v1/forecast?latitude=39.0489&longitude=-94.4839&hourly=temperature_2m,wind_speed_10m,precipitation&wind_speed_unit=mph&temperature_unit=fahrenheit&forecast_days=3",
          "open_meteo_forecast.json")
    fetch("open_meteo_archive",
          "https://archive-api.open-meteo.com/v1/archive?latitude=39.0489&longitude=-94.4839&start_date=2015-12-20&end_date=2015-12-20&hourly=temperature_2m,wind_speed_10m,precipitation&wind_speed_unit=mph&temperature_unit=fahrenheit",
          "open_meteo_archive.json")
    fetch("open_meteo_historical_forecast",
          "https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=39.0489&longitude=-94.4839&start_date=2024-12-21&end_date=2024-12-21&hourly=temperature_2m,wind_speed_10m",
          "open_meteo_historical_forecast.json")
    fetch("nws_points", "https://api.weather.gov/points/39.0489,-94.4839", "nws_points.json",
          headers={"User-Agent": "nfl-ats-engine audit (github actions)"})

    # --- nflverse release metadata (update frequency) ------------------------
    gh = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"} if os.environ.get("GITHUB_TOKEN") else {}
    for tag in ["schedules", "injuries", "depth_charts", "pbp", "rosters", "weekly_rosters",
                "snap_counts", "player_stats", "stats_team", "officials", "pfr_advstats", "nextgen_stats",
                "ftn_charting", "pbp_participation"]:
        fetch(f"gh_release_{tag}", f"https://api.github.com/repos/nflverse/nflverse-data/releases/tags/{tag}",
              f"gh_release_{tag}.json", headers=gh)

    (OUT / "summary.json").write_text(json.dumps(SUMMARY, indent=2))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
