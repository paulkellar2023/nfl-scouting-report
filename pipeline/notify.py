"""Weekly Buttondown emails: one digest to every subscriber; with EMAIL_PER_TEAM also one per team
(subscribers tagged with the team abbreviation) and the digest goes to subscribers tagged ALL. Runs once per week: a marker file in the week folder blocks
repeats from the Saturday and Sunday refreshes. EMAIL_MODE = "draft" creates drafts only."""
import json
import logging
import os
from pathlib import Path

from . import health
from .config import EMAIL_MODE, EMAIL_PER_TEAM, SITE_TITLE, SITE_URL

log = logging.getLogger(__name__)
API = "https://api.buttondown.com/v1/emails"


def _tag_filter(tag):
    return {"predicate": "and", "groups": [],
            "filters": [{"field": "subscriber.tags", "operator": "contains", "value": tag}]}


def _team_body(d, team, teams):
    a, h = d["away"], d["home"]
    link = f"{SITE_URL}g/{d['id']}.html"
    lines = [f"**{teams[a]['name']} at {teams[h]['name']}** · {d['kickoff']}"]
    if d.get("line"):
        lines.append(f"Line: {d['line']['text']}")
    m = d.get("model")
    if m and m.get("market", {}).get("p_home") is not None:
        p = m["p_home"] if team == h else 1 - m["p_home"]
        q = m["market"]["p_home"] if team == h else 1 - m["market"]["p_home"]
        lines.append(f"{teams[team]['nick']} win probability: model {round(100 * p)}%, market {round(100 * q)}%")
    if d.get("summary"):
        lines += ["", d["summary"]]
    keys = d.get("keys", {}).get(team, [])
    if keys:
        lines += ["", f"**{teams[team]['nick']}: 3 keys to success**"]
        lines += [f"{i + 1}. **{k['phrase']}.** {k['detail']}" for i, k in enumerate(keys)]
    lines += ["", f"[Open the full matchup]({link})", "", "_A different lens on the data, not betting advice._"]
    return "\n".join(lines)


def _digest_body(docs, week, teams):
    lines = [f"Week {week} matchups, ordered by playoff leverage.", ""]
    for d in docs:
        a, h = d["away"], d["home"]
        link = f"{SITE_URL}g/{d['id']}.html"
        first = (d.get("summary") or "").split(". ")[0].rstrip(".")
        lines.append(f"- **[{teams[a]['nick']} at {teams[h]['nick']}]({link})** · {d.get('line', {}) and d['line']['text'] or ''}"
                     + (f"  \n  {first}." if first else ""))
    lines += ["", f"[Open the week board]({SITE_URL}#/{docs[0]['season']}/{week})" if docs else "",
              "", "_A different lens on the data, not betting advice._"]
    return "\n".join(lines)


def send_week(wdir, teams, ordered_ids, week):
    key = os.environ.get("BUTTONDOWN_API_KEY")  # GitHub Actions repository secret
    if not key:
        log.info("email: BUTTONDOWN_API_KEY not set, skipping")
        return
    marker = Path(wdir) / "email_sent.json"
    if marker.exists():
        log.info("email: week %s already sent (%s), skipping", week, marker)
        return
    import requests

    docs = []
    for gid in ordered_ids:
        try:
            docs.append(json.loads((Path(wdir) / f"{gid}.json").read_text()))
        except (OSError, ValueError):
            pass
    status = "about_to_send" if EMAIL_MODE == "send" else "draft"
    hdr = {"Authorization": f"Token {key}"}
    if status == "about_to_send":
        hdr["X-Buttondown-Live-Dangerously"] = "true"  # newer API versions refuse a direct send without it
    jobs = [(f"{SITE_TITLE}: Week {week} preview", _digest_body(docs, week, teams), "ALL" if EMAIL_PER_TEAM else None)]
    for d in (docs if EMAIL_PER_TEAM else []):
        for t in (d["away"], d["home"]):
            opp = d["home"] if t == d["away"] else d["away"]
            jobs.append((f"{SITE_TITLE}: {teams[t]['nick']} vs. {teams[opp]['nick']}, Week {week}",
                         _team_body(d, t, teams), t))
    ok = 0
    for subject, body, tag in jobs:
        try:
            payload = {"subject": subject, "body": body, "status": status}
            if tag:
                payload["filters"] = _tag_filter(tag)
            r = requests.post(API, headers=hdr, timeout=20, json=payload)
            r.raise_for_status()
            ok += 1
        except Exception as e:  # one failed email must not stop the others or the build
            log.warning("email: %s failed: %s %s", tag, e, getattr(getattr(e, "response", None), "text", "")[:300])
    log.info("email: %d/%d %s created for week %s", ok, len(jobs), status, week)
    health.info("email", {"created": ok, "total": len(jobs), "status": status})
    if ok < len(jobs):
        health.warn(f"email: only {ok}/{len(jobs)} {status}s created (search the log for 'email:')")
    if ok:
        marker.write_text(json.dumps({"week": week, "status": status, "created": ok}))
