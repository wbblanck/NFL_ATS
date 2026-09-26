"""Static dashboard (HTML) of a week's picks + the live record. Regenerated on demand;
it is a snapshot, not a live page."""
from __future__ import annotations

import datetime as dt
import html
import json
from zoneinfo import ZoneInfo

from engine.data import store
from engine.picks import final

ET = ZoneInfo("America/New_York")


def _signal(drift):
    if drift in (None, "", "UNAVAILABLE"):
        return ("none", "No data")
    a = abs(float(drift))
    return ("strong", "Moved 1+ pt") if a >= 1 else (("lean", "Moved ½ pt") if a > 0 else ("flat", "No move"))


def render(rows: list[dict], season: int, week: int, live: dict, updated: dt.datetime) -> str:
    rec = f"{live['W']}-{live['L']}" if live.get("N") else "0-0"
    games = []
    for r in rows:
        ko = dt.datetime.fromisoformat(r["kickoff_utc"]).astimezone(ET)
        sig_k, sig_l = _signal(r["drift"])
        ph, pa = r.get("p_home"), r.get("p_away")
        pick_p = None
        if ph not in (None, "", "UNAVAILABLE") and r.get("pick"):
            pick_p = float(ph) if r["pick"] == r["home"] else float(pa)
        games.append({"away": r["away"], "home": r["home"], "ko": ko.strftime("%a %-I:%M %p"),
                      "line": r["league_line"], "market": r["market"] if r["market"] not in ("", None) else None,
                      "drift": r["drift"] if r["drift"] not in ("", None) else None, "pick": r.get("pick"),
                      "pick_p": pick_p, "status": r["status"], "sig": sig_k, "sig_label": sig_l,
                      "books": r.get("market_books"), "mtime": (r.get("market_time") or "")[:16],
                      "ph": r.get("proj_home"), "pa": r.get("proj_away"), "ppick": r.get("proj_pick"),
                      "pver": r.get("proj_version"), "pflags": r.get("proj_flags")})
    data = json.dumps({"games": games, "season": season, "week": week, "record": rec, "live": live,
                       "updated": updated.astimezone(ET).strftime("%a %b %-d, %-I:%M %p ET")})
    return TEMPLATE.replace("__DATA__", data).replace("__TITLE__", html.escape(f"Week {week} Picks"))


def live_summary() -> dict:
    preds = store.read_rows(final.predictions_path())
    return {"N": 0, "W": 0, "L": 0, "picked": len(preds)}


