"""The ATS terminal page (site/terminal.html). Data comes from terminal.render; see terminal.py for what it holds.

Views (hash routes): #/slate, #/game/<game_id>, #/performance, #/method. Everything on the page is computed
from the embedded data in the browser: cover chances at any pool line come from each game's margin
distribution, calibration bins and intervals from the graded picks. Display only.
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>__TITLE__</title>
<meta name="theme-color" content="#13213a">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap">
<style>
/* Bonsai ATS terminal. One family (Archivo) used at three widths: condensed for numbers, normal for text,
   expanded for section titles. The yellow first-down line is the pool line everywhere it appears. */
:root{
  --bg:#e7e9e4;--panel:#fafbf8;--panel-2:#f0f2ee;--ink:#13213a;--ink-2:#44506a;--ink-3:#5f6a80;--rule:#d3d8d0;
  --turf:#23613f;--turf-hi:#2c7a50;--turf-dim:#7c8f82;--chalk:rgba(255,255,255,.9);--chalk-2:rgba(255,255,255,.38);--chalk-3:rgba(255,255,255,.16);
  --line:#f2c200;--on-line:#1e1800;--cover:#146c39;--cover-bg:#dcefe2;--miss:#b23a26;--miss-bg:#f7e1dc;
  --s-off:#2a78d6;--s-v3:#1baf7a;--s-hy:#eb6834;--s-v1:#6250d6;--s-key:#e87ba4;--base:#8a93a3;
  --shadow:0 1px 0 rgba(19,33,58,.04),0 6px 18px -10px rgba(19,33,58,.25);
  --f:"Archivo",system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
  --bg:#0c1320;--panel:#131c2c;--panel-2:#182334;--ink:#e6ebf3;--ink-2:#aeb8ca;--ink-3:#8f9ab0;--rule:#24324a;
  --turf:#1b4a32;--turf-hi:#225c3e;--turf-dim:#2b3a33;--cover:#5fd08b;--cover-bg:#12301f;--miss:#ff8c7a;--miss-bg:#3a1a16;
  --s-off:#3987e5;--s-v3:#199e70;--s-hy:#d95926;--s-v1:#9085e9;--s-key:#d55181;--base:#6d7890;--shadow:none}}
:root[data-theme="dark"]{color-scheme:dark;
  --bg:#0c1320;--panel:#131c2c;--panel-2:#182334;--ink:#e6ebf3;--ink-2:#aeb8ca;--ink-3:#8f9ab0;--rule:#24324a;
  --turf:#1b4a32;--turf-hi:#225c3e;--turf-dim:#2b3a33;--cover:#5fd08b;--cover-bg:#12301f;--miss:#ff8c7a;--miss-bg:#3a1a16;
  --s-off:#3987e5;--s-v3:#199e70;--s-hy:#d95926;--s-v1:#9085e9;--s-key:#d55181;--base:#6d7890;--shadow:none}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--ink);font:400 16px/1.5 var(--f);font-stretch:100%;-webkit-font-smoothing:antialiased}
button,input,select{font:inherit;color:inherit}
a{color:inherit}
:focus-visible{outline:3px solid var(--line);outline-offset:2px;border-radius:4px}
.n{font-stretch:72%;font-variant-numeric:tabular-nums;letter-spacing:-.005em}
h1,h2,h3{text-wrap:balance;margin:0}
.skip{position:absolute;left:-999px;top:8px;z-index:20;background:var(--ink);color:var(--bg);padding:8px 12px;border-radius:6px}
.skip:focus{left:12px}

/* shell */
.bar{position:sticky;top:0;z-index:10;background:#13213a;color:#eef2f8;display:flex;align-items:stretch;min-height:56px;
  padding:0 env(safe-area-inset-right) 0 env(safe-area-inset-left);box-shadow:0 2px 0 var(--line)}
.brand{text-decoration:none;color:inherit;display:flex;align-items:center;gap:10px;padding:0 16px;font-weight:800;font-stretch:118%;letter-spacing:.01em;white-space:nowrap}
.brand svg{flex:none}
.wk{background:var(--line);color:var(--on-line);display:flex;align-items:center;padding:0 14px;font-weight:800;font-stretch:80%;font-size:20px;white-space:nowrap}
.recs{display:flex;align-items:center;gap:18px;padding:0 16px;min-width:0;overflow:hidden}
.recs span{display:flex;align-items:baseline;gap:6px;white-space:nowrap}
.recs b{font-weight:800;font-size:22px;font-stretch:72%;font-variant-numeric:tabular-nums}
.recs small{font-size:12px;opacity:.72}
.tabs{display:flex;margin-left:auto}
.tabs a{display:flex;align-items:center;padding:0 16px;text-decoration:none;font-weight:600;font-size:14px;color:#c9d2e2;border-bottom:3px solid transparent;min-height:56px}
.tabs a[aria-current="page"]{color:#fff;border-bottom-color:var(--line)}
.tabs a:hover{color:#fff}
.clock{display:flex;align-items:center;gap:8px;padding:0 16px;font-size:13px;white-space:nowrap;border-left:1px solid rgba(255,255,255,.14)}
.clock i{width:8px;height:8px;border-radius:50%;background:var(--line)}
main{max-width:1120px;margin:0 auto;padding:26px 16px 96px}
main:focus{outline:none}
.view{display:flex;flex-direction:column;gap:28px}
.view[hidden]{display:none}
.panel{background:var(--panel);border:1px solid var(--rule);border-radius:12px;box-shadow:var(--shadow)}
.ph{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:16px 18px 0}
.ph h2{font-size:15px;font-weight:700}
.ph p{margin:0;color:var(--ink-3);font-size:13px}
.pb{padding:12px 18px 18px}
.kicker{font-size:13px;color:var(--ink-3);margin:0}
.hero h1{font-size:clamp(40px,8vw,72px);line-height:.95;font-weight:800;font-stretch:118%;letter-spacing:-.01em}
.hero p{margin:10px 0 0;color:var(--ink-2);max-width:66ch}
.key{list-style:none;margin:8px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--ink-2);font-size:14px}
.key i{display:inline-block;vertical-align:-2px;margin-right:6px}
.k-line{width:4px;height:15px;background:var(--line);border-radius:2px}
.k-bar{width:9px;height:13px;background:var(--turf);border-radius:2px;box-shadow:inset 0 0 0 2px #fff}
.k-ball{width:16px;height:10px;border-radius:50%;background:#7a3b16}
.big{font-weight:800;font-stretch:70%;font-variant-numeric:tabular-nums;line-height:1}

/* controls */
.ctrl{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--rule);background:var(--panel);border-radius:999px;padding:8px 14px;font-size:14px;font-weight:600;cursor:pointer;min-height:40px;touch-action:manipulation}
.chip:hover{border-color:var(--ink-3)}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.chip .c{font-stretch:72%;font-weight:700;margin-left:6px;opacity:.7}
.sel{display:flex;align-items:center;gap:8px;font-size:14px;color:var(--ink-2)}
.sel select{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:8px 10px;min-height:40px;color:var(--ink)}

/* slate */
.slot{display:flex;flex-direction:column;gap:8px}
.slot-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:0 2px;border-bottom:2px solid var(--ink);padding-bottom:6px}
.slot-h h2{font-size:22px;font-weight:800;font-stretch:112%}
.slot-h h2 small{font-size:14px;font-weight:500;font-stretch:100%;color:var(--ink-3);margin-left:8px}
.slot-h .rec{font-size:22px}
.games{display:flex;flex-direction:column;gap:6px}
.g{display:grid;grid-template-columns:150px minmax(0,1fr) 120px;align-items:stretch;min-height:76px;background:var(--panel);border:1px solid var(--rule);
  border-radius:10px;overflow:hidden;text-decoration:none;box-shadow:var(--shadow);touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.g:hover{border-color:var(--ink-3)}
.g:hover .mini{filter:brightness(1.06)}
.who{display:flex;flex-direction:column;justify-content:center;padding:8px 14px;gap:2px;min-width:0}
.who b{font-size:28px;font-weight:800;font-stretch:72%;line-height:1;white-space:nowrap}
.who b span{font-size:17px;font-weight:600;color:var(--ink-2);margin-left:6px}
.who small{font-size:13px;color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.who.none b{font-size:20px;color:var(--ink-3)}
.mini{position:relative;background:var(--turf);overflow:hidden}
.mini.dim{background:var(--turf-dim)}
.mini svg{position:absolute;inset:0;width:100%;height:100%}
.mini .tag{position:absolute;left:8px;top:6px;z-index:2;font-size:11.5px;font-weight:600;background:rgba(5,14,9,.66);color:#fff;border-radius:999px;padding:1px 8px;white-space:nowrap}
.mini .tag.hot{background:var(--line);color:var(--on-line)}
.mini .note{position:absolute;right:8px;bottom:6px;z-index:2}
.mini .note span{display:block;background:rgba(5,14,9,.7);color:#fff;font-size:11.5px;font-weight:600;border-radius:999px;padding:1px 8px;white-space:nowrap}
.out{display:flex;flex-direction:column;align-items:flex-end;justify-content:center;padding:8px 14px;gap:3px;line-height:1.1}
.out .p{font-size:26px;font-weight:800;font-stretch:72%;font-variant-numeric:tabular-nums}
.out .s{font-size:12.5px;font-weight:600;white-space:nowrap}
.w{color:var(--cover)} .l{color:var(--miss)} .m{color:var(--ink-3)}
.side{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.side>*{min-width:0}

/* matchup */
.mh{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;align-items:end}
.mh h1{font-size:clamp(44px,9vw,84px);line-height:.92;font-weight:800;font-stretch:72%;letter-spacing:-.01em}
.mh h1 em{font-style:normal;color:var(--ink-3);font-weight:600;font-size:.5em;vertical-align:.45em;margin:0 .25em}
.mh .pickline{margin-top:8px;font-size:17px;color:var(--ink-2)}
.mh .pickline b{color:var(--ink)}
.nav{display:flex;gap:6px}
.nav a{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:44px;border:1px solid var(--rule);border-radius:10px;background:var(--panel);text-decoration:none;font-size:20px}
.nav a[aria-disabled="true"]{opacity:.35;pointer-events:none}
.nav a:hover,.toggles button:hover{border-color:var(--ink-3);background:var(--panel-2)}
.facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.fact{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:12px 14px}
.fact dt{font-size:12.5px;color:var(--ink-3)}
.fact dd{margin:4px 0 0;font-size:30px;font-weight:800;font-stretch:72%;line-height:1;font-variant-numeric:tabular-nums}
.fact dd small{display:block;font-size:12.5px;font-weight:500;font-stretch:100%;color:var(--ink-3);margin-top:5px}
.field{position:relative;border-radius:12px;overflow:hidden;background:var(--turf);color:#fff}
.field svg{display:block;width:100%;height:auto}
.field .cap{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;padding:12px 16px;font-size:13.5px;background:rgba(0,0,0,.18)}
.field .cap b{font-stretch:72%;font-size:18px}
.field .cap i{display:inline-block;width:14px;height:4px;border-radius:2px;vertical-align:3px;margin-right:6px}
.whatif{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 18px;align-items:center;padding:14px 16px 16px;background:rgba(0,0,0,.26)}
.whatif label{font-size:13.5px}
.whatif input[type=range]{grid-column:1/-1;width:100%;accent-color:var(--line);min-height:32px}
.whatif output{font-size:30px;font-weight:800;font-stretch:72%;font-variant-numeric:tabular-nums;color:var(--line)}
.dtab{padding:4px 16px 14px;background:rgba(0,0,0,.26)}
.dtab summary{color:#fff}
.dtab table{color:#fff}.dtab th{color:rgba(255,255,255,.75)}.dtab td,.dtab th{border-color:rgba(255,255,255,.15)}
.tip{position:absolute;pointer-events:none;background:#0b1220;color:#fff;font-size:12.5px;line-height:1.35;padding:6px 9px;border-radius:6px;white-space:nowrap;z-index:5;box-shadow:0 4px 14px rgba(0,0,0,.3)}
.tip[hidden]{display:none}
.why{margin:0;padding:0 0 0 18px;display:flex;flex-direction:column;gap:8px;max-width:76ch;color:var(--ink-2)}
.drv{display:grid;grid-template-columns:minmax(120px,1.2fr) minmax(0,2fr) 52px;gap:6px 10px;align-items:center;font-size:13.5px}
.drv .bar2{position:relative;height:12px;background:var(--panel-2);border-radius:3px}
.drv .bar2 i{position:absolute;top:0;bottom:0;border-radius:3px}
.drv .bar2 b{position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--ink-3)}
.drv .v{text-align:right;font-stretch:72%;font-weight:700;font-variant-numeric:tabular-nums}
.drv h4{grid-column:1/-1;margin:8px 0 0;font-size:14px}
.chart{position:relative}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--ink-2)}
.legend i{display:inline-block;width:16px;height:3px;border-radius:2px;vertical-align:4px;margin-right:6px}
.toggles{display:flex;flex-wrap:wrap;gap:6px}
.toggles button{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--rule);background:var(--panel);border-radius:999px;padding:6px 12px;font-size:13px;font-weight:600;min-height:36px;cursor:pointer}
.toggles button i{width:14px;height:3px;border-radius:2px}
.toggles button[aria-pressed="false"]{opacity:.45}

/* performance */
.tiles{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.tile{background:var(--panel);border:1px solid var(--rule);border-radius:12px;padding:14px 16px;border-top:4px solid var(--c,var(--rule));box-shadow:var(--shadow)}
.tile .big{font-size:44px}
.tile b{display:block;font-size:14px;margin-top:6px}
.tile small{display:block;font-size:12.5px;color:var(--ink-3)}
.prog{height:8px;border-radius:4px;background:var(--panel-2);overflow:hidden}
.prog i{display:block;height:100%;background:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid var(--rule);text-align:right;font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left}
th{font-size:12.5px;font-weight:600;color:var(--ink-3)}
td.up{color:var(--cover);font-weight:600} td.dn{color:var(--miss);font-weight:600}
.tbl{overflow-x:auto}
details.more>summary{cursor:pointer;font-size:14px;font-weight:600;padding:8px 0;min-height:40px}
.prose{max-width:70ch;color:var(--ink-2)}
.prose h2{font-size:22px;font-weight:800;font-stretch:112%;color:var(--ink);margin:6px 0 8px}
.prose p{margin:0 0 12px}
.prose b{color:var(--ink)}
.empty{color:var(--ink-3)}

@media (max-width:860px){
  .tabs{position:fixed;left:0;right:0;bottom:0;z-index:10;background:#13213a;justify-content:space-around;padding-bottom:env(safe-area-inset-bottom);box-shadow:0 -1px 0 rgba(255,255,255,.08)}
  .tabs a{flex:1;justify-content:center;min-height:56px;border-bottom:0;border-top:3px solid transparent;padding:0 6px}
  .tabs a[aria-current="page"]{border-top-color:var(--line)}
  .clock{display:none}
  .brand span{display:none}
  .tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
  .facts{grid-template-columns:repeat(2,minmax(0,1fr))}
  .side{grid-template-columns:1fr}
}
@media (max-width:560px){
  .recs small{display:none}
  .recs{gap:12px;padding:0 12px}
  .g{grid-template-columns:96px minmax(0,1fr) 92px;min-height:70px}
  .who .t{display:none}
  .who{padding:8px 10px}.who b{font-size:24px}.who b span{font-size:13px;margin-left:3px}
  .out{padding:8px 10px}.out .p{font-size:22px}.out .s{font-size:11.5px}
  .mh{grid-template-columns:1fr}
  .drv{grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) 44px}
}
@media (prefers-reduced-motion:no-preference){
  ::view-transition-old(root),::view-transition-new(root){animation-duration:.22s}
  .rise{animation:rise .5s cubic-bezier(.2,.8,.2,1) both;animation-delay:calc(var(--i,0)*40ms)}
  @keyframes rise{from{opacity:0;transform:translateY(8px)}}
  .grow{transform-box:fill-box;transform-origin:bottom;animation:grow .7s cubic-bezier(.2,.8,.2,1) both;animation-delay:calc(var(--i,0)*9ms + 120ms)}
  @keyframes grow{from{transform:scaleY(0)}}
}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="bar">
  <a class="brand" translate="no" href="#/slate" aria-label="Bonsai ATS, this week’s slate"><svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true"><rect width="26" height="26" rx="5" fill="#23613f"/><path d="M13 3v20" stroke="#f2c200" stroke-width="3"/><path d="M6 3v20M20 3v20" stroke="rgba(255,255,255,.45)" stroke-width="1.5"/></svg><span>Bonsai ATS</span></a>
  <span class="wk" id="wk"></span>
  <span class="recs" id="recs"></span>
  <nav class="tabs" aria-label="Sections"><a href="#/slate" data-v="slate">Slate</a><a href="#/game" data-v="game">Matchup</a><a href="#/performance" data-v="performance">Performance</a><a href="#/method" data-v="method">Method</a></nav>
  <span class="clock" id="clock" hidden><i></i><span></span></span>
</header>
<main id="main" tabindex="-1">
  <section class="view" id="v-slate" aria-label="This week’s slate"></section>
  <section class="view" id="v-game" aria-label="Matchup" hidden></section>
  <section class="view" id="v-performance" aria-label="Model performance" hidden></section>
  <section class="view" id="v-method" aria-label="How the model works" hidden></section>
</main>
<div class="tip" id="tip" hidden></div>
<script>
"use strict";
const D=__DATA__;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const REDUCED=matchMedia('(prefers-reduced-motion: reduce)').matches;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const MINUS='−';
const sgn=v=>v==null||isNaN(v)?'—':v===0?'PK':(v>0?'+':MINUS)+fmtH(Math.abs(v));
const fmtH=a=>{const w=Math.floor(a+1e-9),f=a-w;return f>.25&&f<.75?(w?w:'')+'½':String(Math.round(a))};
const pct=(p,d=0)=>p==null?'—':(p*100).toFixed(d)+'%';
const num=v=>v==null||v===''?null:+v;
const G=D.games||[],byId=Object.fromEntries(G.map(g=>[g.id,g])),DIST=D.dist||{},DET=D.details||{};

/* ---------- the model's margin distribution, from the picked side ---------- */
// dist.p[i] = P(home margin = k0+i). Seen from team T: margin_T = home ? k : -k.
function distFor(g,team){
  const d=DIST[g.id];if(!d)return null;
  const home=team===g.home,pts=[];
  d.p.forEach((p,i)=>{const k=d.k0+i;pts.push([home?k:-k,p])});
  pts.sort((a,b)=>a[0]-b[0]);
  return {pts,lo:home?d.lo:d.hi,hi:home?d.hi:d.lo,c:d.c,total:d.total,model:d.model};
}
const lineFor=(g,team)=>g.line==null?null:(team===g.home?+g.line:-g.line);       // team's pool line
const mktFor=(g,team)=>num(g.market)==null?null:(team===g.home?+g.market:-g.market);
function pCover(f,L){                     // P(team margin + L > 0) = P(margin > -L); half-point L never pushes
  let s=f.hi;for(const [m,p] of f.pts)if(m>-L)s+=p;
  if(-L<f.pts[0][0])s+=f.lo;return s;
}
function pPush(f,L){let s=0;for(const [m,p] of f.pts)if(m===-L)s+=p;return s}
function quant(f,q){let s=f.lo;for(const [m,p] of f.pts){s+=p;if(s>=q)return m}return f.pts[f.pts.length-1][0]}
function mean(f){let s=0,t=0;for(const [m,p] of f.pts){s+=m*p;t+=p}return s/t}
function side(g){
  if(!g.pick)return null;
  const team=g.pick,home=team===g.home,ps=home?g.hs:g.as,os=home?g.as:g.hs,L=lineFor(g,team);
  return {team,opp:home?g.away:g.home,home,L,ps,os,m:g.hs==null||L==null?null:ps-os+L};
}

/* ---------- shell ---------- */
function shell(){
  $('wk').textContent=`Week ${D.week}`;
  const m=k=>(D.models||[]).find(x=>x.label.startsWith(k));
  $('recs').innerHTML=[[m('Official'),'official'],[m('Hybrid'),'hybrid']].filter(a=>a[0]).map(([x,k])=>`<span><b>${x.W}–${x.L}</b><small>${k}</small></span>`).join('');
  const due=(D.due||[]).map(d=>({t:Date.parse(d.iso),...d})).filter(d=>d.t>Date.now());
  if(due.length){const c=$('clock');c.hidden=false;const tick=()=>{const ms=due[0].t-Date.now();if(ms<=0){c.hidden=true;return}
    const h=Math.floor(ms/36e5),mn=Math.floor(ms%36e5/6e4);c.lastElementChild.textContent=`${due[0].game} picks in ${h?h+'h ':''}${mn}m`};tick();setInterval(tick,30000)}
}

/* ---------- slate ---------- */
const FILTERS=[['all','All games',()=>true],['open','Still to play',g=>g.hs==null],['final','Final',g=>g.hs!=null],
  ['moved','Market moved 1+',g=>g.sig==='strong'],['split','Models disagree',g=>(g.ppick&&g.pick&&g.ppick!==g.pick)||(g.hy&&g.pick&&g.hy!==g.pick)]];
const SORTS={kick:['Kickoff',(a,b)=>a.ko_iso.localeCompare(b.ko_iso)],chance:['Cover chance',(a,b)=>(b.pick_p??-1)-(a.pick_p??-1)],
  move:['Market move',(a,b)=>Math.abs(b.drift??-1)-Math.abs(a.drift??-1)]};
let st={f:'all',s:'kick'};                     // the address is the only source of the slate's state
function readQ(q){const u=new URLSearchParams(q||'');st={f:'all',s:'kick'};if(FILTERS.some(x=>x[0]===u.get('f')))st.f=u.get('f');if(SORTS[u.get('s')])st.s=u.get('s')}
function tag(g){
  if(g.sig==='strong')return '<span class="tag hot">Market moved 1+</span>';
  if(g.hy&&g.pick&&g.hy!==g.pick)return `<span class="tag">Hybrid took ${esc(g.hy)}</span>`;
  if(g.ppick&&g.pick&&g.ppick!==g.pick)return `<span class="tag">Projection took ${esc(g.ppick)}</span>`;
  if((D.flips||{})[g.id])return '<span class="tag">Flipped since Wednesday</span>';
  return '';
}
const XR=24;                                     // the strip spans -24..+24 points of the pick's margin
function miniSVG(g,s,idx){
  const f=s&&distFor(g,s.team);
  const W=400,H=76,x=m=>W/2+m/XR*(W/2-8);
  let o='';for(const p of [-21,-14,-7,7,14,21])o+=`<line x1="${x(p)}" x2="${x(p)}" y1="0" y2="${H}" stroke="var(--chalk-3)"/>`;
  if(f){
    const mx=Math.max(...f.pts.map(q=>q[1])),Lc=-s.L;
    f.pts.forEach(([m,p],i)=>{if(m<-XR||m>XR)return;const h=p/mx*(H-18),c=m>Lc?'var(--chalk)':'var(--chalk-2)';
      o+=`<rect class="grow" style="--i:${i}" x="${x(m)-2.6}" y="${H-h}" width="5.2" height="${h}" fill="${c}" rx="1"/>`});
  }
  if(!f&&s&&s.m!=null){const a=x(-s.L),bb=x(Math.max(-XR,Math.min(XR,s.ps-s.os)));
    o+=`<rect x="${Math.min(a,bb)}" y="${H/2-3}" width="${Math.abs(bb-a)}" height="6" rx="3" fill="${s.m>0?'var(--chalk)':'var(--chalk-2)'}"/>`}
  if(s&&s.L!=null)o+=`<line x1="${x(-s.L)}" x2="${x(-s.L)}" y1="0" y2="${H}" stroke="var(--line)" stroke-width="3"/>`;
  if(s&&s.m!=null){const pm=s.ps-s.os,X=x(Math.max(-XR,Math.min(XR,pm)));
    o+=`<g transform="translate(${X},${H/2})"><ellipse rx="9" ry="5.5" fill="#7a3b16" stroke="#fff" stroke-width="1.2"/><path d="M-4 0h8M-2 -2v4M0 -2v4M2 -2v4" stroke="#fff" stroke-width=".9"/></g>`}
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">${o}</svg>`;
}
function gameRow(g,i){
  const s=side(g),f=s&&distFor(g,s.team);
  const who=s?`<span class="who"><b>${esc(s.team)}<span>${sgn(s.L)}</span></b><small>${s.home?'vs':'@'} ${esc(s.opp)}<span class="t"> · ${esc(g.ko.replace(/^\w+ /,''))}</span></small></span>`
             :`<span class="who none"><b>${esc(g.away)} @ ${esc(g.home)}</b><small>No pick recorded</small></span>`;
  let out;
  if(s&&g.hs!=null){const r=g.res==='W'?['w','Covered']:g.res==='L'?['l','Missed']:['m','Push'];
    out=`<span class="p">${s.ps}–${s.os}</span><span class="s ${r[0]}">${r[1]} ${s.m?fmtH(Math.abs(s.m)):''}</span>`}
  else if(s)out=`<span class="p">${pct(g.pick_p)}</span><span class="s m">${g.status==='provisional'?'provisional':'locked'}</span>`;
  else out=g.hs!=null?`<span class="p">${g.as}–${g.hs}</span><span class="s m">final</span>`:'';
  const note=!f?`<span class="note"><span>${s?(g.hs!=null?'No market':'No market yet'):'No pick'}</span></span>`:'';
  const label=s?`${s.team} ${sgn(s.L)} ${s.home?'versus':'at'} ${s.opp}${g.pick_p!=null?`, ${pct(g.pick_p,1)} to cover`:''}${g.res?`, ${g.res==='W'?'covered':'missed'}`:''}`:`${g.away} at ${g.home}, no pick`;
  return `<a class="g rise" style="--i:${i}" href="#/game/${esc(g.id)}" aria-label="${esc(label)}">${who}<span class="mini${f||(s&&s.m!=null)?'':' dim'}">${miniSVG(g,s,i)}${s?tag(g):''}${note}</span><span class="out">${out}</span></a>`;
}
function slate(){
  const v=$('v-slate'),pf=FILTERS.find(x=>x[0]===st.f)[2],gs=G.filter(pf).sort(SORTS[st.s][1]);
  const w=G.filter(g=>g.res==='W').length,l=G.filter(g=>g.res==='L').length,left=G.filter(g=>g.hs==null).length;
  const tb=(D.tiebreak||[]).filter(r=>r.week===D.week).pop();
  let body='';
  if(st.s==='kick'){
    body=(D.slots||[]).map((sl,i)=>{const ss=gs.filter(g=>g.slot===i);if(!ss.length)return '';
      const sw=ss.filter(g=>g.res==='W').length,sl2=ss.filter(g=>g.res==='L').length;
      return `<div class="slot"><div class="slot-h"><h2>${esc(sl.day)}<small>${esc(sl.times)} ET</small></h2>${sw+sl2?`<span class="big rec">${sw}–${sl2}</span>`:''}</div><div class="games">${ss.map(gameRow).join('')}</div></div>`}).join('');
  }else body=`<div class="games">${gs.map(gameRow).join('')}</div>`;
  v.innerHTML=`<div class="hero"><p class="kicker">${esc(D.season)} season · updated ${esc(D.updated)}</p><h1>Week ${D.week}</h1>
    <p>${w}–${l} against the pool line so far${left?`, ${left} to play`:', all final'}.</p><p>Each strip shows the final margins the model expected for the side it took:</p><ul class="key"><li><i class="k-line"></i>Yellow line: the pool line</li><li><i class="k-bar"></i>Bright bars: outcomes that cover</li><li><i class="k-ball"></i>Ball: where the game ended</li></ul></div>
    <div class="ctrl"><div class="chips" role="group" aria-label="Show">${FILTERS.map(([k,lab,fn])=>`<button class="chip" aria-pressed="${st.f===k}" data-f="${k}">${lab}<span class="c">${G.filter(fn).length}</span></button>`).join('')}</div>
    <label class="sel">Sort <select id="sort">${Object.entries(SORTS).map(([k,[lab]])=>`<option value="${k}"${st.s===k?' selected':''}>${lab}</option>`).join('')}</select></label></div>
    ${body||'<p class="empty">No games match. Choose All games to see the full week.</p>'}
    ${tb?`<div class="panel"><div class="ph"><h2>Tiebreaker: total points, ${esc(tb.away)} @ ${esc(tb.home)}</h2><p>From the market total, rounded down at .5</p></div><div class="pb" style="display:flex;gap:28px;flex-wrap:wrap;align-items:baseline">
      <span><span class="big" style="font-size:52px">${tb.guess}</span> <span class="m">guess</span></span><span>Market total <b class="n">${tb.market_total}</b></span><span>Half of games land <b class="n">${tb.r50[0]}–${tb.r50[1]}</b>, 8 in 10 <b class="n">${tb.r80[0]}–${tb.r80[1]}</b></span>${tb.actual!=null?`<span>Final <b class="n">${tb.actual}</b>, off by ${tb.miss}</span>`:''}</div></div>`:''}`;
  v.querySelectorAll('[data-f]').forEach(b=>b.onclick=()=>{st.f=b.dataset.f;save();slate()});
  $('sort').onchange=e=>{st.s=e.target.value;save();slate()};
}
function slateHref(){const q=new URLSearchParams();if(st.f!=='all')q.set('f',st.f);if(st.s!=='kick')q.set('s',st.s);return '#/slate'+(q.toString()?'?'+q:'')}
function save(){history.replaceState(null,'',slateHref());document.querySelectorAll('a[href^="#/slate"]').forEach(a=>a.setAttribute('href',slateHref()))}

/* ---------- matchup ---------- */
function order(){return G.slice().sort(SORTS.kick[1])}
function game(id){
  const v=$('v-game'),g=byId[id]||order().find(x=>x.hs==null)||order()[0];if(!g){v.innerHTML='<p class="empty">No games this week.</p>';return}
  const s=side(g),team=s?s.team:g.home,f=distFor(g,team),det=DET[g.id]||{},o=order(),ix=o.findIndex(x=>x.id===g.id);
  const prev=o[ix-1],next=o[ix+1],L=lineFor(g,team),M=mktFor(g,team);
  const stat=g.hs!=null?(s?`<b class="${g.res==='W'?'w':'l'}">${g.res==='W'?'Covered':'Missed'}</b> · final ${g.as}–${g.hs}`:`Final ${g.as}–${g.hs}`)
    :g.status==='provisional'?'Provisional pick: it can change until the lock':g.status==='final'?`Locked ${esc(g.pick_at||'')} ET`:'No pick was recorded before kickoff';
  const facts=[
    ['Pool line',L==null?'—':`${team} ${sgn(L)}`,'frozen Tuesday'],
    ['Market at the pick',M==null?'—':`${team} ${sgn(M)}`,g.drift==null?'no market captured':g.drift?`moved ${fmtH(Math.abs(g.drift))} off the pool line`:'same as the pool line'],
    ['Cover chance',g.pick_p==null?'—':pct(g.pick_p,1),f&&s?`${fmtH(Math.abs(mean(f)))}-pt projected ${mean(f)>=0?'win':'loss'} margin`:'from the margin distribution'],
    ['Projection',g.ph!=null?`${g.pa}–${g.ph}`:'—',g.ppick?`${esc(g.away)}–${esc(g.home)} · picks ${esc(g.ppick)}`:'player model, tracked only']];
  v.innerHTML=`<div class="mh"><div><p class="kicker">${esc(g.ko)} ET · Week ${D.week}</p><h1>${esc(g.away)}<em>@</em>${esc(g.home)}</h1>
      <p class="pickline">${s?`Pick <b>${esc(team)} ${sgn(L)}</b> · `:''}${stat}</p></div>
      <div class="nav"><a href="#/game/${prev?esc(prev.id):''}" aria-label="Previous game" ${prev?'':'aria-disabled="true"'}>‹</a><a href="#/slate" aria-label="Back to the slate" style="font-size:14px;padding:0 14px">Slate</a><a href="#/game/${next?esc(next.id):''}" aria-label="Next game" ${next?'':'aria-disabled="true"'}>›</a></div></div>
    <dl class="facts">${facts.map(([a,b,c])=>`<div class="fact"><dt>${a}</dt><dd>${b}<small>${c}</small></dd></div>`).join('')}</dl>
    ${f?`<div class="field" id="field"></div>`:`<div class="panel"><div class="pb"><p class="empty">No margin distribution: ${s?'no market line was captured when this pick was made, so the pick has no cover chance':'no pick was made for this game'}.</p></div></div>`}
    <div class="side">
      <div class="panel"><div class="ph"><h2>Why this pick</h2></div><div class="pb">${(det.why||[]).length?`<ul class="why">${det.why.map(w=>`<li>${esc(w)}</li>`).join('')}</ul>`:'<p class="empty">No explanation was recorded.</p>'}</div></div>
      <div class="panel"><div class="ph"><h2>What drives the projection</h2><p>Points added to each team’s expected score</p></div><div class="pb">${drivers(g)}</div></div>
    </div>
    <div class="panel"><div class="ph"><h2>How the line moved</h2><p>${esc(team)}’s spread at every book captured; Pinnacle in bold</p></div><div class="pb"><div class="chart" id="lm"></div><div class="legend" id="lm-key"></div></div></div>`;
  if(f)fieldChart(g,s,team,f,L);
  lineMove(g,team,L);
}
function drivers(g){
  const xp=g.xp;if(!xp||!xp.home)return '<p class="empty">No projection for this game.</p>';
  const all=[...xp.away.items,...xp.home.items].map(i=>Math.abs(i.pts)),mx=Math.max(2,...all);
  const rows=(t,k)=>{const it=xp[k].items.filter(i=>Math.abs(i.pts)>=.1).sort((a,b)=>Math.abs(b.pts)-Math.abs(a.pts)).slice(0,5);
    return `<h4>${esc(t)} <span class="n m">${xp[k].baseline} → ${xp[k].total} pts</span></h4>`+(it.length?it.map(i=>{const w=Math.abs(i.pts)/mx*50,pos=i.pts>=0;
      return `<span title="${esc(i.note||'')}">${esc(i.label)}</span><span class="bar2"><b></b><i style="${pos?`left:50%`:`right:50%`};width:${w}%;background:${pos?'var(--cover)':'var(--miss)'}"></i></span><span class="v">${i.pts>=0?'+':MINUS}${Math.abs(i.pts).toFixed(1)}</span>`}).join(''):'<span class="m" style="grid-column:1/-1">Nothing above 0.1 pts</span>')};
  return `<div class="drv">${rows(g.away,'away')}${rows(g.home,'home')}</div>`;
}
function fieldChart(g,s,team,f,L0){
  const box=$('field'),W=Math.max(320,box.clientWidth||900),H=W<600?250:300,m={l:14,r:14,t:30,b:34},pw=W-m.l-m.r,ph=H-m.t-m.b,R=28;
  const x=k=>m.l+(k+R)/(2*R)*pw,vis=f.pts.filter(q=>q[0]>=-R&&q[0]<=R),mx=Math.max(...vis.map(q=>q[1])),y=p=>m.t+ph-p/mx*ph;
  const bw=pw/(2*R+1)*.78,c0=-f.c*(team===g.home?1:-1),act=s&&s.m!=null?s.ps-s.os:null;
  let base='';for(let k=-R;k<=R;k+=7)base+=`<line x1="${x(k)}" x2="${x(k)}" y1="${m.t-8}" y2="${m.t+ph}" stroke="var(--chalk-3)"/><text x="${x(k)}" y="${H-12}" text-anchor="middle" font-size="12" fill="rgba(255,255,255,.75)">${k>0?'+':k<0?MINUS:''}${Math.abs(k)}</text>`;
  base+=`<text x="${m.l}" y="16" font-size="12.5" fill="rgba(255,255,255,.8)">${esc(team)} loses by</text><text x="${W-m.r}" y="16" text-anchor="end" font-size="12.5" fill="rgba(255,255,255,.8)">${esc(team)} wins by</text>`;
  const bars=vis.map(([k,p],i)=>`<rect class="grow fb" data-k="${k}" style="--i:${i}" x="${x(k)-bw/2}" y="${y(p)}" width="${bw}" height="${m.t+ph-y(p)}" rx="1.5"/>`).join('');
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribution of ${esc(team)}’s final margin; ${pct(pCover(f,L0),1)} beyond the pool line">${base}
      <g id="bars">${bars}</g>
      <line x1="${x(c0)}" x2="${x(c0)}" y1="${m.t-6}" y2="${m.t+ph}" stroke="#fff" stroke-dasharray="3 4" stroke-width="1.5"/>
      <line id="pl" y1="${m.t-12}" y2="${m.t+ph+4}" stroke="var(--line)" stroke-width="4"/>
      ${act!=null?`<g transform="translate(${x(Math.max(-R,Math.min(R,act)))},${m.t+ph-10})"><g id="ball"><ellipse rx="12" ry="7" fill="#7a3b16" stroke="#fff" stroke-width="1.5"/><path d="M-5 0h10M-2.5 -2.6v5.2M0 -2.6v5.2M2.5 -2.6v5.2" stroke="#fff" stroke-width="1.1"/></g></g>`:''}
      <rect id="hit" x="${m.l}" y="${m.t}" width="${pw}" height="${ph}" fill="transparent"/></svg>
    <div class="cap"><span><i style="background:var(--line)"></i>Pool line</span><span><i style="background:repeating-linear-gradient(90deg,#fff 0 3px,transparent 3px 6px)"></i>Market’s expected margin <b>${sgn(c0)}</b></span>
      <span>Middle half <b>${sgn(quant(f,.25))} to ${sgn(quant(f,.75))}</b></span><span>8 in 10 <b>${sgn(quant(f,.1))} to ${sgn(quant(f,.9))}</b></span>${act!=null?`<span>Final <b>${sgn(act)}</b></span>`:''}</div>
    <div class="whatif"><label for="wl">Move the pool line to see the cover chance at any number</label><output id="wo" for="wl"></output>
      <input type="range" id="wl" min="-20.5" max="20.5" step="1" value="${L0}" aria-describedby="wd"><span class="kicker" id="wd" style="color:rgba(255,255,255,.85)"></span></div>
    <details class="more dtab"><summary>The distribution as a table</summary><div class="tbl"><table><thead><tr><th>${esc(team)} final margin</th><th>Chance</th><th>Covers ${esc(team)} ${sgn(L0)}</th></tr></thead><tbody>${f.pts.filter(q=>q[1]>=.002).map(([k,p])=>`<tr><td>${k>0?'wins by '+k:k<0?'loses by '+(-k):'tie'}</td><td>${pct(p,1)}</td><td>${k>-L0?'yes':'no'}</td></tr>`).join('')}</tbody></table></div><p class="kicker" style="color:rgba(255,255,255,.8)">Margins under 0.2% are left out; the table covers ${pct(f.pts.filter(q=>q[1]>=.002).reduce((s,q)=>s+q[1],0),1)} of outcomes.</p></details>`;
  const pl=box.querySelector('#pl'),rs=box.querySelectorAll('.fb'),wl=$('wl'),wo=$('wo'),wd=$('wd');
  const set=L=>{pl.setAttribute('x1',x(-L));pl.setAttribute('x2',x(-L));
    rs.forEach(r=>{const on=+r.dataset.k>-L;r.setAttribute('fill',on?'#fff':'rgba(255,255,255,.34)')});
    const p=pCover(f,L);wo.textContent=pct(p,1);
    wd.textContent=`${team} ${sgn(L)}${L===L0?' (the pool line)':''}: covers ${pct(p,1)}, misses ${pct(1-p,1)}${L!==L0?` · pool line ${sgn(L0)}: ${pct(pCover(f,L0),1)}`:''}`};
  set(L0);wl.oninput=e=>{run&&run.forEach(a=>a.finish());set(+e.target.value)};
  // The one orchestrated moment: bars rise, the pool line drops in, the ball rolls from the market's expected
  // margin to the final margin, and the cover chance counts up from a coin flip. Skipped under reduced motion.
  let run=null;
  if(!REDUCED&&box.animate){
    const ez='cubic-bezier(.2,.8,.2,1)',ball=box.querySelector('#ball');run=[];
    run.push(pl.animate([{transform:'translateY(-30px)',opacity:0},{transform:'none',opacity:1}],{duration:420,delay:420,easing:ez,fill:'backwards'}));
    if(ball){const dx=x(Math.max(-R,Math.min(R,c0)))-x(Math.max(-R,Math.min(R,act)));ball.style.transformBox='fill-box';ball.style.transformOrigin='center';
      run.push(ball.animate([{transform:`translateX(${dx}px) rotate(-540deg)`,opacity:0},{opacity:1,offset:.12},{transform:'none',opacity:1}],{duration:1100,delay:820,easing:ez,fill:'backwards'}))}
    const p1=pCover(f,L0),t0=performance.now()+420;
    const step=now=>{const k=Math.min(1,Math.max(0,(now-t0)/800)),e=1-Math.pow(1-k,3);wo.textContent=pct(.5+(p1-.5)*e,1);if(k<1&&+wl.value===L0)requestAnimationFrame(step);else if(+wl.value===L0)wo.textContent=pct(p1,1)};
    requestAnimationFrame(step);
  }
  const tip=$('tip'),hit=box.querySelector('#hit'),svg=box.querySelector('svg');
  hit.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect(),px=(e.clientX-r.left)*(W/r.width),k=Math.round((px-m.l)/pw*2*R-R),q=f.pts.find(z=>z[0]===k);if(!q){tip.hidden=true;return}
    tip.hidden=false;tip.innerHTML=`${esc(team)} ${k>0?'wins by '+k:k<0?'loses by '+(-k):'ties'}<br>${pct(q[1],1)} of outcomes`;
    tip.style.left=Math.min(innerWidth-tip.offsetWidth-8,e.clientX+12)+'px';tip.style.top=(e.clientY+scrollY-42)+'px'});
  hit.addEventListener('pointerleave',()=>tip.hidden=true);
}
function lineMove(g,team,L){
  const det=DET[g.id]||{},box=$('lm'),key=$('lm-key');if(!box)return;
  const t=(det.t||[]).map(Date.parse),books=Object.entries(det.b||{});
  if(t.length<2||!books.length){box.innerHTML='<p class="empty">No line history was captured for this game.</p>';return}
  const flip=team===g.home?1:-1,ref=det.ref_book||'pinnacle';
  const vals=books.flatMap(([,a])=>a.filter(v=>v!=null).map(v=>v*flip)).concat(L==null?[]:[L]);
  const lo=Math.floor(Math.min(...vals)-.5),hi=Math.ceil(Math.max(...vals)+.5);
  const W=Math.max(320,box.clientWidth||900),H=230,m={l:44,r:16,t:12,b:28},pw=W-m.l-m.r,ph=H-m.t-m.b;
  const X=v=>m.l+(v-t[0])/(t[t.length-1]-t[0]||1)*pw,Y=v=>m.t+(hi-v)/(hi-lo||1)*ph;
  let o='';for(let v=lo;v<=hi;v+=Math.max(.5,Math.ceil((hi-lo)/6*2)/2))o+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--rule)"/><text x="${m.l-8}" y="${Y(v)+4}" text-anchor="end" font-size="12" fill="var(--ink-3)">${sgn(v)}</text>`;
  const days=[];t.forEach((v,i)=>{const d=new Date(v).toLocaleDateString('en-US',{weekday:'short',timeZone:'America/New_York'});if(!days.length||days[days.length-1][1]!==d)days.push([i,d])});
  days.forEach(([i,d])=>o+=`<text x="${X(t[i])}" y="${H-8}" font-size="12" fill="var(--ink-3)">${d}</text>`);
  if(L!=null)o+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(L)}" y2="${Y(L)}" stroke="var(--line)" stroke-width="3"/><text x="${W-m.r}" y="${Y(L)-6}" text-anchor="end" font-size="12" font-weight="600" fill="var(--ink)">Pool line ${sgn(L)}</text>`;
  const path=a=>{let d='',pen=false;a.forEach((v,i)=>{if(v==null){pen=false;return}d+=(pen?'L':'M')+X(t[i])+','+Y(v*flip);pen=true});return d};
  books.filter(([b])=>b!==ref).forEach(([b,a])=>o+=`<path d="${path(a)}" fill="none" stroke="var(--ink-3)" stroke-opacity=".35" stroke-width="1.25"/>`);
  const r=books.find(([b])=>b===ref);if(r)o+=`<path d="${path(r[1])}" fill="none" stroke="var(--ink)" stroke-width="2.5" stroke-linejoin="round"/>`;
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(team)} spread by book over the week">${o}</svg>`;
  key.innerHTML=`<span><i style="background:var(--ink)"></i>${esc(ref[0].toUpperCase()+ref.slice(1))}</span><span><i style="background:var(--ink-3);opacity:.5"></i>${books.length-(r?1:0)} other books</span><span><i style="background:var(--line)"></i>Pool line</span>`;
}

/* ---------- performance ---------- */
const MODELS=[['official','Official pick','--s-off'],['v3','Player projection','--s-v3'],['hybrid','Hybrid','--s-hy'],['v1','Team-only projection','--s-v1'],['keynum','Key-number variant','--s-key']];
const BASES=[['favorite','Always the favorite'],['home','Always the home team']];
let on=new Set(['official','hybrid']);
function wilson(w,n,z=1.96){if(!n)return [0,0];const p=w/n,d=1+z*z/n,c=p+z*z/(2*n),h=z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n));return [(c-h)/d,(c+h)/d]}
function perf(){
  const v=$('v-performance'),mk=k=>(D.models||[]).find(x=>x.label.startsWith(k));
  const tiles=[['Official',mk('Official'),'--s-off'],['Hybrid',mk('Hybrid'),'--s-hy'],['Team-only',mk('Team-only'),'--s-v1'],['Player',mk('Player'),'--s-v3']].filter(t=>t[1]);
  const n=D.graded||0,claim=D.claim_at||256,cal=D.calib||[];
  v.innerHTML=`<div class="hero"><p class="kicker">Graded against the pool line · ${n} live games</p><h1>Too early to call</h1>
      <p>After ${n} games, a coin-flipper’s record lands within ±${Math.round(1.96*Math.sqrt(n))} wins of even 95% of the time. The pre-registered rule makes no claim of skill before ${claim} graded games.</p></div>
    <div class="tiles">${tiles.map(([k,x,c])=>{const t=x.W+x.L,[a,b]=wilson(x.W,t);return `<div class="tile" style="--c:var(${c})"><span class="big">${x.W}–${x.L}</span><b>${esc(x.label.replace(' (tracked)',''))}</b><small>${t?pct(x.W/t):'—'} · 95% range ${pct(a)}–${pct(b)}</small></div>`}).join('')}
      <div class="tile"><span class="big">${n}<span class="m" style="font-size:.45em">/${claim}</span></span><b>Games toward a verdict</b><div class="prog" style="margin-top:8px"><i style="width:${Math.min(100,n/claim*100)}%"></i></div></div></div>
    <div class="panel"><div class="ph"><h2>Wins minus losses against the pool line, game by game</h2><p>${esc(D.curve&&D.curve.verdict||'')}</p></div>
      <div class="pb" style="display:flex;flex-direction:column;gap:12px"><div class="toggles" id="tog"></div><div class="chart" id="cum"></div>
      <details class="more"><summary>As a table</summary><div class="tbl" id="cum-t"></div></details></div></div>
    <div class="side">
      <div class="panel"><div class="ph"><h2>Calibration</h2><p>Stated cover chance vs how often it covered</p></div><div class="pb"><div class="chart" id="cal"></div><p class="kicker" id="cal-n" style="margin-top:8px"></p></div></div>
      <div class="panel"><div class="ph"><h2>Week by week</h2><p>Live weeks only</p></div><div class="pb tbl" id="wk-t"></div></div>
    </div>`;
  toggles();cum();calib(cal);weeks();
}
function toggles(){
  $('tog').innerHTML=MODELS.map(([k,lab,c])=>`<button type="button" data-k="${k}" aria-pressed="${on.has(k)}"><i style="background:var(${c})"></i>${lab}</button>`).join('');
  $('tog').querySelectorAll('button').forEach(b=>b.onclick=()=>{const k=b.dataset.k;on.has(k)?on.delete(k):on.add(k);if(!on.size)on.add('official');toggles();cum()});
}
function cum(){
  const C=D.curve||{},gs=C.games||[];const box=$('cum');if(!gs.length){box.innerHTML='<p class="empty">No graded games yet.</p>';return}
  const keys=[...MODELS.filter(m=>on.has(m[0])),...BASES.map(b=>[b[0],b[1],'--base'])];
  const series=Object.fromEntries(keys.map(([k])=>{let c=0;return [k,gs.map(g=>c+=(g.d[k]||0))]}));
  const n=gs.length,band=C.band||gs.map((g,i)=>1.96*Math.sqrt(i+1));
  const W=Math.max(320,box.clientWidth||900),H=W<600?250:300,m={l:38,r:56,t:12,b:28},pw=W-m.l-m.r,ph=H-m.t-m.b;
  const ymax=Math.max(8,Math.ceil(Math.max(...band,...Object.values(series).flat().map(Math.abs))/4)*4);
  const X=i=>m.l+i/(n-1||1)*pw,Y=v=>m.t+(ymax-v)/(2*ymax)*ph;
  let o='';for(let v=-ymax;v<=ymax;v+=ymax/2)o+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--rule)" stroke-width="${v?1:1.5}"/><text x="${m.l-8}" y="${Y(v)+4}" text-anchor="end" font-size="12" fill="var(--ink-3)">${v>0?'+':v<0?MINUS:''}${Math.abs(v)}</text>`;
  const live=gs.findIndex(g=>g.kind==='live');
  if(live>0)o+=`<rect x="${m.l}" y="${m.t}" width="${X(live)-m.l}" height="${ph}" fill="var(--panel-2)"/><text x="${m.l+6}" y="${m.t+14}" font-size="12" fill="var(--ink-3)">Backtest weeks</text>`;
  o+=`<path d="M${band.map((b,i)=>X(i)+','+Y(b)).join('L')}L${band.map((b,i)=>[i,b]).reverse().map(([i,b])=>X(i)+','+Y(-b)).join('L')}Z" fill="var(--ink)" fill-opacity=".07"/>`;
  let wk=null;gs.forEach((g,i)=>{if(g.week!==wk){wk=g.week;o+=`<text x="${X(i)}" y="${H-8}" font-size="12" fill="var(--ink-3)">W${wk}</text>`}});
  const ends=[];
  keys.forEach(([k,lab,c])=>{const s=series[k],base=c==='--base';
    o+=`<path d="M${s.map((v,i)=>X(i)+','+Y(v)).join('L')}" fill="none" stroke="var(${c})" stroke-width="${base?1.25:k==='official'?2.75:2}" ${base?'stroke-dasharray="3 4"':''} stroke-linejoin="round"/>`;
    if(!base)ends.push([Y(s[n-1]),s[n-1],c,lab])});
  ends.sort((a,b)=>a[0]-b[0]);for(let i=1;i<ends.length;i++)if(ends[i][0]-ends[i-1][0]<15)ends[i][0]=ends[i-1][0]+15;
  ends.forEach(([yy,v,c])=>o+=`<text x="${W-m.r+6}" y="${yy+4}" font-size="12.5" font-weight="700" fill="var(--ink)"><tspan fill="var(${c})">●</tspan> ${v>0?'+':v<0?MINUS:''}${Math.abs(v)}</text>`);
  o+=`<line id="cx" y1="${m.t}" y2="${m.t+ph}" stroke="var(--ink-3)" visibility="hidden"/><rect id="ch" x="${m.l}" y="${m.t}" width="${pw}" height="${ph}" fill="transparent"/>`;
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative wins minus losses for ${keys.filter(k=>k[2]!=='--base').map(k=>k[1]).join(', ')}">${o}</svg><div class="legend" style="margin-top:6px"><span><i style="background:var(--ink);opacity:.15;height:10px;vertical-align:0"></i>95% coin-flip range</span>${BASES.map(b=>`<span><i style="background:repeating-linear-gradient(90deg,var(--base) 0 3px,transparent 3px 6px)"></i>${b[1]}</span>`).join('')}</div>`;
  const svg=box.querySelector('svg'),cx=svg.querySelector('#cx'),tip=$('tip');
  svg.querySelector('#ch').addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect(),px=(e.clientX-r.left)*(W/r.width),i=Math.max(0,Math.min(n-1,Math.round((px-m.l)/pw*(n-1))));
    cx.setAttribute('x1',X(i));cx.setAttribute('x2',X(i));cx.setAttribute('visibility','visible');
    tip.hidden=false;tip.innerHTML=`Week ${gs[i].week} · ${esc(gs[i].label)}${gs[i].kind==='backtest'?' (backtest)':''}<br>`+keys.map(([k,lab])=>`${esc(lab)} ${series[k][i]>0?'+':''}${series[k][i]}`).join('<br>');
    tip.style.left=Math.min(innerWidth-tip.offsetWidth-8,e.clientX+12)+'px';tip.style.top=(e.clientY+scrollY-tip.offsetHeight-12)+'px'});
  svg.querySelector('#ch').addEventListener('pointerleave',()=>{tip.hidden=true;cx.setAttribute('visibility','hidden')});
  $('cum-t').innerHTML=`<table><thead><tr><th>Week</th><th>Games</th>${keys.map(k=>`<th>${esc(k[1])}</th>`).join('')}</tr></thead><tbody>${[...new Set(gs.map(g=>g.week))].map(w=>{const last=gs.map((g,i)=>[g,i]).filter(([g])=>g.week===w).pop()[1];
    return `<tr><td>Week ${w}${gs[last].kind==='backtest'?' (backtest)':''}</td><td>${gs.filter(g=>g.week===w).length}</td>${keys.map(([k])=>`<td>${series[k][last]>0?'+':''}${series[k][last]}</td>`).join('')}</tr>`}).join('')}</tbody></table>`;
}
function calib(cal){
  const box=$('cal');if(!cal.length){box.innerHTML='<p class="empty">No graded picks with a cover chance yet.</p>';return}
  const edges=[0,.47,.5,.53,.56,1],bins=edges.slice(0,-1).map((a,i)=>{const b=edges[i+1],xs=cal.filter(c=>c.p>=a&&c.p<b);
    return {a,b,n:xs.length,w:xs.reduce((s,c)=>s+c.w,0),mp:xs.length?xs.reduce((s,c)=>s+c.p,0)/xs.length:null}}).filter(b=>b.n);
  const W=Math.max(300,box.clientWidth||500),H=260,m={l:44,r:14,t:12,b:34},pw=W-m.l-m.r,ph=H-m.t-m.b,lo=.3,hi=.8;
  const X=p=>m.l+(p-lo)/(hi-lo)*pw,Y=p=>m.t+(hi-p)/(hi-lo)*ph;
  let o='';for(let v=.3;v<=.801;v+=.1)o+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--rule)"/><text x="${m.l-8}" y="${Y(v)+4}" text-anchor="end" font-size="12" fill="var(--ink-3)">${Math.round(v*100)}%</text><text x="${X(v)}" y="${H-12}" text-anchor="middle" font-size="12" fill="var(--ink-3)">${Math.round(v*100)}%</text>`;
  o+=`<line x1="${X(lo)}" y1="${Y(lo)}" x2="${X(hi)}" y2="${Y(hi)}" stroke="var(--ink-3)" stroke-dasharray="4 4"/>`;
  bins.forEach(b=>{const [a,c]=wilson(b.w,b.n),r=b.w/b.n;o+=`<line x1="${X(b.mp)}" x2="${X(b.mp)}" y1="${Y(Math.min(hi,c))}" y2="${Y(Math.max(lo,a))}" stroke="var(--s-off)" stroke-width="2"/><circle cx="${X(b.mp)}" cy="${Y(Math.max(lo,Math.min(hi,r)))}" r="${4+Math.sqrt(b.n)*1.4}" fill="var(--s-off)" stroke="var(--panel)" stroke-width="2"><title>${pct(b.a)}–${pct(b.b)} stated: ${b.w} of ${b.n} covered (${pct(r)}), 95% range ${pct(a)}–${pct(c)}</title></circle><text x="${X(b.mp)+8+Math.sqrt(b.n)*1.4}" y="${Y(Math.max(lo,Math.min(hi,r)))+4}" font-size="11.5" fill="var(--ink-2)">${b.n}</text>`});
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Calibration of the stated cover chance">${o}</svg>`;
  const brier=cal.reduce((s,c)=>s+(c.p-c.w)**2,0)/cal.length,ll=-cal.reduce((s,c)=>s+(c.w?Math.log(c.p):Math.log(1-c.p)),0)/cal.length;
  $('cal-n').textContent=`${cal.length} graded picks with a stated chance. Brier score (mean squared error of the stated chance, lower is better) ${brier.toFixed(3)}; a coin flip scores 0.250. Log loss ${ll.toFixed(3)}; a coin flip scores 0.693. Each dot is a group of picks, labelled with how many; the bar is its 95% range. Dots on the dashed line would be perfect calibration. With this few picks every range is wide.`;
}
function weeks(){
  const T=(D.season_tab||[]).filter(r=>r.kind==='live');const box=$('wk-t');if(!T.length){box.innerHTML='<p class="empty">No live weeks yet.</p>';return}
  const cols=[['official','Official'],['hybrid','Hybrid'],['v1','Team-only'],['v3','Player'],['keynum','Key-number']];
  const cell=r=>r?`<td class="${r[0]>r[1]?'up':r[0]<r[1]?'dn':''}">${r[0]}–${r[1]}</td>`:'<td>—</td>';
  box.innerHTML=`<table><thead><tr><th>Week</th>${cols.map(c=>`<th>${c[1]}</th>`).join('')}</tr></thead><tbody>${T.map(r=>`<tr><td>Week ${r.week}</td>${cols.map(([k])=>cell(r.rec[k])).join('')}</tr>`).join('')}</tbody></table>`;
}

/* ---------- method ---------- */
function method(){
  const c=D.dist_check||{},one=Object.values(DIST)[0];
  $('v-method').innerHTML=`<div class="hero"><p class="kicker">How a pick is made</p><h1>Method</h1><p>Bonsai ATS picks every game against the spread (ATS) for the CBS Bonsai pool: one side per game, graded against the pool’s line.</p></div>
  <div class="prose">
    <h2>The pick</h2><p>The pool freezes its line on Tuesday. By kickoff the betting market may have moved off it. The model takes the side the market moved toward: <b>Pinnacle's line at the lock</b>, 20 minutes before kickoff, is the market input. If Pinnacle is missing it retries once, then reads Pinnacle from OddsPapi, then from OddsLink, and only then uses the median of every book.</p>
    <h2>The cover chance</h2><p>The model predicts the whole distribution of the final margin from two inputs: the market spread at the lock and the market total. It uses every NFL game since 1999 with a closing line, re-centred on this game’s spread and scaled by its total${one?` (${esc(one.model)})`:''}. The cover chance is the share of that distribution beyond the pool line. The matchup page draws it and lets you move the line.</p>
    <p>${c.n?`Check on this page’s data: the exported distribution reproduces the recorded cover chance for <b>${c.ok} of ${c.n}</b> picks this week.`:''} Picks made with no market line have no distribution and no cover chance.</p>
    <h2>The record</h2><p>Every official pick is graded against the pool line, the number the pool grades on. Nothing is filtered and missed picks stay missed. The test was registered in advance: <b>no claim of skill before ${D.claim_at||256} graded games</b>. The projections and the hybrid are tracked for comparison and never make the pick.</p>
    <h2>Freshness</h2><p>Updated ${esc(D.updated)}. Odds-feed credits left: ${D.credits??'unknown'}.</p>
  </div>`;
}

/* ---------- router ---------- */
const views=['slate','game','performance','method'];let cur=null;
function route(){
  const [path,qs]=(location.hash||'#/slate').slice(2).split('?'),h=path.split('/'),name=views.includes(h[0])?h[0]:'slate',arg=decodeURIComponent(h[1]||'');
  if(name==='slate'){readQ(qs);setTimeout(save)}
  const go=()=>{views.forEach(v=>$('v-'+v).hidden=v!==name);
    document.querySelectorAll('.tabs a').forEach(a=>a.setAttribute('aria-current',a.dataset.v===name?'page':'false'));
    ({slate,game:()=>game(arg),performance:perf,method})[name]();
    if(cur!==null){window.scrollTo(0,0);$('main').focus({preventScroll:true})}cur=name;
    document.title=(name==='game'&&byId[arg]?`${byId[arg].away} @ ${byId[arg].home} · `:'')+`Week ${D.week} · Bonsai ATS`};
  if(document.startViewTransition&&!REDUCED&&cur!==null)document.startViewTransition(go);else go();
}
addEventListener('hashchange',route);
addEventListener('keydown',e=>{if(e.target.closest('input,select,textarea'))return;const h=location.hash.split('/');if(h[1]!=='game')return;
  const o=order(),i=o.findIndex(g=>g.id===decodeURIComponent(h[2]||''));if(e.key==='ArrowRight'&&o[i+1])location.hash='#/game/'+o[i+1].id;if(e.key==='ArrowLeft'&&o[i-1])location.hash='#/game/'+o[i-1].id});
let rz;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(()=>{if(cur==='game'||cur==='performance')route()},200)});
shell();route();
</script>
</body>
</html>
"""
