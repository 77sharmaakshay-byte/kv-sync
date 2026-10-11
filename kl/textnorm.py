"""Text saaf karna aur quote ki shabd-shabd jaanch.

Do alag kaam hain, jaan-boojh kar alag rakhe hain:

1. clean(raw)   — PDF se aaye text ko padhne/search layak banana
                  (ligature, ajeeb unicode, page ke header/footer...).
2. match_key()  — quote-jaanch ke liye ek "chaabi": sirf akshar aur ank,
                  lowercase, beech ke space/hyphen/quote-chinh hata kar.
                  Isse "pet it ion" == "petition" aur line-break wala
                  "sustain-\\nability" == "sustainability" ho jata hai,
                  lekin shabd ya unka kram badle to match nahi hota.

find_quote() kisi quote ko judgment ke clean text mein dhundhta hai aur
clean text ke andar uski asli jagah (start, end) lautata hai — taaki app
"para 14 mein mila" dikha sake. Bahut chhote quote (MIN_QUOTE_CHARS se kam
akshar) ko jaanch-layak nahi maana jata, kyunki wo kahin bhi mil jayenge.
"""
import re
import unicodedata

MIN_QUOTE_CHARS = 25

# PDF/pdfium ke ajeeb characters -> saaf roop.
_CHAR_MAP = {
    "­": "",    # soft hyphen
    "￾": "-",   # pdfium: line ke aakhir ka hyphen
    "​": "",    # zero-width space
    "‌": "",
    "‍": "",
    "﻿": "",
    " ": " ",   # non-breaking space
    " ": " ", " ": " ", " ": " ", " ": " ",
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    "…": "...",
    "\r": "",
}
_CHAR_RE = re.compile("|".join(map(re.escape, _CHAR_MAP)))
# pdfium line ke aakhir mein asli hyphen ko U+FFFE likhta hai ("quasi￾\njudicial").
# Ye hamesha joda-hua shabd hota hai, to hyphen rakh kar line jod do.
_PDFIUM_HYPHEN_BREAK = re.compile("￾[ \t]*\n[ \t]*")
_SPACES = re.compile(r"[ \t]+")
_TRAILING = re.compile(r"[ \t]+\n")
_MANY_NL = re.compile(r"\n{3,}")


def clean(raw):
    """Raw PDF text ko saaf karo. Shabd ya unka kram nahi badalta."""
    text = unicodedata.normalize("NFKC", raw.replace("\r\n", "\n"))
    text = _PDFIUM_HYPHEN_BREAK.sub("-", text)
    text = _CHAR_RE.sub(lambda m: _CHAR_MAP[m.group(0)], text)
    text = text.replace("\f", "\n\n")
    text = _SPACES.sub(" ", text)
    text = _TRAILING.sub("\n", text)
    text = _MANY_NL.sub("\n\n", text)
    return text.strip()


def _key_chars(text):
    """(key, positions): key = sirf alnum lowercase; positions[i] = text mein us akshar ki jagah."""
    key, pos = [], []
    for i, ch in enumerate(text):
        if ch.isalnum():
            for c in unicodedata.normalize("NFKC", ch).casefold():
                if c.isalnum():
                    key.append(c)
                    pos.append(i)
    return "".join(key), pos


def match_key(text):
    return _key_chars(text)[0]


def find_quote(quote, text):
    """Quote ko text mein dhundho.

    Lautata hai:
      ("ok", start, end)        — mil gaya; text[start:end] wahi hissa hai
      ("too_short", None, None) — quote mein MIN_QUOTE_CHARS se kam akshar
      ("not_found", None, None) — text mein ye shabd is kram mein nahi hain
    Ek se zyada jagah mile to pehli jagah lautata hai.
    """
    qkey = match_key(quote)
    if len(qkey) < MIN_QUOTE_CHARS:
        return ("too_short", None, None)
    tkey, pos = _key_chars(text)
    i = tkey.find(qkey)
    if i < 0:
        return ("not_found", None, None)
    return ("ok", pos[i], pos[i + len(qkey) - 1] + 1)
