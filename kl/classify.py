"""Faislon ki chhantai: category (Criminal / Service / Civil ...) -> vishay -> upvishay.

Level 1 Nainital HC mein case type se (BA1 = bail, WPSS = service ...), Supreme Court mein
headnote ke pehle vishay ('Service Law - ...') se. Upvishay (jaise Compassionate appointment)
FTS ke niyam se; har niyam ki jaanch namoone padh kar hoti hai (TOPICS mein 'jaancha').

    strength 'mukhya': faisla isi vishay par (kai pannon par zikr, ya chhota faisla)
    strength 'zikr'  : lambe faisle mein ek hi panne par zikr (aksar sirf hawala)
"""
import re

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
SC_SUBJECT = [  # SC headnote ka pehla vishay -> category
    (r"service|civil services|pension", "Service"),
    (r"criminal|penal code|bail|evidence|narcotic|preventive detention|cr\.?\s*p\.?\s*c", "Criminal"),
    (r"income|sales tax|excise|customs|tax|gst", "Tax"),
    (r"labour|industrial", "Labour"),
    (r"constitution|administrative|election|public interest", "Constitutional"),
    (r"contempt", "Contempt"),
    (r"rent|suit|contract|hindu law|land|specific performance|arbitration|insurance|consumer|succession|"
     r"property|transfer of property|civil procedure|limitation|motor", "Civil"),
]

# (category, vishay, upvishay, FTS query, jaancha?) — jaancha = namoone padh kar sahi paya
TOPICS = [
    ("Service", "Appointment", "Compassionate appointment",
     'NEAR(compassionate appointment, 6) OR NEAR(compassionate ground appointment, 10) '
     'OR NEAR(harness rules, 3) OR NEAR(harness appointment, 10)', True),
    ("Service", "Regularisation", "Regularisation",
     'NEAR(regularisation services, 8) OR NEAR(regularization services, 8) OR "regularisation rules" '
     'OR "regularization rules" OR NEAR(regularise services, 6) OR NEAR(regularize services, 6)', False),
    ("Service", "Retirement", "Pension",
     'NEAR(pension retiral, 10) OR "pension rules" OR "pensionary benefits" OR "family pension"', False),
    ("Service", "Career", "Promotion", 'NEAR(promotion seniority, 10) OR "departmental promotion committee"', False),
    ("Service", "Career", "Transfer", '"transfer order" OR "transfer policy"', False),
    ("Service", "Discipline", "Termination / dismissal",
     'NEAR(termination services, 6) OR NEAR(dismissal service, 6) OR "disciplinary proceedings"', False),
    ("Service", "Recruitment", "Eligibility / qualification",
     'NEAR(eligibility qualification advertisement, 12) OR NEAR(essential qualification post, 8)', False),
    ("Criminal", "Bail", "NDPS", '"NDPS Act" OR "Narcotic Drugs and Psychotropic Substances"', False),
    ("Criminal", "Offence", "POCSO", '"POCSO" OR "Protection of Children from Sexual Offences"', False),
    ("Criminal", "Offence", "Dowry / 498A", '"498A" OR "498-A" OR "Dowry Prohibition"', False),
    ("Criminal", "Offence", "Cheque bounce (138 NI)", 'NEAR("Negotiable Instruments" 138, 6)', False),
]
NOT_SERVICE = CRIMINAL  # Service ke upvishay criminal case types par nahi lagte


def level1(case_type):
    ct = (case_type or "").upper()
    for prefixes, cat in LEVEL1:
        if ct.startswith(prefixes):
            return cat
    return None


def sc_category(head):
    m = re.search(r"\]\s*\.?\s*([A-Za-z][A-Za-z &,.()]{3,60}?)\s*[:\-–]", head or "")
    subj = (m.group(1).strip() if m else "").lower()
    for pat, cat in SC_SUBJECT:
        if subj and re.search(pat, subj):
            return cat, m.group(1).strip()
    return None, (m.group(1).strip() if m else None)


def ensure_tables(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            judgment_id INTEGER PRIMARY KEY REFERENCES judgments(id) ON DELETE CASCADE,
            category    TEXT,           -- Criminal / Service / Civil / Writ / Tax / ...
            subject     TEXT            -- SC headnote ka pehla vishay (HC mein NULL)
        );
        CREATE TABLE IF NOT EXISTS topics (
            judgment_id INTEGER NOT NULL REFERENCES judgments(id) ON DELETE CASCADE,
            category TEXT NOT NULL, subject TEXT NOT NULL, topic TEXT NOT NULL,
            strength TEXT NOT NULL,     -- 'mukhya' | 'zikr'
            hits INTEGER NOT NULL,      -- kitne pannon par mila
            PRIMARY KEY (judgment_id, topic)
        );
        CREATE INDEX IF NOT EXISTS topics_topic ON topics(topic, strength);
        CREATE INDEX IF NOT EXISTS categories_cat ON categories(category);
    """)


def run(con, log=print):
    ensure_tables(con)
    con.execute("DELETE FROM categories")
    rows = con.execute("SELECT id, court, case_type FROM judgments").fetchall()
    cats = {jid: (level1(ct) if court == "UKHC" else None, None) for jid, court, ct in rows}
    for jid, head in con.execute("SELECT j.id, substr(t.clean, 1, 1500) FROM judgments j JOIN texts t "
                                 "ON t.judgment_id = j.id WHERE j.court = 'SC'"):
        cats[jid] = sc_category(head)
    con.executemany("INSERT INTO categories (judgment_id, category, subject) VALUES (?, ?, ?)",
                    [(jid, c, s) for jid, (c, s) in cats.items()])
    log(f"categories: {len(cats)}")
    con.execute("DELETE FROM topics")
    out = {}
    for cat, subject, topic, query, _ in TOPICS:
        found = con.execute(
            "SELECT j.id, j.case_type, j.pages, count(*) FROM paragraphs_fts f JOIN paragraphs p ON p.id = f.rowid "
            "JOIN judgments j ON j.id = p.judgment_id WHERE paragraphs_fts MATCH ? GROUP BY j.id", (query,)).fetchall()
        keep = []
        for jid, ct, pages, hits in found:
            if cat == "Service" and (ct or "").upper().startswith(NOT_SERVICE):
                continue
            strength = "mukhya" if hits >= 2 or (pages or 0) <= 3 else "zikr"
            keep.append((jid, cat, subject, topic, strength, hits))
        con.executemany("INSERT OR REPLACE INTO topics VALUES (?, ?, ?, ?, ?, ?)", keep)
        out[topic] = (sum(1 for k in keep if k[4] == "mukhya"), sum(1 for k in keep if k[4] == "zikr"))
        log(f"{topic}: mukhya {out[topic][0]}, zikr {out[topic][1]}")
    con.commit()
    return out
