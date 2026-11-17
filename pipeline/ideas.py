"""Weekly scout for new card ideas. Collects candidates (new nflverse data releases, nflreadr/nflreadpy release notes,
active NFL data repos on GitHub, analytics feeds), asks the LLM which could become a matchup card, and opens one GitHub
issue per idea (label `idea`). PK accepts or declines by adding the label `accepted` or `declined`.
Run: python -m pipeline.ideas  (needs GITHUB_TOKEN with issues:write, GITHUB_REPOSITORY, ANTHROPIC_API_KEY)."""
import datetime as dt
import json
import logging
import os
import re
import xml.etree.ElementTree as ET

import requests

from .config import LLM_MODEL

log = logging.getLogger("pipeline.ideas")
GH = "https://api.github.com"
MAX_IDEAS = 5
LABELS = {"idea": "1D76DB", "accepted": "0E8A16", "declined": "B60205"}
FEEDS = ["https://www.opensourcefootball.com/index.xml", "https://www.reddit.com/r/NFLstatheads/top/.rss?t=week"]
RELEASE_REPOS = ["nflverse/nflverse-data", "nflverse/nflreadr", "nflverse/nflreadpy", "nflverse/nfl4th"]
HAVE = ("team EPA per play (pass, rush), success rate, explosive plays, pressure, blitz, coverage shell, play action, "
        "motion, YAC over expected, broken tackles, red zone, third downs, down and distance, target zones, pass/run "
        "lean (PROE), run gaps, drives, field position, scoring by quarter, win-probability timeline, penalties, "
        "special teams EPA, field goals over expected, 4th-down decisions (nfl4th), Next Gen Stats (time to throw, "
        "aggressiveness, separation, rush yards over expected, 8+ box), PFR advanced (pressures, missed tackles), "
        "fantasy (expected points, WOPR, target share, snap trends, QBR), injuries, Elo, weather")
SHORTLIST = 10  # the LLM proposes up to this many; coverage checks then keep the best MAX_IDEAS
MOCK_BRANCH = "idea-mockups"  # mockup images live on their own branch, so main and the site never change
PROMPT = ("You scout data for an NFL weekly matchup site. Each game page shows cards: one headline that compares the two "
          "teams (or their players) plus one chart that shows the whole league with the two teams highlighted. "
          f"The site already has: {HAVE}.\n"
          "From the candidates in the JSON, pick at most {n} that could become a NEW card. Only pick a candidate if its data "
          "is free, can be downloaded by a script (no scraping behind logins, no paid API), updates at least weekly during "
          "the season, and is at team or player level. Skip anything the site already has. It is fine to pick none.\n"
          "Each idea must also use a chart the site does not publish. Choose the mockup chart type from this list only: "
          "{types}.\n"
          "Return only a JSON array. Each item: {{\"url\": candidate url, \"name\": short name, \"why\": one sentence on "
          "what is new, \"card\": an example card headline, \"access\": how a Python script would load it, "
          "\"data_url\": a direct link to the data file or API if the candidate text shows one, else null, "
          "\"coverage\": what you can tell about seasons, teams and update frequency, \"effort\": \"S\", \"M\" or \"L\", "
          "\"score\": 1-10 for how much it would add, \"mockup\": {{\"type\": one type from the list, \"title\": the card "
          "headline, \"metric\": axis label with units, \"lo\": a realistic low value, \"hi\": a realistic high value, "
          "\"categories\": up to 8 short labels (sub-measures, or two time points for slope and dumbbell)}}}}.")


def _gh(method, path, token, **kw):
    r = requests.request(method, GH + path, timeout=30, headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}, **kw)
    r.raise_for_status()
    return r.json() if r.text else {}


