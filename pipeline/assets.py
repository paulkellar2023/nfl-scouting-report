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
    ok_logos = sum(fetch(m.get("logo_url"), Path(site) / m["logo"]) for m in meta.values())
    ok_heads = sum(fetch(heads.get(pid), Path(site) / "assets" / "heads" / f"{pid}.png") for pid in need_heads)
    log.info("assets: %d/%d logos, %d/%d headshots", ok_logos, len(meta), ok_heads, len(need_heads))
