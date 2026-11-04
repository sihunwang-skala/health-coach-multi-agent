"""Real screenshots of the running Korean UI + an axe-core accessibility scan (no LLM calls, $0).
Needs the app running and system Chrome. Use a throw-away database so no real data is touched:
  COACH_DB=/tmp/shots.db .venv/bin/uvicorn app.server:app --port 8010      (create one user and one staff account first, see docs/ui/DESIGN.md)
  SHOT_BASE=http://localhost:8010 SHOT_USER=... SHOT_PASS=... SHOT_STAFF=... SHOT_STAFF_PASS=... .venv/bin/python scripts/ui_screenshots.py
- Recorded answers (a past evaluation run, /replay, care-team only) are drawn with the page's own renderer: they are NOT live answers.
- The emergency screen is live (code path, no LLM). The approval dialog is a UI-state capture, not a live run.
"""
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "ui" / "screenshots"
BASE = os.environ.get("SHOT_BASE", "http://localhost:8010")
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.0/axe.min.js"


def axe(page, name, report):
    page.add_script_tag(url=AXE)
    report[name] = page.evaluate("axe.run(document, {runOnly:['wcag2a','wcag2aa']}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.length})))")
    report[name + "_hscroll"] = page.evaluate("document.documentElement.scrollWidth > innerWidth")


def sign_in(page, login_path, user, pw, landing):
    page.goto(BASE + login_path)
    page.fill("#inUser" if login_path == "/login" else "#u", user)
    page.fill("#inPw" if login_path == "/login" else "#p", pw)
    page.keyboard.press("Enter")
    page.wait_for_url(BASE + landing)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        staff = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        sp = staff.new_page()
        sp.goto(BASE + "/admin/login")
        sp.screenshot(path=OUT / "admin_login_1280.png")
        axe(sp, "admin_login", report)
        sign_in(sp, "/admin/login", os.environ["SHOT_STAFF"], os.environ["SHOT_STAFF_PASS"], "/admin")
        sp.wait_for_selector("#kpis .kpi")
        sp.wait_for_timeout(1200)
        sp.screenshot(path=OUT / "admin_overview_1280.png", full_page=True)
        axe(sp, "admin_overview_1280", report)
        recorded = staff.request.get(BASE + "/replay/Maria-E1").json()
        pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
        pg.goto(BASE + "/login")
        pg.screenshot(path=OUT / "login_mobile_390.png")
        axe(pg, "login_mobile_390", report)
        pg.click("#tabUp")
        pg.fill("#upName", "길동")
        pg.fill("#upUser", "shot_user1")
        pg.fill("#upPw", "Shotpass123")
        pg.click("#next")
        pg.screenshot(path=OUT / "signup_step2_mobile_390.png", full_page=True)
        for name, w, h in (("mobile_390", 390, 844), ("tablet_768", 768, 1024), ("desktop_1280", 1280, 800)):
            pg = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2).new_page()
            sign_in(pg, "/login", os.environ["SHOT_USER"], os.environ["SHOT_PASS"], "/")
            pg.wait_for_selector(".hello")
            pg.screenshot(path=OUT / f"chat_{name}_empty.png")
            axe(pg, f"chat_{name}_empty", report)
            pg.evaluate("r => { dropHello(); user('저녁 먹고 산책해도 괜찮을까요?'); bot({...r, route:'exercise'}) }", recorded)
            pg.wait_for_selector(".cite")
            pg.wait_for_timeout(400)
            pg.screenshot(path=OUT / f"chat_{name}_answer_recorded.png")
            pg.locator(".cite").first.click()
            pg.wait_for_timeout(500)
            pg.screenshot(path=OUT / f"chat_{name}_evidence_recorded.png")
            axe(pg, f"chat_{name}_evidence", report)
            pg.keyboard.press("Escape")
        pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()   # live emergency (code path)
        sign_in(pg, "/login", os.environ["SHOT_USER"], os.environ["SHOT_PASS"], "/")
        pg.fill("#msg", "가슴이 너무 아파요")
        pg.keyboard.press("Enter")
        pg.wait_for_selector(".banner.danger")
        pg.wait_for_timeout(300)
        pg.screenshot(path=OUT / "chat_mobile_390_emergency.png")
        pg.evaluate("$('adtext').textContent='이 기록을 삭제할까요? \"저녁 먹고 30분 걸었어요\"'; $('approveDlg').showModal()")
        pg.wait_for_timeout(300)
        pg.screenshot(path=OUT / "chat_mobile_390_approval_dialog_ui_state.png")
        b.close()
    (OUT / "a11y_axe_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
