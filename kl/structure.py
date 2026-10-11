"""Clean text -> paragraphs, judges, reportable, order/judgment, citations.

VERSION 1 abhi saada (baseline) hai: khaali line par para todta hai, aur
koi classification nahi karta. Asli PDFs ke analysis ke baad isme SC
headnote/body ka bantwara, para numbers, bench, Reportable aur HC
order-vs-judgment ke niyam aayenge — tab VERSION badhega aur
ingest unhe dobara bana dega.
"""
import re

VERSION = 1

_BLANK = re.compile(r"\n\s*\n")


def _blocks(text):
    """Khaali line se alag hue hisse: (start, end) offsets, khaali hisse chhod kar."""
    pos = 0
    for m in _BLANK.finditer(text):
        yield pos, m.start()
        pos = m.end()
    yield pos, len(text)


def parse(court, clean):
    paragraphs = []
    for start, end in _blocks(clean):
        while start < end and clean[start].isspace():
            start += 1
        while end > start and clean[end - 1].isspace():
            end -= 1
        if end > start:
            paragraphs.append({"para_no": None, "section": "body", "start": start, "end": end})
    return {"paragraphs": paragraphs, "body_start": 0}
