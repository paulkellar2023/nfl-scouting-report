import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge


def agg(df, key, y, w="w"):
    """Recency-weighted mean, sampling variance and effective n per group."""
    keys = [key] if isinstance(key, str) else list(key)
    d = df.loc[df[y].notna(), keys + [y, w]].copy()
    d[y] = d[y].astype(float)
    d["_wy"] = d[w] * d[y]
    d["_wy2"] = d[w] * d[y] ** 2
    d["_w2"] = d[w] ** 2
    g = d.groupby(keys if len(keys) > 1 else keys[0], observed=True)
    s = g[[w, "_wy", "_wy2", "_w2"]].sum()
    out = pd.DataFrame(index=s.index)
    out["value"] = s["_wy"] / s[w]
    var = (s["_wy2"] / s[w] - out["value"] ** 2).clip(lower=1e-6)
    out["neff"] = s[w] ** 2 / s["_w2"]
    out["se2"] = var / out["neff"]
    out["n"] = g.size()
    return out


def _tau2(v, se2):
    obs = np.var(v, ddof=1)
    return max(obs - float(np.mean(se2)), 0.1 * obs, 1e-9)


def eb(tab, min_n=1):
    """Empirical Bayes (method of moments) shrinkage toward the neff-weighted league mean.
    Signal variance floor = 10% of observed variance so ranks never fully collapse."""
    t = tab.copy()
    ok = t["n"] >= min_n
    t["value_s"] = np.nan
    t["se_s"] = np.nan
    v = t.loc[ok]
    if len(v) < 8:
        return t
    mu = np.average(v["value"], weights=v["neff"])
    tau2 = _tau2(v["value"], v["se2"])
    b = v["se2"] / (v["se2"] + tau2)
    t.loc[ok, "value_s"] = mu + (1 - b) * (v["value"] - mu)
    t.loc[ok, "se_s"] = np.sqrt((1 - b) * v["se2"])
    t.attrs["mu"] = mu
    return t


def opp_adjust(df, y, off_key="posteam", def_key="defteam", w="w"):
    """Play-level ridge: y ~ offense + defense + home. Penalty per block = sigma2 / tau2,
    so the ridge is the shrinkage (Gaussian prior with method-of-moments tau2)."""
    d = df.loc[df[y].notna()].copy()
    d[y] = d[y].astype(float)
    n = len(d)
    oc = pd.Categorical(d[off_key])
    dc = pd.Categorical(d[def_key])
    raw_o = agg(d, off_key, y, w)
    raw_d = agg(d, def_key, y, w)
    mu_all = np.average(d[y], weights=d[w])
    sigma2 = float(np.average((d[y] - mu_all) ** 2, weights=d[w]))
    t_o = _tau2(raw_o["value"], raw_o["se2"])
    t_d = _tau2(raw_d["value"], raw_d["se2"])
    so, sd = np.sqrt(t_o), np.sqrt(t_d)
    rows = np.arange(n)
    xo = sparse.csr_matrix((np.full(n, so), (rows, oc.codes)), shape=(n, len(oc.categories)))
    xd = sparse.csr_matrix((np.full(n, sd), (rows, dc.codes)), shape=(n, len(dc.categories)))
    home = ((d["posteam"] == d["home_team"]).astype(float).values - 0.5).reshape(-1, 1)
    x = sparse.hstack([xo, xd, sparse.csr_matrix(home)]).tocsr()
    m = Ridge(alpha=sigma2, fit_intercept=True).fit(x, d[y].values, sample_weight=d[w].values)
    ko = len(oc.categories)
    off_eff = pd.Series(m.coef_[:ko] * so, index=oc.categories)
    def_eff = pd.Series(m.coef_[ko:ko + len(dc.categories)] * sd, index=dc.categories)

    def _finish(raw, eff, tau2):
        t = raw.copy()
        t["value_s"] = m.intercept_ + eff.reindex(t.index)
        t["se_s"] = np.sqrt(sigma2 / (t["neff"] + sigma2 / tau2))
        t.attrs["mu"] = float(m.intercept_)
        return t

    return _finish(raw_o, off_eff, t_o), _finish(raw_d, def_eff, t_d)


def zscore(tab, team, sign=1):
    """Shrunk deviation over the RAW spread. Standardizing by the shrunk spread would cancel
    the shrinkage, so noisy stats would score like stable ones."""
    s = tab["value_s"].dropna()
    raw = tab.loc[s.index, "value"]
    if team not in s.index or len(s) < 8 or raw.std() == 0:
        return np.nan
    return sign * (s[team] - s.mean()) / raw.std()


def rank(tab, team, sign=1, best="high"):
    """Rank 1 = best. best='high' means higher sign*value is better."""
    s = (tab["value_s"].dropna() * sign)
    if team not in s.index:
        return None
    r = s.rank(ascending=(best != "high"), method="min")
    return int(r[team])


def league_mean(tab):
    s = tab["value_s"].dropna()
    return float(s.mean()) if len(s) else np.nan
