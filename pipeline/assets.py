import logging
from pathlib import Path

log = logging.getLogger(__name__)


def fetch(url, path):
    path = Path(path)
    if path.exists() or not isinstance(url, str) or not url.startswith("http"):
        return path.exists()
    try:
        import requests

        r = requests.get(url, timeout=15)
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        return True
    except Exception as e:
        log.warning("asset fetch failed %s: %s", url, e)
        return False


def download(site, meta, heads, need_heads):
    for ab, m in meta.items():
        fetch(m.get("logo_url"), Path(site) / m["logo"])
    for pid in need_heads:
        fetch(heads.get(pid), Path(site) / "assets" / "heads" / f"{pid}.png")
