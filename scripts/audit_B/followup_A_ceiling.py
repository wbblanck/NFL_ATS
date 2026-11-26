# Expected win rate of the follow-the-move rule: point estimate and statistically supported upper bound.
import csv, numpy as np, pandas as pd
R=pd.read_pickle('/tmp/audit_B/scoreB.pkl')
# pick side wins: home if d>0 (pool easier for home), away if d<=0 (zero -> away)
R['win']=np.where(R.d>0,R.y,1-R.y)
cells=R.groupby('d').win.agg(['mean','count']); print(cells.round(4).T.to_string())
P=[r for r in csv.DictReader(open('data/predictions/predictions.csv')) if r['p_home_cover'] not in ('UNAVAILABLE','') ]
drift=np.array([float(r['drift']) for r in P]); d_live=-drift
print('live picks',len(d_live),'max |d|',np.abs(d_live).max(),'mean |d| %.3f'%np.abs(d_live).mean())
vals,cnt=np.unique(np.round(d_live*2)/2,return_counts=True); print(dict(zip(vals,cnt)))
def rate_table(df):
    t=df.groupby('d').win.mean(); return t
def exp_rate(d_arr,tab):
    ks=tab.index.values; out=[]
    for d in d_arr:
        k=ks[np.argmin(np.abs(ks-d))]; out.append(tab[k])
    return np.mean(out)
pt=exp_rate(d_live,rate_table(R)); print('point estimate expected win rate: %.4f'%pt)
# rule of thumb
print('rule of thumb 50 + 2.9*mean|d| = %.4f'%(0.5+0.029*np.abs(d_live).mean()))
# bootstrap: historical games clustered by gid, and live drift rows
rng=np.random.default_rng(7); gids=R.gid.unique(); byg={g:v for g,v in R.groupby('gid')}
# speed: precompute per-game arrays
Rg=R.groupby('gid'); idx=Rg.indices
ds=R.d.values; ws=R.win.values
bs=[]
dvals=np.array(sorted(R.d.unique()))
gid_arr=R.gid.values
gid_list=np.array(list(idx.keys()))
for b in range(1500):
    gs=rng.choice(gid_list,len(gid_list))
    sel=np.concatenate([idx[g] for g in gs])
    t=pd.Series(ws[sel]).groupby(ds[sel]).mean()
    dl=rng.choice(d_live,len(d_live))
    bs.append(exp_rate(dl,t))
bs=np.array(bs)
print('bootstrap (history resampled by game + live drift mix resampled): mean %.4f  95%% interval [%.4f, %.4f]  95%% one-sided upper %.4f'%(bs.mean(),*np.percentile(bs,[2.5,97.5]),np.percentile(bs,95)))
# history only uncertainty (drift mix fixed)
bs2=[]
for b in range(1500):
    gs=rng.choice(gid_list,len(gid_list)); sel=np.concatenate([idx[g] for g in gs]); t=pd.Series(ws[sel]).groupby(ds[sel]).mean(); bs2.append(exp_rate(d_live,t))
print('history-only uncertainty 95%% interval [%.4f, %.4f]'%tuple(np.percentile(bs2,[2.5,97.5])))
# drift-mix-only
t=rate_table(R); bs3=[exp_rate(rng.choice(d_live,len(d_live)),t) for _ in range(3000)]
print('drift-mix-only uncertainty 95%% interval [%.4f, %.4f]'%tuple(np.percentile(bs3,[2.5,97.5])))
# observed live
w=49;n=95; p=w/n; se=np.sqrt(p*(1-p)/n); print('live 49-46: %.4f, one-sided 95%% upper %.4f, two-sided 95%% [%.4f, %.4f]'%(p,p+1.645*se,p-1.96*se,p+1.96*se))
w=55;n=104; p=w/n; se=np.sqrt(p*(1-p)/n); print('live 55-49 on 104: %.4f, one-sided 95%% upper %.4f'%(p,p+1.645*se))
# by season stability of the rate table (does rate at |d|=1 vary by season?)
R['ad']=R.d.abs(); 
for lo,hi in [(0,0),(0.5,0.5),(1,1),(1.5,2),(2.5,3.5)]:
    Q=R[(R.ad>=lo)&(R.ad<=hi)]; g=Q.groupby('season').win.mean()
    print('|d| %.1f-%.1f: pooled %.4f  season range [%.3f, %.3f], SD across seasons %.3f (sampling SD %.3f)'%(lo,hi,Q.win.mean(),g.min(),g.max(),g.std(),np.sqrt(.25/(len(Q)/16))))
# horizon: seasons needed
for edge in [0.024,0.037]:
    n=((1.645+0.84)*0.5/edge)**2; print('games for 80%% power one-sided 5%% at true edge %.1f pp: %d'%(edge*100,n))
