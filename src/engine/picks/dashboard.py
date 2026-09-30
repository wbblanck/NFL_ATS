"""Static dashboard (HTML) of a week's picks + the live record. Regenerated on demand;
it is a snapshot, not a live page. Games are grouped into kickoff slots, each card shows the pool line, the
market's move off it, the pick with its cover chance, the tracked projection, and (once played) the result."""
from __future__ import annotations

import datetime as dt
import html
import json
from zoneinfo import ZoneInfo

from engine.data import store
from engine.picks import final, hybrid

ET = ZoneInfo("America/New_York")


PICK_LEAD_MIN = 20          # the lock run picks each game this long before kickoff (docs/scheduling.md)
SLOT_GAP_H = 2.5            # kickoffs closer than this on one day share a slot
V3, V1 = "proj-players-v3", "proj-poisson-v1"


def _signal(drift):
    if drift in (None, "", "UNAVAILABLE"):
        return ("none", "No data")
    a = abs(float(drift))
    return ("strong", "Moved 1+ pt") if a >= 1 else (("lean", "Moved ½ pt") if a > 0 else ("flat", "No move"))


def _clock(d: dt.datetime) -> str:
    return d.astimezone(ET).strftime("%-I:%M %p")


def _slot_label(kicks: list[dt.datetime]) -> tuple[str, str]:
    """('Sunday', '4:05 & 4:25 PM') for a group of kickoffs on one ET day."""
    uniq = sorted({k.astimezone(ET) for k in kicks})
    parts = [k.strftime("%-I:%M") for k in uniq]
    if len({k.strftime("%p") for k in uniq}) == 1:
        times = " & ".join(parts) + " " + uniq[-1].strftime("%p")
    else:
        times = " & ".join(k.strftime("%-I:%M %p") for k in uniq)
    return uniq[0].strftime("%A"), times


def slots_for(kickoffs: dict[str, dt.datetime]) -> tuple[dict[str, int], list[dict]]:
    """Group games into kickoff slots: same ET day and within SLOT_GAP_H of the slot's first kickoff."""
    order = sorted(kickoffs.items(), key=lambda kv: kv[1])
    groups: list[list[tuple[str, dt.datetime]]] = []
    for gid, ko in order:
        e = ko.astimezone(ET)
        if groups:
            first = groups[-1][0][1].astimezone(ET)
            if e.date() == first.date() and (e - first).total_seconds() <= SLOT_GAP_H * 3600:
                groups[-1].append((gid, ko))
                continue
        groups.append([(gid, ko)])
    index, meta = {}, []
    for i, grp in enumerate(groups):
        day, times = _slot_label([k for _, k in grp])
        meta.append({"day": day, "times": times})
        index.update({gid: i for gid, _ in grp})
    return index, meta


def _result_char(v) -> str | None:
    """'BUF W' -> 'W'."""
    return v.strip()[-1] if isinstance(v, str) and v.strip()[-1:] in ("W", "L") else None


def render(rows: list[dict], season: int, week: int, live: dict, updated: dt.datetime,
           results: dict | None = None, details: dict | None = None, season_table: list | None = None,
           credits: int | None = None, straightup: list | None = None) -> str:
    """results: game_id -> graded row from live.compute (result, proj_<version> strings); optional.
    details: game_id -> per-game detail from game_detail.build (book lines over time, why, inputs); optional."""
    results = results or {}
    rec = f"{live['W']}-{live['L']}" if live.get("N") else "0-0"
    kicks = {r["game_id"]: dt.datetime.fromisoformat(r["kickoff_utc"]) for r in rows}
    slot_of, slots = slots_for(kicks)
    games, upcoming = [], []
    for r in rows:
        ko = kicks[r["game_id"]]
        sig_k, sig_l = _signal(r["drift"])
        ph, pa = r.get("p_home"), r.get("p_away")
        pick_p = None
        if ph not in (None, "", "UNAVAILABLE") and r.get("pick"):
            pick_p = float(ph) if r["pick"] == r["home"] else float(pa)
        mt = None
        if r.get("market_time"):
            try:
                mt = dt.datetime.fromisoformat(str(r["market_time"]))
            except ValueError:
                mt = None
        lead = None if mt is None else round((ko - mt).total_seconds() / 60)
        pick_at = ko - dt.timedelta(minutes=PICK_LEAD_MIN)
        if r["status"] == "provisional" and pick_at > updated:
            upcoming.append((pick_at, f"{r['away']} @ {r['home']}"))
        g = results.get(r["game_id"], {})
        pres = _result_char(g.get(f"proj_{r.get('proj_version') or V3}"))
        hy, hysrc = hybrid.pick(r.get("pick"), r.get("drift"), r.get("v1_pick"))
        games.append({"id": r["game_id"], "away": r["away"], "home": r["home"], "ko": ko.astimezone(ET).strftime("%a %-I:%M %p"),
                      "slot": slot_of[r["game_id"]], "ko_iso": ko.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "line": r["league_line"],
                      "market": r["market"] if r["market"] not in ("", None) else None,
                      "drift": float(r["drift"]) if r["drift"] not in ("", None, "UNAVAILABLE") else None,
                      "pick": r.get("pick"), "pick_p": pick_p, "status": r["status"], "sig": sig_k, "sig_label": sig_l,
                      "books": r.get("market_books"), "at": None if mt is None else _clock(mt), "lead": lead,
                      "pick_at": _clock(pick_at), "ph": r.get("proj_home"), "pa": r.get("proj_away"),
                      "ppick": r.get("proj_pick"), "pver": r.get("proj_version"), "pflags": r.get("proj_flags"),
                      "hs": r.get("home_score"), "as": r.get("away_score"), "res": g.get("result"), "pres": pres,
                      "xp": r.get("proj_why"), "hy": hy, "hysrc": hysrc, "hres": _result_char(g.get("hybrid"))})
    models = [{"label": "Official pick", "W": live.get("W", 0), "L": live.get("L", 0)}]
    for label, v in (("Team-only projection", V1), ("Player projection", V3)):
        m = (live.get("projection_models") or {}).get(v)
        if m:
            models.append({"label": label, "W": m["W"], "L": m["L"]})
    if live.get("hybrid"):
        h = live["hybrid"]
        models.append({"label": "Hybrid (tracked)", "W": h["W"], "L": h["L"],
                       "note": f"differs {h['differ']}: hybrid right {h['hybrid_only']}, pick right {h['live_only']}"})
    nxt = min(upcoming) if upcoming else None
    from engine.picks.season import MODELS as _SM
    data = json.dumps({"su": straightup or [], "credits": credits, "season_tab": season_table or [], "season_models": _SM, "games": games, "slots": slots, "details": details or {}, "season": season, "week": week, "record": rec, "models": models,
                       "graded": live.get("N", 0), "claim_at": live.get("claim_at", 256),
                       "next_lock": None if nxt is None else {"at": _clock(nxt[0]), "game": nxt[1]},
                       "updated": updated.astimezone(ET).strftime("%a %b %-d, %-I:%M %p ET")})
    return TEMPLATE.replace("__DATA__", data).replace("__TITLE__", html.escape(f"Week {week} Picks"))


def live_summary() -> dict:
    preds = store.read_rows(final.predictions_path())
    return {"N": 0, "W": 0, "L": 0, "picked": len(preds)}


