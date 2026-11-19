# Run from the repo root: python scripts/audit_B/<name>.py (needs /tmp/audit_B to exist). Read-only audit helper.
"""Regression of actual margin on the close and v1's disagreement with it. Run v1_collect.py first (writes /tmp/audit_B/v1.pkl)."""
import pandas as pd, statsmodels.api as sm
D = pd.read_pickle('/tmp/audit_B/v1.pkl')
D['mkt'] = D.spread_line
D['dis'] = D.v1 - D.mkt
m = sm.OLS(D.margin, sm.add_constant(D[['mkt', 'dis']])).fit(cov_type='cluster', cov_kwds={'groups': D.season * 100 + D.week})
print(m.summary().tables[1])
