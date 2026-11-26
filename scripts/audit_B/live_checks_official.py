# Run from the repo root: python scripts/audit_B/<name>.py (needs /tmp/audit_B to exist). Read-only audit helper.
import csv, re, math, collections
P=list(csv.DictReader(open('data/predictions/predictions.csv')))
res={}
for l in open('data/predictions/live_record.md'):
    m=re.match(r'\| 2026 \| (\d+) \| (\S+) \| (\S+) \| (\S+) \| (\S+) \| ([WL]) \|',l)
    if m: res[m.group(2)]=(m.group(6),m.group(3))
rows=[]
for r in P:
    g=r['game_id']
    if g not in res: continue
    w=res[g][0]=='W'
    rows.append((r,w))
print(len(P),len(rows))
# model-based
mk=[(r,w) for r,w in rows if r['p_home_cover'] not in('UNAVAILABLE','')]
print('with model p',len(mk), 'W',sum(w for _,w in mk))
conf=[max(float(r['p_home_cover']),float(r['p_away_cover'])) for r,_ in mk]
print('mean stated win prob %.4f  actual %.4f'%(sum(conf)/len(conf), sum(w for _,w in mk)/len(mk)))
# brier on pick prob
br=sum((c-(1 if w else 0))**2 for c,(r,w) in zip(conf,mk))/len(mk)
ll=-sum(math.log(c if w else 1-c) for c,(r,w) in zip(conf,mk))/len(mk)
print('brier(pick) %.4f logloss %.4f (coin .25/.6931)'%(br,ll))
# agreement with drift rule
dis=0;zero=0
for r,w in mk:
    d=float(r['drift'])
    rule='home' if d<0 else 'away'
    if d==0: zero+=1
    if rule!=r['pick']: dis+=1
print('disagree with drift rule',dis,'zero drift',zero)
# by |drift|
b=collections.defaultdict(lambda:[0,0,0.0])
for (r,w),c in zip(mk,conf):
    d=abs(float(r['drift'])); k='0' if d==0 else '0.5' if d<=0.5 else '1' if d<=1 else '1.5-2' if d<=2 else '2.5+'
    b[k][0]+=1;b[k][1]+=w;b[k][2]+=c
for k in ['0','0.5','1','1.5-2','2.5+']:
    n,w,c=b[k]; print(k,n,w,'-',n-w,'win %.3f stated %.3f'%(w/n,c/n))
# pick-share of flags
fl=collections.Counter()
for r in P:
    for f in r['flags'].split(';'):
        if f: fl[f]+=1
print(fl)
print(collections.Counter(r['feature_version'] for r in P))
print(collections.Counter(r['model_version'] for r in P))
