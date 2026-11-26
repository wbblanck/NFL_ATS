# Run from the repo root: python scripts/audit_B/<name>.py (needs /tmp/audit_B to exist). Read-only audit helper.
import sys; sys.path.insert(0,'src')
import numpy as np, polars as pl, nflreadpy as nfl
from engine.models.margin_dist import MarginDist, TotalDist
s=nfl.load_schedules(seasons=list(range(2000,2026))).filter(pl.col('game_type')=='REG',pl.col('result').is_not_null(),pl.col('spread_line').is_not_null(),pl.col('total_line').is_not_null()).select('spread_line','total_line','result').to_pandas()
c=-s.spread_line.values; m=s.result.values.astype(float); T=s.total_line.values
kn=MarginDist('keynum').fit(c,m); sh=MarginDist('shifted').fit(c,m); td=TotalDist().fit(c,m,T)
print('weights', np.round(kn.w[:21],2))
for cc,t in [(-7,6.5),(-7,7.5),(-3,2.5),(-3,3.5),(-6.5,6.5),(-2.5,2.5),(-10,9.5),(-10,10.5),(-6,5.5),(-6,6.5),(-3.5,3.5)]:
    sel=(c==cc)
    emp=(m[sel]>t).mean() if sel.sum() else float('nan')
    print(f'close {cc:+.1f} line S={-t:+.1f}: n={sel.sum():4d} empirical P(home covers) {emp:.3f} | keynum {kn.sf([t],[cc])[0]:.3f} shifted {sh.sf([t],[cc])[0]:.3f} total {td.sf([t],[cc],[45])[0]:.3f}')
