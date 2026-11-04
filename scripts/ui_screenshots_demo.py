"""Screenshots of the current UI in demo mode (COACH_DEMO=1), using the synthetic demo users and their saved demo history.
No LLM calls, $0. Needs the app running and system Chrome:
  .venv/bin/uvicorn app.server:app --port 8000
  SHOT_BASE=http://localhost:8000 .venv/bin/python scripts/ui_screenshots_demo.py
Pictures go to docs/ui/screenshots/2026-11/. They show saved demo history (a past evaluation run and its Korean translation), not live answers."""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "ui" / "screenshots" / "2026-11"
BASE = os.environ.get("SHOT_BASE", "http://localhost:8000")


def ctx(b, w, h, lang="ko", fs=None):
    c = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
    js = f"try{{localStorage.setItem('coach_lang','{lang}');" + (f"localStorage.setItem('coach_fs','{fs}');" if fs else "") + "}catch(e){}"
    c.add_init_script(js)
    return c


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for lang in ("ko", "en"):
            pg = ctx(b, 1280, 900, lang).new_page()
            pg.goto(BASE + "/login"); pg.wait_for_selector("#people button"); pg.wait_for_timeout(300)
            pg.screenshot(path=OUT / f"login_{lang}_1280.png")
            pg.goto(BASE + "/admin/login"); pg.wait_for_timeout(400)
            pg.screenshot(path=OUT / f"admin_login_{lang}_1280.png")
            # care-team console with the busiest two-week window
            pg.click("#demoBtn"); pg.wait_for_url(BASE + "/admin"); pg.wait_for_selector("#kpis .kpi"); pg.wait_for_timeout(1200)
            pg.screenshot(path=OUT / f"admin_overview_{lang}_1280.png", full_page=True)
            for v in ("alerts", "people"):
                pg.goto(BASE + f"/admin#{v}"); pg.wait_for_timeout(900)
                pg.screenshot(path=OUT / f"admin_{v}_{lang}_1280.png", full_page=True)
        # chat: history with citations, evidence panel, mobile, big text
        for lang in ("ko", "en"):
            for name, w, h in (("desktop_1280", 1280, 860), ("mobile_390", 390, 844)):
                pg = ctx(b, w, h, lang).new_page()
                pg.goto(BASE + "/login"); pg.wait_for_selector("#people button")
                pg.locator("#people button").nth(3).click(); pg.wait_for_url(BASE + "/"); pg.wait_for_timeout(1500)
                pg.screenshot(path=OUT / f"chat_{lang}_{name}_history.png")
                if pg.locator(".cite").count():
                    pg.locator(".cite").first.scroll_into_view_if_needed(); pg.locator(".cite").first.click(); pg.wait_for_timeout(600)
                    pg.screenshot(path=OUT / f"chat_{lang}_{name}_evidence.png")
        pg = ctx(b, 390, 844, "ko", fs=24).new_page()
        pg.goto(BASE + "/login"); pg.wait_for_selector("#people button"); pg.locator("#people button").nth(3).click()
        pg.wait_for_url(BASE + "/"); pg.wait_for_timeout(1500)
        pg.screenshot(path=OUT / "chat_ko_mobile_390_text_size_24.png")
        b.close()


if __name__ == "__main__":
    main()
