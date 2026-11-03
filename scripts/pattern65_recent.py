"""Companion to pattern65_search.py: the same search on 2022-25 alone and pooled 2007-25.
Usage: python scripts/pattern65_recent.py NFLVERSE_GAMES_CSV OUT_JSON  (needs data/backtests/gap2022_games.csv)."""
import sys; sys.path.insert(0,'scripts')
import pandas as pd, numpy as np, json
import pattern65_search as P
W=sys.argv[1]
g=pd.read_csv(W)
bt=P.load_backtest(g); gp=P.load_gap2022(); c25=P.load_2025(); lv=P.load_live(g)
cols=['game_id','season','week','home_team','away_team','pick','line','mkt','p_home','w']
allp=pd.concat([d[cols].assign(src=n) for n,d in [('bt',bt),('gp',gp),('c25',c25)]],ignore_index=True)
feats=["side","role","spread","keyline","week","slot","div","roof","rest","total","conf","move","team"]
out={}
def run(name,d,min_n,seed):
    d=d.reset_index(drop=True); f=P.add_features(d,g); y=d.w.to_numpy()
    P.RNG=np.random.default_rng(seed)
    r,_,_=P.scan(f,y,feats,3,min_n,label=name)
    r['hits']=r['hits'][:15]
    out[name]=r
    print(name,len(d),'base',round(r['base_rate'],3),'subsets',r['n_subsets'],'hits65',r['real_hits'],'null',round(r['null_hits_mean'],1),'p95',r['null_hits_p95'],'P',r['null_hits_ge_real'],'holm best',r['holm_best_p_vs_base'],'bar',r['holm_bar_first'])
    for h in r['hits'][:8]: print('   ',h['subset'],h['n'],h['w'],round(h['rate'],3),'%.1e'%h['p_vs_base'])
run('recent_2022_25',allp[allp.season>=2022],25,1)
run('pooled_2007_25',allp,30,2)
json.dump(out,open(sys.argv[2],'w'),indent=1,default=float)
