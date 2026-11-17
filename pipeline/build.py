"""Weekly build: python -m pipeline.build [--week N] [--synthetic]"""
import argparse
import os
import datetime as dt
import json
import logging
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import (assets, bracket, clean, context, elo, extras, fantasy, special, tendencies, viz, viz2, weather, feeds, health, league, leverage, model, model_cards, notify,
               record, share, stats, story, summary, templates_player, templates_team)
from .text import agree
from .config import FILL_VARIETY, VARIETY
from .config import BUTTONDOWN_USERNAME, EMAIL_PER_TEAM, GOATCOUNTER_CODE, MODEL_FIRST_SEASON, SITE_URL
from .config import (HANDLE, MAX_PLAYER_CARDS, MAX_TEAM_CARDS, MIN_PLAYER_CARDS, MIN_TEAM_CARDS,
                     PRIMETIME_BONUS, SEASON, SITE_TITLE)

log = logging.getLogger("build")
DAYS = {"Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun", "Monday": "Mon"}
LAST_REG_WEEK = 18


def _json(o):
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


def _nan_free(o):
    """NaN is not valid JSON and breaks the page; write it as null."""
    if isinstance(o, float):
        return None if o != o else o
    if isinstance(o, dict):
        return {k: _nan_free(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_nan_free(v) for v in o]
    return o


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_nan_free(obj), default=_json, separators=(",", ":")))


def wname(w):
    return f"wk{w:02d}" if isinstance(w, int) else f"wk{w}"


def detect_week(sched, season):
    reg = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
    open_ = reg[reg["result"].isna()]
    return int(open_["week"].min()) if len(open_) else int(reg["week"].max())


def _ok(v):
    return v is not None and not (isinstance(v, float) and np.isnan(v))


def line_info(g):
    sp, tot = g.get("spread_line"), g.get("total_line")
    if not _ok(sp):
        return None
    sp = float(sp)
    fav = g.home_team if sp > 0 else g.away_team
    text = "PK" if sp == 0 else f"{fav} -{abs(sp):g}"
    out = {"spread": sp, "text": text, "total": None, "implied": None}
    if _ok(tot):
        tot = float(tot)
        out["total"] = tot
        out["text"] += f" · O/U {tot:g}"
        out["implied"] = {g.home_team: round((tot + sp) / 2, 1), g.away_team: round((tot - sp) / 2, 1)}
    return out


def kickoff(g):
    try:
        t = dt.datetime.strptime(str(g.gametime), "%H:%M")
        tm = t.strftime("%-I:%M %p")
    except ValueError:
        return "Date and time TBD"
    day = DAYS.get(str(g.get("weekday")), str(g.get("weekday"))[:3])
    date = str(g.gameday)[5:].replace("-", "/").lstrip("0")
    return f"{day} {date} · {tm} ET"


