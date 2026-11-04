"""Every Korean string in the static HTML of the sign-in pages, the chat and the care-team console has an English entry in web/i18n.js (including the care-team console)."""
import re
from html.parser import HTMLParser
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
HANGUL = re.compile("[가-힣]")


class Strings(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in ("script", "style")
        self.out += [v for k, v in attrs if k in ("placeholder", "aria-label", "title") and v and HANGUL.search(v)]

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style")

    def handle_data(self, data):
        if not self.skip and data.strip() and HANGUL.search(data):
            self.out.append(data.strip())


def test_every_static_korean_string_has_an_english_entry():
    en = {k.replace("\\'", "'") for k in re.findall(r"'((?:[^'\\]|\\.)*)':", (WEB / "i18n.js").read_text())}
    en |= {k.replace("\\'", "'") for k in re.findall(r'"((?:[^"\\]|\\.)*)":', (WEB / "i18n.js").read_text())}
    allowed_dynamic = {"언어"}   # set by mountLang()
    for page in ("login.html", "admin-login.html", "index.html", "admin.html"):
        p = Strings()
        p.feed((WEB / page).read_text())
        missing = [s for s in p.out if s not in en and s not in allowed_dynamic]
        assert not missing, (page, missing)
