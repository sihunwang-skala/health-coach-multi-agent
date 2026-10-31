"""Real screenshots of the running Korean UI + an axe-core accessibility scan (no LLM calls, $0).
Needs the app on :8000 and system Chrome:  .venv/bin/python scripts/ui_screenshots.py
- The emergency step is live and adds one row to data/coach.db (delete it afterwards if you keep that DB clean).
- Answers shown are RECORDED evaluation runs (/replay), not live answers; the emergency screen is live (code path, no LLM).
- The approval dialog is opened from the page's own dialog code with a sample question (a UI-state capture, not a live run).
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "ui" / "screenshots"
BASE = "http://localhost:8000"
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.0/axe.min.js"


def axe(page, name, report):
    page.add_script_tag(url=AXE)
    r = page.evaluate("axe.run(document, {runOnly:['wcag2a','wcag2aa']}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.length})))")
    report[name] = r


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for name, w, h in (("mobile_360", 360, 760), ("tablet_768", 768, 1024), ("desktop_1280", 1280, 800)):
            pg = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2).new_page()
            pg.goto(f"{BASE}/?user=u01&replay=Maria-E1")
            pg.wait_for_selector(".cite")
            pg.wait_for_timeout(500)
            pg.screenshot(path=OUT / f"user_{name}_answer.png")
            axe(pg, f"user_{name}", report)
            pg.locator(".cite").first.click()
            pg.wait_for_timeout(400)
            pg.screenshot(path=OUT / f"user_{name}_citation.png")
            report[f"user_{name}_hscroll"] = pg.evaluate("document.documentElement.scrollWidth > innerWidth")
            pg.keyboard.press("Escape")
        pg = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2).new_page()
        pg.goto(f"{BASE}/admin")
        pg.wait_for_selector("#kpis .kpi")
        pg.wait_for_timeout(1200)
        pg.screenshot(path=OUT / "admin_desktop_1280.png", full_page=True)
        axe(pg, "admin_desktop_1280", report)
        report["admin_1280_hscroll"] = pg.evaluate("document.documentElement.scrollWidth > innerWidth")
        pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()   # live emergency (code path)
        pg.goto(f"{BASE}/?user=u01")
        pg.wait_for_selector("#msg")
        pg.fill("#msg", "산책 후 가슴이 조이고 숨이 막혀요")
        pg.click("#send")
        pg.wait_for_selector(".banner")
        pg.evaluate("window.scrollTo(0,0)")
        pg.wait_for_timeout(300)
        pg.screenshot(path=OUT / "user_mobile_390_emergency.png")
        pg.evaluate("askApproval({thread_id:'sample',interrupt:{question:'이 기록을 삭제할까요? \"저녁 먹고 30분 걸었어요\"'}})")
        pg.wait_for_timeout(300)
        pg.screenshot(path=OUT / "user_mobile_390_approval_dialog_ui_state.png")
        b.close()
    (OUT / "a11y_axe_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
