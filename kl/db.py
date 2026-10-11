"""Judgments database (SQLite + FTS5).

Pilot ke liye ek hi file wala database: Mac par bina server ke chalta hai.
Launch ke waqt yahi tables PostgreSQL mein jayengi.

Tables:
  judgments   — har judgment/order ki ek row (metadata + classification)
  texts       — poora text: raw (PDF se jaisa aaya) aur clean (normalize ke baad)
  paragraphs  — clean text ke para, char offsets ke saath (quote-jaanch ke liye)
  citations   — text mein mile citations (SCC/AIR/SCR/INSC...) aur statutes
  treatments  — "overruled", "per incuriam" jaise shabd, para ke saath
  paragraphs_fts — paragraphs par full-text search (BM25)
"""
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS judgments (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,          -- 'sc-scr' | 'uk-hc' | 'sc-old'
    source_key      TEXT NOT NULL UNIQUE,   -- sc: '2024_10_108_125', uk: pdf ka naam bina .pdf
    court           TEXT NOT NULL,          -- 'SC' | 'UKHC'
    title           TEXT,
    petitioner      TEXT,
    respondent      TEXT,
    case_no         TEXT,                   -- jaise 'WPSS/1190/2024' ya 'Criminal Appeal No. 1031 of 2015'
    case_type       TEXT,                   -- jaise 'WPSS', 'BA1', 'Criminal Appeal'
    decision_date   TEXT,                   -- ISO yyyy-mm-dd
    year            INTEGER,
    judges          TEXT,                   -- JSON list
    bench_size      INTEGER,
    author_judge    TEXT,
    neutral_citation TEXT,                  -- '2024 INSC 735'
    report_citation TEXT,                   -- '[2024] 10 S.C.R. 108'
    cnr             TEXT,
    disposal        TEXT,
    reportable      TEXT,                   -- 'reportable' | 'non_reportable' | NULL (pata nahi)
    doc_kind        TEXT,                   -- 'judgment' | 'order' | NULL (abhi text nahi padha)
    doc_kind_score  REAL,
    has_text        INTEGER,                -- 1 = PDF mein text layer mila
    pages           INTEGER,
    chars           INTEGER,
    pdf_archive     TEXT,                   -- kis tar mein hai (data folder ke relative)
    pdf_member      TEXT,                   -- tar ke andar file ka naam
    pdf_sha256      TEXT,
    meta_json       TEXT,                   -- source metadata ki baaki fields
    text_version    INTEGER                 -- kis parser version se text bana; NULL = abhi nahi
);
CREATE INDEX IF NOT EXISTS judgments_court_year ON judgments(court, year);
CREATE INDEX IF NOT EXISTS judgments_cnr ON judgments(cnr);
CREATE INDEX IF NOT EXISTS judgments_neutral ON judgments(neutral_citation);
CREATE INDEX IF NOT EXISTS judgments_pdf ON judgments(pdf_archive, pdf_member);

CREATE TABLE IF NOT EXISTS texts (
    judgment_id INTEGER PRIMARY KEY REFERENCES judgments(id) ON DELETE CASCADE,
    raw         TEXT NOT NULL,
    clean       TEXT NOT NULL,
    body_start  INTEGER                     -- clean text mein court ke apne shabd kahan se shuru (headnote ke baad)
);

CREATE TABLE IF NOT EXISTS paragraphs (
    id          INTEGER PRIMARY KEY,
    judgment_id INTEGER NOT NULL REFERENCES judgments(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,           -- 0,1,2... document order
    para_no     TEXT,                       -- judgment ka apna para number ('12'), ya NULL
    section     TEXT NOT NULL,              -- 'header' | 'headnote' | 'body' | 'order'
    opinion     TEXT,                       -- kis judge ki opinion (jahan alag-alag ho)
    char_start  INTEGER NOT NULL,           -- texts.clean mein offset
    char_end    INTEGER NOT NULL,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS paragraphs_judgment ON paragraphs(judgment_id, seq);

CREATE VIRTUAL TABLE IF NOT EXISTS paragraphs_fts USING fts5(
    text, content='paragraphs', content_rowid='id',
    tokenize="porter unicode61 remove_diacritics 2"
);
CREATE TRIGGER IF NOT EXISTS paragraphs_ai AFTER INSERT ON paragraphs BEGIN
    INSERT INTO paragraphs_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS paragraphs_ad AFTER DELETE ON paragraphs BEGIN
    INSERT INTO paragraphs_fts(paragraphs_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TABLE IF NOT EXISTS citations (
    id          INTEGER PRIMARY KEY,
    judgment_id INTEGER NOT NULL REFERENCES judgments(id) ON DELETE CASCADE,
    paragraph_id INTEGER REFERENCES paragraphs(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,              -- 'SCC' | 'AIR' | 'SCR' | 'INSC' | 'SCC_ONLINE' | 'STATUTE' ...
    raw         TEXT NOT NULL,
    normalized  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS citations_norm ON citations(normalized);
CREATE INDEX IF NOT EXISTS citations_judgment ON citations(judgment_id);

CREATE TABLE IF NOT EXISTS treatments (
    id          INTEGER PRIMARY KEY,
    judgment_id INTEGER NOT NULL REFERENCES judgments(id) ON DELETE CASCADE,
    paragraph_id INTEGER REFERENCES paragraphs(id) ON DELETE CASCADE,
    phrase      TEXT NOT NULL,              -- 'overruled' | 'per_incuriam' | 'distinguished' ...
    context     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS treatments_judgment ON treatments(judgment_id);
"""


def connect(path):
    """Database kholo (na ho to banao) aur schema laga do."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    con.commit()
    return con
