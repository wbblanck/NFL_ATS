# Builds the v3 design matrix exactly as the pre-registered evaluation does (engine.backtest.players_v3_eval), cached.
import sys,time,pickle; sys.path.insert(0,'src')
t=time.time()
from engine.backtest import players_v3_eval as E
ctx=E.prepare('/tmp/audit_B/v3cache', log=lambda *a: print(*a,flush=True))
print('prepared',time.time()-t,flush=True)
D,k=365,500
f=E.features(ctx['data'],ctx['sched'],D,k,ctx['const'])
d=E.design(f,ctx['rates'],ctx['games'])
d.write_parquet('/tmp/audit_B/v3_design.parquet'); 
pickle.dump({'res':ctx['res']},open('/tmp/audit_B/v3_res.pkl','wb'))
ctx['reg'].write_parquet('/tmp/audit_B/v3_reg.parquet')
print('design',d.shape,time.time()-t,flush=True)
