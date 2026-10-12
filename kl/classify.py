"""Faislon ki chhantai, paanch level (niyam kl/taxonomy.py mein):

    1 Shreni   : Nainital HC mein case type se (BA1 = bail, WPSS = service ...); Supreme Court mein headnote ke
                 pehle vishay ('Service Law - ...', 'Code of Criminal Procedure, 1973 - ...') ya header ke
                 '(Criminal Appeal No. ...)' se. Jahan in se pata na chale (WPMS, Special Appeal, bina headnote
                 ka SC faisla), wahan faisle ke text ke sabse mazboot upvishay se.
    2-3 Vishay, Upvishay : FTS niyam (taxonomy.TOPICS)
    4 Mudda    : upvishay ke andar khaas sawaal (taxonomy.ISSUES)
    5 Nateeja  : judgments.disposal se; 'disposed' wale faislon mein aakhri hissa padh kar

Tables:
    categories(judgment_id, category, subject, outcome)  — har faisle ki ek line (level 1 + 5)
    labels(judgment_id, category, vishay, upvishay, mudda, strength, hits) — level 1-4; mudda '' = upvishay ki line
    khoj (view)  — labels + nateeja + faisle ki pehchaan, ek query mein filter ke liye
    strength 'mukhya': faisla isi vishay par (kai pannon par zikr, ya chhota faisla)
    strength 'zikr'  : lambe faisle mein ek hi panne par zikr (aksar sirf hawala)
"""
import re
from collections import defaultdict

from kl import taxonomy

CRIMINAL = ("BA", "ABA", "BAST", "BAC", "SABA", "C482", "C528", "C407", "C447", "CRLA", "CRLR", "CRJA", "WPCRL",
            "HABC", "GA", "SPLA")
LEVEL1 = [  # (case type prefix, category) — pehla mel jeetta hai
    (("WPSS", "WPSB"), "Service"),
    (("WPPIL",), "PIL"),
    (("WPMS", "WPMB"), "Writ"),
    (("CLCON",), "Contempt"),
    (("ITA", "ITR", "STR", "CEXA", "TTR", "CTR", "VATR"), "Tax"),
    (CRIMINAL, "Criminal"),
    (("FA", "SA", "AO", "CLR", "C24", "ARBAP", "FAFO", "COMP", "TEST", "CA"), "Civil"),
    (("SPA",), "Special Appeal"),
]
OPEN = (None, "Writ", "Special Appeal")  # in par text ka upvishay shreni tay karta hai
SC_SUBJECT = [  # SC headnote ka pehla vishay -> shreni (pehla mel jeetta hai)
    (r"contempt", "Contempt"),
    (r"service|civil services|pension|recruitment|seniority|armed forces", "Service"),
    (r"hindu marriage|family|muslim law|mohammedan|guardian|divorce|maintenance|child", "Family"),
    (r"criminal|penal code|bail|evidence|narcotic|preventive detention|cr\.?\s*p\.?\s*c|corruption|arms act|"
     r"investigation|sentenc|terroris|unlawful activities|negotiable", "Criminal"),
    (r"income|sales tax|excise|customs|tax|gst|stamp|value added", "Tax"),
    (r"labour|industrial|workmen|factories|provident fund|minimum wages|employees", "Labour"),
    (r"land acquisition|land|revenue|ceiling|zamindari", "Land"),
    (r"arbitration|compan|insolvency|banking|securiti", "Commercial"),
    (r"constitution|administrative|election|representation of the people|public interest|judicial review|"
     r"natural justice|education|universit|municipal|urban|town planning|environment|forest|mines|electricity|"
     r"tender|housing|co-?operative|government grants", "Constitutional"),
    (r"rent|suit|contract|hindu law|specific|insurance|consumer|succession|property|civil procedure|limitation|"
     r"motor|\bwill\b|lease|deeds|partition|injunction|adverse possession|decree|easement|registration|tenancy",
     "Civil"),
]
# Headnote ka pehla vishay: '...JJ.] Code of Criminal Procedure, 1973 - ss. 438...' / 'MOTOR VEHICLES ACT, 1988:'
SUBJ_OLD = re.compile(r"\]\s*\.?\s*([A-Za-z][A-Za-z &,.()]{3,60}?)\s*[:\-–]")
SUBJ_ACT = re.compile(r"((?:Code|CODE)\s+[Oo][Ff]\s+[A-Za-z ]{3,40}?(?:,?\s*\d{4})?|"  # 'Code of Criminal Procedure, 1973'
                      r"(?:(?:[A-Z][\w.'’()&-]*|of|the|and|for|to|in|&),?\s+){0,8}?"  # 'Prevention of Corruption Act'
                      r"(?:Act|ACT|Constitution of India|CONSTITUTION OF INDIA|Law|LAW|Laws|LAWS|Rules|RULES|"
                      r"Regulations?|REGULATIONS?)(?:,?\s*\d{4})?)\s*[:\-–]")
