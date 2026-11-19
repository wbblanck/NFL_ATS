# Key-number estimator: what the weights are applied to, and which conditional distribution is correctly specified. Walk-forward 2010-2025.
import sys; sys.path.insert(0,'src')
import numpy as np, polars as pl, nflreadpy as nfl, pandas as pd
from math import erf, sqrt
from engine.models.margin_dist import MarginDist, EPS
s=nfl.load_schedules(seasons=list(range(2000,2026))).filter(pl.col('game_type')=='REG',pl.col('result').is_not_null(),pl.col('spread_line').is_not_null()).select('season','spread_line','result').to_pandas().reset_index(drop=True)
s['c']=-s.spread_line; s['m']=s.result.astype(float)
GRID=np.arange(-80,81); K=20
ncdf=np.vectorize(erf)
def base(c,sig):
    cc=np.asarray(c,float)[:,None]; k=GRID[None,:]
    return 0.5*(1+ncdf((k+0.5+cc)/sig/sqrt(2)))-0.5*(1+ncdf((k-0.5+cc)/sig/sqrt(2)))
def norm(p): return p/p.sum(1,keepdims=True)
def ipf(b,key,obs_idx,nkeys,iters=200):
    """b: games x grid base pmf; key: grid -> weight index (or -1 = weight 1); returns weights matching observed key counts (multinomial MLE)."""
    w=np.ones(nkeys); obs=np.bincount(obs_idx[obs_idx>=0],minlength=nkeys).astype(float)
    for _ in range(iters):
        wk=np.where(key>=0,w[np.clip(key,0,None)],1.0)
        p=norm(b*wk[None,:])
        exp=np.zeros(nkeys)
        for j in range(nkeys): exp[j]=p[:,key==j].sum()
        w2=w*np.where(exp>0,obs/np.maximum(exp,1e-12),1.0)
        if np.max(np.abs(w2-w))<1e-6: w=w2;break
        w=w2
    return w
def fit_models(tr):
    sig=float(np.std(tr.m+tr.c))
    b=base(tr.c.values,sig)
    # actual-margin keys: |k|, 0..20
    key_m=np.where(np.abs(GRID)<=K,np.abs(GRID),-1)
    obs_m=np.where(np.abs(tr.m.values)<=K,np.abs(tr.m.values),-1).astype(int)
    wm=ipf(b,key_m,obs_m,K+1)
    # market-relative keys: 2|r| for r=k+c, per game -> need per-game keys, so build per-game weight matrices by looping idx
    return sig,wm
def ipf_resid(tr,sig,iters=200):
    c=tr.c.values; b=base(c,sig); r2=np.abs(np.round(2*(GRID[None,:]+c[:,None]))).astype(int)  # games x grid index of 2|r|
    keyidx=np.where(r2<=2*K,r2,-1); nk=2*K+1
    obs=np.round(2*np.abs(tr.m.values+c)).astype(int); obs=np.where(obs<=2*K,obs,-1)
    w=np.ones(nk); ob=np.bincount(obs[obs>=0],minlength=nk).astype(float)
    for _ in range(iters):
        wk=np.where(keyidx>=0,w[np.clip(keyidx,0,None)],1.0); p=norm(b*wk)
        exp=np.zeros(nk)
        for j in range(nk): exp[j]=p[keyidx==j].sum()
        w2=w*np.where(exp>0,ob/np.maximum(exp,1e-12),1.0)
        if np.max(np.abs(w2-w))<1e-6: w=w2;break
        w=w2
    return w
def pmf_ratio(c,sig,wr): # code's estimator: weights by |k| from simple observed/expected ratio
    pass
