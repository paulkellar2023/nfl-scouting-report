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
    "You are a sharp NFL analytics writer. Write a three-sentence matchup preview in your own voice for fans who "
    "know the numbers. Each preview should read differently from the last: vary how sentences open and what you lead with.\n"
    "Sentence 1: the one matchup most likely to decide this game, taken from `keys` or `storylines`. Frame it as a "
    "tension: what has to go right, for whom, and why it matters here. Use one or two numbers.\n"
    "Sentence 2: the player angle. Name the x-factor from `players` and what he runs into, or contrast the two "
    "quarterbacks if their ranks are far apart.\n"
    "Sentence 3: our number against the market. Say whether `model` agrees with `market_win_pct` or not, and which "
    "factor drives our number. If `model` is null, use the market alone.\n"
    "Rules: use only facts and numbers from the JSON, and at most two numbers per sentence. If a fact is missing, "
    "skip it without comment: never mention missing data, the JSON or 'the data'. Active voice, concrete verbs. "
    "Do not use these stock phrases: 'on paper', 'x-factor', 'under center', 'best counter', 'the model favors', "
    "'has the edge'. No betting advice, no em dashes, no hype words. Exactly three sentences, 50 to 85 words, plain text."
)
STOCK = ("on paper", "x-factor", "under center", "best counter", "the model favors", "has the edge", "the data")
_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _nums(s):
    return {n.lstrip("+-").rstrip("0").rstrip(".") or "0" for n in _NUM.findall(s)}


VERSION = "8"  # bump to regenerate cached summaries after a prompt or fallback change


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
            msg = client.messages.create(model=LLM_MODEL, max_tokens=8000, system=SYSTEM,
                                         messages=[{"role": "user", "content": json.dumps(facts)}])
            text = "".join(b.text for b in msg.content if b.type == "text").strip().replace("—", ",")
            if not text:  # the model thinks first; a small budget can run out before any text block
                LAST_ERR = f"empty reply (stop_reason={msg.stop_reason}, blocks={[b.type for b in msg.content]})"
                log.warning("summary: attempt %d %s", attempt + 1, LAST_ERR)
                continue
            bad = _nums(text) - allowed
            n_sent = len(re.findall(r"[.!?](?:\s|$)", text))
            stock = [p for p in STOCK if p in text.lower()]
            if not bad and n_sent == 3 and not stock:
                return text, "llm"
            if not bad:
                LAST_ERR = f"format: {n_sent} sentences, stock phrases {stock}"
                log.warning("summary: attempt %d %s", attempt + 1, LAST_ERR)
                if attempt == 1 and n_sent <= 4:
                    return text, "llm"  # numbers check out; a near-miss on format beats the rule-based text
                continue
            LAST_ERR = f"used numbers not in the facts {sorted(bad)[:5]}"
            log.warning("summary: attempt %d used numbers not in facts %s", attempt + 1, sorted(bad))
    except Exception as e:  # never fail the build on the summary
        LAST_ERR = f"{type(e).__name__}: {str(e)[:200]}"
        log.warning("summary: API call failed (%s: %s), using fallback", type(e).__name__, e)
    return fallback(facts), "rule"
