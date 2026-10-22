"""Record a live demo of the user screen and the care-team screen (real LLM calls, about $0.04) with Playwright driving
the installed Chrome. Saves docs/img/live_*.png screenshots and docs/demo.mp4. The server must be running on --url
(default :8000).
    .venv/bin/python scripts/record_demo.py [--url http://localhost:8000]
"""
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
IMG, TMP = ROOT / "docs" / "img", ROOT / "cache" / "video"
URL = sys.argv[sys.argv.index("--url") + 1] if "--url" in sys.argv else "http://localhost:8000"
SCENES = [  # (user, message, screenshot name, approve the HITL prompt?)
    ("u01", "Should I take a walk after dinner, and how should I eat my rice so it doesn't spike my blood sugar?", "live_mixed_diet_exercise", False),
    ("u10", "I have proliferative retinopathy. Can I keep lifting heavy weights?", "live_walter_retinopathy", False),
    ("u06", "My blood sugar is 95 before my walk. Should I eat something first?", "live_kenji_glucose", False),
    ("u08", "I'm sweating, shaky and confused after my walk.", "live_emergency", False),
    ("u09", "I want to talk to a nurse.", "live_handoff", False),
    ("u10", "Can I skip my insulin before tennis so I don't go low?", "live_med_change", False),
    ("u01", "I walked 30 minutes after dinner today.", "live_log", False),
    ("u01", "Delete my last record, it was wrong.", "live_delete_approval", True),
]


def main():
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    scenes = [x for x in SCENES if not only or x[2] in only]
    shutil.rmtree(TMP, ignore_errors=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1100, "height": 900})
        page = ctx.new_page()
        TMP.mkdir(parents=True, exist_ok=True)
        frame = [0]

        def snap(times=1):  # frames for the video (system ffmpeg joins them; no extra download)
            for _ in range(times):
                page.screenshot(path=str(TMP / f"f{frame[0]:05d}.png"))
                frame[0] += 1

        def wait_cards(k, timeout_s):
            for _ in range(int(timeout_s / 0.4)):
                snap()
                if page.evaluate("document.querySelectorAll('#log > .card:not(.me)').length") > k:
                    return
                page.wait_for_timeout(250)
            raise TimeoutError("no answer")
        page.goto(URL)
        page.wait_for_timeout(800)
        for user, msg, shot, approve in scenes:
            page.select_option("#user", user)
            page.wait_for_timeout(400)
            n = page.locator("#log > .card:not(.me)").count()   # after the switch: a new user starts an empty chat
            page.fill("#msg", "")
            for i in range(0, len(msg), 6):
                page.type("#msg", msg[i:i + 6], delay=10)
                snap()
            page.click("#send")
            wait_cards(n, 90)
            snap(8)
            if approve:
                page.screenshot(path=str(IMG / f"{shot}.png"))
                snap(4)
                page.locator("#log > .card:not(.me)").last.locator("button", has_text="Approve").click()
                wait_cards(n + 1, 30)
                snap(8)
                shot = shot.replace("approval", "done")
            page.screenshot(path=str(IMG / f"{shot}.png"))
            print("recorded", shot, flush=True)
        if not only or "live_my_info" in only:   # the user's own information, shown only when opened
            page.select_option("#user", "u06")
            page.wait_for_timeout(600)
            page.evaluate("document.getElementById('meBox').open = true; document.getElementById('meBox').scrollIntoView()")
            page.wait_for_timeout(500)
            snap(6)
            page.screenshot(path=str(IMG / "live_my_info.png"))
        if not only or "live_admin" in only:     # care-team screen: alerts, charts, one person
            page.goto(URL + "/admin")
            page.wait_for_timeout(2500)
            snap(8)
            page.screenshot(path=str(IMG / "live_admin_overview.png"), full_page=True)
            page.evaluate("person('u06')")
            page.wait_for_timeout(1500)
            snap(8)
            page.locator("#person").screenshot(path=str(IMG / "live_admin_person.png"))
            print("recorded admin", flush=True)
        snap(10)
        ctx.close()
        b.close()
    if only:  # screenshots only (no new video)
        return
    out = ROOT / "docs" / "demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "4", "-i", str(TMP / "f%05d.png"), "-vf", "scale=900:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "28", str(out)], check=True)
    print("video", out, f"{out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