TEMPLATE = r"""<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800&family=Public+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* Layout: a scoreboard header, one summary panel, then kickoff-slot sections of game cards.
   Each card reads top to bottom: teams and pick, how far the market moved off the frozen pool line, the
   cover chance, the tracked projection, and once played the score and result. */
:root{--bg:#eef0f4;--panel:#ffffff;--panel-2:#f5f6f9;--ink:#0f1a2b;--ink-2:#41506b;--ink-3:#586580;--rule:#dbe0ea;
--flag:#ffc800;--flag-soft:#fff0b8;--on-flag:#0f1a2b;--flat-bg:#e4e8ef;--band:rgba(15,26,43,.10);
--win:#146c36;--win-bg:#e2f4e8;--loss:#b3261e;--loss-bg:#fde7e5;
--display:"Big Shoulders Display","Arial Narrow",Impact,sans-serif;--body:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#0a111f;--panel:#111a2c;--panel-2:#16213a;--ink:#e8edf7;--ink-2:#b3bfd4;--ink-3:#8e9bb4;--rule:#243250;--flag-soft:#4a3c08;--flat-bg:#1c2740;--band:rgba(232,237,247,.14);--win:#63d68d;--win-bg:#123322;--loss:#ff8f86;--loss-bg:#40181a}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#0a111f;--panel:#111a2c;--panel-2:#16213a;--ink:#e8edf7;--ink-2:#b3bfd4;--ink-3:#8e9bb4;--rule:#243250;--flag-soft:#4a3c08;--flat-bg:#1c2740;--band:rgba(232,237,247,.14);--win:#63d68d;--win-bg:#123322;--loss:#ff8f86;--loss-bg:#40181a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--body);padding-inline:16px;padding-block:28px 56px}
.wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:26px}
.eyebrow,.lab,.legend,.chip,.pill,.axis,.mono{font-family:var(--mono)}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2)}
h1{margin:0;font:800 clamp(52px,12vw,92px)/.9 var(--display);letter-spacing:.005em;text-transform:uppercase}
h2{margin:0;font:800 30px/1 var(--display);text-transform:uppercase;letter-spacing:.01em}
.meta{color:var(--ink-2);font-size:14px}
header{display:flex;flex-direction:column;gap:10px}
.next{display:inline-flex;align-items:center;gap:8px;font-size:14px;color:var(--ink)}
.next[hidden]{display:none}
.next i{width:9px;height:9px;border-radius:50%;background:var(--flag);border:2px solid var(--ink);flex:none}

/* summary */
.summary{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:18px;display:flex;flex-direction:column;gap:18px}
.records{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,140px),1fr));gap:18px 24px}
.rec{display:flex;flex-direction:column;gap:2px;min-width:0}
.rec .v{font:800 46px/1 var(--display);font-variant-numeric:tabular-nums}
.rec .l{font-size:13px;color:var(--ink-2)}
.rec .s{font:400 12px/1.4 var(--mono);color:var(--ink-3)}
.bar-row{display:flex;flex-direction:column;gap:6px}
.bar-row .top{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 16px;font-size:13px;color:var(--ink-2)}
.meter{height:8px;border-radius:4px;background:var(--panel-2);border:1px solid var(--rule);overflow:hidden}
.meter i{display:block;height:100%;min-width:3px;background:var(--ink)}

/* controls */
.controls{display:flex;flex-direction:column;gap:12px}
.filters{display:flex;flex-wrap:wrap;gap:8px}
.filters button{font:500 13px var(--body);color:var(--ink-2);background:var(--panel);border:1px solid var(--rule);border-radius:999px;padding:7px 14px;cursor:pointer}
.filters button:hover{border-color:var(--ink-3)}
.filters button[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.filters button:focus-visible,summary:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.legend{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:12px;color:var(--ink-2);align-items:center}
.legend span{display:inline-flex;align-items:center;gap:7px}
.k-pool{width:9px;height:9px;transform:rotate(45deg);border:2px solid var(--ink);background:var(--panel);flex:none}
.k-mkt{width:11px;height:11px;border-radius:50%;background:var(--flag);border:2px solid var(--ink);flex:none}

/* slots and cards */
#slots{display:flex;flex-direction:column;gap:32px}
.slot{display:flex;flex-direction:column;gap:12px}
.slot-h{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 16px;border-bottom:2px solid var(--ink);padding-bottom:8px}
.slot-h h2 small{font:500 14px var(--mono);letter-spacing:0;color:var(--ink-2);margin-left:10px;text-transform:none}
.slot-h .st{font:500 12px var(--mono);color:var(--ink-2)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:14px}
@media (min-width:900px){.grid{grid-template-columns:repeat(var(--cols,3),minmax(0,1fr))}}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:14px;min-width:0}
.card-h{display:flex;justify-content:space-between;align-items:center;gap:8px}
.ko{font:500 12px var(--mono);color:var(--ink-2)}
.pill{font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:4px 8px;border-radius:999px;white-space:nowrap}
.pill.locked{background:var(--ink);color:var(--bg)}
.pill.prov{border:1px solid var(--ink-3);color:var(--ink-2)}
.pill.none{background:var(--flat-bg);color:var(--ink-2)}
.pill.won{background:var(--win-bg);color:var(--win)}
.pill.lost{background:var(--loss-bg);color:var(--loss)}
.teams{display:flex;flex-direction:column;gap:4px}
.team{display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:10px;padding:6px 10px;border-radius:7px;min-width:0}
.team .code{font:800 34px/1 var(--display);letter-spacing:.01em}
.team .tag{font:500 10px var(--mono);letter-spacing:.1em;text-transform:uppercase}
.team .sp{font:500 15px var(--mono);font-variant-numeric:tabular-nums;justify-self:end}
.team .sc{font:800 34px/1 var(--display);font-variant-numeric:tabular-nums;min-width:1.4em;text-align:right}
.team.picked{background:var(--ink);color:var(--bg)}
.team:not(.picked) .sp{color:var(--ink-2)}
.move{display:flex;flex-direction:column;gap:8px}
.move-top{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;font-size:13px;color:var(--ink-2)}
.chip{font-size:11px;padding:4px 8px;border-radius:999px;white-space:nowrap}
.chip.strong{background:var(--flag);color:var(--on-flag)}
.chip.lean{background:var(--flag-soft);color:var(--ink)}
.chip.flat,.chip.none{background:var(--flat-bg);color:var(--ink-2)}
.track{position:relative;height:34px}
.track .base{position:absolute;left:0;right:0;top:11px;height:2px;background:var(--rule)}
.track .tk{position:absolute;top:8px;width:1px;height:8px;background:var(--ink-3);opacity:.6}
.track .seg{position:absolute;top:10px;height:4px;background:var(--ink);border-radius:2px}
.track .pool{position:absolute;left:50%;top:6px;width:11px;height:11px;margin-left:-5.5px;transform:rotate(45deg);border:2px solid var(--ink);background:var(--panel);z-index:1}
.track .dot{position:absolute;top:5px;width:14px;height:14px;margin-left:-7px;border-radius:50%;background:var(--flag);border:2px solid var(--ink);z-index:2}
.track .end{position:absolute;top:22px;font:500 10px var(--mono);letter-spacing:.06em;color:var(--ink-3)}
.track .end.l{left:0}.track .end.r{right:0}
.track.nodata .base{background:repeating-linear-gradient(90deg,var(--rule) 0 6px,transparent 6px 10px)}
.pick-meter{display:grid;grid-template-columns:auto 1fr;grid-template-areas:"lab pct" "g g";align-items:baseline;gap:6px 12px}
.pick-meter .lab{grid-area:lab;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}
.pick-meter .pct{grid-area:pct;justify-self:end;font:800 30px/1 var(--display);font-variant-numeric:tabular-nums}
.gauge{grid-area:g;position:relative;height:8px;border-radius:4px;background:var(--panel-2);border:1px solid var(--rule)}
.gauge i{position:absolute;top:-1px;bottom:-1px;background:var(--ink);border-radius:0 4px 4px 0}
.gauge b{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--ink-2);left:33.333%}
.axis{grid-area:g;position:relative;height:0}
.axis span{position:absolute;top:8px;font-size:10px;color:var(--ink-3);transform:translateX(-50%)}
.proj{border-top:1px dashed var(--rule);padding-top:10px;display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;font-size:12px;color:var(--ink-2)}
.proj .lab{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);flex-basis:100%}
.proj .mono{color:var(--ink)}
.proj .diff{font:500 11px var(--mono);border:1px solid var(--ink-3);border-radius:999px;padding:2px 7px}
.proj .ok{color:var(--win)}.proj .no{color:var(--loss)}
.cover{font-size:13px;color:var(--ink-2)}
.empty{color:var(--ink-2);padding:24px 0}


/* game view */
.wrap[hidden]{display:none}
.card{cursor:pointer}
.card:hover{border-color:var(--ink-3)}
.more{align-self:flex-start;font:500 12px var(--mono);color:var(--ink);background:none;border:0;padding:0;cursor:pointer;text-decoration:underline;text-underline-offset:3px}
.more:focus-visible,.back:focus-visible{outline:2px solid var(--ink);outline-offset:3px;border-radius:4px}
.back{align-self:flex-start;font:500 13px var(--body);color:var(--ink);background:var(--panel);border:1px solid var(--rule);border-radius:999px;padding:7px 14px;cursor:pointer}
.back:hover{border-color:var(--ink-3)}
.d-title{display:flex;flex-direction:column;gap:10px}
.d-match{display:flex;align-items:baseline;flex-wrap:wrap;gap:10px 16px;font:800 clamp(44px,10vw,76px)/.95 var(--display);text-transform:uppercase}
.d-match .at{font-size:.5em;color:var(--ink-3)}
.d-facts{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;font-size:14px;color:var(--ink-2)}
.d-facts b{color:var(--ink);font-weight:600}
.panel[hidden]{display:none}
.panel{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:12px;min-width:0}
h3{margin:0;font:800 22px/1 var(--display);text-transform:uppercase;letter-spacing:.01em}
.sub{font-size:13px;color:var(--ink-2);margin:0}
.panel ul{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:8px;max-width:80ch;font-size:14px}
.chart{position:relative;min-width:0}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.chart svg text{font-family:var(--mono);font-size:11px;fill:var(--ink-3)}
.chart .c-grid{stroke:var(--rule);stroke-width:1}
.chart .c-band{fill:var(--band)}
.chart .c-med{fill:none;stroke:var(--ink);stroke-width:2;stroke-linejoin:round}
.chart .c-pool{stroke:var(--ink-2);stroke-width:1.5;stroke-dasharray:5 4}
.chart .c-pt{fill:var(--panel);stroke:var(--ink);stroke-width:2}
.chart .c-lock{fill:var(--flag);stroke:var(--ink);stroke-width:2}
.chart .c-cross{stroke:var(--ink-3);stroke-width:1}
.chart .c-poollab{fill:var(--ink-2)}
.tip{position:absolute;top:4px;pointer-events:none;background:var(--ink);color:var(--bg);border-radius:6px;padding:8px 10px;font:400 12px/1.5 var(--mono);white-space:nowrap;z-index:3}
.tip b{font-weight:500}
.key{display:flex;flex-wrap:wrap;gap:6px 18px;font:400 12px var(--mono);color:var(--ink-2)}
.key span{display:inline-flex;align-items:center;gap:7px}
.k-band{width:16px;height:10px;background:var(--band);border:1px solid var(--rule)}
.k-line{width:18px;height:0;border-top:2px solid var(--ink)}
.k-dash{width:18px;height:0;border-top:2px dashed var(--ink-2)}
.tbl{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th{font:500 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule);white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid var(--rule);white-space:nowrap}
tr:last-child td{border-bottom:0}
td.n,th.n{text-align:right;font-family:var(--mono)}
td:first-child,th:first-child{position:sticky;left:0;background:var(--panel)}
tr.med td:first-child{background:var(--panel-2)}
tr.med td{font-weight:600;background:var(--panel-2)}
.m{font:500 11px var(--mono);border-radius:999px;padding:2px 7px;margin-left:6px}
.m.same{background:var(--flag);color:var(--on-flag)}
.m.hook{background:var(--flag-soft);color:var(--ink)}
.m.off{background:var(--flat-bg);color:var(--ink-2)}
.cols2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:16px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font-size:13px;margin:0}
.kv dt{color:var(--ink-3);font:400 12px var(--mono)}
.kv dd{margin:0;font-family:var(--mono)}
.kv-h{font:800 26px/1 var(--display);text-transform:uppercase;margin:0 0 8px}

/* how the projected score was built */
.drivers{font-size:12px;color:var(--ink-2);display:grid;grid-template-columns:auto 1fr;gap:3px 12px;align-items:baseline}
.drivers .dt{font-family:var(--mono);color:var(--ink)}
.drivers .lab{grid-column:1/-1;font:400 10px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}
.drivers b{font:500 12px var(--mono);color:var(--ink)}
.build-top{display:flex;flex-wrap:wrap;gap:6px 24px;align-items:baseline;font-size:14px;color:var(--ink-2)}
.build-top b{color:var(--ink);font-weight:600}
.teams2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:22px 32px}
.tb{display:flex;flex-direction:column;gap:12px;min-width:0}
.tb-h{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 14px}
.tb-h .code{font:800 30px/1 var(--display);text-transform:uppercase}
.tb-h .tot{font:800 30px/1 var(--display);font-variant-numeric:tabular-nums}
.tb-h .from{font:400 12px var(--mono);color:var(--ink-2);margin-left:auto}
.axis-row{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr) 3.6em;gap:10px;font:400 10px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3)}
.axis-row .mid{display:flex;justify-content:space-between}
.br{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr) 3.6em;gap:10px;align-items:center;padding:8px 0;border-top:1px solid var(--rule)}
.br .name{display:flex;flex-direction:column;gap:1px;min-width:0}
.br .name b{font-weight:600;font-size:14px}
.br .name small{font-size:12px;color:var(--ink-2);line-height:1.35}
.br .track2{position:relative;height:16px}
.br .track2::before{content:"";position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:var(--ink-3)}
.br .track2 i{position:absolute;top:2px;height:12px;border-radius:2px}
.br .track2 i.up{left:50%;background:var(--ink);border-radius:0 3px 3px 0}
.br .track2 i.dn{right:50%;background:var(--ink-3);border-radius:3px 0 0 3px}
.br .val{font:500 14px var(--mono);text-align:right;font-variant-numeric:tabular-nums}
.none{font-size:12px;color:var(--ink-2);border-top:1px solid var(--rule);padding-top:10px}
.none b{font-weight:600;color:var(--ink)}
.pend{font-size:12px;color:var(--ink);background:var(--flag-soft);border-radius:6px;padding:8px 10px}
.sum{font:400 12px var(--mono);color:var(--ink-2);border-top:2px solid var(--ink);padding-top:8px;display:flex;flex-wrap:wrap;gap:2px 10px}
.sum b{color:var(--ink);font-weight:500}
@media (max-width:520px){
  .axis-row{display:none}
  .br{grid-template-columns:minmax(0,1fr) 3.6em;grid-template-areas:"name val" "bar bar";gap:6px 10px}
  .br .name{grid-area:name}.br .val{grid-area:val}.br .track2{grid-area:bar}
}
.xbtn{font:500 12px var(--mono);color:var(--ink);background:var(--panel-2);border:1px solid var(--rule);border-radius:8px;padding:9px 12px;cursor:pointer;text-align:left;display:flex;justify-content:space-between;gap:8px;width:100%}
.xbtn:hover{border-color:var(--ink-3)}.xbtn:focus-visible,.xclose:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.xp{display:flex;flex-direction:column;gap:14px;border-top:1px solid var(--rule);padding-top:12px;cursor:default}
.xp[hidden]{display:none}
.xp .tb-h .from{display:none}
.xp .axis-row{display:none}
.xp .br{grid-template-columns:minmax(0,1fr) 3.6em;grid-template-areas:"name val" "bar bar";gap:6px 10px}
.xp .br .name{grid-area:name}.xp .br .val{grid-area:val}.xp .br .track2{grid-area:bar}
.xclose{font:500 12px var(--mono);color:var(--ink-2);background:none;border:1px solid var(--rule);border-radius:8px;padding:8px 12px;cursor:pointer;align-self:flex-start}

/* notes */
details{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:14px 18px}
summary{cursor:pointer;font:600 14px var(--body)}
details div{display:flex;flex-direction:column;gap:10px;margin-top:12px;font-size:13px;color:var(--ink-2);max-width:78ch}
details p{margin:0}
@media (prefers-reduced-motion:no-preference){.meter i,.gauge i{transition:width .3s}}
</style>
<div class="wrap" id="board">
  <header>
    <div class="eyebrow">Bonsai Pool 2026 · NFL_ATS</div>
    <h1 id="h1"></h1>
    <div class="meta" id="meta"></div>
    <div class="next" id="next" hidden><i></i><span id="next-t"></span></div>
  </header>
  <section class="summary" aria-label="Season record">
    <div class="records" id="records"></div>
    <div class="bar-row">
      <div class="top"><span id="ev-a"></span><span id="ev-b"></span></div>
      <div class="meter" role="img" id="ev-m"><i id="ev-i"></i></div>
    </div>
  </section>
  <section class="panel" id="season-panel" hidden aria-label="Season by week">
    <h3>Season by week</h3>
    <p class="sub" id="season-note"></p>
    <div class="tbl"><table id="season-tab"></table></div>
  </section>
  <section class="panel" id="su-panel" hidden aria-label="Picking winners">
    <h3>Picking winners (straight up)</h3>
    <p class="sub" id="su-note"></p>
    <div class="tbl"><table id="su-tab"></table></div>
  </section>
  <section class="controls">
    <div class="filters" role="group" aria-label="Filter games">
      <button id="f-all" aria-pressed="true">All games</button>
      <button id="f-strong" aria-pressed="false">Moved 1+ pt</button>
      <button id="f-differs" aria-pressed="false">Projection disagrees</button>
      <button id="f-hybrid" aria-pressed="false">Hybrid disagrees</button>
    </div>
    <div class="legend">
      <span><i class="k-pool"></i>Pool line (frozen Tuesday)</span>
      <span><i class="k-mkt"></i>Market at lock</span>
      <span><b class="chip strong">Moved 1+ pt</b> historically 57%</span>
      <span><b class="chip lean">Moved ½ pt</b> ~51%</span>
      <span><b class="chip flat">No move</b> ~52%</span>
    </div>
  </section>
  <main id="slots"></main>
  <details>
    <summary>How to read this page</summary>
    <div>
      <p><b>Pool line and spreads.</b> Each team shows its spread on the pool line. A minus sign means that team is favored. The market track underneath shows where the betting market stood at lock compared with the pool line, in the home team's spread: left means the market moved toward the home team, right toward the away team.</p>
      <p><b>The pick</b> is the side the market moved toward, with a cover chance from how games have finished relative to the closing spread since 1999. <b>Provisional</b> picks use the latest market snapshot and can change. The official pick is locked about 20 minutes before kickoff and never changes.</p>
      <p><b>Historical win rates</b> are 2007–2021. The 2025 holdout was weaker, at 52% on 1+ point moves. No claim of skill is made before 256 graded games.</p>
      <p><b>Projections</b> are tracked for comparison and do not make the pick. The player projection (proj-players-v3) adjusts team scoring strength for the starting quarterback, injured starters weighted by snaps, rest, travel and roof. Against the market it was a coin flip in 2022–2025 testing (docs/players_v3_report.md). "Injury report pending" means the game statuses were not yet published, so injuries are not reflected. It rates a listed backup quarterback from the depth chart and does not know if that backup is also out.</p>
      <p><b>Hybrid (tracked)</b> keeps the pick when the market moved 1+ point off the pool line and uses the team-only projection when it moved ½ point or not at all. It is followed for comparison only and never makes the pick (docs/hybrid_tracking.md).</p>
    </div>
  </details>
</div>
<div class="wrap" id="detail" hidden></div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=(v,d)=>Number(v).toFixed(d).replace(/(\.\d)0$/,'$1');
const sgn=v=>v===null||v===undefined?'—':(v>0?'+':v<0?'−':'')+num(Math.abs(v),2);
const FR={0:'',0.25:'¼',0.5:'½',0.75:'¾'};
const pts=a=>{const w=Math.floor(a),f=FR[a-w]??String(a-w);const t=(w?w:'')+f;return (t===''?'0':t)+(a<=1?' pt':' pts')};
const pct=(w,l)=>{const n=w+l;if(!n)return null;const r=w/n;return [Math.round(r*100),Math.round(Math.sqrt(r*(1-r)/n)*100)]};
$('h1').textContent=`Week ${D.week}`;
$('meta').textContent=`${D.season} regular season · snapshot ${D.updated}`+(D.credits!=null?` · odds API credits left ${D.credits}${D.credits<150?' (optional captures paused)':''}`:'');
if(D.next_lock){$('next').hidden=false;$('next-t').textContent=`Next pick locks ${D.next_lock.at} ET · ${D.next_lock.game}`}
const g=D.games, locked=g.filter(x=>x.status==='final').length;
$('records').innerHTML=D.models.map(m=>{const p=pct(m.W,m.L);
  return `<div class="rec"><span class="v">${m.W}–${m.L}</span><span class="l">${esc(m.label)}</span><span class="s">${p?`${p[0]}% ± ${p[1]} · vs pool line`:'no games graded yet'}${m.note?`<br>${esc(m.note)}`:''}</span></div>`}).join('')
  +`<div class="rec"><span class="v">${locked}/${g.length}</span><span class="l">Picks locked this week</span><span class="s">${g.length-locked?`${g.filter(x=>x.status==='provisional').length} still provisional`:'nothing left to lock'}</span></div>`;
const pg=Math.min(100,D.graded/D.claim_at*100);
$('ev-a').textContent=`${D.graded} of ${D.claim_at} graded games before any claim of skill`;
$('ev-b').textContent=`±${Math.round(50/Math.sqrt(Math.max(D.graded,1)))} pts standard error at ${D.graded} games`;
$('ev-i').style.width=pg+'%';
$('ev-m').setAttribute('aria-label',`${D.graded} of ${D.claim_at} games graded`);
(function(){
  const T=D.season_tab||[];if(!T.length)return;
  const M=D.season_models;$('season-panel').hidden=false;
  const cell=r=>r&&(r[0]+r[1])?`${r[0]}–${r[1]}`:'—';
  const sum=rows=>Object.fromEntries(M.map(([k])=>[k,rows.reduce((a,w)=>[a[0]+w.rec[k][0],a[1]+w.rec[k][1]],[0,0])]));
  const live=T.filter(w=>w.kind==='live');
  const row=(lab,rec,cls)=>`<tr${cls?` class="${cls}"`:''}><td>${lab}</td>${M.map(([k])=>`<td class="n">${cell(rec[k])}</td>`).join('')}</tr>`;
  $('season-tab').innerHTML=`<thead><tr><th>Week</th>${M.map(([,l])=>`<th class="n">${esc(l)}</th>`).join('')}</tr></thead><tbody>`
    +T.map(w=>row(`Week ${w.week}${w.kind==='backtest'?' <span class="m hook">backtest</span>':''}`,w.rec)).join('')
    +(live.length?row('Live total',sum(live),'med'):'')+row('Season incl. backtest',sum(T),'med')+'</tbody>';
  $('season-note').textContent=T.some(w=>w.kind==='backtest')?'Weeks marked backtest were not picked live: each model re-run as it would have been at lock, on the real pool lines from the Picks history, with the closing line as the market. Only live weeks count toward the official record.':'';
})();
(function(){
  const T=D.su||[];if(!T.length)return;
  $('su-panel').hidden=false;
  const M=[['market','Market favorite'],['v3','Player projection'],['v1','Team-only projection']];
  const cell=r=>r&&(r[0]+r[1])?`${r[0]}–${r[1]} <span class="sub">${Math.round(r[0]/(r[0]+r[1])*100)}%</span>`:'—';
  const tag=k=>k==='backtest'?' <span class="m hook">backtest</span>':k==='mixed'?' <span class="m hook">incl. backtest</span>':'';
  const tot=Object.fromEntries(M.map(([k])=>[k,T.reduce((a,w)=>[a[0]+w.rec[k][0],a[1]+w.rec[k][1]],[0,0])]));
  const exp=T.reduce((a,w)=>a+w.expected,0);
  const row=(lab,rec,e,cls)=>`<tr${cls?` class="${cls}"`:''}><td>${lab}</td>${M.map(([k])=>`<td class="n">${cell(rec[k])}</td>`).join('')}<td class="n">${e.toFixed(1)}</td></tr>`;
  $('su-tab').innerHTML=`<thead><tr><th>Week</th>${M.map(([,l])=>`<th class="n">${esc(l)}</th>`).join('')}<th class="n">Market expected wins</th></tr></thead><tbody>`
    +T.map(w=>row(`Week ${w.week}${tag(w.kind)}`,w.rec,w.expected)).join('')+row('Season',tot,exp,'med')+'</tbody>';
  $('su-note').textContent='Tracked only; never changes the pick. The market favorite at lock wins about 66% of games over time (2010–2025). Beating the expected wins column over a season, not one week, is what would count. Backtest rows use the closing line and projections rebuilt as of each week.';
})();
const half=x=>{const w=Math.floor(x),f=x-w;return f===0.5?(w?w+'½':'½'):num(x,1)};

function team(x,side,picked){
  const code=side==='a'?x.away:x.home, sp=x.line==null?null:(side==='a'?-x.line:x.line);
  const sc=side==='a'?x.as:x.hs;
  return `<div class="team${picked?' picked':''}"><span class="code">${esc(code)}</span><span class="tag">${picked?'Pick':''}</span><span class="sp">${sgn(sp)}</span><span class="sc">${sc==null?'':sc}</span></div>`;
}
function track(x){
  if(x.drift==null)return `<div class="track nodata" role="img" aria-label="No market data yet"><span class="base"></span></div>`;
  const R=2.5,pos=Math.max(0,Math.min(100,(x.drift+R)/(2*R)*100)),lo=Math.min(50,pos),wd=Math.abs(pos-50);
  const ticks=[-2,-1,1,2].map(t=>`<span class="tk" style="left:${(t+R)/(2*R)*100}%"></span>`).join('');
  const toward=x.drift===0?'no move':`${pts(Math.abs(x.drift))} toward ${x.drift<0?x.home:x.away}`;
  const lbl=`Pool line ${x.home} ${sgn(x.line)}, market ${x.market==null?'unknown':sgn(x.market)}: ${toward}`;
  return `<div class="track" role="img" aria-label="${esc(lbl)}" title="${esc(lbl)}"><span class="base"></span>${ticks}<span class="seg" style="left:${lo}%;width:${wd}%"></span><span class="pool"></span><span class="dot" style="left:${pos}%"></span><span class="end l">${esc(x.home)}</span><span class="end r">${esc(x.away)}</span></div>`;
}
function move(x){
  if(x.drift==null&&x.status==='started_no_final_pick')return '<div class="cover">No pick was recorded before kickoff.</div>';
  if(x.drift==null)return `<div class="move"><div class="move-top"><span class="chip none">No market data</span></div>${track(x)}</div>`;
  const txt=x.drift===0?`${esc(x.home)} ${sgn(x.line)}, unchanged`:`${esc(x.home)} ${sgn(x.line)} → ${sgn(x.market)} · toward ${esc(x.drift<0?x.home:x.away)}`;
  return `<div class="move"><div class="move-top"><span class="chip ${x.sig}">${esc(x.sig_label)}</span><span class="mono">${txt}</span></div>${track(x)}</div>`;
}
function meter(x){
  if(x.pick_p==null)return '';
  const p=x.pick_p*100,lo=45,hi=60,mid=(50-lo)/(hi-lo)*100,w=Math.max(0,Math.min(hi,p)-50)/(hi-lo)*100;
  return `<div class="pick-meter"><span class="lab">Cover chance · ${esc(x.pick)}</span><span class="pct">${p.toFixed(1)}%</span><div class="gauge" role="img" aria-label="${p.toFixed(1)}% on a 45 to 60% scale"><b></b><i style="left:${mid}%;width:${w}%"></i></div></div>`;
}
function proj(x){
  if(x.ph==null)return '';
  const label=x.pver&&x.pver!=='proj-players-v3'?'Team-only projection':'Player projection';
  const differs=x.ppick&&x.pick&&x.ppick!==x.pick;
  const pend=(x.pflags||'').includes('INJ_STATUS_MISSING');
  const r=x.pres==='W'?'<span class="ok">✓ covered</span>':x.pres==='L'?'<span class="no">✕ missed</span>':'';
  return `<div class="proj"><span class="lab">${label}</span><span class="mono">${esc(x.away)} ${Number(x.pa).toFixed(1)} – ${esc(x.home)} ${Number(x.ph).toFixed(1)}</span><span>picks ${esc(x.ppick||'—')}</span>${differs?'<span class="diff">differs</span>':''}${pend?'<span class="diff">injury report pending</span>':''}${r}</div>`;
}
function hyb(x){
  if(x.hysrc!=='v1'||!x.hy)return '';
  const d=x.hy!==x.pick;
  const r=x.hres==='W'?'<span class="ok">✓</span>':x.hres==='L'?'<span class="no">✕</span>':'';
  return `<div class="proj"><span class="lab">Hybrid (tracked, not the pick)</span><span>Small move, so it uses the team-only projection: <b class="mono">${esc(x.hy)}</b></span>${d?'<span class="diff">differs</span>':''}${r}</div>`;
}
function stateBadge(x){
  if(x.res==='W')return '<span class="pill won">✓ Won</span>';
  if(x.res==='L')return '<span class="pill lost">✕ Lost</span>';
  if(x.status==='final')return `<span class="pill locked">Locked${x.at?' '+esc(x.at):''}</span>`;
  if(x.status==='provisional')return `<span class="pill prov">Provisional</span>`;
  return '<span class="pill none">No pick recorded</span>';
}
function foot(x){
  const bits=[];
  if(x.hs!=null&&x.line!=null){
    const m=(x.hs-x.as)+x.line;
    bits.push(m===0?'Landed on the pool line':`${esc(m>0?x.home:x.away)} covered the pool line by ${half(Math.abs(m))}`);
  }
  if(x.status==='final'&&x.lead!=null)bits.push(`picked ${x.at} ET, ${x.lead} min before kickoff`);
  else if(x.status==='provisional')bits.push(`snapshot ${x.at||'—'} ET · picks at ${x.pick_at} ET`);
  return bits.length?`<div class="cover">${bits.join(' · ')}</div>`:'';
}

/* ---- how the projected score was built ---- */
const SMALL=0.25;
const sg1=(v,d=1)=>(v>0.049?'+':v<-0.049?'−':'')+Math.abs(v).toFixed(d);
const XNOTE={off:'scoring over recent games',def:'scoring allowed over recent games',home:'playing at home',other:'roof, division game, model calibration'};
const XLAB={other:'Everything else',qb:'Starting quarterback',own_inj:'Injuries',opp_inj:"Opponent's injuries",sched:'Rest and travel'};
const isInj=k=>k==='own_inj'||k==='opp_inj';
const pending=x=>(x.pflags||'').includes('INJ_STATUS_MISSING');
function xItems(x,side){
  const t=x.xp[side],team=side==='home'?x.home:x.away,opp=side==='home'?x.away:x.home;
  return t.items.filter(i=>!(pending(x)&&isInj(i.key))).map(i=>({...i,
    label:i.key==='off'?`${team} offense`:i.key==='def'?`${opp} defense`:(XLAB[i.key]||i.label),note:i.note||XNOTE[i.key]||''}));
}
function xBlock(x,side,scale){
  const t=x.xp[side],team=side==='home'?x.home:x.away,all=xItems(x,side);
  const shown=all.filter(i=>Math.abs(i.pts)>=SMALL).sort((a,b)=>Math.abs(b.pts)-Math.abs(a.pts));
  const quiet=all.filter(i=>Math.abs(i.pts)<SMALL);
  const row=i=>{const w=Math.min(50,Math.abs(i.pts)/scale*50);
    return `<div class="br"><div class="name"><b>${esc(i.label)}</b><small>${esc(i.note)}</small></div>
      <div class="track2" role="img" aria-label="${esc(i.label)} ${sg1(i.pts)} points"><i class="${i.pts>=0?'up':'dn'}" style="width:${w}%"></i></div>
      <div class="val">${sg1(i.pts)}</div></div>`};
  const q=quiet.length?`<div class="none"><b>Small effects, under ¼ point each:</b> ${quiet.map(i=>`${esc(i.label.toLowerCase())} ${sg1(i.pts)}`).join(' · ')}</div>`:'';
  return `<div class="tb"><div class="tb-h"><span class="code">${esc(team)}</span><span class="tot">${t.total.toFixed(1)}</span><span class="from">starts at ${t.baseline.toFixed(1)} · league-average team</span></div>
    <div class="axis-row"><span>Factor</span><span class="mid"><span>◂ subtracts</span><span>adds ▸</span></span><span style="text-align:right">Points</span></div>
    ${shown.map(row).join('')}${q}
    <div class="sum"><b>${t.baseline.toFixed(1)}</b> start <b>${sg1(t.total-t.baseline)}</b> net <b>= ${t.total.toFixed(1)}</b> projected points</div></div>`;
}
const xScale=x=>Math.ceil(Math.max(...['home','away'].flatMap(s=>xItems(x,s).map(i=>Math.abs(i.pts))),1.5));
function xDrivers(x){
  if(!x.xp)return '';
  const line=s=>{const team=s==='home'?x.home:x.away;
    const top=xItems(x,s).filter(i=>Math.abs(i.pts)>=SMALL).sort((p,q)=>Math.abs(q.pts)-Math.abs(p.pts)).slice(0,2)
      .map(i=>`${esc(i.key==='qb'?'QB':i.key==='home'?'home field':i.label)} <b>${sg1(i.pts)}</b>`).join(' · ');
    return `<span class="dt"><b>${esc(team)} ${x.xp[s].total.toFixed(1)}</b></span><span>${top||'no single big driver'}</span>`};
  return `<div class="drivers"><span class="lab">Biggest drivers</span>${line('away')}${line('home')}</div>`;
}
const openX=new Set();
function xExpand(x){
  if(!x.xp)return '';
  const o=openX.has(x.id),sc=xScale(x);
  return `<button class="xbtn" data-x="${esc(x.id)}" aria-expanded="${o}" aria-controls="xp-${esc(x.id)}"><span>How each score was built</span><span aria-hidden="true">${o?'▴':'▾'}</span></button>
    <div class="xp" id="xp-${esc(x.id)}"${o?'':' hidden'}>${xBlock(x,'away',sc)}${xBlock(x,'home',sc)}
    <p class="sub" style="font-size:12px">Each team starts at what an average team scores; bars add or subtract from that and sum to the projected score.</p>
    <button class="xclose" data-x="${esc(x.id)}">Close ✕</button></div>`;
}
function xPanel(x){
  if(!x.xp)return '';
  const margin=x.ph-x.pa,sc=xScale(x);
  const takes=x.ppick&&x.line!=null?`<span>So the projection takes <b>${esc(x.ppick)}</b> against the pool line (${esc(x.home)} ${sgn(x.line)})</span>`:'';
  return `<section class="panel"><h3>How the projected score was built</h3>
    <div class="build-top"><span>Projected <b>${esc(x.away)} ${Number(x.pa).toFixed(1)} – ${esc(x.home)} ${Number(x.ph).toFixed(1)}</b></span><span>${esc(margin>=0?x.home:x.away)} by ${Math.abs(margin).toFixed(1)}</span>${takes}</div>
    ${pending(x)?'<div class="pend"><b>Injuries are not counted yet.</b> Official statuses come out Wednesday to Friday, and this projection will update then.</div>':''}
    <p class="sub">Each team starts from what an average team scores against an average defense at a neutral site. Every bar adds or subtracts from that, and the pieces add up to the projected score (to the nearest tenth).</p>
    <div class="teams2">${xBlock(x,'away',sc)}${xBlock(x,'home',sc)}</div></section>`;
}
function card(x){
  const pa=x.pick===x.away,ph=x.pick===x.home;
  return `<article class="card" data-id="${esc(x.id)}"><div class="card-h"><span class="ko">${esc(x.ko)}</span>${stateBadge(x)}</div>
    <div class="teams">${team(x,'a',pa)}${team(x,'h',ph)}</div>${move(x)}${meter(x)}${proj(x)}${hyb(x)}${xDrivers(x)}${xExpand(x)}${foot(x)}<button class="more" data-id="${esc(x.id)}">Book-by-book lines ›</button></article>`;
}
const cols=n=>n===4||n===10?2:3;      // fill the rows: 4 games make 2x2, not 3+1
const pred={all:()=>true,strong:x=>x.sig==='strong',differs:x=>x.ppick&&x.pick&&x.ppick!==x.pick,hybrid:x=>x.hysrc==='v1'&&x.hy&&x.pick&&x.hy!==x.pick};
function draw(k){
  const out=D.slots.map((s,i)=>{
    const gs=g.filter(x=>x.slot===i&&pred[k](x));
    if(!gs.length)return '';
    const all=g.filter(x=>x.slot===i),prov=all.filter(x=>x.status==='provisional').length,played=all.every(x=>x.hs!=null);
    const st=played?'Final':prov?`${prov} provisional`:'All picks locked';
    return `<section class="slot"><div class="slot-h"><h2>${esc(s.day)}<small>${esc(s.times)} ET</small></h2><span class="st">${all.length} game${all.length>1?'s':''} · ${st}</span></div><div class="grid" style="--cols:${cols(gs.length)}">${gs.map(card).join('')}</div></section>`;
  }).join('');
  $('slots').innerHTML=out||'<p class="empty">No games match this filter.</p>';
}
function setF(k){for(const n of ['all','strong','differs','hybrid'])$('f-'+n).setAttribute('aria-pressed',n===k);draw(k)}
for(const n of ['all','strong','differs','hybrid'])$('f-'+n).onclick=()=>setF(n);
draw('all');
/* ---- game view ---- */
const byId=Object.fromEntries(g.map(x=>[x.id,x]));
const BOOKS={draftkings:'DraftKings',fanduel:'FanDuel',betmgm:'BetMGM',caesars:'Caesars',pinnacle:'Pinnacle',bet365:'bet365',betrivers:'BetRivers',hardrock:'Hard Rock',bovada:'Bovada',betonline:'BetOnline',fanatics:'Fanatics',prophetx:'ProphetX',novig:'Novig',fliff:'Fliff',parx:'Parx'};
const bk=b=>BOOKS[b]||b.charAt(0).toUpperCase()+b.slice(1);
const ET='America/New_York';
const etTime=ms=>new Date(ms).toLocaleString('en-US',{timeZone:ET,weekday:'short',hour:'numeric',minute:'2-digit'});
const etDay=ms=>new Date(ms).toLocaleString('en-US',{timeZone:ET,weekday:'short',month:'numeric',day:'numeric'});
const med=a=>{const s=[...a].sort((p,q)=>p-q),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2};
const diff=v=>Math.abs(v)<1e-9?'same':(v>0?'+':'−')+num(Math.abs(v),2);
function snaps(d){
  return d.t.map((t,i)=>{const v=Object.values(d.b).map(a=>a[i]).filter(z=>z!=null);
    return {ms:Date.parse(t),n:v.length,lo:Math.min(...v),hi:Math.max(...v),med:med(v)}});
}
function chart(x,d,W){
  const S=snaps(d),n=S.length,ko=Date.parse(x.ko_iso),pool=x.line;
  const H=W<520?240:300,m={l:50,r:14,t:14,b:32},pw=W-m.l-m.r,ph=H-m.t-m.b;
  const all=S.flatMap(s=>[s.lo,s.hi]).concat(pool==null?[]:[pool]);
  let lo=Math.min(...all)-0.5,hi=Math.max(...all)+0.5;
  if(hi-lo<3){const c=(hi+lo)/2;lo=c-1.5;hi=c+1.5}
  const step=hi-lo>6?1:0.5,t0=n>1?S[0].ms:S[0].ms-36e5,t1=Math.max(ko,S[n-1].ms+6e4);
  const X=ms=>m.l+(ms-t0)/(t1-t0)*pw,Y=v=>m.t+(v-lo)/(hi-lo)*ph;
  let o='';
  for(let v=Math.ceil(lo/step)*step;v<=hi+1e-9;v+=step)o+=`<line class="c-grid" x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${m.l-8}" y="${Y(v)+4}" text-anchor="end">${sgn(v)}</text>`;
  // day ticks at midnight ET
  const parts=new Intl.DateTimeFormat('en-US',{timeZone:ET,hour12:false,hour:'numeric',minute:'numeric',second:'numeric'}).formatToParts(new Date(t0)).reduce((a,p)=>(a[p.type]=+p.value,a),{});
  let tk=t0+(((24-(parts.hour%24))*60-parts.minute)*60-parts.second)*1000,last=-99;
  for(;tk<t1;tk+=864e5){const px=X(tk);if(px-last>70&&px<W-m.r-130&&px>m.l+20){o+=`<line class="c-grid" x1="${px}" x2="${px}" y1="${H-m.b}" y2="${H-m.b+5}"/><text x="${px}" y="${H-m.b+18}" text-anchor="middle">${esc(etDay(tk+36e5))}</text>`;last=px}}
  o+=`<text x="${W-m.r}" y="${H-m.b+18}" text-anchor="end">Kickoff ${esc(x.ko.replace(/^\w+ /,''))}</text>`;
  if(n>1)o+=`<polygon class="c-band" points="${S.map(s=>X(s.ms)+','+Y(s.lo)).join(' ')} ${[...S].reverse().map(s=>X(s.ms)+','+Y(s.hi)).join(' ')}"/>`;
  else o+=`<line class="c-med" style="stroke-width:8;opacity:.18" x1="${X(S[0].ms)}" x2="${X(S[0].ms)}" y1="${Y(S[0].lo)}" y2="${Y(S[0].hi)}"/>`;
  if(pool!=null)o+=`<line class="c-pool" x1="${m.l}" x2="${W-m.r}" y1="${Y(pool)}" y2="${Y(pool)}"/><text class="c-poollab" x="${W-m.r}" y="${Y(pool)-6}" text-anchor="end">Pool line ${sgn(pool)}</text>`;
  if(n>1)o+=`<polyline class="c-med" points="${S.map(s=>X(s.ms)+','+Y(s.med)).join(' ')}"/>`;
  const li=d.lock?d.lock.i:-1;
  S.forEach((s,i)=>{if(i!==li)o+=`<circle class="c-pt" cx="${X(s.ms)}" cy="${Y(s.med)}" r="4"/>`});
  if(li>=0)o+=`<circle class="c-lock" cx="${X(S[li].ms)}" cy="${Y(S[li].med)}" r="7"/>`;
  o+=`<line class="c-cross" id="xh" x1="0" x2="0" y1="${m.t}" y2="${H-m.b}" hidden/>`;
  const lbl=`Line movement for ${x.away} at ${x.home}: ${n} captures, median ${sgn(S[0].med)} to ${sgn(S[n-1].med)}`;
  return {svg:`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" tabindex="0" aria-label="${esc(lbl)}">${o}</svg>`,S,X,Y,m,H};
}
function drawChart(x,d){
  const box=$('chart');if(!box)return;
  const W=Math.max(280,Math.floor(box.clientWidth||320)),c=chart(x,d,W);
  box.innerHTML=c.svg+'<div class="tip" id="tip" hidden></div>';
  const svg=box.querySelector('svg'),tip=$('tip'),xh=$('xh');
  const show=i=>{const s=c.S[i],px=c.X(s.ms);xh.removeAttribute('hidden');xh.setAttribute('x1',px);xh.setAttribute('x2',px);
    const dv=x.line==null?'':` · ${diff(s.med-x.line)} vs pool`;
    tip.innerHTML=`<b>${esc(etTime(s.ms))} ET</b><br>Median ${sgn(s.med)}${dv}<br>Range ${sgn(s.lo)} to ${sgn(s.hi)} · ${s.n} books`;
    tip.hidden=false;const tw=tip.offsetWidth;tip.style.left=Math.max(0,Math.min(W-tw,px-tw/2))+'px'};
  const hide=()=>{tip.hidden=true;xh.setAttribute('hidden','')};
  svg.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect(),px=(e.clientX-r.left)*(W/r.width);
    let b=0,bd=1e9;c.S.forEach((s,i)=>{const dd=Math.abs(c.X(s.ms)-px);if(dd<bd){bd=dd;b=i}});show(b)});
  svg.addEventListener('pointerleave',hide);svg.addEventListener('blur',hide);
  let k=c.S.length-1;svg.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'){k=Math.max(0,k-1);show(k);e.preventDefault()}
    else if(e.key==='ArrowRight'){k=Math.min(c.S.length-1,k+1);show(k);e.preventDefault()}else if(e.key==='Escape')hide()});
}
function booksTable(x,d){
  if(!d.lock)return '<p class="sub">No book lines were captured for this game yet.</p>';
  const L=d.lock,tue=d.tue;
  const tueNote=tue?(()=>{const v=Object.values(tue.books),same=v.filter(b=>b.m==='same').length,hook=v.filter(b=>b.m==='hook').length;
    return `<p class="sub">Tuesday posting window (${esc(tue.at)}): ${same} of ${v.length} books had exactly the pool line, ${hook} were a half point away.</p>`})():'';
  const rows=L.books.map(b=>{const t=tue&&tue.books[b.book];
    return `<tr><td>${esc(bk(b.book))}</td><td class="n">${sgn(b.spread)}</td><td class="n">${x.line==null?'—':diff(b.spread-x.line)}</td><td class="n">${diff(b.spread-L.median)}</td><td class="n">${esc(b.price)||'—'}</td><td class="n">${esc(b.upd)||'—'}</td>${tue?`<td class="n">${t?sgn(t.line)+`<span class="m ${t.m}">${t.m==='same'?'= pool':t.m==='hook'?'hook':'differs'}</span>`:'—'}</td>`:''}</tr>`}).join('');
  return `${tueNote}<div class="tbl"><table><thead><tr><th>Book</th><th class="n">${esc(x.home)} spread</th><th class="n">vs pool</th><th class="n">vs median</th><th class="n">Price</th><th class="n">Updated</th>${tue?'<th class="n">Tuesday</th>':''}</tr></thead><tbody>
    <tr class="med"><td>Median (model input)</td><td class="n">${sgn(L.median)}</td><td class="n">${x.line==null?'—':diff(L.median-x.line)}</td><td class="n">—</td><td class="n">—</td><td class="n">${L.n} books</td>${tue?'<td class="n"></td>':''}</tr>${rows}</tbody></table></div>`;
}
function inputsPanel(x,d){
  const I=d.inputs;
  if(!I)return `<p class="sub">Projection inputs are recorded when a pick locks. This game has not locked yet.</p>`;
  const side=(code,s,opp)=>`<div><h4 class="kv-h">${esc(code)}</h4><dl class="kv">
    <dt>Starting QB</dt><dd>${esc(s.starter_name||'—')}${s.qb1_out?' (QB1 out)':''}</dd>
    <dt>QB vs team norm</dt><dd>${s.qb_delta==null?'—':(s.qb_delta>0?'+':s.qb_delta<0?'−':'')+Math.abs(s.qb_delta).toFixed(3)} EPA/dropback</dd>
    <dt>Depth chart read</dt><dd>${s.depth_snapshot?esc(etTime(Date.parse(s.depth_snapshot)))+' ET':'—'}</dd>
    <dt>Injury rows</dt><dd>${s.injury_rows??'—'}</dd>
    <dt>Missing OL / skill</dt><dd>${s.ol??'—'} / ${s.skill??'—'}</dd>
    <dt>Missing opp DL / LB / DB</dt><dd>${s.opp_dl??'—'} / ${s.opp_lb??'—'} / ${s.opp_db??'—'}</dd>
    <dt>Rest vs opponent</dt><dd>${s.rest_diff>0?'+':''}${s.rest_diff??'—'} days</dd>
    <dt>Time zones travelled</dt><dd>${s.tz_shift??'—'}</dd>
    <dt>Roof</dt><dd>${s.dome?'dome / closed':'open air'}${s.dome_estimated?' (estimated)':''}</dd></dl></div>`;
  const fl=(I.flags||[]).length?`<p class="sub">Flags: ${I.flags.map(esc).join(', ')}</p>`:'';
  return `<div class="cols2">${side(x.away,I.away)}${side(x.home,I.home)}</div>${fl}
    <p class="sub">It rates the depth-chart starter. If that player is also out, or the starter changes after the report, the projection does not know.</p>`;
}
function snapTable(d){
  const S=snaps(d);if(!S.length)return '';
  return `<details><summary>Captures as a table</summary><div class="tbl"><table><thead><tr><th>Time (ET)</th><th class="n">Books</th><th class="n">Low</th><th class="n">Median</th><th class="n">High</th></tr></thead><tbody>${S.map(s=>`<tr><td>${esc(etTime(s.ms))}</td><td class="n">${s.n}</td><td class="n">${sgn(s.lo)}</td><td class="n">${sgn(s.med)}</td><td class="n">${sgn(s.hi)}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function detailHTML(x){
  const d=(D.details||{})[x.id]||{};
  const slot=D.slots[x.slot];
  const res=x.hs!=null?`<span>Final <b>${esc(x.away)} ${x.as} – ${esc(x.home)} ${x.hs}</b></span>`:'';
  const pick=x.pick?`<span>Pick <b>${esc(x.pick)}</b>${x.pick_p!=null?` · ${(x.pick_p*100).toFixed(1)}% to cover`:''}</span>`:'';
  const has=d.t&&d.t.length;
  return `<button class="back" id="back">← Week ${D.week}</button>
  <section class="d-title"><div class="ko">${esc(x.ko)} ET · ${esc(slot.day)} ${esc(slot.times)}</div>
    <div class="d-match"><span>${esc(x.away)}</span><span class="at">@</span><span>${esc(x.home)}</span></div>
    <div class="d-facts">${stateBadge(x)}${x.line!=null?`<span>Pool line <b>${esc(x.home)} ${sgn(x.line)}</b></span>`:''}${pick}${res}${d.total!=null?`<span>Total <b>${d.total}</b></span>`:''}</div></section>
  ${d.why&&d.why.length?`<section class="panel"><h3>Why this pick</h3><ul>${d.why.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></section>`:''}
  ${xPanel(x)}
  <section class="panel"><h3>Line movement</h3>
    <p class="sub">Spread on ${esc(x.home)} across every book. Higher on the chart means the market favors ${esc(x.home)} more; lower favors ${esc(x.away)} more.</p>
    ${has?`<div class="key"><span><i class="k-line"></i>Median of books</span><span><i class="k-band"></i>Range across books</span><span><i class="k-dash"></i>Pool line</span><span><i class="k-mkt"></i>${x.status==='final'?'Pick captured':'Latest capture'}</span></div><div class="chart" id="chart"></div>${snapTable(d)}`:'<p class="sub">No book lines were captured for this game yet.</p>'}
  </section>
  <section class="panel"><h3>Every book${d.lock?` at ${esc(d.lock.at)} ET`:''}${d.lock&&x.status!=='final'?' · latest':''}</h3>${booksTable(x,d)}</section>
  <section class="panel"><h3>What the projection used</h3>${inputsPanel(x,d)}</section>`;
}
let saved=0,ro=null;
function showGame(id){
  const x=byId[id];if(!x)return false;
  saved=window.scrollY;$('board').hidden=true;const el=$('detail');el.hidden=false;el.innerHTML=detailHTML(x);
  const d=(D.details||{})[id]||{};
  if(d.t&&d.t.length){drawChart(x,d);if(window.ResizeObserver){let w=0;ro&&ro.disconnect();ro=new ResizeObserver(es=>{const nw=Math.round(es[0].contentRect.width);if(nw&&nw!==w){w=nw;drawChart(x,d)}});ro.observe($('chart'))}}
  $('back').onclick=()=>{try{history.replaceState(null,'',location.pathname+location.search)}catch(e){}showBoard()};
  window.scrollTo(0,0);$('back').focus();return true;
}
function showBoard(){
  ro&&ro.disconnect();$('detail').hidden=true;$('detail').innerHTML='';$('board').hidden=false;window.scrollTo(0,saved);
}
function open(id){try{location.hash=id}catch(e){}showGame(id)}
$('slots').addEventListener('click',e=>{
  const b=e.target.closest('.xbtn,.xclose');
  if(b){const id=b.dataset.x,card=b.closest('.card'),want=b.classList.contains('xclose')?false:!openX.has(id);
    want?openX.add(id):openX.delete(id);
    const box=card.querySelector('.xp'),btn=card.querySelector('.xbtn');
    box.hidden=!want;btn.setAttribute('aria-expanded',want);btn.lastElementChild.textContent=want?'▴':'▾';
    if(!want)btn.focus();return}
  if(e.target.closest('.xp'))return;
  const c=e.target.closest('.card');if(c)open(c.dataset.id)});
function route(){const id=(location.hash||'').slice(1);if(id&&byId[id])showGame(id);else if(!$('detail').hidden)showBoard()}
window.addEventListener('hashchange',route);route();
</script>
"""
