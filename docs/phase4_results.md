# Phase 4 — Cover-probability results

Generated 2026-09-25T04:10:30+00:00 by `python -m engine coverprob` (nflverse snapshot 20260925T041016Z). Pre-registration: `docs/phase4_preregistration.md`. Walk-forward 2007–2021; target = home covers the SBRO open (frozen-line proxy); c = nflverse close (market-at-lock proxy). Kernel bandwidth chosen per test season on the last 3 training seasons (validation thresholds = close ± 0.5).

Excluded: 119 pushes on a whole-number open, 15 games with no usable open. Coin-flip log loss = 0.6931.

## Pooled out-of-sample

| estimator | n | log_loss | brier | argmax_W | argmax_L | argmax_win_rate | argmax_se | p_min | p_max |
|---|---|---|---|---|---|---|---|---|---|
| shifted | 3722 | 0.6862 | 0.2466 | 2043 | 1679 | 0.5489 | 0.0082 | 0.1695 | 0.9443 |
| normal | 3722 | 0.6863 | 0.2466 | 2043 | 1679 | 0.5489 | 0.0082 | 0.1747 | 0.9451 |
| kernel_sym | 3722 | 0.6885 | 0.2478 | 2000 | 1722 | 0.5373 | 0.0082 | 0.0001 | 0.9779 |
| kernel | 3722 | 0.6894 | 0.2482 | 1979 | 1743 | 0.5317 | 0.0082 | 0.0001 | 0.9293 |

D0-full drift rule on the same games: W 2043 L 1679 → 0.5489 (SE 0.0082).

**Default estimator (lowest log loss): `shifted`.** Pick-rule switch to argmax (pre-registered: only if argmax ATS ≥ D0-full): **YES**.

## Per season

| season | n | ll_normal | h_normal | ll_shifted | h_shifted | ll_kernel | h_kernel | ll_kernel_sym | h_kernel_sym |
|---|---|---|---|---|---|---|---|---|---|
| 2007 | 244 | 0.6784 | nan | 0.6777 | nan | 0.6842 | 2.0000 | 0.6829 | 2.0000 |
| 2008 | 248 | 0.6869 | nan | 0.6852 | nan | 0.6833 | 2.0000 | 0.6833 | 1.5000 |
| 2009 | 251 | 0.6821 | nan | 0.6809 | nan | 0.6821 | 1.5000 | 0.6831 | 1.5000 |
| 2010 | 247 | 0.6894 | nan | 0.6887 | nan | 0.6825 | 1.5000 | 0.6833 | 1.0000 |
| 2011 | 250 | 0.6888 | nan | 0.6892 | nan | 0.6838 | 1.0000 | 0.6882 | 1.5000 |
| 2012 | 250 | 0.6841 | nan | 0.6817 | nan | 0.6843 | 0.5000 | 0.6831 | 0.5000 |
| 2013 | 244 | 0.6901 | nan | 0.6931 | nan | 0.7047 | 0.5000 | 0.6999 | 0.5000 |
| 2014 | 253 | 0.6913 | nan | 0.6924 | nan | 0.6929 | 1.5000 | 0.6914 | 1.5000 |
| 2015 | 250 | 0.6882 | nan | 0.6881 | nan | 0.6929 | 2.0000 | 0.6922 | 1.0000 |
| 2016 | 244 | 0.6943 | nan | 0.6946 | nan | 0.6897 | 2.0000 | 0.6887 | 1.5000 |
| 2017 | 247 | 0.6844 | nan | 0.6866 | nan | 0.6889 | 1.5000 | 0.6856 | 0.5000 |
| 2018 | 244 | 0.6906 | nan | 0.6920 | nan | 0.7115 | 0.5000 | 0.7033 | 0.5000 |
| 2019 | 247 | 0.6763 | nan | 0.6737 | nan | 0.6795 | 1.0000 | 0.6738 | 0.5000 |
| 2020 | 248 | 0.6865 | nan | 0.6861 | nan | 0.6866 | 2.0000 | 0.6881 | 2.0000 |
| 2021 | 255 | 0.6831 | nan | 0.6835 | nan | 0.6940 | 2.0000 | 0.7003 | 3.0000 |