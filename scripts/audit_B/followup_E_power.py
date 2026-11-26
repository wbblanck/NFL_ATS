# What a market-disagreement signal of weight w is worth in the pool, and how many games it takes to confirm it.
import csv, numpy as np
from math import erf, sqrt
Phi=np.vectorize(lambda x:0.5*(1+erf(x/sqrt(2))))
P=[r for r in csv.DictReader(open('data/predictions/predictions.csv')) if r['p_home_cover'] not in('UNAVAILABLE','')]
d_live=-np.array([float(r['drift']) for r in P])      # d = S - c (positive: pool line easier for home)
rng=np.random.default_rng(2); N=400000; sig=13.0; sd_delta=3.45; sd_eps=12.8
print('w     SD of shift w*delta   win-rate gain over drift-only (pp)   games for 80%% power (one-sided 5%%) to see weight w')
for w in [0.05,0.10,0.15,0.25,0.35,0.50]:
    d=rng.choice(d_live,N); delta=rng.normal(0,sd_delta,N); mu=w*delta
    ph=Phi((d+mu)/sig)             # true P(home covers pool line)
    pick_drift=d>0; pick_adj=(d+mu)>0       # model with the true weight (best case)
    win=lambda pick: np.where(pick,ph,1-ph).mean()
    gain=win(pick_adj)-win(pick_drift)
    n=((1.645+0.84)*sd_eps/(sd_delta*w))**2
    print('%.2f  %.2f                  %+.2f                                   %6.0f  (%.1f NFL seasons of 272)'%(w,w*sd_delta,100*gain,n,n/272))
print('\nGames needed to detect a weight w with 80%% power when the disagreement SD is different (SD 1.5 = a quieter feature set):')
for sdd in [1.5,3.45]:
    print(' SD(delta)=%.2f:'%sdd,' '.join('w=%.2f -> %d'%(w,((1.645+0.84)*sd_eps/(sdd*w))**2) for w in [0.15,0.25,0.5,1.0]))
