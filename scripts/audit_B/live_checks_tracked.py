# Run from the repo root: python scripts/audit_B/<name>.py (needs /tmp/audit_B to exist). Read-only audit helper.
import csv,re,math,collections
res={}
for l in open('data/predictions/live_record.md'):
    m=re.match(r'\| 2026 \| (\d+) \| (\S+) \| (\S+) \| (\S+) \| (\S+) \| ([WL]) \|',l)
    if m:
        a,h=m.group(5).split('-'); res[m.group(2)]=(m.group(3),float(m.group(4)),int(a),int(h))
P={r['game_id']:r for r in csv.DictReader(open('data/predictions/predictions.csv'))}
J=list(csv.DictReader(open('data/predictions/projections.csv')))
print(collections.Counter(r['model_version'] for r in J))
def home_cov(g):
    _,S,a,h=res[g]; return (h-a)>-S
out={}
for ver in ['proj-poisson-v1','proj-players-v3']:
    rows=[r for r in J if r['model_version']==ver and r['game_id'] in res and r['proj_p_home_cover'] not in('',None)]
    seen={}
    for r in rows: seen[r['game_id']]=r
    out[ver]=seen
off={g:p for g,p in P.items() if g in res and p['p_home_cover'] not in('UNAVAILABLE','')}
common=set(off)&set(out['proj-poisson-v1'])&set(out['proj-players-v3'])
print('common games',len(common))
def score(ver,games,key='proj_p_home_cover',pickfn=None):
    W=0;n=0;br=0;ll=0;conf=0
    for g in games:
        p=float(out[ver][g][key]) if ver!='off' else float(off[g]['p_home_cover'])
        y=1 if home_cov(g) else 0
        pick_home=p>0.5
        W+= (pick_home==bool(y)); n+=1
        pp=p if pick_home else 1-p
        conf+=pp; br+=(pp-(1 if pick_home==bool(y) else 0))**2; ll+=-math.log(pp if pick_home==bool(y) else 1-pp)
    return n,W,n-W,conf/n,br/n,ll/n
for name in ['off','proj-poisson-v1','proj-players-v3']:
    ver=name
    print(name,'n %d W %d L %d stated %.3f brier %.4f ll %.4f'%score(ver,common))
# paired official vs v1/v3
def pick(ver,g):
    p=float(off[g]['p_home_cover']) if ver=='off' else float(out[ver][g]['proj_p_home_cover'])
    return p>0.5
for v in ['proj-poisson-v1','proj-players-v3']:
    d=[g for g in common if pick('off',g)!=pick(v,g)]
    vr=sum(pick(v,g)==home_cov(g) for g in d)
    print(v,'differs',len(d),'model right',vr,'official right',len(d)-vr)
# v1 stated prob extremes
ps=[abs(float(out['proj-poisson-v1'][g]['proj_p_home_cover'])-.5) for g in common]
print('v1 mean |p-.5| %.3f max %.3f'%(sum(ps)/len(ps),max(ps)))
ps=[abs(float(out['proj-players-v3'][g]['proj_p_home_cover'])-.5) for g in common]
print('v3 mean |p-.5| %.3f max %.3f'%(sum(ps)/len(ps),max(ps)))
ps=[abs(float(off[g]['p_home_cover'])-.5) for g in common]
print('off mean |p-.5| %.3f max %.3f'%(sum(ps)/len(ps),max(ps)))
# v1 reliability
bins=collections.defaultdict(lambda:[0,0,0.0])
for g in common:
    p=float(out['proj-poisson-v1'][g]['proj_p_home_cover']); pp=max(p,1-p); y=(home_cov(g)==(p>0.5))
    k='50-55' if pp<.55 else '55-65' if pp<.65 else '65-75' if pp<.75 else '75+'
    bins[k][0]+=1;bins[k][1]+=y;bins[k][2]+=pp
for k in ['50-55','55-65','65-75','75+']:
    n,w,c=bins[k]; 
    if n: print('v1',k,n,w,'stated %.3f actual %.3f'%(c/n,w/n))