rows=[]; cover=[]
for Y in range(2010,2026):
    tr=s[s.season<Y]; te=s[s.season==Y]
    sig,wm=fit_models(tr); wr=ipf_resid(tr,sig)
    kn=MarginDist('keynum').fit(tr.c.values,tr.m.values)
    c=te.c.values; m=te.m.values.astype(int); bt=base(c,sig)
    # N
    pN=bt
    # K (as coded)
    pK=kn.pmf(c)
    # KM: actual-margin atoms by multinomial MLE
    wk=np.where(np.abs(GRID)<=K,wm[np.clip(np.abs(GRID),0,K)],1.0); pKM=norm(bt*wk[None,:])
    # KR: market-relative atoms
    r2=np.abs(np.round(2*(GRID[None,:]+c[:,None]))).astype(int); wkr=np.where(r2<=2*K,wr[np.clip(r2,0,2*K)],1.0); pKR=norm(bt*wkr)
    # R1: empirical residual pmf by parity of c, 3% normal-smoothing mixture
    trr=(tr.m+tr.c).values; par_tr=(tr.c.values%1==0)
    pR=np.zeros_like(bt)
    for par in [True,False]:
        sel=par_tr==par; rv=np.round(2*trr[sel]).astype(int)  # half-units
        cnt=pd.Series(rv).value_counts()
        te_sel=(c%1==0)==par
        for i in np.where(te_sel)[0]:
            rr=np.round(2*(GRID+c[i])).astype(int)
            emp=np.array([cnt.get(x,0) for x in rr],float); emp=emp/ max(sel.sum(),1)
            pR[i]=0.97*emp+0.03*bt[i]
    pR=norm(pR)
    idx=m+80
    for name,p in [('normal',pN),('keynum as coded',pK),('keynum MLE actual-margin',pKM),('keynum MLE market-relative',pKR),('empirical residual by parity',pR)]:
        lp=np.log(np.clip(p[np.arange(len(m)),idx],1e-12,None))
        rows.append(pd.DataFrame({'season':Y,'model':name,'logp':lp,'g':np.arange(len(m))+Y*1000}))
    # cover-probability scores at pick-like lines, d=S-c in -2..2 (|d|<=2)
    for j in range(-3,4):
        S=np.floor(c)+0.5+j; d=S-c; keep=np.abs(d)<=2.0
        y=(m>-S).astype(float)
        for name,p in [('normal',pN),('keynum as coded',pK),('keynum MLE actual-margin',pKM),('keynum MLE market-relative',pKR),('empirical residual by parity',pR)]:
            ph=(p*(GRID[None,:]>(-S)[:,None])).sum(1); ph=np.clip(ph,EPS,1-EPS)
            cover.append(pd.DataFrame({'season':Y,'model':name,'g':np.arange(len(m))+Y*1000,'d':d,'ll':-(y*np.log(ph)+(1-y)*np.log(1-ph)),'br':(ph-y)**2,'keep':keep}))
L=pd.concat(rows); C=pd.concat(cover)
print('Margin pmf score: mean log P(actual margin), 2010-2025 walk-forward, %d games'%L.g.nunique())
sc=L.groupby('model').logp.mean().sort_values(ascending=False); print(sc.round(5).to_string())
base_m='normal'
rng=np.random.default_rng(3)
def boot(a,b,df,col,B=1500):
    A=df[df.model==a].set_index('g')[col]; Bm=df[df.model==b].set_index('g')[col]; d=(A-Bm); 
    g=d.index.values; v=d.values; bs=[v[rng.integers(0,len(v),len(v))].mean() for _ in range(B)]
    return v.mean(),np.percentile(bs,[2.5,97.5])
print('\nPaired differences in mean log P(actual margin) (positive = first model better):')
for a,b in [('keynum as coded','normal'),('keynum MLE actual-margin','keynum as coded'),('keynum MLE actual-margin','normal'),('keynum MLE market-relative','keynum MLE actual-margin'),('empirical residual by parity','keynum MLE actual-margin'),('empirical residual by parity','normal'),('empirical residual by parity','keynum as coded')]:
    m_,ci=boot(a,b,L,'logp'); print('  %-28s minus %-28s %+.5f  95%% CI [%+.5f, %+.5f]'%(a,b,m_,ci[0],ci[1]))
print('\nCover-probability log loss at pick-like lines |d|<=2 (lower better):')
Q=C[C.keep]; print(Q.groupby('model').agg(logloss=('ll','mean'),brier=('br','mean')).round(5).to_string())
# self-consistency of coded estimator: mean predicted P(|m|=k) vs observed in the test seasons
te=s[s.season>=2010]
print('\nSelf-consistency of the coded key-number estimator (OOS, pooled 2010-2025): predicted vs observed share of |margin| = k')
pred=np.zeros(K+1); n=0
for Y in range(2010,2026):
    tr=s[s.season<Y]; tt=s[s.season==Y]; kn=MarginDist('keynum').fit(tr.c.values,tr.m.values); p=kn.pmf(tt.c.values)
    for j in range(K+1): pred[j]+=p[:,np.abs(GRID)==j].sum()
    n+=len(tt)
obs=np.array([(np.abs(te.m.values)==j).sum() for j in range(K+1)],float)
print(' k   '+' '.join('%5d'%j for j in [0,1,2,3,4,5,6,7,8,10,14]))
print('pred '+' '.join('%5.1f'%(100*pred[j]/n) for j in [0,1,2,3,4,5,6,7,8,10,14]))
print('obs  '+' '.join('%5.1f'%(100*obs[j]/n) for j in [0,1,2,3,4,5,6,7,8,10,14]))
# conditional check: P(margin==+/-3) and P(r==0) by |c| bucket, observed vs coded vs MLE-actual