SC_HEAD = re.compile(r"\(\s*(civil|criminal|writ|transfer|special leave)[^)]{0,30}?(appeal|petition)|"
                     r"(civil|criminal) (?:appellate|original) jurisdiction", re.I)


def level1(case_type):
    ct = (case_type or "").upper()
    for prefixes, cat in LEVEL1:
        if ct.startswith(prefixes):
            return cat
    return None


def sc_category(head):
    """SC faisle ka shuru (1500 akshar) -> (shreni ya None, headnote ka vishay, header ki shreni)."""
    head = head or ""
    subj = None
    for rx in (SUBJ_OLD, SUBJ_ACT):
        m = rx.search(head)
        if m and len(m.group(1).strip()) > 3:
            subj = re.sub(r"\s+", " ", m.group(1)).strip(" ,.")
            break
    cat = None
    if subj:
        for pat, c in SC_SUBJECT:
            if re.search(pat, subj.lower()):
                cat = c
                break
    m = SC_HEAD.search(head)
    kind = ((m.group(1) or m.group(3) or "").lower() if m else "")
    header = "Criminal" if "criminal" in kind else "Civil" if "civil" in kind else (
        "Constitutional" if kind == "writ" else None)
    return cat, subj, header


def outcome(disposal, tail):
    d = re.sub(r"leave granted\s*&?\s*", "", (disposal or "").lower())
    res = None
    for pat, name in taxonomy.OUTCOME:
        if re.search(pat, d):
            res = name
            break
    if res in (None, "Nipataara") and tail:
        t = re.sub(r"\s+", " ", tail)
        for pat, name in taxonomy.DISPOSED_TAIL:
            if re.search(pat, t, re.I):
                return name
    return res


def ensure_tables(con):
    con.executescript("""
        DROP TABLE IF EXISTS topics;      -- purani (sirf 3 level wali) table
        DROP TABLE IF EXISTS categories;
        CREATE TABLE categories (
            judgment_id INTEGER PRIMARY KEY REFERENCES judgments(id) ON DELETE CASCADE,
            category    TEXT,           -- level 1: Criminal / Service / Civil / Family / Land / ...
            subject     TEXT,           -- SC headnote ka pehla vishay (HC mein NULL)
            outcome     TEXT            -- level 5: Paksh mein / Khilaf / Nipataara / ...
        );
        CREATE TABLE IF NOT EXISTS labels (
            judgment_id INTEGER NOT NULL REFERENCES judgments(id) ON DELETE CASCADE,
            category TEXT NOT NULL, vishay TEXT NOT NULL, upvishay TEXT NOT NULL,
            mudda    TEXT NOT NULL DEFAULT '',   -- '' = upvishay ki line; warna level 4
            strength TEXT NOT NULL,              -- 'mukhya' | 'zikr'
            hits     INTEGER NOT NULL,           -- kitne pannon par mila
            PRIMARY KEY (judgment_id, upvishay, mudda)
        );
        CREATE INDEX IF NOT EXISTS labels_path ON labels(category, vishay, upvishay, mudda, strength);
        CREATE INDEX IF NOT EXISTS labels_up ON labels(upvishay, mudda, strength);
        CREATE INDEX IF NOT EXISTS categories_cat ON categories(category, outcome);
        -- khoj ke liye ek jagah sab: shreni / vishay / upvishay / mudda / nateeja + faisle ki pehchaan
        DROP VIEW IF EXISTS khoj;
        CREATE VIEW khoj AS
            SELECT j.id AS judgment_id, j.court, j.case_no, j.neutral_citation, j.title, j.decision_date, j.year,
                   l.category AS shreni, l.vishay, l.upvishay, l.mudda, l.strength, l.hits, c.outcome AS nateeja
            FROM labels l JOIN categories c ON c.judgment_id = l.judgment_id JOIN judgments j ON j.id = l.judgment_id;
    """)


