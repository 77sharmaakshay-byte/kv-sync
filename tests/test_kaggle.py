from collections import Counter

from kl import kaggle


def test_judges_pairs_surname_initials():
    assert kaggle._judges("SIKRI, S.M.,SHELAT, J.M.") == ["SIKRI, S.M.", "SHELAT, J.M."]
    assert kaggle._judges("") == []


def test_tail_matches_zip_names():
    assert kaggle._tail("jonew/judis/1524.pdf") == "judis/1524.pdf"
    assert kaggle._tail("supreme_court_judgments/judis/1524.PDF", 1) == "1524.pdf"


def test_dup_single_candidate_ignores_respondent_spelling():
    existing = {("2024-04-04", kaggle._key("KRISHNADATT AWASTHY")): [kaggle._key("STATE OF MADHYA PRADESH & ORS.")]}
    counts = Counter({("2024-04-04", kaggle._key("KRISHNADATT AWASTHY")): 1})
    assert kaggle._is_dup(existing, counts, "2024-04-04", "KRISHNADATT AWASTHY", "STATE OF M.P..")


def test_dup_same_day_same_petitioner_needs_respondent():
    k = ("2024-04-05", kaggle._key("STATE OF MAHARASHTRA"))
    existing = {k: [kaggle._key("RAMESH"), kaggle._key("SURESH")]}
    counts = Counter({k: 3})
    assert kaggle._is_dup(existing, counts, *k[:1], "THE STATE OF MAHARASHTRA", "SURESH & ORS.")
    assert not kaggle._is_dup(existing, counts, *k[:1], "STATE OF MAHARASHTRA", "MAHESH")
    assert not kaggle._is_dup(existing, counts, "2024-04-06", "STATE OF MAHARASHTRA", "RAMESH")


def test_zip_member_names_match_csv_rows():
    names = ["pdfs/-0___jonew__judis__10166.pdf", "pdfs/-0___jonew__judis__10187.pdf",
             "pdfs/636-2009___supremecourt__2009__636__636_2009_Judgement_04-Apr-2024.pdf", "judgments.csv"]
    assert kaggle._parse_member(names[0]) == ("-0", "jonew/judis/10166.pdf")
    idx = kaggle._index(names)
    assert kaggle._find(idx, "-0", "jonew/judis/10187.pdf") == names[1]
    assert kaggle._find(idx, "636-2009", "supremecourt/2009/636/636_2009_Judgement_04-Apr-2024.pdf") == names[2]
    assert kaggle._find(idx, "", "jonew/judis/10166.pdf") == names[0]  # diary na mile to link se
    assert kaggle._find(idx, "-0", "jonew/judis/99999.pdf") is None
