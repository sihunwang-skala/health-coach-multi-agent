"""One clean screenshot per screen for the README and docs/ui/SCREENSHOTS.md (demo mode, synthetic users, saved demo
history, no LLM calls, $0). No grey overlay: the dim layer behind the evidence panel is hidden for the picture.
  .venv/bin/uvicorn app.server:app --port 8000
  SHOT_BASE=http://localhost:8000 .venv/bin/python scripts/ui_screenshots_readme.py
Output: docs/ui/screenshots/readme/NN_name_lang.png"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "ui" / "screenshots" / "readme"
BASE = os.environ.get("SHOT_BASE", "http://localhost:8000")
NO_DIM = "document.getElementById('scrim') && (document.getElementById('scrim').style.display='none')"


def ctx(b, w, h, lang="ko", fs=None):
    c = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
    js = f"try{{localStorage.setItem('coach_lang','{lang}');" + (f"localStorage.setItem('coach_fs','{fs}');" if fs else "") + "}catch(e){}"
    c.add_init_script(js)
    return c.new_page()


def enter(pg, i=3):
    pg.goto(BASE + "/login"); pg.wait_for_selector("#people button"); pg.locator("#people button").nth(i).click()
    pg.wait_for_url(BASE + "/"); pg.wait_for_selector(".cite"); pg.wait_for_timeout(1200)


KEYS = ["저녁 먹고 잠깐", "short walk", "walk after dinner", "walking after dinner"]


def to_first_answer(pg):
    """Scroll so the question about a walk after dinner and its whole answer (with evidence chips) are in view."""
    ok = pg.evaluate("""(keys)=>{const s=document.getElementById('scroll'),th=document.getElementById('thread');
      const kids=[...th.children];
      for(let i=0;i<kids.length;i++){const k=kids[i]; if(keys.some(x=>k.textContent.includes(x)) && !k.querySelector('.cite')){
        let a=kids.slice(i+1,i+3).find(n=>n.querySelector('.cite')); if(a){window.__cite=[...th.querySelectorAll('.cite')].indexOf(a.querySelector('.cite'));
        s.scrollTo({top:k.offsetTop-40}); return true}}} return false}""", KEYS)
    if not ok:
        pg.evaluate("""()=>{const s=document.getElementById('scroll');window.__cite=0;s.scrollTo({top:document.querySelector('.cite').offsetTop-300})}""")
    pg.wait_for_timeout(400)


def click_cite(pg):
    pg.evaluate("document.querySelectorAll('.cite')[window.__cite||0].click()")


def _old_first_answer(pg):
    pg.evaluate("""()=>{const s=document.getElementById('scroll'),c=document.querySelector('.cite');
      let n=c; while(n&&!(n.parentElement&&n.parentElement.id==='thread')) n=n.parentElement;
      s.scrollTo({top:n.offsetTop-90})}"""); pg.wait_for_timeout(400)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for lang in ("ko", "en"):
            pg = ctx(b, 1280, 900, lang)
            pg.goto(BASE + "/login"); pg.wait_for_selector("#people button"); pg.wait_for_timeout(300)
            pg.screenshot(path=OUT / f"01_user_login_{lang}.png")
            enter(pg); to_first_answer(pg)
            pg.screenshot(path=OUT / f"02_chat_answer_{lang}.png")
            click_cite(pg); pg.wait_for_timeout(700); pg.evaluate(NO_DIM); pg.wait_for_timeout(200)
            pg.screenshot(path=OUT / f"03_evidence_panel_{lang}.png")
            pg.keyboard.press("Escape")
            pg.evaluate("document.querySelector('.banner.danger').scrollIntoView({block:'center'})"); pg.wait_for_timeout(300)
            pg.screenshot(path=OUT / f"04_emergency_{lang}.png")
            st = ctx(b, 1280, 1000, lang)
            st.goto(BASE + "/admin/login"); st.wait_for_timeout(300)
            st.screenshot(path=OUT / f"05_care_login_{lang}.png")
            st.click("#demoBtn"); st.wait_for_url(BASE + "/admin"); st.wait_for_selector("#kpis .kpi"); st.wait_for_timeout(1300)
            st.set_viewport_size({"width": 1280, "height": 930}); st.screenshot(path=OUT / f"06_care_overview_{lang}.png")
            st.set_viewport_size({"width": 1280, "height": 1000})
            st.set_viewport_size({"width": 1280, "height": 560})
            st.goto(BASE + "/admin#alerts"); st.wait_for_timeout(1000); st.screenshot(path=OUT / f"07_care_alerts_{lang}.png")
            st.set_viewport_size({"width": 1280, "height": 1000})
            st.goto(BASE + "/admin#people"); st.wait_for_selector("#users tr.pick"); st.wait_for_timeout(600)
            st.screenshot(path=OUT / f"08_care_users_{lang}.png")
            st.locator("#users tr.pick").nth(4).click(); st.wait_for_timeout(1500)
            st.evaluate("document.getElementById('person').scrollIntoView();window.scrollBy(0,-110)"); st.wait_for_timeout(500)
            st.screenshot(path=OUT / f"09_care_user_detail_{lang}.png")
        for lang, fs, name in (("ko", None, "11_mobile_chat"), ("ko", None, "12_mobile_evidence"), ("ko", 24, "13_mobile_large_text"), ("en", None, "14_mobile_english")):
            pg = ctx(b, 390, 844, lang, fs); enter(pg); to_first_answer(pg)
            if name.endswith("evidence"):
                click_cite(pg); pg.wait_for_timeout(700); pg.evaluate(NO_DIM); pg.wait_for_timeout(200)
            pg.screenshot(path=OUT / f"{name}.png")
        b.close()


if __name__ == "__main__":
    main()
