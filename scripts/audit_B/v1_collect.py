# Run from the repo root: python scripts/audit_B/<name>.py (needs /tmp/audit_B to exist). Read-only audit helper.
import sys,time; sys.path.insert(0,'src')
import numpy as np, polars as pl, nflreadpy as nfl, pandas as pd
from engine.models import projection as P
t0=time.time()
sched=nfl.load_schedules(seasons=list(range(2012,2026)))
ts=nfl.load_team_stats(seasons=list(range(2012,2026)))
print('loaded',time.time()-t0, ts.columns[:12])
games=P.team_games(ts,sched)
reg=sched.filter(pl.col('game_type')=='REG',pl.col('result').is_not_null(),pl.col('spread_line').is_not_null()).to_pandas()
out=[]
for Y in range(2017,2026):
    for wk in range(3,19):
        g=reg[(reg.season==Y)&(reg.week==wk)]
        if len(g)==0: continue
        try: rt=P.fit(games,Y*25+wk,Y,8,5.0)
        except Exception as e: print('fit fail',Y,wk,e); continue
        for _,r in g.iterrows():
            h=P.FRANCHISE.get(r.home_team,r.home_team); a=P.FRANCHISE.get(r.away_team,r.away_team)
            try: q=rt.rates(h,a)
            except ValueError: continue
            pr=P.Projection(P.points_pmf(q['home_td'],q['home_fg'],rt.p_xp,rt.p_2),P.points_pmf(q['away_td'],q['away_fg'],rt.p_xp,rt.p_2))
            mh,ma=pr.mean_scores()
            out.append((Y,wk,r.spread_line,r.result,mh-ma,np.sqrt(pr.margin_pmf@(np.arange(-90,91)-(mh-ma))**2)))
D=pd.DataFrame(out,columns=['season','week','spread_line','margin','v1','v1_sd'])
D.to_pickle('/tmp/audit_B/v1.pkl'); print(len(D),time.time()-t0)