def candidates(token, since):
    out = []
    for repo in RELEASE_REPOS:
        try:
            for rel in _gh("GET", f"/repos/{repo}/releases?per_page=30", token):
                if (rel.get("published_at") or rel.get("created_at") or "") >= since.isoformat():
                    out.append({"source": f"{repo} release", "title": rel.get("name") or rel.get("tag_name"),
                                "url": rel["html_url"], "text": (rel.get("body") or "")[:1500]})
        except Exception as e:
            log.warning("ideas: %s releases failed: %s", repo, e)
    try:
        q = f"nfl (data OR stats OR analytics) in:name,description,topics pushed:>{since.date()} stars:>=10"
        for it in _gh("GET", "/search/repositories", token, params={"q": q, "sort": "stars", "per_page": 20})["items"]:
            out.append({"source": "GitHub repo", "title": it["full_name"], "url": it["html_url"],
                        "text": (it.get("description") or "")[:400]})
    except Exception as e:
        log.warning("ideas: repo search failed: %s", e)
    for url in FEEDS:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "the-drill-down-ideas/1.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for it in root.iter():
                tag = it.tag.split("}")[-1]
                if tag not in ("item", "entry"):
                    continue
                f = {c.tag.split("}")[-1]: c for c in it}
                link = f.get("link")
                href = (link.get("href") or link.text) if link is not None else None
                body = next((f[k] for k in ("description", "content", "summary") if k in f), None)  # Elements are falsy: no `or`
                text = re.sub(r"<[^>]+>", " ", (body.text if body is not None else "") or "")
                if href:
                    out.append({"source": url.split("/")[2], "title": (f["title"].text if "title" in f else "") or "",
                                "url": href, "text": " ".join(text.split())[:600]})
        except Exception as e:
            log.warning("ideas: feed %s failed: %s", url, e)
    return out


