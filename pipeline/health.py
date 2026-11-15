"""Build health: collected during the build, written to site/data/health.json.
`python -m pipeline.health <path>` exits 1 on status 'fail', so the workflow fails and GitHub emails you."""
import datetime as dt
import json
import sys
from pathlib import Path

H = {"warnings": [], "errors": [], "info": {}}


def warn(msg):
    H["warnings"].append(msg)


def error(msg):
    H["errors"].append(msg)


def info(key, value):
    H["info"][key] = value


def write(site):
    status = "fail" if H["errors"] else "warn" if H["warnings"] else "ok"
    out = {"status": status, "checked": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), **H}
    p = Path(site) / "data" / "health.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, default=str))
    return status


if __name__ == "__main__":
    h = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "site/data/health.json").read_text())
    for w in h["warnings"]:
        print(f"::warning::{w}")
    for e in h["errors"]:
        print(f"::error::{e}")
    print(f"health: {h['status']}")
    sys.exit(1 if h["status"] == "fail" else 0)
