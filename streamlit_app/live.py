"""Live scores for the dashboard viewer: fetched from ESPN on each page load, shown above the season summary.

Display only. Nothing here is written anywhere or used to grade: the record is graded after the game by
`engine grade`, as before. "Covering" is against the frozen pool line (league_line, the line the pool grades on).

ESPN: site.web.api.espn.com answered from a GitHub runner on 2026-09-30 while site.api.espn.com returned Access
Denied (docs/evidence/probe/20260930T034922Z/), so the web host is tried first. Any failure shows no live strip.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from engine.picks import hybrid                      # noqa: E402  (pure: no heavy imports)
from engine.teams import UnknownTeam, to_canonical   # noqa: E402

URLS = ["https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ET = ZoneInfo("America/New_York")


def fetch_scoreboard(timeout: float = 6.0) -> dict | None:
    for url in URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            if isinstance(d, dict) and isinstance(d.get("events"), list):
                return d
        except Exception:
            continue
    return None


def live_games(board: dict | None, states: tuple[str, ...] = ("in",)) -> list[dict]:
    """Games in progress (status state "in", which includes halftime); `states` adds e.g. "post" for finished games."""
    out = []
    for e in (board or {}).get("events") or []:
        st = (e.get("status") or {}).get("type") or {}
        if st.get("state") not in states:
            continue
        comp = (e.get("competitions") or [{}])[0]
        side = {}
        for c in comp.get("competitors") or []:
            t = c.get("team") or {}
            try:
                code = to_canonical(t.get("abbreviation") or "")
            except UnknownTeam:
                code = None
            try:
                score = int(float(c.get("score") or 0))
            except (TypeError, ValueError):
                score = 0
            side[c.get("homeAway")] = {"code": code, "abbr": t.get("abbreviation") or "?", "score": score,
                                       "color": "#" + (t.get("color") or "586580"), "id": t.get("id")}
        if "home" not in side or "away" not in side:
            continue
        sit = comp.get("situation") or {}
        poss = sit.get("possession")
        out.append({"home": side["home"], "away": side["away"],
                    "detail": st.get("shortDetail") or st.get("detail") or "In progress",
                    "halftime": st.get("name") == "STATUS_HALFTIME",
                    "possession": "home" if poss and poss == side["home"]["id"] else
                                  "away" if poss and poss == side["away"]["id"] else None,
                    "down": sit.get("shortDownDistanceText") or sit.get("downDistanceText"),
                    "redzone": bool(sit.get("isRedZone")), "start": e.get("date"), "state": st.get("state")})
    return out


def load_picks(root: Path = ROOT) -> dict[tuple[str, str], dict]:
    """(home, away) -> latest final pick this season, with the hybrid's pick (docs/hybrid_tracking.md)."""
    pred_path, proj_path = root / "data" / "predictions" / "predictions.csv", root / "data" / "predictions" / "projections.csv"
    if not pred_path.exists():
        return {}
    v1 = {}
    if proj_path.exists():
        with open(proj_path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("model_version") == "proj-poisson-v1":
                    v1[r["game_id"]] = r.get("proj_pick")
    out = {}
    with open(pred_path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("supersedes"):
                continue
            hy, src = hybrid.pick(r.get("pick_team"), r.get("drift"), v1.get(r["game_id"]))
            out[(r["home_team"], r["away_team"])] = {**r, "hybrid_team": hy, "hybrid_source": src}
    return out


def cover_margin(team: str, home: str, home_score: int, away_score: int, league_line: float) -> float:
    """Points `team` is covering the pool line by (negative = not covering). league_line is the home spread."""
    home_margin = home_score - away_score + league_line
    return home_margin if team == home else -home_margin


def _line_text(team: str, home: str, league_line: float) -> str:
    v = league_line if team == home else -league_line
    return "PK" if v == 0 else f"{v:+g}"


def _state(m: float) -> tuple[str, str]:
    if m > 0:
        return "cov", f"Covering by {m:g}"
    if m < 0:
        return "miss", f"Needs {-m:g}" if -m != 0.5 else "Needs a ½ point"
    return "push", "Push right now"


def cards(games: list[dict], picks: dict) -> list[dict]:
    out = []
    for g in games:
        h, a = g["home"], g["away"]
        p = picks.get((h["code"], a["code"]))
        c = {**g, "pick": None}
        if p and p.get("league_line") not in (None, ""):
            ll = float(p["league_line"])
            rows = []
            for who, team in (("Pick", p.get("pick_team")), ("Hybrid", p.get("hybrid_team"))):
                if not team or (who == "Hybrid" and team == p.get("pick_team")):
                    continue
                m = cover_margin(team, h["code"], h["score"], a["score"], ll)
                cls, txt = _state(m)
                rows.append({"who": who, "team": team, "line": _line_text(team, h["code"], ll), "cls": cls, "txt": txt})
            c["pick"] = rows
        out.append(c)
    return out


CSS = """
<style>
.live{background:var(--panel);border:1px solid var(--rule);border-radius:12px;padding:16px 16px 14px;position:relative;overflow:hidden}
.live::before{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:linear-gradient(90deg,#e5322d,var(--flag),#e5322d);background-size:200% 100%;animation:lv-sweep 3.2s linear infinite}
@keyframes lv-sweep{to{background-position:-200% 0}}
.lv-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}
.lv-tag{white-space:nowrap;display:inline-flex;align-items:center;gap:8px;font:500 12px var(--mono);letter-spacing:.16em;text-transform:uppercase;color:#e5322d}
.lv-dot{width:9px;height:9px;border-radius:50%;background:#e5322d;box-shadow:0 0 0 0 rgba(229,50,45,.6);animation:lv-pulse 1.6s infinite}
@keyframes lv-pulse{70%{box-shadow:0 0 0 9px rgba(229,50,45,0)}100%{box-shadow:0 0 0 0 rgba(229,50,45,0)}}
.lv-upd{font:400 11px var(--mono);color:var(--ink-3);letter-spacing:.06em;text-align:right}
@media (max-width:520px){.lv-upd .lv-hint{display:none}}
.lv-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}
.lv-card{background:var(--panel-2);border:1px solid var(--rule);border-left:4px solid var(--rule);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:10px}
.lv-row{display:grid;grid-template-columns:6px 1fr auto;align-items:center;gap:10px}
.lv-bar{width:6px;height:30px;border-radius:3px;box-shadow:0 0 0 1px var(--band)}
.lv-card.cov{border-left-color:var(--win)} .lv-card.miss{border-left-color:var(--loss)} .lv-card.push{border-left-color:var(--flag)}
.lv-team{font:800 26px/1 var(--display);text-transform:uppercase;letter-spacing:.02em;display:flex;align-items:center;gap:8px}
.lv-ball{font-size:13px;filter:saturate(1.2)}
.lv-score{font:800 38px/1 var(--display);font-variant-numeric:tabular-nums;min-width:2ch;text-align:right}
.lv-row.lead .lv-score{color:var(--ink)} .lv-row.trail .lv-score{color:var(--ink-3)}
.lv-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;font:400 12px var(--mono);color:var(--ink-2)}
.lv-clock{background:var(--ink);color:var(--panel);border-radius:999px;padding:2px 9px;font-weight:500;letter-spacing:.04em}
.lv-rz{color:#e5322d;font-weight:500}
.lv-pick{display:flex;align-items:center;justify-content:space-between;gap:8px;border-top:1px dashed var(--rule);padding-top:9px}
.lv-who{font:500 11px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3)}
.lv-who.hy{color:var(--c-hy)}
.lv-side{font:600 15px var(--body)}
.lv-chip{font:500 12px var(--mono);padding:3px 9px;border-radius:999px;white-space:nowrap}
.lv-chip.cov{background:var(--win-bg);color:var(--win)} .lv-chip.miss{background:var(--loss-bg);color:var(--loss)}
.lv-chip.push{background:var(--flag-soft);color:var(--ink)}
.lv-note{font:400 11px var(--mono);color:var(--ink-3);margin-top:10px}
@media (prefers-reduced-motion:reduce){.live::before,.lv-dot{animation:none}}
</style>"""


def render(cs: list[dict], now: dt.datetime | None = None) -> str:
    if not cs:
        return ""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET)
    e = html.escape
    out = [CSS, '<section class="live" aria-label="Games in progress"><div class="lv-top">',
           '<span class="lv-tag"><i class="lv-dot"></i>Live now</span>',
           f'<span class="lv-upd">Updated {e(now.strftime("%-I:%M %p ET"))}<span class="lv-hint"> · refresh for the latest</span></span></div>',
           '<div class="lv-grid">']
    for c in cs:
        a, h = c["away"], c["home"]
        main = (c.get("pick") or [{}])[0].get("cls", "")
        out.append(f'<article class="lv-card {main}">')
        for k, s in (("away", a), ("home", h)):
            o = h if k == "away" else a
            lead = "lead" if s["score"] >= o["score"] else "trail"
            ball = '<span class="lv-ball" title="Has the ball">🏈</span>' if c["possession"] == k else ""
            out.append(f'<div class="lv-row {lead}"><i class="lv-bar" style="background:{e(s["color"])}"></i>'
                       f'<span class="lv-team">{e(s["abbr"])}{ball}</span><span class="lv-score">{s["score"]}</span></div>')
        meta = [f'<span class="lv-clock">{e("Halftime" if c["halftime"] else c["detail"])}</span>']
        if c.get("down") and not c["halftime"]:
            meta.append(f'<span>{e(c["down"])}</span>')
        if c.get("redzone"):
            meta.append('<span class="lv-rz">Red zone</span>')
        out.append(f'<div class="lv-meta">{"".join(meta)}</div>')
        for p in c.get("pick") or []:
            who = "hy" if p["who"] == "Hybrid" else ""
            out.append(f'<div class="lv-pick"><span><span class="lv-who {who}">{e(p["who"])}</span> '
                       f'<span class="lv-side">{e(p["team"])} {e(p["line"])}</span></span>'
                       f'<span class="lv-chip {p["cls"]}">{e(p["txt"])}</span></div>')
        if c.get("pick") is None:
            out.append('<div class="lv-pick"><span class="lv-who">No pick recorded for this game</span></div>')
        out.append('</article>')
    out.append('</div><p class="lv-note">Live, not final: covering is against the pool line and is graded only '
               'after the game.</p></section>')
    return "".join(out)


def inject(page: str, strip: str) -> str:
    """Put the strip right after the dashboard's header; unchanged page if there is nothing live or no header."""
    if not strip or "</header>" not in page:
        return page
    return page.replace("</header>", "</header>" + strip, 1)


DATA_TAG = re.compile(r'(<script id="live-data" type="application/json">)[^<]*(</script>)')


def page_data(board: dict | None, now: dt.datetime | None = None) -> dict:
    """Scores for the redesigned page's own live layer: games in progress and games that finished on the board."""
    now = now or dt.datetime.now(dt.timezone.utc)
    games = [{"home": g["home"]["code"], "away": g["away"]["code"], "hs": g["home"]["score"], "as": g["away"]["score"],
              "state": g["state"], "detail": g["detail"], "halftime": g["halftime"]}
             for g in live_games(board, ("in", "post")) if g["home"]["code"] and g["away"]["code"]]
    return {"asof": now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "games": games}


def inject_data(page: str, data: dict) -> str:
    """Fill the `live-data` placeholder of the redesigned page; unchanged page if it has none."""
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return DATA_TAG.sub(lambda m: m.group(1) + payload + m.group(2), page, count=1)
