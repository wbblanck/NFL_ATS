# Key-number estimator specification tests: era drift, spread-dependence, and cover-probability value vs the Official estimator.
import sys; sys.path.insert(0,'src')
import numpy as np, polars as pl, nflreadpy as nfl, pandas as pd
from math import erf, sqrt
from engine.models.margin_dist import TotalDist, EPS
s=nfl.load_schedules(seasons=list(range(2000,2026))).filter(pl.col('game_type')=='REG',pl.col('result').is_not_null(),pl.col('spread_line').is_not_null(),pl.col('total_line').is_not_null()).select('season','spread_line','total_line','result').to_pandas().reset_index(drop=True)
s['c']=-s.spread_line; s['m']=s.result.astype(float); s['T']=s.total_line
GRID=np.arange(-80,81); K=20; ncdf=np.vectorize(erf)
def base(c,sig):
    cc=np.asarray(c,float)[:,None]; k=GRID[None,:]
    return 0.5*(1+ncdf((k+0.5+cc)/sig/sqrt(2)))-0.5*(1+ncdf((k-0.5+cc)/sig/sqrt(2)))
norm=lambda p:p/p.sum(1,keepdims=True)
key=np.where(np.abs(GRID)<=K,np.abs(GRID),-1)
def ipf(b,m,gw,iters=300):
    obs_idx=np.where(np.abs(m)<=K,np.abs(m),-1).astype(int)
    ob=np.zeros(K+1)
    for j in range(K+1): ob[j]=gw[obs_idx==j].sum()
    w=np.ones(K+1)
    for _ in range(iters):
        wk=np.where(key>=0,w[np.clip(key,0,None)],1.0); p=norm(b*wk[None,:])
        ex=np.array([(gw[:,None]*p[:,key==j]).sum() for j in range(K+1)])
        w2=w*np.where(ex>0,ob/np.maximum(ex,1e-12),1.0)
        if np.max(np.abs(w2-w))<1e-6: w=w2;break
        w=w2
    return w
def apply(w,b): 
    wk=np.where(key>=0,w[np.clip(key,0,None)],1.0); return norm(b*wk[None,:])
buckets=[(0,3.01),(3.01,6.51),(6.51,9.51),(9.51,99)]
rm=[];cv=[]; zero=[]
for Y in range(2010,2026):
    tr=s[s.season<Y]; te=s[s.season==Y]; sig=float(np.std(tr.m+tr.c))
    btr=base(tr.c.values,sig); bte=base(te.c.values,sig); m=te.m.values.astype(int); c=te.c.values
    one=np.ones(len(tr)); 
    models={}
    models['A all-history']=apply(ipf(btr,tr.m.values.astype(int),one),bte)
    rec=(tr.season>=Y-10).values
    models['A10 last 10 seasons']=apply(ipf(btr[rec],tr.m.values[rec].astype(int),np.ones(rec.sum())),bte)
    gw=0.5**((Y-1-tr.season.values)/8.0)
    models['Ad half-life 8 seasons']=apply(ipf(btr,tr.m.values.astype(int),gw),bte)
    pb=np.zeros_like(bte)
    for lo,hi in buckets:
        a=(np.abs(tr.c.values)>=lo)&(np.abs(tr.c.values)<hi); b2=(np.abs(c)>=lo)&(np.abs(c)<hi)
        if b2.any(): pb[b2]=apply(ipf(btr[a],tr.m.values[a].astype(int),np.ones(a.sum())),bte[b2])
    models['Ab by spread bucket (all-history)']=pb
    pb2=np.zeros_like(bte)
    for lo,hi in buckets:
        a=(np.abs(tr.c.values)>=lo)&(np.abs(tr.c.values)<hi)&rec; b2=(np.abs(c)>=lo)&(np.abs(c)<hi)
        if b2.any(): pb2[b2]=apply(ipf(btr[a],tr.m.values[a].astype(int),np.ones(a.sum())),bte[b2])
    models['Ab10 bucket + last 10 seasons']=pb2
    models['normal']=bte
    td=TotalDist('shifted_total').fit(tr.c.values,tr.m.values,tr['T'].values)
    gid=np.arange(len(m))+Y*1000
    for n,p in models.items():
        rm.append(pd.DataFrame({'season':Y,'model':n,'g':gid,'logp':np.log(np.clip(p[np.arange(len(m)),m+80],1e-12,None))}))
    for j in range(-3,4):
        S=np.floor(c)+0.5+j; d=S-c; y=(m>-S).astype(float)
        for n,p in list(models.items())+[('OFFICIAL total-shifted',None)]:
            ph=td.sf(-S,c,te['T'].values) if p is None else (p*(GRID[None,:]>(-S)[:,None])).sum(1)
            ph=np.clip(ph,EPS,1-EPS)
            cv.append(pd.DataFrame({'season':Y,'model':n,'g':gid,'d':d,'y':y,'ph':ph,'ll':-(y*np.log(ph)+(1-y)*np.log(1-ph)),'br':(ph-y)**2}))
        # zero-move tie: half-point close and S=c
    p=models['Ab by spread bucket (all-history)']
