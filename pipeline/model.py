"""Win-probability model: ridge regression on home margin, then P(home win) = Phi(margin / sigma).
All features are built walk-forward (only weeks before the game). Linear model, so the
per-feature SHAP value is exact: beta_j * z_j in points, summing to the projected margin."""
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import stats as S
from .config import HALF_LIFE_WEEKS, MARGIN_SD, WP_EFF

log = logging.getLogger(__name__)

FEATS = ["pass_edge", "rush_edge", "qb_diff", "inj_off", "inj_def", "rest_diff"]
LABELS = {"pass_edge": "Passing matchup", "rush_edge": "Rushing matchup", "qb_diff": "Starting QB",
          "inj_off": "Offensive injuries", "inj_def": "Defensive injuries", "rest_diff": "Rest", "home": "Home field"}
PRIOR_SEASON_W = 0.35       # weight on last season's plays (decays further by week)
QB_PRIOR, QB_K = -0.05, 150  # QB EPA/dropback shrinks toward replacement level with k pseudo-dropbacks
STATUS_W = {"Out": 1.0, "Doubtful": 0.85, "Questionable": 0.25}
ALPHAS = [0.1, 0.3, 1, 3, 10, 30, 100, 300]
CACHE = Path("model/cache")


def _prep(pbp):
    d = pbp
    if "season_type" in d.columns:
        d = d[d["season_type"] == "REG"]
    d = d[d["play_type"].isin(["pass", "run"]) & d["epa"].notna() & d["posteam"].notna()].copy()
    for c in ["pass", "qb_dropback", "wp", "epa", "week", "season"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["dropback"] = (d["qb_dropback"].fillna(0) == 1) | (d["pass"].fillna(0) == 1)
    d["eff"] = d["wp"].between(*WP_EFF)
    d["qb_id"] = d["passer_player_id"].where(d["passer_player_id"].notna(), d["rusher_player_id"]).where(d["dropback"])
    return d[["season", "week", "game_id", "posteam", "defteam", "home_team", "epa", "dropback", "eff", "qb_id"]]


def _state(d, season, week):
    cur = d[(d["season"] == season) & (d["week"] < week)].copy()
    cur["w"] = 0.5 ** ((week - cur["week"]) / HALF_LIFE_WEEKS)
    prev = d[d["season"] == season - 1].copy()
    prev["w"] = PRIOR_SEASON_W * 0.5 ** ((prev["week"].max() + 1 - prev["week"] + week - 1) / HALF_LIFE_WEEKS)
    sub = pd.concat([cur, prev])
    e = sub[sub["eff"]]
    if e["posteam"].nunique() < 30:
        return None, None
    out = {}
    for unit, mask in (("pass", e["dropback"]), ("rush", ~e["dropback"])):
        o, df = S.opp_adjust(e[mask], "epa")
        out[unit] = (o["value_s"].to_dict(), df["value_s"].to_dict(), o.attrs["mu"])
    q = S.agg(e[e["dropback"] & e["qb_id"].notna()], "qb_id", "epa")
    qbv = ((q["value"] * q["neff"] + QB_PRIOR * QB_K) / (q["neff"] + QB_K)).to_dict()
    return out, qbv


def _starters(d):
    s = d[d["dropback"] & d["qb_id"].notna()].groupby(["game_id", "posteam", "qb_id"]).size().reset_index(name="n")
    return s.sort_values("n").groupby(["game_id", "posteam"]).tail(1).set_index(["game_id", "posteam"])["qb_id"].to_dict()


def _injury_table(inj, snaps, players):
    """Rows: season, week, team, pid, name, pos, status, side, snap, weight. Empty if sources missing."""
    cols = ["season", "week", "team", "pid", "name", "pos", "status", "side", "snap", "weight"]
    if inj is None or snaps is None or not len(inj) or not len(snaps):
        return pd.DataFrame(columns=cols)
    i = inj[inj["report_status"].isin(STATUS_W)].copy()
    if "game_type" in i.columns:
        i = i[i["game_type"] == "REG"]
    i = i[i["position"] != "QB"]
    sn = snaps.copy()
    if "game_type" in sn.columns:
        sn = sn[sn["game_type"] == "REG"]
    idmap = {}
    if players is not None and {"gsis_id", "pfr_id"} <= set(players.columns):
        idmap = dict(zip(players["gsis_id"], players["pfr_id"]))
    i["pfr"] = i["gsis_id"].map(idmap)
    i["key"] = np.where(i["pfr"].notna(), i["pfr"], i["full_name"].astype(str) + "|" + i["team"].astype(str))
    sn["key"] = sn["pfr_player_id"].where(sn["pfr_player_id"].isin(set(i["pfr"].dropna())),
                                          sn["player"].astype(str) + "|" + sn["team"].astype(str))
    m = i[["season", "week", "team", "key", "full_name", "position", "report_status"]].merge(
        sn[["season", "week", "key", "offense_pct", "defense_pct"]].rename(columns={"week": "sw"}), on=["season", "key"], how="left")
    m = m[(m["sw"] < m["week"]) & (m["sw"] >= m["week"] - 4)]
    g = m.groupby(["season", "week", "team", "key", "full_name", "position", "report_status"], dropna=False)[["offense_pct", "defense_pct"]].mean().reset_index()
    g["side"] = np.where(g["offense_pct"].fillna(0) >= g["defense_pct"].fillna(0), "off", "def")
    g["snap"] = np.where(g["side"] == "off", g["offense_pct"], g["defense_pct"]).astype(float)
    g["snap"] = np.where(g["snap"] > 1.5, g["snap"] / 100, g["snap"])
    g["weight"] = g["snap"] * g["report_status"].map(STATUS_W)
    g = g.rename(columns={"key": "pid", "full_name": "name", "position": "pos", "report_status": "status"})
    return g[g["weight"] > 0.05][cols]


def _features(d, sched, injt, seasons, max_week=None, starters_override=None):
    starters = _starters(d)
    inj_sum = injt.groupby(["season", "week", "team", "side"])["weight"].sum().unstack("side").fillna(0) if len(injt) else None
    rows = []
    for s in seasons:
        sch = sched[(sched["season"] == s) & (sched["game_type"] == "REG")]
        weeks = sorted(sch["week"].unique())
        if max_week is not None:
            weeks = [w for w in weeks if w <= max_week]
        for w in weeks:
            st, qbv = _state(d, s, w)
            if st is None:
                continue
            for _, g in sch[sch["week"] == w].iterrows():
                h, a = g.home_team, g.away_team
                po, pd_, _ = st["pass"]
                ro, rd, _ = st["rush"]
                try:
                    pe = po[h] + pd_[a] - po[a] - pd_[h]
                    re_ = ro[h] + rd[a] - ro[a] - rd[h]
                except KeyError:
                    continue
                qs = {}
                for t in (h, a):
                    q = (starters_override or {}).get(t) if (max_week is not None and w == max_week) else None
                    qs[t] = q or starters.get((g.game_id, t))
                inj = {t: (inj_sum.loc[(s, w, t)] if inj_sum is not None and (s, w, t) in inj_sum.index else None) for t in (h, a)}
                io = lambda t, side: float(inj[t].get(side, 0)) if inj[t] is not None else 0.0
                rest = (g.get("home_rest", 7) or 7) - (g.get("away_rest", 7) or 7)
                rows.append({"game_id": g.game_id, "season": s, "week": w, "home": h, "away": a,
                             "pass_edge": pe, "rush_edge": re_,
                             "qb_diff": qbv.get(qs[h], QB_PRIOR) - qbv.get(qs[a], QB_PRIOR),
                             "qb_home": qs[h], "qb_away": qs[a], "qb_home_v": qbv.get(qs[h], QB_PRIOR), "qb_away_v": qbv.get(qs[a], QB_PRIOR),
                             "inj_off": io(h, "off") - io(a, "off"), "inj_def": io(h, "def") - io(a, "def"),
                             "rest_diff": float(np.clip(rest if pd.notna(rest) else 0, -7, 7)),
                             "home_flag": 0.0 if str(g.get("location", "Home")) == "Neutral" else 1.0,
                             "margin": g.get("result"), "spread_line": g.get("spread_line"),
                             "home_ml": g.get("home_moneyline"), "away_ml": g.get("away_moneyline"),
                             "ratings": json.dumps({**{t: {k: round(float(v), 4) for k, v in (("off_pass", po[t]), ("def_pass", pd_[t]),
                                                                                       ("off_rush", ro[t]), ("def_rush", rd[t]))} for t in (h, a)},
                                                    "mu": {"pass": round(float(st["pass"][2]), 4), "rush": round(float(st["rush"][2]), 4)}})})
    return pd.DataFrame(rows)


def market_prob(spread, home_ml, away_ml):
    def imp(ml):
        return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)
    if pd.notna(home_ml) and pd.notna(away_ml) and home_ml != 0 and away_ml != 0:
        ph, pa = imp(float(home_ml)), imp(float(away_ml))
        return ph / (ph + pa), "moneyline"
    if pd.notna(spread):
        return float(norm.cdf(float(spread) / MARGIN_SD)), "spread"
    return None, None