def kicked_off(g, now):
    """True if the game's ET kickoff time has passed (or a result exists)."""
    if _ok(g.get("result")):
        return True
    try:
        from zoneinfo import ZoneInfo
        ko = dt.datetime.strptime(f"{g.gameday} {g.gametime}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("America/New_York"))
        return now >= ko
    except (ValueError, TypeError):
        return False


FIELD_TEAM = {"passchart", "runchart", "drives", "fourthmap", "redzone", "downs", "explosive_map", "wpline", "quarters", "tug",
              "thirds", "penalties", "splits"}
FIELD_PLAYER = {"rcvchart", "pressmap", "tree"}
CARD_CAP = 14  # cards kept per tab: the default view shows 4-6, filters and Top 10 can reach the rest


def with_field(cards, n, pool, kinds, cap=10):
    """Default view gets at least 1 field chart and at most 2. A 4-card default gets 2 field charts added at the end."""
    is_f = lambda c: c["id"].split(":")[0] in kinds
    top, rest = cards[:n], cards[n:]
    extra = sorted([c for c in pool if is_f(c) and c not in cards], key=lambda c: -c["score"])
    avail = [c for c in rest if is_f(c)] + extra
    if len([c for c in top if is_f(c)]) > 2:
        keep, drop = [], []
        for c in top:
            (drop if is_f(c) and sum(is_f(k) for k in keep) >= 2 else keep).append(c)
        top, rest = keep, drop + rest
    if n <= 4 and (avail or any(is_f(c) for c in top)):
        fs = sorted([c for c in top + avail if is_f(c)], key=lambda c: -c["score"])[:2]
        nf = [c for c in cards if not is_f(c)][:4]
        top = nf + fs  # 4 regular cards, then the 2 field charts last
    elif not any(is_f(c) for c in top) and avail and top:
        top = top[:-1] + [avail[0]]
    rest = [c for c in cards + extra if c not in top]
    out = top + rest
    return out[:max(cap, len(top))], len(top)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=SEASON)
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--site", default="site")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--refresh-started", action="store_true", help="rebuild games that already kicked off (testing)")
    ap.add_argument("--backfill", action="store_true",
                    help="build a past week after the fact (data before that week only); leaves projections, bracket and email alone")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.synthetic:
        from . import synth
        hist = synth.load_history(list(range(args.season - 4, args.season + 1)), args.season, args.week or 12)
        raw = {**hist, "pbp": hist["cur_pbp"], "sched": hist["cur_sched"], "x": synth.extras(hist["cur_pbp"], args.season)}
        first = args.season - 3
    else:
        from . import load
        raw = load.load(args.season)
        first = MODEL_FIRST_SEASON
    synth_run = bool(raw.get("synthetic"))
    sched = raw["sched"]
    sched = sched[sched["season"] == args.season]
    week = args.week or detect_week(sched, args.season)
    if not args.synthetic:
        try:
            hist = load.load_history(args.season, first, raw["pbp"], model.CACHE)
        except Exception:
            log.exception("history load failed; building without the model")
            health.error("history load failed: model skipped")
            hist = None
    log.info("season %s target week %s", args.season, week)
    if week < 3:
        raise SystemExit("need at least 2 played weeks")
    if args.backfill and not args.week:
        raise SystemExit("--backfill needs --week")

    plays, flags = clean.prepare(raw, week)
    health.info("week", week)
    health.info("plays", int(len(plays)))
    health.info("flags", flags)
    health.info("sources", {k: raw.get(k) is not None for k in ("rosters", "part", "ftn")})
    sum_counts = {"llm": 0, "rule": 0, "kept": 0, "cached": 0}
    reg = sched[sched["game_type"] == "REG"]
    games = reg[reg["week"] == week]
    active = sorted(set(plays["posteam"].dropna()) | set(games["home_team"]) | set(games["away_team"]))
    M = context.team_meta(raw["teams"], active)
    pctx = context.player_context(plays, raw.get("rosters"), sched, week)
    pctx["flags"] = flags
    pctx["need_heads"] = set()
    X = extras.tables(raw.get("x"), plays, sched, args.season, week)
    for pid, nm in X["names"].items():
        pctx["names"].setdefault(pid, nm)
    for pid, t in X["teams"].items():
        pctx["team"].setdefault(pid, t)

    tpls = templates_team.build(plays, flags, pctx["qb"], active, X)
    shells = templates_team.shell_tables(plays) if flags["coverage"] else None
    gaps = templates_team.gap_tables(plays)
    form = templates_team.form_tables(plays)
    luck = templates_team.luck_tables(plays) if flags["int_worthy"] else None
    ptabs = templates_player.build_tables(plays, flags, X)
    SP = special.tables(raw["pbp"], args.season, week, bot=None if synth_run else special.load_bot(args.season))
    TX = tendencies.tables(plays, tpls)
    VZ = viz.tables(plays, raw["pbp"], args.season, week)
    V2 = viz2.tables(plays, raw["pbp"], args.season, week)
    health.info("visuals", sorted(k for k in VZ if not k.endswith("_lg")))
    snap_t = fantasy.snap_table((hist or {}).get("snaps"), args.season, week)
    if snap_t is not None:
        ptabs["snap"] = snap_t
    E = elo.Elo((hist or {}).get("sched") if (hist or {}).get("sched") is not None else raw["sched"], args.season, week)
    health.info("phase4", {"special": sorted(SP), "snaps": snap_t is not None, "elo_teams": len(E.r)})

    preds, mmeta, predict = {}, None, None
    if hist is not None and hist.get("sched") is not None:
        try:
            preds, mmeta, predict = model.run(hist, args.season, week, pctx["qb"], first)
        except Exception:
            log.exception("model failed; building without it")
            health.error("model failed: Model tab skipped")

    e = plays[plays["eff"]]
    o_all, d_all = stats.opp_adjust(e, "epa")
    lev = leverage.simulate(sched, M, week, leverage.ratings(o_all, d_all))
    lev_teams, lev_proj = lev.pop("_teams", {}), lev.pop("_proj", {})

    site = Path(args.site)
    ddir = site / "data" / str(args.season)
    idx_path = site / "data" / "index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {"weeks": []}
    # projections from the last build are rebuilt from scratch (a backfill leaves them alone)
    if not args.backfill:
        for w in [w for w in idx.get("weeks", []) if w.get("projected") or w["week"] == "PO"]:
            shutil.rmtree(site / "data" / str(w["season"]) / wname(w["week"]), ignore_errors=True)
        idx["weeks"] = [w for w in idx.get("weeks", []) if not (w.get("projected") or w["week"] == "PO")]

    wdir = ddir / wname(week)
    if args.backfill and (wdir / "games.json").exists() and not json.loads((wdir / "games.json").read_text()).get("backfill"):
        log.info("backfill: week %s already has a live report, skipping", week)
        return
    prev_line, prev_doc, prev_tile = {}, {}, {}
    if wdir.exists():
        for f in wdir.glob(f"{args.season}_*.json"):
            try:
                dd = json.loads(f.read_text())
                prev_doc[dd["id"]] = dd
                if dd.get("line"):
                    prev_line[dd["id"]] = (dd["line"], dd.get("line_asof", dd.get("built")))
            except (ValueError, KeyError):
                pass
        try:
            prev_tile = {t["id"]: t for t in json.loads((wdir / "games.json").read_text())["games"]}
        except (OSError, ValueError, KeyError):
            pass
        shutil.rmtree(wdir)
    now = dt.datetime.now(dt.timezone.utc)
    WX = {} if synth_run else weather.forecasts(reg[reg["season"] == args.season], now)  # kickoff forecasts, next 15 days
    built = now.strftime("%Y-%m-%dT%H:%MZ")
    span = f"Weeks 1-{week - 1}, {args.season}" if week > 2 else f"Week 1, {args.season}"

    # Variety across a week's games: a card type already in the default view of earlier games this week loses up to
    # VARIETY of its score (in proportion to how many of them showed it). Small on purpose: it only breaks near-ties.
    seen = {"n": 0, "c": {}}

    def reset_variety():
        seen["n"], seen["c"] = 0, {}

    def vary(pool):
        for c in pool:
            if c and c.get("score") is not None:
                c.setdefault("score_raw", c["score"])
                share = seen["c"].get(c["id"].split(":")[0], 0) / seen["n"] if seen["n"] else 0.0
                c["score"] = round(c["score_raw"] * (1 - VARIETY * share), 3)

    def note_shown(*views):
        seen["n"] += 1
        for k in {c["id"].split(":")[0] for cards, n in views for c in cards[:n]}:
            seen["c"][k] = seen["c"].get(k, 0) + 1

    def fill(cards, n, kinds, target=6):
        """Every default view shows `target` cards when that many exist. Open slots go to the best remaining cards,
        weighted harder toward types this week's other games have not shown (FILL_VARIETY). Max 2 field charts."""
        if n >= target or len(cards) <= n:
            return cards, n
        is_f = lambda c: c["id"].split(":")[0] in kinds
        top = cards[:n]
        nf = sum(is_f(c) for c in top)
        share = lambda c: seen["c"].get(c["id"].split(":")[0], 0) / seen["n"] if seen["n"] else 0.0
        for c in sorted(cards[n:], key=lambda c: -c.get("score_raw", c["score"]) * (1 - FILL_VARIETY * share(c))):
            if len(top) >= target:
                break
            if is_f(c) and nf >= 2:
                continue
            top.append(c)
            nf += is_f(c)
        return top + [c for c in cards if c not in top], len(top)

    def make(g, mode, label, ko_text=None, neutral=False):
        """mode: live (this week) | proj (future regular-season week) | po (playoff game)."""
        a_, h_ = g.away_team, g.home_team
        game = {"span": span, "coach": {a_: g.get("away_coach"), h_: g.get("home_coach")}}
        cands = []
        for t in tpls:
            for off, de in ((a_, h_), (h_, a_)):
                c = story.evaluate(t, off, de)
                if c:
                    cands.append(c)
        rendered = [story.render(c, M, game) for c in cands]
        specials = []
        for off, de in ((a_, h_), (h_, a_)):
            specials.append(story.gap_card(gaps, off, de, M, game))
            if shells:
                specials.append(story.shell_card(shells, off, de, M, game))
        specials = [s for s in specials if s]
        ctxs = [story.form_card(form, a_, h_, M, game), story.luck_card(luck, a_, h_, M, game),
                extras.box_card(X, a_, h_, M, game), extras.box_card(X, h_, a_, M, game),
                special.st_card(SP, a_, h_, M, game), special.fg_card(SP, a_, h_, M, game), special.fourth_card(SP, a_, h_, M, game),
                tendencies.zone_card(TX, a_, h_, M, game), tendencies.lean_card(TX, a_, h_, M, game),
                viz.pass_card(VZ, a_, h_, M, game), viz.run_card(VZ, a_, h_, M, game), viz.drive_card(VZ, a_, h_, M, game),
                viz.fourth_map_card(VZ, a_, h_, M, game)] + [f(V2, a_, h_, M, game) for f in (
                    viz2.redzone_card, viz2.downs_card, viz2.explosive_card, viz2.wp_card, viz2.quarters_card, viz2.tug_card,
                    viz2.third_card, viz2.penalty_card, viz2.splits_card)]
        pool_t = rendered + specials + [c for c in ctxs if c]
        vary(pool_t)
        team_cards, team_n = story.select(pool_t, MIN_TEAM_CARDS, MAX_TEAM_CARDS, (a_, h_), cap=CARD_CAP)
        team_cards, team_n = with_field(team_cards, team_n, [c for c in pool_t if c], FIELD_TEAM, CARD_CAP)
        team_cards, team_n = fill(team_cards, team_n, FIELD_TEAM)
        pc = templates_player.Cards(ptabs, pctx, M, tpls, game)
        tpp = {t.id: t for t in tpls}
        extra_p = [viz.receiver_card(VZ, a_, h_, M, game, pctx, pc._name, pc._img),
                   viz.pressure_card(VZ, a_, h_, M, game, pctx, pc._name, pc._img, ptabs.get("qb_ttt"),
                                     tpp["pressure"].deff if "pressure" in tpp else None),
                   viz2.tree_card(V2, a_, h_, M, game, pc._name, pc._img)]
        pool_p = pc.all(a_, h_) + [c for c in extra_p if c]
        vary(pool_p)
        player_cards, player_n = templates_player.select(pool_p, MIN_PLAYER_CARDS, MAX_PLAYER_CARDS, cap=CARD_CAP)
        player_cards, player_n = with_field(player_cards, player_n, [c for c in pool_p if c], FIELD_PLAYER, CARD_CAP)
        player_cards, player_n = fill(player_cards, player_n, FIELD_PLAYER)
        pool_f = fantasy.Fantasy(ptabs, pctx, M, tpls, game).all(a_, h_)
        vary(pool_f)
        fantasy_cards, fantasy_n = fantasy.select(pool_f)
        note_shown((team_cards, team_n), (player_cards, player_n), (fantasy_cards, fantasy_n))
        keys = story.keys_pair(a_, h_, cands, specials, tpls, M)
        heat = []
        for c in cands:
            if c["id"] in ("pass_epa", "rush_epa"):
                heat.append({"team": c["a"], "unit": "PASS" if c["id"] == "pass_epa" else "RUSH",
                             "edge": round(float(c["edge"]), 2)})
        heat.sort(key=lambda x: (x["team"] != a_, x["unit"]))
        lv = lev.get(g.game_id, {"leverage": 0.0, "by_team": {}, "p_playoffs": {}})
        prime = ":" in str(g.get("gametime")) and str(g.get("gametime")) >= "19:00"
        ln_now = line_info(g)
        ln, ln_asof = prev_line.get(g.game_id, (ln_now, built)) if mode == "live" else (ln_now, built)
        if mode == "live":
            mp = preds.get(g.game_id)
        elif predict:
            rest = (g.get("home_rest") - g.get("away_rest")) if _ok(g.get("home_rest")) and _ok(g.get("away_rest")) else 0.0
            mp = predict(h_, a_, neutral, rest, g.get("spread_line"), g.get("home_moneyline"), g.get("away_moneyline"))
        else:
            mp = None
        ed = E.card_data(h_, a_, neutral)
        mcards = model_cards.build(mp, mmeta, M, pctx["names"], ed) if mp else []
        kicker = f"{M[a_]['nick']} at {M[h_]['nick']} · {label}, {args.season}".upper()
        plurals = [M[t]["label"] for t in (a_, h_) if M[t].get("plural")]
        for c in team_cards + player_cards + fantasy_cards + mcards:
            c.pop("_key", None)
            for f in ("t1", "t2", "sub"):
                c[f] = agree(c[f], plurals)
        for t in keys:
            for k in keys[t]:
                k["phrase"], k["detail"] = agree(k["phrase"], plurals), agree(k["detail"], plurals)
        labels = {t: M[t]["label"] for t in (a_, h_)}
        mkt_p = (mp or {}).get("market", {}).get("p_home")
        if mkt_p is None and ln_now:
            mkt_p = model.market_prob(ln_now["spread"], g.get("home_moneyline"), g.get("away_moneyline"))[0]
        lean_t = summary.lean(h_, a_, mp["p_home"] if mp else None, mkt_p, labels)
        facts = {"matchup": f"{M[a_]['name']} at {M[h_]['name']}", "labels": labels, "lean": lean_t,
                 "lean_abbr": next((t for t in (a_, h_) if labels[t] == lean_t), None),
                 "line": ln_now["text"] if ln_now else None,
                 "model_win_pct": {h_: round(100 * mp["p_home"]), a_: round(100 * (1 - mp["p_home"]))} if mp else None,
                 "market_win_pct": {h_: round(100 * mkt_p), a_: round(100 * (1 - mkt_p))} if mkt_p is not None else None,
                 "keys": {t: [{"phrase": k["phrase"], "detail": k["detail"], "favorable": k["favorable"]} for k in keys[t]] for t in keys},
                 "storylines": [{"team": labels.get(c["owner"], c["owner"]), "text": f"{c['t1']} {c['t2']}"}
                                for c in team_cards[:4]],
                 "players": pc.watch(a_, h_, player_cards),
                 "model": None}
        if mp:
            fav = h_ if mp["p_home"] >= 0.5 else a_
            sgn = 1 if fav == h_ else -1
            tops = sorted([c for c in mp["contribs"] if sgn * c["pts"] > 0.2], key=lambda c: -sgn * c["pts"])[:2]
            facts["model"] = {"favorite": labels[fav], "win_pct": round(100 * max(mp["p_home"], 1 - mp["p_home"])),
                              "top_factors": [{"label": c["label"], "points": round(abs(c["pts"]), 1), "toward": labels[fav]}
                                              for c in tops]}
        fh = summary.facts_hash(facts)
        prev = prev_doc.get(g.game_id, {})
        if mode != "live":
            summ, summ_src = summary.fallback(facts), "rule"
        elif prev.get("summary_hash") == fh and prev.get("summary") and prev.get("summary_src") == "llm":
            summ, summ_src = prev["summary"], prev.get("summary_src", "llm")
            sum_counts["cached"] += 1
        elif args.no_llm:
            summ, summ_src = summary.fallback(facts), "rule"
        else:
            summ, summ_src = summary.summarize(facts)
            sum_counts[summ_src] += 1
        summ = agree(summ, plurals)
        ko = ko_text or kickoff(g)
        doc = {"id": g.game_id, "season": args.season, "week": int(g.week) if mode != "po" else "PO", "away": a_, "home": h_,
               "kicker": kicker, "kickoff": ko, "primetime": prime, "line": ln, "leverage": lv, "summary": summ,
               "summary_src": summ_src, "summary_hash": fh, "keys": keys, "heat": heat, "team_cards": team_cards,
               "player_cards": player_cards, "team_n": team_n, "player_n": player_n, "built": built,
               "fantasy_cards": fantasy_cards, "fantasy_n": fantasy_n,
               "after_kickoff": kicked_off(g, now) if mode == "live" else False, "line_asof": ln_asof, "line_now": ln_now,
               "mode": mode, "through_week": week - 1, "backfill": args.backfill,
               "model": ({"p_home": mp["p_home"], "margin": mp["margin"], "market": mp["market"],
                          "summary": agree(model_cards.summary(mp, M, ed["p_home"]), plurals)} if mp else None),
               "elo": ed,
               "model_cards": mcards, "weather": WX.get(g.game_id)}
        tile = {"id": g.game_id, "away": a_, "home": h_, "kickoff": ko, "primetime": prime,
                "line": ln, "leverage": lv["leverage"], "heat": heat, "ko": f"{g.get('gameday')}T{g.get('gametime')}",
                "model": {"p_home": mp["p_home"], "mkt": mp["market"]["p_home"], "elo": ed["p_home"]} if mp else None,
                "elo": ed["p_home"], "weather": WX.get(g.game_id),
                "rank": lv["leverage"] + (PRIMETIME_BONUS if prime else 0.0),
                "tease": [team_cards[0]["t1"], team_cards[0]["t2"]] if team_cards else None,
                "tease_owner": team_cards[0]["owner"] if team_cards else None}
        return doc, tile

    # ---------- this week ----------
    board, docs = [], []
    reset_variety()
    for _, g in games.iterrows():
        started = kicked_off(g, now)
        if started and not args.refresh_started and g.game_id in prev_doc and g.game_id in prev_tile:
            _write(wdir / f"{g.game_id}.json", prev_doc[g.game_id])
            docs.append(prev_doc[g.game_id])
            board.append(prev_tile[g.game_id])
            pd_ = prev_doc[g.game_id]
            note_shown((pd_.get("team_cards", []), pd_.get("team_n", 0)), (pd_.get("player_cards", []), pd_.get("player_n", 0)),
                       (pd_.get("fantasy_cards", []), pd_.get("fantasy_n", 0)))
            log.info("kept pre-kickoff report for %s", g.game_id)
            sum_counts["kept"] += 1
            continue
        doc, tile = make(g, "live", f"Week {week}")
        _write(wdir / f"{g.game_id}.json", doc)
        docs.append(doc)
        board.append(tile)
    board.sort(key=lambda x: -x["rank"])
    if mmeta:
        _write(wdir / "model_meta.json", {k: v for k, v in mmeta.items() if k != "season_walk"})
    _write(wdir / "games.json", {"season": args.season, "week": week, "built": built, "span": span,
                                 "synthetic": synth_run, "flags": flags, "backfill": args.backfill, "games": board})
    new_weeks = [{"season": args.season, "week": week, "built": built, "synthetic": synth_run, "games": len(board),
                  **({"backfill": True} if args.backfill else {})}]
    if args.backfill:
        weeks = [w for w in idx["weeks"] if not (w["season"] == args.season and w["week"] == week)] + new_weeks
        weeks.sort(key=lambda w: (w["season"], w["week"] if isinstance(w["week"], int) else 99))
        idx["weeks"] = weeks
        if not idx.get("latest"):
            idx["latest"] = {"season": args.season, "week": week}
        idx.setdefault("title", SITE_TITLE)
        idx.setdefault("site_url", SITE_URL)
        _write(idx_path, idx)
        _write(site / "data" / "teams.json", M)
        log.info("backfill: wrote %d games to %s (%d new preview images)", len(board), wdir, share.write(site, docs, M))
        return

    # ---------- projected weeks through week 18 ----------
    fut = sorted(int(w) for w in reg["week"].unique() if week < int(w) <= LAST_REG_WEEK)
    n_proj = 0
    for fw in fut:
        pb = []
        pdir = ddir / wname(fw)
        shutil.rmtree(pdir, ignore_errors=True)
        reset_variety()
        for _, g in reg[reg["week"] == fw].iterrows():
            doc, tile = make(g, "proj", f"Projected week {fw}")
            _write(pdir / f"{g.game_id}.json", doc)
            pb.append(tile)
        pb.sort(key=lambda x: -x["rank"])
        _write(pdir / "games.json", {"season": args.season, "week": fw, "built": built, "span": span, "synthetic": synth_run,
                                     "flags": flags, "projected": True, "through_week": week - 1, "games": pb})
        new_weeks.append({"season": args.season, "week": fw, "built": built, "synthetic": synth_run, "games": len(pb), "projected": True})
        n_proj += len(pb)

    # ---------- playoff bracket ----------
    def prob(h, a, neutral):
        p = predict(h, a, neutral) if predict else None
        return p["p_home"] if p else None
    status, sd, rounds, _ = bracket.plan(sched, args.season, M, prob, lev_proj)
    podir = ddir / "wkPO"
    shutil.rmtree(podir, ignore_errors=True)
    pob, out_rounds = [], []
    reset_variety()
    for rd in rounds:
        og = []
        for gm in rd["games"]:
            row = gm.pop("row")
            if row is None:
                row = pd.Series({"game_id": gm["id"], "home_team": gm["home"], "away_team": gm["away"], "week": "PO",
                                 "gametime": None, "gameday": None, "weekday": None, "spread_line": np.nan, "total_line": np.nan,
                                 "result": np.nan, "home_moneyline": np.nan, "away_moneyline": np.nan})
            ko = None if gm["actual"] else f"{rd['name']} · projected matchup"
            doc, tile = make(row, "po", rd["name"], ko_text=ko, neutral=gm["neutral"])
            if gm["final"]:
                tile["final"] = gm["final"]
            tile.update({"round": rd["code"], "conf": gm.get("conf"), "seeds": gm["seeds"], "winner": gm["winner"],
                         "actual": gm["actual"]})
            doc["round"] = rd["name"]
            _write(podir / f"{doc['id']}.json", doc)
            pob.append(tile)
            og.append({**{k: tile.get(k) for k in ("id", "home", "away", "seeds", "winner", "final", "actual", "conf")},
                       "p_home": (tile["model"] or {}).get("p_home"), "neutral": gm["neutral"]})
        out_rounds.append({"code": rd["code"], "name": rd["name"], "games": og})
    if pob:
        _write(podir / "games.json", {"season": args.season, "week": "PO", "built": built, "span": span, "synthetic": synth_run,
                                      "flags": flags, "projected": status != "final", "through_week": week - 1, "games": pob})
        new_weeks.append({"season": args.season, "week": "PO", "built": built, "synthetic": synth_run, "games": len(pob),
                          "projected": status != "final"})
    champ = out_rounds[-1]["games"][0]["winner"] if out_rounds and out_rounds[-1]["code"] == "SB" else None
    _write(ddir / "bracket.json", {"season": args.season, "status": status, "through_week": week - 1, "built": built,
                                   "seeds": sd, "rounds": out_rounds, "champion": champ, "synthetic": synth_run,
                                   "seed_basis": "projected" if getattr(bracket.plan, "by_proj", False) else "standings",
                                   "luck": (mmeta or {}).get("luck")})
    log.info("projected: %d games in weeks %s · bracket %s, %d games", n_proj, fut, status, len(pob))

    # ---------- index ----------
    _write(site / "data" / "teams.json", M)
    weeks = [w for w in idx["weeks"] if not (w["season"] == args.season and w["week"] == week)]
    if not synth_run:
        for w in [w for w in weeks if w.get("synthetic")]:
            sdir = site / "data" / str(w["season"]) / wname(w["week"])
            for f in sdir.glob(f"{w['season']}_*.json"):
                (site / "og" / f"{f.stem}.png").unlink(missing_ok=True)
                (site / "g" / f"{f.stem}.html").unlink(missing_ok=True)
            shutil.rmtree(sdir, ignore_errors=True)
        weeks = [w for w in weeks if not w.get("synthetic")]
    weeks += new_weeks
    weeks.sort(key=lambda w: (w["season"], w["week"] if isinstance(w["week"], int) else 99))
    real = [w for w in weeks if not w.get("projected") and isinstance(w["week"], int)]
    _write(idx_path, {"title": SITE_TITLE, "handle": HANDLE, "weeks": weeks, "site_url": SITE_URL,
                      "buttondown": BUTTONDOWN_USERNAME or None, "email_per_team": EMAIL_PER_TEAM,
                      "goatcounter": GOATCOUNTER_CODE or None,
                      "latest": {"season": real[-1]["season"], "week": real[-1]["week"]}})

    # ---------- recaps, record, league, share pages ----------
    n_graded = record.grade_weeks(site, args.season, week, sched, plays, tpls, M, synth_run)
    n_pub, n_walk = record.build(site, args.season, week, mmeta, synth_run, E.pre)
    league.build(site, args.season, week, plays, sched, tpls, lev_teams, lev_proj, M, pctx["qb"], pctx["names"], synth_run)
    for od in ddir.glob("wk*"):
        if od != wdir and od.name[2:].isdigit() and (od / "games.json").exists() \
                and not json.loads((od / "games.json").read_text()).get("projected"):
            docs += [json.loads(f.read_text()) for f in od.glob(f"{args.season}_*.json") if not (site / "g" / f"{f.stem}.html").exists()]
    n_og = share.write(site, docs, M)
    log.info("recaps: %d graded · record: %d published, %d walk-forward · %d new preview images", n_graded, n_pub, n_walk, n_og)
    health.info("recaps", {"graded": n_graded, "published": n_pub, "walk": n_walk})
    log.info("feeds: %d items", feeds.build(site, M))
    if not synth_run:
        nl, nh = assets.download(site, M, pctx["heads"], pctx["need_heads"])
        if nl < len(M):
            health.warn(f"logos: {nl}/{len(M)} downloaded")
        notify.send_week(wdir, M, [b["id"] for b in board], week)
    log.info("wrote %d games to %s", len(board), wdir)
    health.info("games", len(board))
    health.info("projected_games", n_proj)
    health.info("summaries", sum_counts)
    health.info("luck", (mmeta or {}).get("luck"))
    health.info("model", {"ran": bool(mmeta), **({k: mmeta[k] for k in ("alpha", "sigma", "hfa", "n_train")} if mmeta else {})})
    if not board:
        health.error("no games written")
    if os.environ.get("ANTHROPIC_API_KEY") and not args.no_llm and sum_counts["rule"]:
        health.warn(f"LLM summary fell back to rule-based for {sum_counts['rule']} games. Last error: {summary.LAST_ERR or 'unknown'}")
    log.info("health: %s", health.write(site))


if __name__ == "__main__":
    main()
