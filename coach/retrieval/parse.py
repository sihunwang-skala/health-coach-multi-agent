"""PMC JATS XML -> title + sections (section title, text). Tables are linearised row by row ("column: value; ...") so
numbers in guideline tables stay searchable. References, figures and acknowledgements are dropped."""
import re

from lxml import etree

SKIP = re.compile(r"(?i)^(references?|acknowledg|funding|conflicts? of interest|competing interests|author contributions|"
                  r"supplementary|abbreviations|data availability|ethics)")


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def _table(tw) -> str:
    rows = tw.findall(".//tr")
    if not rows:
        return ""
    head = [_text(c) for c in rows[0].findall("./th") + rows[0].findall("./td")]
    out = []
    for r in rows[1:]:
        cells = [_text(c) for c in r.findall("./td") + r.findall("./th")]
        out.append("; ".join(f"{h}: {c}" if h else c for h, c in zip(head + [""] * len(cells), cells) if c))
    cap = _text(tw.find(".//caption")) if tw.find(".//caption") is not None else ""
    return (cap + "\n" if cap else "") + "\n".join(x for x in out if x)


def parse_pmc_xml(xml: str) -> dict:
    root = etree.fromstring(xml.encode(), parser=etree.XMLParser(recover=True, huge_tree=True))
    art = root.find(".//article") if root.tag != "article" else root
    art = art if art is not None else root
    t = art.find(".//article-title")
    title = _text(t) if t is not None else ""
    sections = []
    ab = art.find(".//abstract")
    if ab is not None:
        sections.append({"title": "Abstract", "text": _text(ab)})
    body = art.find(".//body")
    if body is not None:
        for sec in body.iter("sec"):
            st = sec.find("./title")
            name = _text(st) if st is not None else ""
            if SKIP.search(name):
                continue
            paras = [_text(p) for p in sec.findall("./p")]
            tables = [_table(tw) for tw in sec.findall("./table-wrap")]
            txt = "\n".join([x for x in paras + tables if x])
            if txt:
                sections.append({"title": name, "text": txt})
        if len(sections) <= 1:  # body without <sec>
            txt = "\n".join(_text(p) for p in body.findall(".//p"))
            if txt:
                sections.append({"title": "Body", "text": txt})
    for tw in art.findall(".//floats-group//table-wrap"):
        tx = _table(tw)
        if tx:
            sections.append({"title": "Table", "text": tx})
    return {"title": title, "sections": sections}