class Ridge:
    def fit(self, df, alpha):
        X = df[FEATS].astype(float)
        self.mu, self.sd = X.mean(), X.std().replace(0, 1)
        Z = ((X - self.mu) / self.sd).values
        A = np.column_stack([Z, df["home_flag"].values])
        P = np.diag([1.0] * len(FEATS) + [0.0])
        self.beta = np.linalg.solve(A.T @ A + alpha * P, A.T @ df["margin"].astype(float).values)
        self.alpha = alpha
        return self

    def contribs(self, df):
        Z = ((df[FEATS].astype(float) - self.mu) / self.sd).values
        c = Z * self.beta[:-1]
        return np.column_stack([c, df["home_flag"].values * self.beta[-1]])

    def predict(self, df):
        return self.contribs(df).sum(axis=1)


def _ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _fit_alpha(train):
    seasons = sorted(train["season"].unique())
    if len(seasons) < 3:
        return 30.0
    best, ba = 1e18, 30.0
    for a in ALPHAS:
        err = []
        for s in seasons[-3:]:
            tr, te = train[train["season"] != s], train[train["season"] == s]
            err.append(np.mean((Ridge().fit(tr, a).predict(te) - te["margin"]) ** 2))
        if np.mean(err) < best:
            best, ba = np.mean(err), a
    return ba


