"""Chart images for emails: open the built site in headless Chromium, screenshot chosen parts, upload each PNG to
Buttondown's image store. Optional: any failure skips that image and the email goes out with what worked."""
import functools
import http.server
import logging
import threading

import requests

log = logging.getLogger(__name__)
IMAGES = "https://api.buttondown.com/v1/images"
HIDE = ".card-actions, .catbar, .cardbar, .topbar, header, nav, footer { display: none !important; }"


def _serve(site):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    h = functools.partial(Quiet, directory=str(site))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def shots(site, specs, key, tmp, upload=None):
    """specs: dicts with name, route (hash route), sel (CSS), optional tab (matchup tab to click), text (must contain),
    width. Returns {name: image_url}. `upload(path)` overrides the Buttondown upload (tests)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("snaps: playwright not installed, no images")
        return {}

    def up(path):
        with open(path, "rb") as f:
            r = requests.post(IMAGES, headers={"Authorization": f"Token {key}"}, files={"image": f}, timeout=30)
        r.raise_for_status()
        return r.json()["image"]

    out, srv = {}, _serve(site)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            for sp in specs:
                try:
                    p = b.new_page(viewport={"width": sp.get("width", 760), "height": 1400}, device_scale_factor=2)
                    p.goto(f"http://127.0.0.1:{srv.server_port}/{sp['route']}")
                    p.wait_for_selector(sp["sel"], timeout=20000)
                    if sp.get("tab"):
                        p.click(f"button[data-tab='{sp['tab']}']")
                    p.add_style_tag(content=HIDE)
                    p.wait_for_timeout(1500)  # cards fade in
                    loc = p.locator(f"{sp['sel']}:visible", has_text=sp["text"]) if sp.get("text") else p.locator(f"{sp['sel']}:visible")
                    if loc.count():
                        path = f"{tmp}/{sp['name']}.png"
                        loc.first.screenshot(path=path)
                        out[sp["name"]] = (upload or up)(path)
                    p.close()
                except Exception as e:
                    log.warning("snaps: %s: %s", sp["name"], e)
            b.close()
    except Exception as e:
        log.warning("snaps: %s", e)
    finally:
        srv.shutdown()
    return out
