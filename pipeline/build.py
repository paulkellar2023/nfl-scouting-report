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

from . import (assets, clean, context, feeds, health, league, leverage, model, model_cards, notify, record, share, stats, story,
               summary, templates_player, templates_team)
from .text import agree
from .config import BUTTONDOWN_USERNAME, GOATCOUNTER_CODE, MODEL_FIRST_SEASON, SITE_URL
from .config import (HANDLE, MAX_PLAYER_CARDS, MAX_TEAM_CARDS, MIN_PLAYER_CARDS, MIN_TEAM_CARDS,
                     PRIMETIME_BONUS, SEASON, SITE_TITLE)

log = logging.getLogger("build")
DAYS = {"Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun", "Monday": "Mon"}


def _json(o):
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, default=_json, separators=(",", ":")))


def detect_week(sched, season):
    reg = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
    open_ = reg[reg["result"].isna()]
    return int(open_["week"].min()) if len(open_) else int(reg["week"].max())


def line_info(g):
    sp, tot = g.get("spread_line"), g.get("total_line")
    if sp is None or pd.isna(sp):
        return None
    sp = float(sp)
    fav = g.home_team if sp > 0 else g.away_team
    text = "PK" if sp == 0 else f"{fav} -{abs(sp):g}"
    out = {"spread": sp, "text": text, "total": None, "implied": None}
    if tot is not None and not pd.isna(tot):
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
        tm = str(g.gametime)
    day = DAYS.get(str(g.get("weekday")), str(g.get("weekday"))[:3])
    date = str(g.gameday)[5:].replace("-", "/").lstrip("0")
    return f"{day} {date} · {tm} ET"


