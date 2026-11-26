# Run from the repo root: python scripts/audit_B/<name>.py (needs /tmp/audit_B to exist). Read-only audit helper.
import sys; sys.path.insert(0,'src')
import numpy as np, polars as pl, nflreadpy as nfl, math, pandas as pd
from engine.models.margin_dist import MarginDist, TotalDist, EPS
s=nfl.load_schedules(seasons=list(range(2000,2027))).filter(pl.col('game_type')=='REG',pl.col('result').is_not_null(),pl.col('spread_line').is_not_null(),pl.col('total_line').is_not_null()).select('season','week','spread_line','total_line','result').to_pandas()
s['c']=-s.spread_line; s['m']=s.result.astype(float); s['T']=s.total_line
print('2026 games', (s.season==2026).sum(), 'int share 2026', (s[s.season==2026].c%1==0).mean())
print('int share 2025 by week', s[s.season==2025].groupby('week').apply(lambda g:(g.c%1==0).mean()).round(2).tolist())
rows=[]
for Y in range(2010,2026):
    tr=s[s.season<Y]; te=s[s.season==Y]
    sh=MarginDist('shifted').fit(tr.c.values,tr.m.values)
    nm=MarginDist('normal').fit(tr.c.values,tr.m.values)
    kn=MarginDist('keynum').fit(tr.c.values,tr.m.values)
    td=TotalDist('shifted_total').fit(tr.c.values,tr.m.values,tr['T'].values)
    base=np.floor(te.c.values)+0.5
    for j in range(-3,4):
        S=base+j; d=S-te.c.values
        t=-S
        y=(te.m.values>t).astype(float)
        out=pd.DataFrame({'season':Y,'c':te.c.values,'d':d,'par':(te.c.values%1==0),'y':y})
        out['shifted']=sh.sf(t,te.c.values); out['normal']=nm.sf(t,te.c.values); out['keynum']=kn.sf(t,te.c.values)
        out['total']=td.sf(t,te.c.values,te['T'].values)
        rows.append(out)
D=pd.concat(rows); D.to_pickle('/tmp/audit_B/cal2.pkl')
print(len(D))
def ll(p,y): p=np.clip(p,EPS,1-EPS); return -(y*np.log(p)+(1-y)*np.log(1-p)).mean()
for k in ['shifted','total','normal','keynum']:
    print(k,'logloss %.5f brier %.5f'%(ll(D[k].values,D.y.values),((D[k]-D.y)**2).mean()))
print('constant-by-d ideal not computed; base rate',D.y.mean())
# reliability by predicted p bins for 'total'
D['bin']=pd.cut(D.total,[0,.1,.2,.3,.4,.45,.5,.55,.6,.7,.8,.9,1])
print(D.groupby('bin',observed=True).agg(n=('y','size'),pred=('total','mean'),act=('y','mean')).round(3).to_string())
# by offset d and parity, home near-zero offsets
for par in [False,True]:
    g=D[(D.par==par)&(D.d.abs()<=2.5)].groupby('d').agg(n=('y','size'),pred=('total','mean'),pred_sh=('shifted','mean'),pred_kn=('keynum','mean'),act=('y','mean'))
    g['se']=np.sqrt(g.act*(1-g.act)/g.n)
    print('integer close' if par else 'half-point close'); print(g.round(3).to_string())
