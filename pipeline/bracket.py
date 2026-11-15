"""Playoff picture: seeds from current standings (approximate main tiebreakers), then rounds filled by the
model favorite. Once the regular season is over, real playoff games from the schedule replace projections."""
import pandas as pd

ROUNDS = [("WC", "Wild Card"), ("DIV", "Divisional"), ("CON", "Conference"), ("SB", "Super Bowl")]
SCHED_TYPE = {"WC": "WC", "DIV": "DIV", "CON": "CON", "SB": "SB"}


def standings(reg, M):
    played = reg[reg["result"].notna()]
    S = {t: {"w": 0.0, "t": 0, "g": 0, "dw": 0.0, "dg": 0, "cw": 0.0, "cg": 0, "pf": 0, "pa": 0, "h2h": {}} for t in M}
    for _, g in played.iterrows():
        h, a = g.home_team, g.away_team
        if h not in S or a not in S:
            continue
        hw = 1.0 if g.result > 0 else 0.5 if g.result == 0 else 0.0
        div = M[h]["division"] == M[a]["division"]
        conf = M[h]["conf"] == M[a]["conf"]
        for t, o, w, pf, pa in ((h, a, hw, g.home_score, g.away_score), (a, h, 1 - hw, g.away_score, g.home_score)):
            s = S[t]
            s["w"] += w
            s["t"] += int(w == 0.5)
            s["g"] += 1
            s["pf"] += int(pf) if pd.notna(pf) else 0
            s["pa"] += int(pa) if pd.notna(pa) else 0
            s["h2h"].setdefault(o, [0.0, 0])
            s["h2h"][o][0] += w
            s["h2h"][o][1] += 1
            if div:
                s["dw"] += w
                s["dg"] += 1
            if conf:
                s["cw"] += w
                s["cg"] += 1
    return S


def _pct(w, g):
    return w / g if g else 0.5


def rank(teams, S, M):
    """Order by win %; ties broken by head-to-head (within the tied group), division % (same division only),
    conference %, point differential, then name. Approximate: the NFL's full procedure has more steps."""
    teams = sorted(teams, key=lambda t: -_pct(S[t]["w"], S[t]["g"]))
    out, i = [], 0
    while i < len(teams):
        grp = [t for t in teams if abs(_pct(S[t]["w"], S[t]["g"]) - _pct(S[teams[i]]["w"], S[teams[i]]["g"])) < 1e-9]
        if len(grp) > 1:
            same_div = len({M[t]["division"] for t in grp}) == 1

            def key(t):
                hw = sum(S[t]["h2h"].get(o, [0, 0])[0] for o in grp if o != t)
                hg = sum(S[t]["h2h"].get(o, [0, 0])[1] for o in grp if o != t)
                return (-_pct(hw, hg), -(_pct(S[t]["dw"], S[t]["dg"]) if same_div else 0), -_pct(S[t]["cw"], S[t]["cg"]),
                        -(S[t]["pf"] - S[t]["pa"]), t)
            grp = sorted(grp, key=key)
        out += grp
        i += len(grp)
    return out


def seeds(S, M):
    out = {}
    for conf in sorted({m["conf"] for m in M.values()}):
        ct = [t for t in M if M[t]["conf"] == conf]
        winners = [rank([t for t in ct if M[t]["division"] == d], S, M)[0] for d in sorted({M[t]["division"] for t in ct})]
        wins = rank(winners, S, M)
        wild = rank([t for t in ct if t not in winners], S, M)[:3]
        out[conf] = [{"seed": i + 1, "team": t, "w": int(S[t]["w"] - S[t]["t"] / 2), "t": S[t]["t"],
                      "l": int(S[t]["g"] - S[t]["w"] - S[t]["t"] / 2)} for i, t in enumerate(wins + wild)]
    return out


def plan(sched, season, M, prob):
    """prob(home, away, neutral) -> P(home wins) or None. Returns (status, seeds, rounds)."""
    reg = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
    S = standings(reg, M)
    final = bool(len(reg)) and reg["result"].notna().all()
    sd = seeds(S, M)
    post = sched[(sched["season"] == season) & (sched["game_type"].isin(SCHED_TYPE.values()))]
    seed_of = {x["team"]: (c, x["seed"]) for c, xs in sd.items() for x in xs}
    alive = {c: [x["team"] for x in xs] for c, xs in sd.items()}
    rounds = []

    def real(rcode, a, h):
        if not final:
            return None
        r = post[(post["game_type"] == SCHED_TYPE[rcode]) & (((post["home_team"] == h) & (post["away_team"] == a)) |
                                                            ((post["home_team"] == a) & (post["away_team"] == h)))]
        return r.iloc[0] if len(r) else None

    def game(rcode, hi, lo, neutral=False):
        g = real(rcode, lo, hi)
        if g is not None:
            hi, lo = g.home_team, g.away_team
        p = prob(hi, lo, neutral)
        winner, fin = None, None
        if g is not None and pd.notna(g.get("result")):
            winner = hi if g.result > 0 else lo
            fin = {hi: int(g.home_score), lo: int(g.away_score)}
        elif p is not None:
            winner = hi if p >= 0.5 else lo
        return {"id": g.game_id if g is not None else f"{season}_PO_{rcode}_{lo}_{hi}", "round": rcode, "home": hi, "away": lo,
                "seeds": {hi: seed_of.get(hi, (None, None))[1], lo: seed_of.get(lo, (None, None))[1]},
                "p_home": p, "winner": winner, "final": fin, "actual": g is not None, "neutral": neutral,
                "row": g}

    # Wild card: 2v7, 3v6, 4v5. Divisional: 1 vs lowest seed left. Higher seed hosts.
    champs = {}
    for rcode, name in ROUNDS[:3]:
        games = []
        for c in sorted(alive):
            tm = alive[c]
            sk = lambda t: seed_of[t][1]
            tm = sorted(tm, key=sk)
            if rcode == "WC":
                pairs = [(tm[1], tm[6]), (tm[2], tm[5]), (tm[3], tm[4])]
                nxt = [tm[0]]
            else:
                pairs = [(tm[i], tm[-1 - i]) for i in range(len(tm) // 2)]
                nxt = []
            for hi, lo in pairs:
                gm = game(rcode, hi, lo)
                gm["conf"] = c
                games.append(gm)
                nxt.append(gm["winner"])
            alive[c] = [t for t in nxt if t]
            if rcode == "CON" and alive[c]:
                champs[c] = alive[c][0]
        rounds.append({"code": rcode, "name": name, "games": games})
        if any(len(v) < 1 for v in alive.values()):
            break
    if len(champs) == 2:
        a, b = sorted(champs.values(), key=lambda t: (-_pct(S[t]["w"], S[t]["g"]), t))
        rounds.append({"code": "SB", "name": "Super Bowl", "games": [dict(game("SB", a, b, neutral=True), conf=None)]})
    status = "final" if final else "projected"
    return status, sd, rounds, S
