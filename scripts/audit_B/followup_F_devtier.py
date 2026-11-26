# Development-tier test of the disagreement layer (docs/disagreement_model_preregistration.md): feature blocks Q, I, X
# predicting the market residual r = margin + close, orthogonalised against the close, rolling origin 2013-2021.
# Run followup_D_prepare.py first (writes the cached v3 design matrix).
import sys,json; sys.path.insert(0,'src')
import numpy as np, polars as pl, pandas as pd
from math import erf, sqrt
from engine.models import projection as P
d=pl.read_parquet('/tmp/audit_B/v3_design.parquet').to_pandas(); reg=pl.read_parquet('/tmp/audit_B/v3_reg.parquet').to_pandas()
FR=P.FRANCHISE
reg['h']=reg.home_team.replace(FR); reg['a']=reg.away_team.replace(FR)
reg=reg[(reg.game_type=='REG')&reg.result.notna()&reg.spread_line.notna()][['game_id','season','h','a','result','spread_line']]
BLOCKS={'Q':['qb_delta'],'I':['ol','skill','opp_dl','opp_lb','opp_db'],'X':['rest_diff','short_week','off_bye','tz_shift']}
# division and dome are game-level (same for both teams) so their home-minus-away difference is zero: they move totals, not margins
feats=[f for b in BLOCKS.values() for f in b]
h=reg.merge(d[['game_id','team']+feats],left_on=['game_id','h'],right_on=['game_id','team']).drop(columns='team')
a=reg.merge(d[['game_id','team']+feats],left_on=['game_id','a'],right_on=['game_id','team']).drop(columns='team')
G=h[['game_id','season','result','spread_line']].copy()
for f in feats: G[f]=h[f].values-a.set_index('game_id').loc[h.game_id,f].values
G['c']=-G.spread_line; G['r']=G.result+G.c      # r = margin + close: the part of the result the market did not predict
print('games',len(G),'seasons',G.season.min(),G.season.max(),'features',feats)
def ortho(tr,te,cols):
    """Residualise features on the close (linear + quadratic) using training rows only."""
    Xc=lambda df:np.column_stack([np.ones(len(df)),df.c.values,df.c.values**2])
    B=np.linalg.lstsq(Xc(tr),tr[cols].values,rcond=None)[0]
    return tr[cols].values-Xc(tr)@B, te[cols].values-Xc(te)@B
def ridge_fit(X,y,alpha):
    mu=X.mean(0); sd=X.std(0)+1e-9; Z=(X-mu)/sd; ym=y.mean()
    w=np.linalg.solve(Z.T@Z+alpha*np.eye(Z.shape[1]),Z.T@(y-ym)); return mu,sd,w,ym
def ridge_pred(m,X): mu,sd,w,ym=m; return ((X-mu)/sd)@w+ym
def pick_alpha(tr,cols):
    best=None; seasons=sorted(tr.season.unique())
    for al in [30,300,3000,30000]:
        sse=0
        for s in seasons:
            a_=tr[tr.season!=s]; b_=tr[tr.season==s]; Xa,Xb=ortho(a_,b_,cols); m=ridge_fit(Xa,a_.r.values,al); sse+=((b_.r.values-ridge_pred(m,Xb))**2).sum()
        if best is None or sse<best[0]: best=(sse,al)
    return best[1]
def run(blockset,train_hi,test_years):
    cols=[f for b in blockset for f in BLOCKS[b]]; out=[]
    for Y in test_years:
        tr=G[(G.season>=2013)&(G.season<min(Y,train_hi+1))] if train_hi else G[(G.season>=2013)&(G.season<Y)]; te=G[G.season==Y]
        al=pick_alpha(tr,cols); Xa,Xb=ortho(tr,te,cols); m=ridge_fit(Xa,tr.r.values,al); mu=ridge_pred(m,Xb)
        sig=tr.r.std(); base=tr.r.mean()
        gain=((te.r.values-base)**2-(te.r.values-mu)**2)/(2*sig**2)       # normal log-score gain over the baseline centre, per game
        out.append(pd.DataFrame({'season':Y,'r':te.r.values,'mu':mu-base,'gain':gain,'alpha':al}))
    return pd.concat(out)
def summarize(R,label):
    n=len(R); g=R.gain.values; se=g.std(ddof=1)/np.sqrt(n); t=g.mean()/se
    from scipy import stats
    p1=1-stats.norm.cdf(t)
    X=np.column_stack([np.ones(n),R.mu.values]); beta=np.linalg.lstsq(X,R.r.values,rcond=None)[0]; res=R.r.values-X@beta
    cov=np.linalg.inv(X.T@X)@(X.T*res**2)@X@np.linalg.inv(X.T@X); b,sb=beta[1],np.sqrt(cov[1,1]); sdmu=R.mu.std()
    print('%-34s n=%4d  mean log-score gain %+.5f (SE %.5f) one-sided p=%.3f | slope of r on prediction %+.2f (SE %.2f) | prediction SD %.2f pts -> effective shift SD %.2f pts (SE %.2f)'%(label,n,g.mean(),se,p1,b,sb,sdmu,b*sdmu,sb*sdmu))
    return {'label':label,'n':n,'gain':g.mean(),'se':se,'p1':p1,'slope':b,'slope_se':sb,'pred_sd':sdmu,'eff_shift':b*sdmu,'eff_shift_se':sb*sdmu}
print('\n=== Development tier: rolling origin, train 2013..Y-1, test 2016-2021 (confirmation not claimed) ===')
rows=[]
for lab,bs in [('Q (qb_delta)','Q'),('I (injury loads)','I'),('X (rest/bye/short/travel)','X'),('Q+I+X combined','QIX')]:
    R=run(list(bs),None,range(2016,2022)); rows.append(summarize(R,lab))
ps=sorted([(r['p1'],r['label']) for r in rows[:3]]); print('\nHolm over the three blocks Q, I, X (alpha 0.05): thresholds 0.0167, 0.0250, 0.0500')
for i,(p,l) in enumerate(ps): print('  %-28s p=%.3f  threshold %.4f  %s'%(l,p,0.05/(3-i),'PASS' if p<=0.05/(3-i) else 'fail')); 
print('\n=== Burned tier (non-confirmatory consistency check): train 2013-2021 only, test 2022-2025 ===')
for lab,bs in [('Q (qb_delta)','Q'),('I (injury loads)','I'),('X (rest/bye/short/travel)','X'),('Q+I+X combined','QIX')]:
    R=run(list(bs),2021,range(2022,2026)); summarize(R,lab)
json.dump(rows,open('/tmp/audit_B/devtier.json','w'),indent=1)