def triage(cands, n=SHORTLIST):
    import anthropic

    from .mockups import NEW_TYPES

    types = "; ".join(f"{k} ({v})" for k, v in NEW_TYPES.items())
    msg = anthropic.Anthropic().messages.create(model=LLM_MODEL, max_tokens=12000, system=PROMPT.format(n=n, types=types),
                                                messages=[{"role": "user", "content": json.dumps(cands)}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\[.*\]", text, re.S)
    ideas = json.loads(m.group(0)) if m else []
    urls = {c["url"] for c in cands}
    return [i for i in ideas if isinstance(i, dict) and i.get("url") in urls][:n]  # only real candidate links


def _recent(ts, days):
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")) >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    except ValueError:
        return False


def coverage(idea, token):
    """Checks the data, not the LLM's word. Returns (status, note). status: weekly, stale, unverified."""
    season = str(dt.date.today().year if dt.date.today().month >= 8 else dt.date.today().year - 1)
    m = re.match(r"https://github.com/([^/]+/[^/]+)(?:/releases/tag/([^/?#]+))?", idea["url"])
    try:
        if m and m.group(2):  # a data release: does it have this season's file, updated in the last 10 days?
            rel = _gh("GET", f"/repos/{m.group(1)}/releases/tags/{m.group(2)}", token)
            cur = [a for a in rel.get("assets", []) if season in a["name"]]
            fresh = [a for a in cur if _recent(a.get("updated_at"), 10)]
            if fresh:
                return "weekly", f"{len(cur)} file(s) for {season}; newest updated {max(a['updated_at'] for a in fresh)[:10]}"
            if cur:
                return "stale", f"{season} file(s) exist but none updated in the last 10 days"
            return "stale", f"no {season} file in this release ({len(rel.get('assets', []))} files in all)"
        if m:  # a repo: recent commits and data files that name this season?
            info = _gh("GET", f"/repos/{m.group(1)}", token)
            tree = _gh("GET", f"/repos/{m.group(1)}/git/trees/{info['default_branch']}?recursive=1", token).get("tree", [])
            data = [t["path"] for t in tree if re.search(r"\.(csv|parquet|json|rds)(\.gz)?$", t["path"]) and season in t["path"]]
            if data and _recent(info.get("pushed_at"), 14):
                return "weekly", f"{len(data)} {season} data file(s); last push {info['pushed_at'][:10]}"
            if not _recent(info.get("pushed_at"), 14):
                return "stale", f"no push since {str(info.get('pushed_at'))[:10]}"
            return "unverified", f"active repo (last push {info['pushed_at'][:10]}) but no {season} data files found"
        if idea.get("data_url"):
            r = requests.head(idea["data_url"], timeout=20, allow_redirects=True)
            lm = r.headers.get("Last-Modified")
            if r.ok and lm:
                when = dt.datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc)
                return ("weekly" if _recent(when.isoformat(), 10) else "stale"), f"data link answers; last modified {when.date()}"
            return ("unverified" if r.ok else "stale"), f"data link answers {r.status_code}, no last-modified date"
    except Exception as e:
        return "unverified", f"check failed: {type(e).__name__}"
    return "unverified", "article or post: no data file to check"


def upload(repo, token, path, local):
    """Put a mockup PNG on the idea-mockups branch (made from main on first use). Returns its raw URL."""
    import base64

    try:
        _gh("GET", f"/repos/{repo}/branches/{MOCK_BRANCH}", token)
    except requests.HTTPError:
        sha = _gh("GET", f"/repos/{repo}/git/ref/heads/main", token)["object"]["sha"]
        _gh("POST", f"/repos/{repo}/git/refs", token, json={"ref": f"refs/heads/{MOCK_BRANCH}", "sha": sha})
    with open(local, "rb") as f:
        _gh("PUT", f"/repos/{repo}/contents/{path}", token, json={
            "message": f"Idea mockup {path}", "branch": MOCK_BRANCH, "content": base64.b64encode(f.read()).decode()})
    return f"https://raw.githubusercontent.com/{repo}/{MOCK_BRANCH}/{path}"


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    token, repo = os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"]
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(os.environ.get("IDEAS_DAYS", "8")))
    for name, color in LABELS.items():
        try:
            _gh("POST", f"/repos/{repo}/labels", token, json={"name": name, "color": color})
        except requests.HTTPError:
            pass  # already exists
    seen = set()
    for state in ("open", "closed"):
        for iss in _gh("GET", f"/repos/{repo}/issues?labels=idea&state={state}&per_page=100", token):
            seen |= set(re.findall(r"https?://\S+", iss.get("body") or ""))
    cands = list({c["url"]: c for c in candidates(token, since) if c["url"] not in seen}.values())
    log.info("ideas: %d new candidates", len(cands))
    if not cands:
        return
    from .mockups import NEW_TYPES, render

    ideas = []
    for i in triage(cands[:80]):
        i["cov"], i["cov_note"] = coverage(i, token)
        if i["cov"] == "stale" or (i.get("mockup") or {}).get("type") not in NEW_TYPES:
            log.info("ideas: dropped %s (%s; mockup %s)", i.get("name"), i["cov_note"], (i.get("mockup") or {}).get("type"))
            continue
        i["rank"] = float(i.get("score", 0) or 0) + (3 if i["cov"] == "weekly" else 0)  # verified weekly data ranks first
        ideas.append(i)
    ideas = sorted(ideas, key=lambda i: -i["rank"])[:MAX_IDEAS]
    stamp = f"{dt.date.today().isoformat()}/{os.environ.get('GITHUB_RUN_ID', 'local')}"  # unique per run
    for k, i in enumerate(ideas):
        img = ""
        try:
            local = f"/tmp/idea_{k}.png"
            if render(i["mockup"], local, i["url"]):
                img = f"![mockup]({upload(repo, token, f'{stamp}/idea_{k}.png', local)})\n\n"
        except Exception as e:
            log.warning("ideas: mockup for %s failed: %s", i.get("name"), e)
        badge = {"weekly": "✅ Verified: updates weekly", "unverified": "⚠️ Not verified"}[i["cov"]]
        body = (f"{img}**Source:** {i['url']}\n\n**What is new:** {i.get('why', '')}\n\n**Example card:** {i.get('card', '')}\n\n"
                f"**New chart type:** {i['mockup']['type']} (mockup above, made-up data)\n\n"
                f"**Data coverage:** {badge}. {i['cov_note']}. LLM read: {i.get('coverage', '')}\n\n"
                f"**How to load it:** {i.get('access', '')}\n\n"
                f"**Effort:** {i.get('effort', '?')} · **Score:** {i.get('score', '?')}/10\n\n---\n"
                "Decide: add the label `accepted` or `declined`. Accepted ideas are the queue for new cards. "
                "Found by the weekly idea scout (LLM triage; check the source before building).")
        _gh("POST", f"/repos/{repo}/issues", token, json={"title": f"Card idea: {i.get('name', 'untitled')}"[:120],
                                                          "body": body, "labels": ["idea"]})
        log.info("ideas: opened %s", i.get("name"))
    log.info("ideas: %d issues opened", len(ideas))


if __name__ == "__main__":
    main()
