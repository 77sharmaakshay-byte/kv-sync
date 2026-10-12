"""kl/classify.py + kl/taxonomy.py: niyam chalte hain, nateeja aur SC vishay sahi padhe jaate hain.

    python3 -m unittest tests.test_classify
"""
import sqlite3
import unittest

from kl import classify, taxonomy


class ClassifyTest(unittest.TestCase):
    def test_every_fts_rule_is_valid(self):
        con = sqlite3.connect(":memory:")
        con.execute('CREATE VIRTUAL TABLE f USING fts5(text, tokenize="porter unicode61 remove_diacritics 2")')
        con.execute("INSERT INTO f VALUES ('compassionate appointment under the dying in harness rules 1974')")
        queries = [t[3] for t in taxonomy.TOPICS] + [q for v in taxonomy.ISSUES.values() for _, q in v]
        for q in queries:
            con.execute("SELECT count(*) FROM f WHERE f MATCH ?", (q,)).fetchone()  # galat syntax par error
        ups = {t[2] for t in taxonomy.TOPICS}
        assert all(up in ups for up in taxonomy.ISSUES)
        assert all(up in ups for _, up in taxonomy.CASE_TOPICS)

    def test_outcome(self):
        assert classify.outcome("DISMISSED AS WITHDRAWN", None) == "Wapas / bekaar"
        assert classify.outcome("Leave Granted & Dismissed", None) == "Khilaf"
        assert classify.outcome("Case Partly allowed", None) == "Aanshik paksh mein"
        assert classify.outcome("ALLOWED", None) == "Paksh mein"
        assert classify.outcome("DISPOSED", "The writ petition is allowed. No order as to costs.") == "Paksh mein"
        assert classify.outcome("DISPOSED", "Entire proceedings of Criminal Case No. 535 of 2020 are quashed.") == "Paksh mein"
        assert classify.outcome("DISPOSED", "respondent no.2 to decide the representation moved by the petitioner") \
            == "Nirdesh: vibhag vichaar kare"
        assert classify.outcome("DISPOSED", "the writ petition stands disposed of.") == "Nipataara"

    def test_sc_category(self):
        head = ("[2014] 4 S.C.R. 1\nPAWAN KUMAR\nv.\nHARKISHAN DASS\n(Civil Appeal No. 5906 of 2008)\nJANUARY 29, 2014\n"
                "[P.SATHASIVAM, CJI.) RANJAN GOGOi AND\nSHIVA KIRTI SINGH, JJ.]\nMOTOR VEHICLES ACT, 1988:\nFatal accident -")
        assert classify.sc_category(head) == ("Civil", "MOTOR VEHICLES ACT, 1988", "Civil")
        head = ("SUDAM CHARAN DASH\nV.\nSTATE OF ORISSA\n(Criminal Appeal No. 1862 of 2013)\nOCTOBER 25, 2013\n"
                "[RANJANA PRAKASH DESAI AND\nMADAN B. LOKUR, J~.]\nCode of Criminal Procedure, 1973 - ss. 438 and 439 -")
        cat, subj, header = classify.sc_category(head)
        assert (cat, header) == ("Criminal", "Criminal") and subj.startswith("Code of Criminal Procedure")
        assert classify.level1("WPSS") == "Service" and classify.level1("BA1") == "Criminal"