def _fit_sigma(m, y):
    grid = np.arange(8, 20.01, 0.25)
    return float(grid[np.argmin([_ll(norm.cdf(m / s), y) for s in grid])])


def backtest(feat, min_train=2):
    done = feat[feat["margin"].notna() & (feat["margin"] != 0)].copy()
    seasons = sorted(done["season"].unique())
    rows, preds = [], []
    for i, s in enumerate(seasons):
        if i < min_train:
            continue
        tr, te = done[done["season"] < s], done[done["season"] == s].copy()
        a = _fit_alpha(tr)
        r = Ridge().fit(tr, a)
        sig = _fit_sigma(r.predict(tr), (tr["margin"] > 0).astype(float).values)
        te["p"] = norm.cdf(r.predict(te) / sig)
        te["pm"] = [market_prob(x, y, z)[0] for x, y, z in zip(te["spread_line"], te["home_ml"], te["away_ml"])]
        te = te[te["pm"].notna()]
        y = (te["margin"] > 0).astype(float).values
        rows.append({"season": int(s), "n": int(len(te)), "model_ll": round(_ll(te["p"].values, y), 4),
                     "mkt_ll": round(_ll(te["pm"].astype(float).values, y), 4),
                     "model_brier": round(float(np.mean((te["p"] - y) ** 2)), 4),
                     "mkt_brier": round(float(np.mean((te["pm"].astype(float) - y) ** 2)), 4),
                     "model_acc": round(float(np.mean((te["p"] > 0.5) == y)), 3),
                     "mkt_acc": round(float(np.mean((te["pm"].astype(float) > 0.5) == y)), 3)})
        preds.append(pd.DataFrame({"p": te["p"].values, "y": y}))
    calib = []
    if preds:
        pp = pd.concat(preds)
        pp["bin"] = np.clip((pp["p"] * 10).astype(int), 0, 9)
        for b, g in pp.groupby("bin"):
            if len(g) >= 15:
                calib.append({"pred": round(float(g["p"].mean()), 3), "obs": round(float(g["y"].mean()), 3), "n": int(len(g))})
    return rows, calib