def kicked_off(g, now):
    """True if the game's ET kickoff time has passed (or a result exists)."""
    if pd.notna(g.get("result")):
        return True
    try:
        from zoneinfo import ZoneInfo
        ko = dt.datetime.strptime(f"{g.gameday} {g.gametime}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("America/New_York"))
        return now >= ko
    except (ValueError, TypeError):
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=SEASON)
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--site", default="site")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--refresh-started", action="store_true", help="rebuild games that already kicked off (testing)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.synthetic:
        from . import synth
        hist = synth.load_history(list(range(args.season - 4, args.season + 1)), args.season, args.week or 12)
        raw = {**hist, "pbp": hist["cur_pbp"], "sched": hist["cur_sched"]}
        first = args.season - 3
    else:
        from . import load
        raw = load.load(args.season)
        first = MODEL_FIRST_SEASON
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

    plays, flags = clean.prepare(raw, week)
    health.info("week", week)
    health.info("plays", int(len(plays)))
    health.info("flags", flags)
    health.info("sources", {k: raw.get(k) is not None for k in ("rosters", "part", "ftn")})
    sum_counts = {"llm": 0, "rule": 0, "kept": 0, "cached": 0}
    games = sched[(sched["week"] == week) & (sched["game_type"] == "REG")]
    active = sorted(set(plays["posteam"].dropna()) | set(games["home_team"]) | set(games["away_team"]))
    M = context.team_meta(raw["teams"], active)
    pctx = context.player_context(plays, raw.get("rosters"), sched, week)
    pctx["flags"] = flags
    pctx["need_heads"] = set()

    tpls = templates_team.build(plays, flags, pctx["qb"], active)
    shells = templates_team.shell_tables(plays) if flags["coverage"] else None
    gaps = templates_team.gap_tables(plays)
    form = templates_team.form_tables(plays)
    luck = templates_team.luck_tables(plays) if flags["int_worthy"] else None
    ptabs = templates_player.build_tables(plays, flags)

    preds, mmeta = {}, None
    if hist is not None and hist.get("sched") is not None:
        try:
            preds, mmeta = model.run(hist, args.season, week, pctx["qb"], first)
        except Exception:
            log.exception("model failed; building without it")
            health.error("model failed: Model tab skipped")

    e = plays[plays["eff"]]
    o_all, d_all = stats.opp_adjust(e, "epa")
    lev = leverage.simulate(sched, M, week, leverage.ratings(o_all, d_all))
    lev_teams = lev.pop("_teams", {})

    site = Path(args.site)
    wdir = site / "data" / str(args.season) / f"wk{week:02d}"
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
    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    span = f"Weeks 1-{week - 1}, {args.season}" if week > 2 else f"Week 1, {args.season}"
    board, docs = [], []
    for _, g in games.iterrows():
        a_, h_ = g.away_team, g.home_team
        started = kicked_off(g, now)
        if started and not args.refresh_started and g.game_id in prev_doc and g.game_id in prev_tile:
            _write(wdir / f"{g.game_id}.json", prev_doc[g.game_id])
            docs.append(prev_doc[g.game_id])
            board.append(prev_tile[g.game_id])
            log.info("kept pre-kickoff report for %s", g.game_id)
            sum_counts["kept"] += 1
            continue
        game = {"span": span}
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
        ctxs = [story.form_card(form, a_, h_, M, game), story.luck_card(luck, a_, h_, M, game)]
        team_cards, team_n = story.select(rendered + specials + [c for c in ctxs if c], MIN_TEAM_CARDS, MAX_TEAM_CARDS, (a_, h_))
        pc = templates_player.Cards(ptabs, pctx, M, tpls, game)
        player_cards, player_n = templates_player.select(pc.all(a_, h_), MIN_PLAYER_CARDS, MAX_PLAYER_CARDS)
        keys = {t: story.keys_for(t, cands, specials, M) for t in (a_, h_)}
        heat = []
        for c in cands:
            if c["id"] in ("pass_epa", "rush_epa"):
                heat.append({"team": c["a"], "unit": "PASS" if c["id"] == "pass_epa" else "RUSH",
                             "edge": round(float(c["edge"]), 2)})
        heat.sort(key=lambda x: (x["team"] != a_, x["unit"]))
        lv = lev.get(g.game_id, {"leverage": 0.0, "by_team": {}, "p_playoffs": {}})
        prime = str(g.gametime) >= "19:00"
        ln_now = line_info(g)
        ln, ln_asof = prev_line.get(g.game_id, (ln_now, built))
        mp = preds.get(g.game_id)
        mcards = model_cards.build(mp, mmeta, M, pctx["names"]) if mp else []
        kicker = f"{M[a_]['nick']} at {M[h_]['nick']} · Week {week}, {args.season}".upper()
        plurals = [M[t]["label"] for t in (a_, h_) if M[t].get("plural")]
        for c in team_cards + player_cards + mcards:
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
        if prev.get("summary_hash") == fh and prev.get("summary"):
            summ, summ_src = prev["summary"], prev.get("summary_src", "llm")
            sum_counts["cached"] += 1
        elif args.no_llm:
            summ, summ_src = summary.fallback(facts), "rule"
        else:
            summ, summ_src = summary.summarize(facts)
            sum_counts[summ_src] += 1
        summ = agree(summ, plurals)
        doc = {"id": g.game_id, "season": args.season, "week": week, "away": a_, "home": h_, "kicker": kicker,
               "kickoff": kickoff(g), "primetime": prime, "line": ln, "leverage": lv, "summary": summ, "summary_src": summ_src, "summary_hash": fh,
               "keys": keys, "heat": heat, "team_cards": team_cards, "player_cards": player_cards,
               "team_n": team_n, "player_n": player_n, "built": built, "after_kickoff": started, "line_asof": ln_asof, "line_now": ln_now,
               "model": ({"p_home": mp["p_home"], "margin": mp["margin"], "market": mp["market"],
                          "summary": agree(model_cards.summary(mp, M), plurals)} if mp else None),
               "model_cards": mcards}
        _write(wdir / f"{g.game_id}.json", doc)
        docs.append(doc)
        board.append({"id": g.game_id, "away": a_, "home": h_, "kickoff": kickoff(g), "primetime": prime,
                      "line": ln, "leverage": lv["leverage"], "heat": heat, "ko": f"{g.gameday}T{g.gametime}",
                      "model": {"p_home": mp["p_home"], "mkt": mp["market"]["p_home"]} if mp else None,
                      "rank": lv["leverage"] + (PRIMETIME_BONUS if prime else 0.0),
                      "tease": [team_cards[0]["t1"], team_cards[0]["t2"]] if team_cards else None,
                      "tease_owner": team_cards[0]["owner"] if team_cards else None})
    board.sort(key=lambda x: -x["rank"])
    if mmeta:
        _write(wdir / "model_meta.json", {k: v for k, v in mmeta.items() if k != "season_walk"})
    _write(wdir / "games.json", {"season": args.season, "week": week, "built": built, "span": span,
                                 "synthetic": bool(raw.get("synthetic")), "flags": flags, "games": board})
    _write(site / "data" / "teams.json", M)
    idx_path = site / "data" / "index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {"weeks": []}
    weeks = [w for w in idx.get("weeks", []) if not (w["season"] == args.season and w["week"] == week)]
    if not raw.get("synthetic"):
        for w in [w for w in weeks if w.get("synthetic")]:
            sdir = site / "data" / str(w["season"]) / f"wk{w['week']:02d}"
            for f in sdir.glob(f"{w['season']}_*.json"):
                (site / "og" / f"{f.stem}.png").unlink(missing_ok=True)
                (site / "g" / f"{f.stem}.html").unlink(missing_ok=True)
            shutil.rmtree(sdir, ignore_errors=True)
        weeks = [w for w in weeks if not w.get("synthetic")]
    weeks.append({"season": args.season, "week": week, "built": built, "synthetic": bool(raw.get("synthetic")),
                  "games": len(board)})
    weeks.sort(key=lambda w: (w["season"], w["week"]))
    _write(idx_path, {"title": SITE_TITLE, "handle": HANDLE, "weeks": weeks, "site_url": SITE_URL,
                      "buttondown": BUTTONDOWN_USERNAME or None, "goatcounter": GOATCOUNTER_CODE or None,
                      "latest": {"season": weeks[-1]["season"], "week": weeks[-1]["week"]}})
    synth_run = bool(raw.get("synthetic"))
    n_graded = record.grade_weeks(site, args.season, week, sched, plays, tpls, M, synth_run)
    n_pub, n_walk = record.build(site, args.season, week, mmeta, synth_run)
    league.build(site, args.season, week, plays, sched, tpls, lev_teams, M, pctx["qb"], pctx["names"], synth_run)
    for od in (site / "data" / str(args.season)).glob("wk*"):
        if od != wdir:
            docs += [json.loads(f.read_text()) for f in od.glob(f"{args.season}_*.json") if not (site / "g" / f"{f.stem}.html").exists()]
    n_og = share.write(site, docs, M)
    log.info("recaps: %d graded · record: %d published, %d walk-forward · %d new preview images", n_graded, n_pub, n_walk, n_og)
    health.info("recaps", {"graded": n_graded, "published": n_pub, "walk": n_walk})
    log.info("feeds: %d items", feeds.build(site, M))
    if not raw.get("synthetic"):
        nl, nh = assets.download(site, M, pctx["heads"], pctx["need_heads"])
        if nl < len(M):
            health.warn(f"logos: {nl}/{len(M)} downloaded")
        notify.send_week(wdir, M, [b["id"] for b in board], week)
    log.info("wrote %d games to %s", len(board), wdir)
    health.info("games", len(board))
    health.info("summaries", sum_counts)
    health.info("model", {"ran": bool(mmeta), **({k: mmeta[k] for k in ("alpha", "sigma", "hfa", "n_train")} if mmeta else {})})
    if not board:
        health.error("no games written")
    if os.environ.get("ANTHROPIC_API_KEY") and not args.no_llm and sum_counts["rule"]:
        health.warn(f"LLM summary fell back to rule-based for {sum_counts['rule']} games (search the log for 'summary:')")
    log.info("health: %s", health.write(site))


if __name__ == "__main__":
    main()