L=pd.concat(rm); C=pd.concat(cv)
print('Mean log P(actual margin), 2010-2025 walk-forward, 4175 games'); print(L.groupby('model').logp.mean().sort_values(ascending=False).round(5).to_string())
rng=np.random.default_rng(5)
def paired(df,a,b,col,mask=None,B=1500):
    A=df[df.model==a]; Bm=df[df.model==b]
    if mask is not None: A=A[mask(A)]; Bm=Bm[mask(Bm)]
    d=(A[col].values-Bm[col].values); g=A.g.values
    ser=pd.Series(d).groupby(g).sum(); n=pd.Series(1,index=g).groupby(g).sum()
    gs=ser.values; ns=n.reindex(ser.index).values; bs=[]
    for _ in range(B):
        k=rng.integers(0,len(gs),len(gs)); bs.append(gs[k].sum()/ns[k].sum())
    return d.mean(),np.percentile(bs,[2.5,97.5])
print('\nPaired mean log P(actual margin) differences (positive = first better):')
for a,b in [('A10 last 10 seasons','A all-history'),('Ad half-life 8 seasons','A all-history'),('Ab by spread bucket (all-history)','A all-history'),('Ab10 bucket + last 10 seasons','A all-history'),('Ab10 bucket + last 10 seasons','A10 last 10 seasons')]:
    m_,ci=paired(L,a,b,'logp'); print('  %-36s minus %-24s %+.5f [%+.5f, %+.5f]'%(a,b,m_,ci[0],ci[1]))
print('\nCover-probability scores at pick-like lines (|d|<=2): mean log loss / Brier')
mk=lambda D:(D.d.abs()<=2.0).values
Q=C[C.d.abs()<=2.0]; print(Q.groupby('model').agg(logloss=('ll','mean'),brier=('br','mean')).sort_values('logloss').round(5).to_string())
print('\nPaired cover log loss (negative = first better) vs OFFICIAL, |d|<=2 and |d|<=0.5 and integer-close key lines:')
for a in ['A all-history','A10 last 10 seasons','Ab by spread bucket (all-history)','Ab10 bucket + last 10 seasons']:
    for lab,mask in [('|d|<=2',lambda D:(D.d.abs()<=2.0).values),('|d|<=0.5',lambda D:(D.d.abs()<=0.5).values)]:
        m_,ci=paired(C,a,'OFFICIAL total-shifted','ll',mask=mask); print('  %-36s %-8s %+.5f [%+.5f, %+.5f]'%(a,lab,m_,ci[0],ci[1]))
# zero-move tie-break: half-point close, S=c. Win rate of "away" (Official) vs the key-number model's side
Z=C[(C.d==0)]; 
piv=Z.pivot_table(index=['g','season'],columns='model',values='ph').reset_index(); yy=Z[Z.model=='OFFICIAL total-shifted'].set_index('g').y
piv['y']=piv.g.map(yy)
for name in ['A all-history','Ab by spread bucket (all-history)','A10 last 10 seasons']:
    pick_home=piv[name]>0.5; away=1-piv.y; home=piv.y
    win=np.where(pick_home,home,away)
    for lab,msk in [('2010-2021',piv.season<=2021),('2022-2025',piv.season>=2022),('all',piv.season>=0)]:
        print('zero-move games %s: %-34s picks home on %.0f%% ; wins %.3f vs always-away %.3f (n=%d)'%(lab,name,100*pick_home[msk].mean(),win[msk].mean(),away[msk].mean(),msk.sum()))
