import json
import logging
import os

from .config import LLM_MODEL

log = logging.getLogger(__name__)

SYSTEM = (
    "You write two-sentence NFL matchup previews for a technical analytics audience. "
    "Use only the facts in the JSON the user sends. Do not add statistics, injuries, history, "
    "records, or a prediction of the winner. Write exactly two sentences, plain text, "
    "no em dashes, no hype words."
)


def summarize(facts):
    key = os.environ.get("ANTHROPIC_API_KEY")  # set as a GitHub Actions repository secret
    if not key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model=LLM_MODEL, max_tokens=220, system=SYSTEM,
                                     messages=[{"role": "user", "content": json.dumps(facts)}])
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text.replace("—", ",") or None
    except Exception as e:  # summary is optional; never fail the build
        log.warning("summary failed: %s", e)
        return None
