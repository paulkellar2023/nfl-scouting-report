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
    "You write two-sentence NFL matchup previews for a technical analytics audience.\n"
    "Sentence 1: say that the team named in `lean` has the edge on paper (or that it is close, if `lean` is "
    "'close'), and give the 1 or 2 strongest reasons from `keys` or `storylines`, with their numbers.\n"
    "Sentence 2: give the other team's best counter-edge or the matchup that could flip the game, with a number.\n"
    "Rules: use only facts and numbers from the JSON. Do not add statistics, injuries, records, history or "
    "betting advice. Use hedged wording such as 'on paper' or 'the numbers favor'. Exactly two sentences, "
    "plain text, no em dashes, under 70 words."
)
_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _nums(s):
    return {n.lstrip("+-").rstrip("0").rstrip(".") or "0" for n in _NUM.findall(s)}


VERSION = "2"  # bump to regenerate cached summaries after a prompt or fallback change


def facts_hash(facts):
    return hashlib.sha1((VERSION + json.dumps(facts, sort_keys=True)).encode()).hexdigest()[:12]


def lean(home, away, model_p, market_p, labels):
    p = model_p if model_p is not None else market_p
    if p is None or abs(p - 0.5) < 0.05:
        return "close"
    return labels[home] if p > 0.5 else labels[away]


def fallback(facts):
    """Two sentences from the keys: the lean team's top key, then the other team's best favorable key."""
    keys, labels, lead = facts["keys"], facts["labels"], facts.get("lean_abbr")
    first = lambda k: k["detail"].split(". ")[0].rstrip(".")
    teams = list(keys)
    t1 = lead or max(teams, key=lambda t: sum(k["favorable"] for k in keys[t]))
    k1 = next((k for k in keys[t1] if k["favorable"]), keys[t1][0] if keys[t1] else None)
    s1 = (f"On paper {labels[t1]} has the edge" if lead else "On paper this one is close") + \
         (f": {first(k1)}." if k1 else ".")
    other = [t for t in teams if t != t1][0]
    k2 = next((k for k in keys[other] if k["favorable"]), None)
    s2 = f" {labels[other]}'s best counter is to {k2['phrase'][0].lower() + k2['phrase'][1:]}: {first(k2)}." if k2 else ""
    return s1 + s2


def summarize(facts):
    key = os.environ.get("ANTHROPIC_API_KEY")  # GitHub Actions repository secret
    if not key:
        log.warning("summary: ANTHROPIC_API_KEY not set, using rule-based fallback")
        return fallback(facts), "rule"
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        allowed = _nums(json.dumps(facts))
        for attempt in range(2):
            msg = client.messages.create(model=LLM_MODEL, max_tokens=220, temperature=0, system=SYSTEM,
                                         messages=[{"role": "user", "content": json.dumps(facts)}])
            text = "".join(b.text for b in msg.content if b.type == "text").strip().replace("—", ",")
            bad = _nums(text) - allowed
            if text and not bad:
                return text, "llm"
            log.warning("summary: attempt %d used numbers not in facts %s", attempt + 1, sorted(bad))
    except Exception as e:  # never fail the build on the summary
        log.warning("summary: API call failed (%s: %s), using fallback", type(e).__name__, e)
    return fallback(facts), "rule"