def _hits(con, query):
    return con.execute(
        "SELECT p.judgment_id, count(*) FROM paragraphs_fts f JOIN paragraphs p ON p.id = f.rowid "
        "WHERE paragraphs_fts MATCH ? GROUP BY p.judgment_id", (query,)).fetchall()


def run(con, log=print):
    ensure_tables(con)
    con.execute("DELETE FROM labels")
    meta = {jid: (court, ct, pages, disp) for jid, court, ct, pages, disp in
            con.execute("SELECT id, court, case_type, pages, disposal FROM judgments")}
    base, subject, header = {}, {}, {}
    for jid, (court, ct, _, _) in meta.items():
        base[jid] = level1(ct) if court == "UKHC" else None
    for jid, head in con.execute("SELECT j.id, substr(t.clean, 1, 1500) FROM judgments j JOIN texts t "
                                 "ON t.judgment_id = j.id WHERE j.court = 'SC'"):
        base[jid], subject[jid], header[jid] = sc_category(head)
    log(f"level 1 (case type / headnote): {sum(1 for v in base.values() if v)} / {len(base)}")

    # level 2-3
    rows, best = [], defaultdict(lambda: (0, None))
    by_topic = {}
    by_type = defaultdict(set)  # upvishay -> case type se mile faisle
    for jid, (court, ct, _, _) in meta.items():
        for prefixes, up in taxonomy.CASE_TOPICS:
            if court == "UKHC" and (ct or "").upper().startswith(prefixes):
                by_type[up].add(jid)
    for cat, vishay, up, query, _ in taxonomy.TOPICS:
        keep = {}
        found = dict(_hits(con, query))
        for jid in by_type[up]:
            found.setdefault(jid, 0)
        for jid, hits in found.items():
            court, ct, pages, _ = meta[jid]
            crim = (ct or "").upper().startswith(CRIMINAL) or header.get(jid) == "Criminal"
            if cat == "Service" and crim:
                continue  # criminal case mein 'appointment' ka zikr service matter nahi
            if cat == "Criminal" and base[jid] == "Service":
                continue
            strength = "mukhya" if hits >= 2 or (pages or 0) <= 3 or jid in by_type[up] else "zikr"
            keep[jid] = (strength, hits)
            rows.append((jid, cat, vishay, up, "", strength, hits))
            if strength == "mukhya" and hits > best[jid][0]:
                best[jid] = (hits, cat)
        by_topic[up] = (cat, vishay, keep)
        log(f"{cat} / {vishay} / {up}: mukhya {sum(1 for s, _ in keep.values() if s == 'mukhya')}, "
            f"zikr {sum(1 for s, _ in keep.values() if s == 'zikr')}")

    # level 4: sirf unhi faislon mein jinme upvishay mila
    for up, issues in taxonomy.ISSUES.items():
        cat, vishay, keep = by_topic[up]
        for mudda, query in issues:
            n = 0
            for jid, hits in _hits(con, query):
                if jid in keep:
                    rows.append((jid, cat, vishay, up, mudda, keep[jid][0], hits))
                    n += 1
            log(f"   {up} / {mudda}: {n}")
    con.executemany("INSERT OR REPLACE INTO labels VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    # level 1 aakhri: case type / headnote, warna text ka sabse mazboot upvishay, warna SC header
    final = {}
    for jid, b in base.items():
        if b in OPEN and best[jid][1]:
            final[jid] = best[jid][1]
        else:
            final[jid] = b or header.get(jid)

    # level 5
    open_ids = [jid for jid, (_, _, _, d) in meta.items() if outcome(d, None) in (None, "Nipataara")]
    tails = {}
    for i in range(0, len(open_ids), 2000):
        chunk = open_ids[i:i + 2000]
        tails.update(con.execute(f"SELECT judgment_id, substr(clean, -2500) FROM texts WHERE judgment_id IN "
                                 f"({','.join('?' * len(chunk))})", chunk).fetchall())
    cats = [(jid, final[jid], subject.get(jid), outcome(meta[jid][3], tails.get(jid))) for jid in meta]
    con.executemany("INSERT INTO categories VALUES (?, ?, ?, ?)", cats)
    con.commit()
    log(f"categories: {len(cats)}, labels: {len(rows)}")
    return len(cats), len(rows)