TEMPLATE = r"""<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#f4f6f3;--panel:#fff;--ink:#15202a;--ink-2:#4b5560;--ink-3:#7a838b;--rule:#dde2dc;
--accent:#1f6f4a;--accent-soft:#e3efe8;--strong:#1f6f4a;--strong-bg:#dcefe4;--lean:#8a6200;--lean-bg:#f8edd2;
--flat:#5d666e;--flat-bg:#eceeea;
--display:"Barlow Condensed","Arial Narrow",Arial,sans-serif;--body:"IBM Plex Sans",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#121a17;--panel:#19221e;--ink:#eef2ee;--ink-2:#b9c2bc;--ink-3:#8b958f;--rule:#2c3833;--accent:#5cc494;--accent-soft:#1f3229;--strong:#7bd9aa;--strong-bg:#1d3a2c;--lean:#e8c26a;--lean-bg:#3a2f14;--flat:#b9c2bc;--flat-bg:#262f2b}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121a17;--panel:#19221e;--ink:#eef2ee;--ink-2:#b9c2bc;--ink-3:#8b958f;--rule:#2c3833;--accent:#5cc494;--accent-soft:#1f3229;--strong:#7bd9aa;--strong-bg:#1d3a2c;--lean:#e8c26a;--lean-bg:#3a2f14;--flat:#b9c2bc;--flat-bg:#262f2b}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.5 var(--body);padding-inline:16px;padding-block:24px 48px}
.wrap{max-width:960px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
h1{font:700 clamp(32px,6vw,46px)/1 var(--display);margin:0;letter-spacing:.01em}
h2{font:700 24px/1.1 var(--display);margin:0}
.eyebrow{font:500 12px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.meta{color:var(--ink-2);font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
@media (max-width:700px){.tiles{grid-template-columns:repeat(2,1fr)}}
.tile{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.tile .v{font:700 30px/1.05 var(--display);font-variant-numeric:tabular-nums}
.tile .l{font-size:13px;color:var(--ink-2)}
.filters{display:flex;flex-wrap:wrap;gap:8px}
.filters button{font:500 13px var(--body);color:var(--ink-2);background:var(--panel);border:1px solid var(--rule);border-radius:999px;padding:6px 12px;cursor:pointer}
.filters button[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.filters button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tablebox{overflow-x:auto;background:var(--panel);border:1px solid var(--rule);border-radius:6px}
table{border-collapse:collapse;width:100%;min-width:880px;font-variant-numeric:tabular-nums}
th{font:500 11px/1.2 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);text-align:left;padding:10px 12px;border-bottom:1px solid var(--rule)}
td{padding:10px 12px;border-bottom:1px solid var(--rule);vertical-align:middle}
tr:last-child td{border-bottom:0}
.game{font-weight:600}.ko{color:var(--ink-2);font-size:13px}
.num{font-family:var(--mono);font-size:14px}
.pick{font:700 20px/1 var(--display);letter-spacing:.02em}
.bar{height:6px;border-radius:3px;background:var(--rule);width:90px;overflow:hidden;margin-top:5px}
.bar i{display:block;height:100%;background:var(--accent);border-radius:3px}
.chip{display:inline-block;font:500 12px/1 var(--body);padding:5px 8px;border-radius:999px;white-space:nowrap}
.chip.strong{color:var(--strong);background:var(--strong-bg)}.chip.lean{color:var(--lean);background:var(--lean-bg)}
.chip.flat,.chip.none{color:var(--flat);background:var(--flat-bg)}
.status{font-size:12px;color:var(--ink-3)}
.note{font-size:13px;color:var(--ink-2);max-width:75ch}
.legend{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:13px;color:var(--ink-2);align-items:center}
</style>
<div class="wrap">
  <header style="display:flex;flex-direction:column;gap:8px">
    <div class="eyebrow">Bonsai Pool 2026 · NFL_ATS model</div>
    <h1 id="h1"></h1>
    <div class="meta" id="meta"></div>
  </header>
  <div class="tiles" id="tiles"></div>
  <section style="display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;align-items:center">
      <h2>Picks</h2>
      <div class="filters" role="group" aria-label="Filter games">
        <button id="f-all" aria-pressed="true">All games</button>
        <button id="f-strong" aria-pressed="false">Moved 1+ pt</button>
      </div>
    </div>
    <div class="legend"><span class="chip strong">Moved 1+ pt</span> historically 57% · <span class="chip lean">Moved ½ pt</span> ~51% · <span class="chip flat">No move</span> ~52%, near a coin flip</div>
    <div class="tablebox"><table>
      <thead><tr><th>Game</th><th>League line</th><th>Market now</th><th>Market move</th><th>Pick</th><th>Cover chance</th><th>Projected score</th><th>Status</th></tr></thead>
      <tbody id="rows"></tbody></table></div>
    <p class="note">Lines are the home team's spread (negative = home favored). <b>Provisional</b> picks use the latest market snapshot and can flip before lock; the official pick is locked 15–25 minutes before each game and never changes. Win rates quoted are 2007–2021 history; the 2025 holdout was weaker (52% on 1+ pt moves). <b>Projected scores</b> come from the player model (proj-players-v3): team scoring strength adjusted for the starting quarterback, injured starters weighted by snaps, rest, travel and roof. It is tracked for comparison only and does not make the pick: it projects scores better than the team-only model, but against the market it was a coin flip in 2022–2025 testing (docs/players_v3_report.md). "Injury report pending" means the Friday game statuses were not yet published, so injuries are not reflected.</p>
  </section>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
$('h1').textContent=`Week ${D.week} picks`;
$('meta').textContent=`${D.season} regular season · snapshot ${D.updated}`;
const g=D.games, strong=g.filter(x=>x.sig==='strong').length, fin=g.filter(x=>x.status==='final').length,
      prov=g.filter(x=>x.status==='provisional').length;
const tiles=[[D.record,'Season record vs league line'],[`${fin} / ${g.length}`,'Official picks locked'],[prov,'Provisional (can change)'],[strong,'Games with a 1+ pt move']];
$('tiles').innerHTML=tiles.map(([v,l])=>`<div class="tile"><span class="v">${v}</span><span class="l">${l}</span></div>`).join('');
const fmt=v=>v===null||v===undefined?'—':(v>0?'+':'')+Number(v).toFixed(1);
const status={final:'Official (locked)',provisional:'Provisional',started_no_final_pick:'Started · no pick recorded'};
function draw(onlyStrong){
  $('rows').innerHTML=g.filter(x=>!onlyStrong||x.sig==='strong').map(x=>{
    const pct=x.pick_p==null?null:Math.round(x.pick_p*1000)/10;
    return `<tr><td><div class="game">${x.away} @ ${x.home}</div><div class="ko">${x.ko}</div></td>
      <td class="num">${x.home} ${fmt(x.line)}</td>
      <td class="num">${x.market==null?'—':x.home+' '+fmt(x.market)}</td>
      <td><span class="chip ${x.sig}">${x.sig_label}</span></td>
      <td class="pick">${x.pick||'—'}</td>
      <td>${pct==null?'—':`<span class="num">${pct.toFixed(1)}%</span><div class="bar"><i style="width:${Math.max(0,Math.min(100,(pct-40)*5))}%"></i></div>`}</td>
      <td>${x.ph==null?'—':`<span class="num">${x.away} ${x.pa.toFixed(1)} – ${x.home} ${x.ph.toFixed(1)}</span><div class="status">Projection picks ${x.ppick||'—'}${x.ppick&&x.ppick!==x.pick?' (differs)':''}${x.pver&&x.pver!=='proj-players-v3'?' · team-only model':''}${(x.pflags||'').includes('INJ_STATUS_MISSING')?' · injury report pending':''}</div>`}</td>
      <td class="status">${status[x.status]||x.status}</td></tr>`}).join('');
}
function setF(s){$('f-all').setAttribute('aria-pressed',!s);$('f-strong').setAttribute('aria-pressed',s);draw(s);}
$('f-all').onclick=()=>setF(false);$('f-strong').onclick=()=>setF(true);
draw(false);
</script>
"""
