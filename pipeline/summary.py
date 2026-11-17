"""Two-sentence 'who has the edge' summary. The lean (which team) is decided in code, from the
model when it exists, else the market. The LLM only explains it with numbers from the facts.
Output numbers are checked against the facts; on failure we use a rule-based fallback."""
import hashlib
import json
import logging
import os
import re

from .config import LLM_MODEL

log = logging.getLogger(__name__)

SYSTEM = (
    "You write three-sentence NFL matchup previews for a technical analytics audience.\n"
    "Sentence 1: say that the team named in `lean` has the edge on paper (or that it is close, if `lean` is "
    "'close'), with its strongest reason from `keys`, then the other team's best counter-edge, with numbers.\n"
    "Sentence 2: from `players`, compare the two quarterbacks by their EPA per dropback ranks, then name the "
    "x-factor player with his number and the matchup it meets.\n"
    "Sentence 3: the model's main reasons, from `model`: its favorite, win probability and the top factors "
    "with their point values. If `model` is null, write about the market from `market_win_pct` instead.\n"
    "Rules: use only facts and numbers from the JSON. Do not add statistics, injuries, records, history or "
    "betting advice. Use hedged wording such as 'on paper'. Exactly three sentences, plain text, no em dashes, "
    "under 100 words."
)
_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _nums(s):
    return {n.lstrip("+-").rstrip("0").rstrip(".") or "0" for n in _NUM.findall(s)}


VERSION = "7"  # bump to regenerate cached summaries after a prompt or fallback change


def facts_hash(facts):
    return hashlib.sha1((VERSION + json.dumps(facts, sort_keys=True)).encode()).hexdigest()[:12]


def lean(home, away, model_p, market_p, labels):
    p = model_p if model_p is not None else market_p
    if p is None or abs(p - 0.5) < 0.05:
        return "close"
    return labels[home] if p > 0.5 else labels[away]


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _clause(k):
    """'Pittsburgh ranks 1st in EPA per designed run (+0.03). ...' -> 'Pittsburgh ranks 1st in EPA per designed run, +0.03'"""
    first = k["detail"].split(". ")[0].rstrip(".")
    return first.replace(" (", ", ").rstrip(")")


def fallback(facts):
    """Three sentences: edge and counter from the keys, players to watch, the model's top factors."""
    keys, labels, lead = facts["keys"], facts["labels"], facts.get("lean_abbr")
    teams = list(keys)
    t1 = lead or max(teams, key=lambda t: sum(k["favorable"] for k in keys[t]))
    other = [t for t in teams if t != t1][0]
    k1 = next((k for k in keys[t1] if k["favorable"]), keys[t1][0] if keys[t1] else None)
    k2 = next((k for k in keys[other] if k["favorable"]), None)
    if lead:
        s = f"On paper {labels[t1]} has the edge" + (f" ({_clause(k1)})" if k1 else "")
    else:
        s = "On paper this one is close" + (f": {labels[t1]}'s best edge is to {k1['phrase'][0].lower() + k1['phrase'][1:]} ({_clause(k1)})" if k1 else "")
    if k2:
        s += f", while {labels[other]}'s best counter is to {k2['phrase'][0].lower() + k2['phrase'][1:]} ({_clause(k2)})"
    out = [s + "."]
    pw = facts.get("players") or {}
    qbs, xf = pw.get("qbs", []), pw.get("xfactor")
    parts = []
    if len(qbs) == 2:
        q1, q2 = sorted(qbs, key=lambda q: q["rank"])
        parts.append(f"Under center, {q1['name']} ranks {_ord(q1['rank'])} of {q1['of']} in EPA per dropback and "
                     f"{q2['name']} ranks {_ord(q2['rank'])}")
    elif qbs:
        parts.append(f"Under center, {qbs[0]['name']} ranks {_ord(qbs[0]['rank'])} of {qbs[0]['of']} in EPA per dropback")
    if xf:
        d = xf["detail"].rstrip(".")
        parts.append(f"x-factor: {xf['headline'].rstrip('.')}" + (f", and {d[0].lower() + d[1:] if d.startswith(('The ', 'His ')) else d}" if d else ""))
    if parts:
        out.append("; ".join(parts) + ".")
    m = facts.get("model")
    if m and m["top_factors"]:
        f = [f"{x['label'].lower().replace('qb', 'QB')} ({x['points']:.1f} pts)" for x in m["top_factors"][:2]]
        out.append(f"The model favors {m['favorite']} at {m['win_pct']}%, mostly on " + " and ".join(f) + ".")
    return " ".join(out)


LAST_ERR = None  # last failure reason, shown in the build health warnings


def summarize(facts):
    global LAST_ERR
    key = os.environ.get("ANTHROPIC_API_KEY")  # GitHub Actions repository secret
    if not key:
        log.warning("summary: ANTHROPIC_API_KEY not set, using rule-based fallback")
        return fallback(facts), "rule"
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        allowed = _nums(json.dumps(facts))
        for attempt in range(2):
            msg = client.messages.create(model=LLM_MODEL, max_tokens=2000, system=SYSTEM,
                                         messages=[{"role": "user", "content": json.dumps(facts)}])
            text = "".join(b.text for b in msg.content if b.type == "text").strip().replace("—", ",")
            if not text:  # e.g. the token budget ran out before any text block
                LAST_ERR = f"empty reply (stop_reason={msg.stop_reason}, blocks={[b.type for b in msg.content]})"
                log.warning("summary: attempt %d %s", attempt + 1, LAST_ERR)
                continue
            bad = _nums(text) - allowed
            if not bad:
                return text, "llm"
            LAST_ERR = f"used numbers not in the facts {sorted(bad)[:5]}"
            log.warning("summary: attempt %d used numbers not in facts %s", attempt + 1, sorted(bad))
    except Exception as e:  # never fail the build on the summary
        LAST_ERR = f"{type(e).__name__}: {str(e)[:200]}"
        log.warning("summary: API call failed (%s: %s), using fallback", type(e).__name__, e)
    return fallback(facts), "rule"
