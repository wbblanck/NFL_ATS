# Run from repo root. Does the Official estimator add information beyond the drift-only forecaster? Walk-forward 2010-2025.
import sys; sys.path.insert(0,'src')
import numpy as np, polars as pl, nflreadpy as nfl, pandas as pd, statsmodels.api as sm
from engine.models.margin_dist import MarginDist, TotalDist, EPS
s=nfl.load_schedules(seasons=list(range(2000,2026))).filter(pl.col('game_type')=='REG',pl.col('result').is_not_null(),pl.col('spread_line').is_not_null(),pl.col('total_line').is_not_null()).select('season','week','spread_line','total_line','result').to_pandas().reset_index(drop=True)
s['gid']=s.index; s['c']=-s.spread_line; s['m']=s.result.astype(float); s['T']=s.total_line
J=range(-3,4)
def grid(df):
    base=np.floor(df.c.values)+0.5; out=[]
    for j in J:
        S=base+j; out.append(pd.DataFrame({'gid':df.gid.values,'season':df.season.values,'c':df.c.values,'T':df['T'].values,'d':S-df.c.values,'t':-S,'y':(df.m.values>-S).astype(float)}))
    return pd.concat(out,ignore_index=True)
G=grid(s)
def ll(p,y): p=np.clip(p,EPS,1-EPS); return -(y*np.log(p)+(1-y)*np.log(1-p))
res=[]
for Y in range(2010,2026):
    tr=G[G.season<Y]; te=G[G.season==Y].copy(); trg=s[s.season<Y]
    # drift-only lookup by exact d (encodes parity), smoothed
    lk=tr.groupby('d').y.agg(['sum','count']); lk['p']=(lk['sum']+20*0.5)/(lk['count']+20)
    te['p_lookup']=te.d.map(lk.p).values
    # drift-only logistic
    lg=sm.Logit(tr.y.values,sm.add_constant(tr[['d']].values)).fit(disp=0)
    te['p_logit']=lg.predict(sm.add_constant(te[['d']].values))
    td=TotalDist('shifted_total').fit(trg.c.values,trg.m.values,trg['T'].values)
    sh=MarginDist('shifted').fit(trg.c.values,trg.m.values)
    nm=MarginDist('normal').fit(trg.c.values,trg.m.values)
    te['p_official']=td.sf(te.t.values,te.c.values,te['T'].values)
    te['p_shifted']=sh.sf(te.t.values,te.c.values)
    te['p_normal']=nm.sf(te.t.values,te.c.values)
    te['p_const']=0.5
    res.append(te)
R=pd.concat(res,ignore_index=True); R.to_pickle('/tmp/audit_B/scoreB.pkl')
models=['p_const','p_logit','p_lookup','p_normal','p_shifted','p_official']
print('pairs',len(R),'games',R.gid.nunique(),'seasons 2010-2025')
def table(mask,label):
    Q=R[mask]; print('\n',label,'n pairs',len(Q))
    for m in models: print('  %-10s logloss %.5f brier %.5f'%(m,ll(Q[m].values,Q.y.values).mean(),((Q[m]-Q.y)**2).mean()))
table(R.d.abs()>=0,'all offsets |d|<=3.5')
table(R.d.abs()<=2.0,'live-like offsets |d|<=2')
# paired difference official minus lookup/logit with game-clustered bootstrap
rng=np.random.default_rng(1)
def paired(a,b,mask,B=2000,metric='ll'):
    Q=R[mask]; 
    f=(lambda p:ll(p,Q.y.values)) if metric=='ll' else (lambda p:(p-Q.y.values)**2)
    d=f(Q[a].values)-f(Q[b].values)
    g=pd.Series(d).groupby(Q.gid.values).sum(); n=Q.groupby('gid').size()
    ids=g.index.values; gs=g.values; ns=n.values
    bs=[]
    for _ in range(B):
        k=rng.integers(0,len(ids),len(ids)); bs.append(gs[k].sum()/ns[k].sum())
    return d.mean(),np.percentile(bs,[2.5,97.5])
for lab,mask in [('all',R.d.abs()>=0),('|d|<=2',R.d.abs()<=2.0)]:
    for metric in ['ll','brier']:
        for a,b in [('p_official','p_lookup'),('p_official','p_logit'),('p_shifted','p_lookup'),('p_normal','p_lookup'),('p_lookup','p_const')]:
            m,ci=paired(a,b,mask,metric=metric)
            print('%-7s %-5s %-10s minus %-9s mean diff %+.5f  95%% CI [%+.5f, %+.5f]  (negative = first is better)'%(lab,metric,a,b,m,ci[0],ci[1]))
# per-season win count (official better than lookup in how many seasons)
for metric in ['ll']:
    wins=0
    for Y,Q in R.groupby('season'):
        d=ll(Q.p_official.values,Q.y.values).mean()-ll(Q.p_lookup.values,Q.y.values).mean(); wins+=d<0
    print('seasons official log loss < lookup:',wins,'of 16')
# stacking regression: does the official's extra move beyond drift-only lookup carry signal?
lgt=lambda p:np.log(np.clip(p,EPS,1-EPS)/(1-np.clip(p,EPS,1-EPS)))
Q=R.copy(); X=pd.DataFrame({'lk':lgt(Q.p_lookup),'extra':lgt(Q.p_official)-lgt(Q.p_lookup)}); 
m=sm.GLM(Q.y.values,X,family=sm.families.Binomial()).fit(cov_type='cluster',cov_kwds={'groups':Q.gid.values})
print(m.summary().tables[1]); print('SD of extra (logit units): %.4f; mean |extra| prob pts: %.2f pp'%(X.extra.std(),100*(Q.p_official-Q.p_lookup).abs().mean()))
