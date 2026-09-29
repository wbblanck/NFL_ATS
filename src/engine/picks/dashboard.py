"""Static dashboard (HTML) of a week's picks + the live record. Regenerated on demand;
it is a snapshot, not a live page. Games are grouped into kickoff slots, each card shows the pool line, the
market's move off it, the pick with its cover chance, the tracked projection, and (once played) the result."""
from __future__ import annotations

import datetime as dt
import html
import json
from zoneinfo import ZoneInfo

from engine.data import store
from engine.picks import final

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
           results: dict | None = None) -> str:
    """results: game_id -> graded row from live.compute (result, proj_<version> strings); optional."""
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
        games.append({"id": r["game_id"], "away": r["away"], "home": r["home"], "ko": ko.astimezone(ET).strftime("%a %-I:%M %p"),
                      "slot": slot_of[r["game_id"]], "line": r["league_line"],
                      "market": r["market"] if r["market"] not in ("", None) else None,
                      "drift": float(r["drift"]) if r["drift"] not in ("", None, "UNAVAILABLE") else None,
                      "pick": r.get("pick"), "pick_p": pick_p, "status": r["status"], "sig": sig_k, "sig_label": sig_l,
                      "books": r.get("market_books"), "at": None if mt is None else _clock(mt), "lead": lead,
                      "pick_at": _clock(pick_at), "ph": r.get("proj_home"), "pa": r.get("proj_away"),
                      "ppick": r.get("proj_pick"), "pver": r.get("proj_version"), "pflags": r.get("proj_flags"),
                      "hs": r.get("home_score"), "as": r.get("away_score"), "res": g.get("result"), "pres": pres})
    models = [{"label": "Official pick", "W": live.get("W", 0), "L": live.get("L", 0)}]
    for label, v in (("Team-only projection", V1), ("Player projection", V3)):
        m = (live.get("projection_models") or {}).get(v)
        if m:
            models.append({"label": label, "W": m["W"], "L": m["L"]})
    nxt = min(upcoming) if upcoming else None
    data = json.dumps({"games": games, "slots": slots, "season": season, "week": week, "record": rec, "models": models,
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
--flag:#ffc800;--flag-soft:#fff0b8;--on-flag:#0f1a2b;--flat-bg:#e4e8ef;
--win:#146c36;--win-bg:#e2f4e8;--loss:#b3261e;--loss-bg:#fde7e5;
--display:"Big Shoulders Display","Arial Narrow",Impact,sans-serif;--body:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#0a111f;--panel:#111a2c;--panel-2:#16213a;--ink:#e8edf7;--ink-2:#b3bfd4;--ink-3:#8e9bb4;--rule:#243250;--flag-soft:#4a3c08;--flat-bg:#1c2740;--win:#63d68d;--win-bg:#123322;--loss:#ff8f86;--loss-bg:#40181a}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#0a111f;--panel:#111a2c;--panel-2:#16213a;--ink:#e8edf7;--ink-2:#b3bfd4;--ink-3:#8e9bb4;--rule:#243250;--flag-soft:#4a3c08;--flat-bg:#1c2740;--win:#63d68d;--win-bg:#123322;--loss:#ff8f86;--loss-bg:#40181a}
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

/* notes */
details{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:14px 18px}
summary{cursor:pointer;font:600 14px var(--body)}
details div{display:flex;flex-direction:column;gap:10px;margin-top:12px;font-size:13px;color:var(--ink-2);max-width:78ch}
details p{margin:0}
@media (prefers-reduced-motion:no-preference){.meter i,.gauge i{transition:width .3s}}
</style>
<div class="wrap">
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
  <section class="controls">
    <div class="filters" role="group" aria-label="Filter games">
      <button id="f-all" aria-pressed="true">All games</button>
      <button id="f-strong" aria-pressed="false">Moved 1+ pt</button>
      <button id="f-differs" aria-pressed="false">Projection disagrees</button>
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
    </div>
  </details>
</div>
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
$('meta').textContent=`${D.season} regular season · snapshot ${D.updated}`;
if(D.next_lock){$('next').hidden=false;$('next-t').textContent=`Next pick locks ${D.next_lock.at} ET · ${D.next_lock.game}`}
const g=D.games, locked=g.filter(x=>x.status==='final').length;
$('records').innerHTML=D.models.map(m=>{const p=pct(m.W,m.L);
  return `<div class="rec"><span class="v">${m.W}–${m.L}</span><span class="l">${esc(m.label)}</span><span class="s">${p?`${p[0]}% ± ${p[1]} · vs pool line`:'no games graded yet'}</span></div>`}).join('')
  +`<div class="rec"><span class="v">${locked}/${g.length}</span><span class="l">Picks locked this week</span><span class="s">${g.length-locked?`${g.filter(x=>x.status==='provisional').length} still provisional`:'nothing left to lock'}</span></div>`;
const pg=Math.min(100,D.graded/D.claim_at*100);
$('ev-a').textContent=`${D.graded} of ${D.claim_at} graded games before any claim of skill`;
$('ev-b').textContent=`±${Math.round(50/Math.sqrt(Math.max(D.graded,1)))} pts standard error at ${D.graded} games`;
$('ev-i').style.width=pg+'%';
$('ev-m').setAttribute('aria-label',`${D.graded} of ${D.claim_at} games graded`);
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
function card(x){
  const pa=x.pick===x.away,ph=x.pick===x.home;
  return `<article class="card"><div class="card-h"><span class="ko">${esc(x.ko)}</span>${stateBadge(x)}</div>
    <div class="teams">${team(x,'a',pa)}${team(x,'h',ph)}</div>${move(x)}${meter(x)}${proj(x)}${foot(x)}</article>`;
}
const cols=n=>n===4||n===10?2:3;      // fill the rows: 4 games make 2x2, not 3+1
const pred={all:()=>true,strong:x=>x.sig==='strong',differs:x=>x.ppick&&x.pick&&x.ppick!==x.pick};
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
function setF(k){for(const n of ['all','strong','differs'])$('f-'+n).setAttribute('aria-pressed',n===k);draw(k)}
for(const n of ['all','strong','differs'])$('f-'+n).onclick=()=>setF(n);
draw('all');
</script>
"""
