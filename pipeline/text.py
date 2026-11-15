import math
import re


def ordinal(n):
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def rank_phrase(r, n):
    """'NFL's best', '3rd-best', '4th-worst', 'NFL's worst'."""
    if r == 1:
        return "NFL's best"
    if r == n:
        return "NFL's worst"
    if r <= n / 2:
        return f"{ordinal(r)}-best"
    return f"{ordinal(n + 1 - r)}-worst"


def fmt(v, kind):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if kind in ("epa", "yds", "pct_pm") and abs(v) < (0.005 if kind == "epa" else 0.05 if kind == "yds" else 0.0005):
        v = 0.0
    if kind == "epa":
        return f"{v:+.2f}"
    if kind == "pct":
        return f"{100 * v:.0f}%"
    if kind == "pct1":
        return f"{100 * v:.1f}%"
    if kind == "pct_pm":
        return f"{100 * v:+.1f}%"
    if kind == "yds":
        return f"{v:+.1f} yds"
    return f"{v:.2f}"


def possessive(name):
    return name + ("'" if name.endswith("s") else "'s")


_PL = {"has": "have", "is": "are", "isn't": "aren't", "ranks": "rank", "plays": "play", "walls": "wall",
       "averages": "average", "allows": "allow", "carves": "carve", "manages": "manage", "feasts": "feast",
       "struggles": "struggle", "throws": "throw", "uses": "use", "blitzes": "blitz", "gets": "get"}
_VERBS = "|".join(re.escape(v) for v in _PL)


def agree(text, plurals):
    """Verb agreement for plural team labels ('the Giants has' -> 'the Giants have')."""
    if not isinstance(text, str):
        return text
    for lab in plurals:
        text = re.sub(rf"({re.escape(lab)})( rarely)? ({_VERBS})\b",
                      lambda m: f"{m.group(1)}{m.group(2) or ''} {_PL[m.group(3)]}", text, flags=re.I)
        text = re.sub(rf"({re.escape(lab)}) are playing its", r"\1 are playing their", text, flags=re.I)
    text = re.sub(r"(^|[.!?]\s+)the\b", lambda m: m.group(1) + "The", text)
    return text
