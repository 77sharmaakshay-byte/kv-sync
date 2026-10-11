import unittest

from kl import textnorm


class CleanTest(unittest.TestCase):
    def test_pdfium_hyphen_at_line_end_is_joined(self):
        self.assertEqual(textnorm.clean("brother￾\r\nin-law"), "brother-in-law")

    def test_ligatures_quotes_and_spaces(self):
        self.assertEqual(textnorm.clean("ﬁled  “writ” petition"), 'filed "writ" petition')

    def test_soft_hyphen_and_zero_width_removed(self):
        self.assertEqual(textnorm.clean("peti­tion​"), "petition")

    def test_page_break_becomes_blank_line(self):
        self.assertEqual(textnorm.clean("end of page\fstart"), "end of page\n\nstart")

    def test_words_and_order_unchanged(self):
        raw = "The appeal is allowed.\n\n\n\nNo costs."
        self.assertEqual(textnorm.match_key(textnorm.clean(raw)), textnorm.match_key(raw))


class FindQuoteTest(unittest.TestCase):
    TEXT = ("12. It is settled law that the chain of circumstantial evidence must be complete\n"
            "and must give out an inescapable conclusion of guilt. Pet it ion is allowed.")

    def test_exact_quote_found_with_offsets(self):
        q = "the chain of circumstantial evidence must be complete and must give out"
        status, start, end = textnorm.find_quote(q, self.TEXT)
        self.assertEqual(status, "ok")
        self.assertTrue(self.TEXT[start:end].startswith("the chain"))
        self.assertTrue(self.TEXT[start:end].endswith("give out"))

    def test_line_breaks_curly_quotes_and_letter_spacing_tolerated(self):
        q = "“inescapable conclusion of guilt. Petition is allowed”"
        self.assertEqual(textnorm.find_quote(q, self.TEXT)[0], "ok")

    def test_changed_word_not_found(self):
        q = "the chain of direct evidence must be complete and must give out"
        self.assertEqual(textnorm.find_quote(q, self.TEXT)[0], "not_found")

    def test_reordered_words_not_found(self):
        q = "must be complete the chain of circumstantial evidence and must give out"
        self.assertEqual(textnorm.find_quote(q, self.TEXT)[0], "not_found")

    def test_short_quote_refused(self):
        self.assertEqual(textnorm.find_quote("settled law", self.TEXT)[0], "too_short")


if __name__ == "__main__":
    unittest.main()
