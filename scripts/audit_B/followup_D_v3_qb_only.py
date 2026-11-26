# QB-only v3 vs full v3: identical team-games, identical features (build once), identical fit window (2013-2021), tests 2022-2025.
import sys,pickle; sys.path.insert(0,'src')
import numpy as np, polars as pl, pandas as pd, statsmodels.api as sm
from engine.backtest import players_v3_eval as E
from engine.features import players_v3 as V
from engine.models import projection as P
d=pl.read_parquet('/tmp/audit_B/v3_design.parquet'); reg=pl.read_parquet('/tmp/audit_B/v3_reg.parquet'); res=pickle.load(open('/tmp/audit_B/v3_res.pkl','rb'))['res']
ALL=list(V.FEATURES); print('features',ALL)
# complete-case: both models use exactly the same rows (drop team-games with any null feature or rate)
need=ALL+['lam_td','lam_fg','td','fg']
nb=d.height; d=d.drop_nulls(need); print('team-games',nb,'->',d.height,'after dropping nulls')
MG=np.arange(-P.MAXP,P.MAXP+1)
def fit_run(feats):
    V.FEATURES=feats
    tr=E._split(d,*E.TRAIN); beta=E.fit_beta(tr); out={}
    for name,(lo,hi) in {'train 2013-2021':E.TRAIN,'2022':(2022,2022),'2023':(2023,2023),'2024':(2024,2024),'2025':(2025,2025),'Test A 2022-2024':E.TEST_A,'Test B+A 2022-2025':(2022,2025)}.items():
        s=E._split(reg,lo,hi); pm=E.game_pmfs(E._split(d,lo,hi),s,beta); out[name]=pm
    V.FEATURES=ALL
    return beta,out
def v1_run():
    V.FEATURES=ALL; out={}
    for name,(lo,hi) in {'train 2013-2021':E.TRAIN,'2022':(2022,2022),'2023':(2023,2023),'2024':(2024,2024),'2025':(2025,2025),'Test A 2022-2024':E.TEST_A,'Test B+A 2022-2025':(2022,2025)}.items():
        s=E._split(reg,lo,hi); out[name]=E.game_pmfs(E._split(d,lo,hi),s,None)
    return out
pm_v1=v1_run()
bq,pm_q=fit_run(['qb_delta']); bf,pm_f=fit_run(ALL)
nonqb=[f for f in ALL if f!='qb_delta']; bn,pm_n=fit_run(nonqb)
print('QB-only TD beta %.3f (se %.3f), FG beta %.3f (se %.3f)'%(bq['td']['b'][1],bq['td']['se'][1],bq['fg']['b'][1],bq['fg']['se'][1]))
print('full v3 TD qb beta %.3f (se %.3f)'%(bf['td']['b'][1],bf['td']['se'][1]))
models={'v1 (no player terms)':pm_v1,'QB-only (2 betas+int)':pm_q,'full v3 (12 features)':pm_f,'everything except QB (11)':pm_n}
rng=np.random.default_rng(11)
def lls(pm):
    return pd.Series({g:np.log(max(float(p[int(res[g])+P.MAXP]),1e-12)) for g,p in pm.items() if g in res})
print('\nMean margin log-likelihood per game (higher better), identical games across models')
tab={}
for blk in pm_f.keys():
    common=set(pm_f[blk])&set(pm_q[blk])&set(pm_v1[blk])&set(pm_n[blk])&set(res)
    row={}
    for n,pmx in models.items():
        s=lls({g:pmx[blk][g] for g in common}); row[n]=s
    tab[blk]=row; 
    print('%-20s n=%4d '%(blk,len(common))+'  '.join('%s %.4f'%(n.split(' ')[0] if n.startswith(('v1','QB','full')) else 'noQB',row[n].mean()) for n in models))
def paired(a,b,blk,B=2000):
    d_=(tab[blk][a]-tab[blk][b]).values; bs=[d_[rng.integers(0,len(d_),len(d_))].mean() for _ in range(B)]
    return d_.mean(),d_.std(ddof=1)/np.sqrt(len(d_)),np.percentile(bs,[2.5,97.5])
print('\nPaired differences (per game) with 95% bootstrap CI')
for blk in ['Test A 2022-2024','2025','Test B+A 2022-2025','2022','2023','2024','train 2013-2021']:
    for a,b in [('QB-only (2 betas+int)','v1 (no player terms)'),('full v3 (12 features)','v1 (no player terms)'),('full v3 (12 features)','QB-only (2 betas+int)'),('everything except QB (11)','v1 (no player terms)')]:
        m,se,ci=paired(a,b,blk); print('  %-18s %-26s minus %-22s %+.5f (SE %.5f) [%+.5f, %+.5f]'%(blk,a,b,m,se,ci[0],ci[1]))
# incremental info vs market: margin ~ close + (model mean margin - close)
sched=reg.select('game_id','result','spread_line').to_pandas().set_index('game_id')
print('\nWeight on model disagreement with the close (regress actual margin on close and (model mean margin - close)); identical games')
for blk in ['Test A 2022-2024','2025','Test B+A 2022-2025']:
    common=set(pm_f[blk])&set(pm_q[blk])&set(pm_v1[blk])&set(res); ids=sorted(g for g in common if not pd.isna(sched.spread_line.get(g)))
    for n,pmx in models.items():
        mm=np.array([float((MG*pmx[blk][g]).sum()) for g in ids]); close=sched.loc[ids,'spread_line'].values; y=sched.loc[ids,'result'].values
        X=sm.add_constant(np.column_stack([close,mm-close])); fit=sm.OLS(y,X).fit(cov_type='HC1')
        print('  %-20s %-28s n=%d weight %+.3f (SE %.3f)  MAE model %.3f  MAE close %.3f'%(blk,n,len(ids),fit.params[2],fit.bse[2],np.abs(y-mm).mean(),np.abs(y-close).mean()))