def season_walk(allf, season, week):
    """Walk-forward predictions for this season's played weeks: week w uses a model fit only on games before w."""
    done = allf[allf["margin"].notna()]
    cur = done[(done["season"] == season) & (done["week"] < week)]
    rows = []
    for w in sorted(cur["week"].unique()):
        tr = done[(done["season"] < season) | (done["week"] < w)]
        r = Ridge().fit(tr, _fit_alpha(tr))
        sig = _fit_sigma(r.predict(tr), (tr["margin"] > 0).astype(float).values)
        te = cur[cur["week"] == w]
        for (_, g), p in zip(te.iterrows(), norm.cdf(r.predict(te) / sig)):
            pm = market_prob(g["spread_line"], g["home_ml"], g["away_ml"])[0]
            rows.append({"id": g["game_id"], "week": int(w), "home": g["home"], "away": g["away"], "p": round(float(p), 4),
                         "pm": None if pm is None else round(float(pm), 4), "margin": float(g["margin"])})
    return rows


def run(hist, season, week, starters, first_season):
    """hist: dict with pbp (multi-season), sched, injuries, snaps, players. Returns (preds by game_id, meta)."""
    d = _prep(hist["pbp"])
    sched = hist["sched"]
    injt = _injury_table(hist.get("injuries"), hist.get("snaps"), hist.get("players"))
    log.info("model: %d plays, %d injury rows", len(d), len(injt))
    CACHE.mkdir(parents=True, exist_ok=True)
    parts = []
    for s in range(first_season, season):
        f = CACHE / f"features_{s}.csv"
        if f.exists() and not hist.get("synthetic"):
            parts.append(pd.read_csv(f))
            continue
        if not (d["season"] == s).any():
            continue
        fs = _features(d, sched, injt, [s])
        if not hist.get("synthetic"):
            fs.to_csv(f, index=False)
        parts.append(fs)
    cur = _features(d, sched, injt, [season], max_week=week, starters_override=starters)
    allf = pd.concat(parts + [cur], ignore_index=True)
    train = allf[allf["margin"].notna() & ((allf["season"] < season) | (allf["week"] < week))]
    bt, calib = backtest(allf[allf["season"] < season])
    alpha = _fit_alpha(train)
    r = Ridge().fit(train, alpha)
    sig = _fit_sigma(r.predict(train), (train["margin"] > 0).astype(float).values)
    tgt = cur[cur["week"] == week]
    contrib = r.contribs(tgt) if len(tgt) else np.zeros((0, len(FEATS) + 1))
    injw = injt[(injt["season"] == season) & (injt["week"] == week)]
    preds = {}
    for k, (_, g) in enumerate(tgt.iterrows()):
        m = float(contrib[k].sum())
        pm, src = market_prob(g["spread_line"], g["home_ml"], g["away_ml"])
        inj_list = {t: injw[injw["team"] == t].sort_values("weight", ascending=False)
                    [["name", "pos", "status", "side", "snap", "weight"]].round(3).to_dict("records") for t in (g.home, g.away)}
        preds[g.game_id] = {
            "home": g.home, "away": g.away, "margin": round(m, 2), "sigma": sig,
            "p_home": round(float(norm.cdf(m / sig)), 4),
            "market": {"p_home": None if pm is None else round(pm, 4), "source": src,
                       "spread": None if pd.isna(g["spread_line"]) else float(g["spread_line"])},
            "contribs": [{"key": f, "label": LABELS[f], "pts": round(float(v), 2)} for f, v in zip(FEATS + ["home"], contrib[k])],
            "ratings": json.loads(g["ratings"]),
            "qb": {g.home: {"id": g["qb_home"], "value": round(float(g["qb_home_v"]), 3)},
                   g.away: {"id": g["qb_away"], "value": round(float(g["qb_away_v"]), 3)}},
            "injuries": inj_list,
            "inj_pts": {"off": round(float(contrib[k][FEATS.index("inj_off")]), 2),
                        "def": round(float(contrib[k][FEATS.index("inj_def")]), 2)},
        }
    meta = {"backtest": bt, "calib": calib, "sigma": sig, "alpha": alpha, "n_train": int(len(train)),
            "coef_pts_per_sd": {LABELS[f]: round(float(b), 2) for f, b in zip(FEATS, r.beta[:-1])},
            "hfa": round(float(r.beta[-1]), 2), "train_seasons": [int(first_season), int(season)],
            "injuries_available": bool(len(injt)), "season_walk": season_walk(allf, season, week)}
    log.info("model: alpha %s sigma %.2f hfa %.2f coefs %s", alpha, sig, r.beta[-1], meta["coef_pts_per_sd"])
    return preds, meta
