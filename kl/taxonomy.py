"""Faislon ki chhantai ke paanch level (kl/classify.py inhe database mein lagata hai):

    1 Shreni   : Criminal / Service / Civil / Constitutional / Tax / Labour / Family / Land / Commercial
    2 Vishay   : jaise Service -> Appointment, Pay, Retirement
    3 Upvishay : jaise Appointment -> Compassionate appointment
    4 Mudda    : upvishay ke andar khaas sawaal, jaise "Der se aavedan"
    5 Nateeja  : paksh mein / khilaf / nirdesh ke saath nipataara / wapas ... (classify.outcome)

Har niyam ek FTS5 query hai (paragraphs_fts: porter stemming, to 'appointments' = 'appointment').
jaancha=True tabhi jab namoone padh kar sahi paya; baaki naye hain, jaanch baaki.
"""

# (shreni, vishay, upvishay, FTS query, jaancha)
TOPICS = [
    # ---- Service ----
    ("Service", "Appointment", "Compassionate appointment",
     'NEAR(compassionate appointment, 6) OR NEAR(compassionate ground appointment, 10) '
     'OR NEAR(harness rules, 3) OR NEAR(harness appointment, 10)', True),
    ("Service", "Appointment", "Selection / merit list",
     '"select list" OR "merit list" OR "selection list" OR "wait list" OR "waiting list"', False),
    ("Service", "Recruitment", "Eligibility / qualification",
     'NEAR(eligibility qualification advertisement, 12) OR NEAR(essential qualification post, 8)', False),
    ("Service", "Recruitment", "Reservation in recruitment",
     '"horizontal reservation" OR "vertical reservation" OR NEAR(reservation recruitment, 8) '
     'OR NEAR(reserved category candidate, 4)', False),
    ("Service", "Regularisation", "Regularisation",
     'NEAR(regularisation services, 8) OR NEAR(regularization services, 8) OR "regularisation rules" '
     'OR "regularization rules" OR NEAR(regularise services, 6) OR NEAR(regularize services, 6)', False),
    ("Service", "Regularisation", "Daily wage / contractual",
     '"daily wager" OR "daily wage" OR "daily rated" OR NEAR(contractual employee, 3) OR "upnal" OR "outsourc"', False),
    ("Service", "Pay", "Pay scale / equal pay",
     '"equal pay for equal work" OR NEAR(pay scale parity, 10) OR "pay anomaly" OR "selection grade" '
     'OR NEAR("assured career progression", 5) OR "ACP"', False),
    ("Service", "Pay", "Recovery of excess payment",
     'NEAR(recovery excess payment, 6) OR NEAR(recovery "excess amount", 6) OR "Rafiq Masih"', False),
    ("Service", "Career", "Promotion", 'NEAR(promotion seniority, 10) OR "departmental promotion committee"', False),
    ("Service", "Career", "Seniority", '"seniority list" OR NEAR(inter se seniority, 3) OR "seniority rules"', False),
    ("Service", "Career", "Transfer", '"transfer order" OR "transfer policy"', False),
    ("Service", "Discipline", "Termination / dismissal",
     'NEAR(termination services, 6) OR NEAR(dismissal service, 6) OR "disciplinary proceedings"', False),
    ("Service", "Discipline", "Suspension", '"suspension order" OR NEAR(placed under suspension, 3)', False),
    ("Service", "Retirement", "Pension",
     'NEAR(pension retiral, 10) OR "pension rules" OR "pensionary benefits" OR "family pension"', False),
    ("Service", "Retirement", "Gratuity / leave encashment", '"gratuity" OR "leave encashment"', False),
    ("Service", "Retirement", "Compulsory / voluntary retirement",
     '"compulsory retirement" OR "compulsorily retired" OR "voluntary retirement"', False),
    # ---- Criminal ----
    ("Criminal", "Bail", "Regular bail", 'NEAR(bail "section 439", 10) OR NEAR(bail "section 483", 10)', False),
    ("Criminal", "Bail", "Anticipatory bail", '"anticipatory bail" OR NEAR(bail "section 438", 8)', False),
    ("Criminal", "Bail", "Default bail", '"default bail" OR NEAR("167(2)" bail, 8) OR "indefeasible right"', False),
    ("Criminal", "Bail", "Cancellation of bail",  # 'misuse kiya to bail cancel' wali aam line nahi
     '"application for cancellation of bail" OR "cancellation of bail application" OR "bail cancellation application" '
     'OR NEAR(seeking cancellation bail, 4)', False),
    ("Criminal", "Bail", "Suspension of sentence", '"suspension of sentence" OR NEAR(suspend sentence "section 389", 8)', False),
    ("Criminal", "Liberty", "Habeas corpus", '"habeas corpus"', False),
    ("Criminal", "Quashing", "Quashing (482 CrPC / 528 BNSS)",
     'NEAR(quash "section 482", 12) OR NEAR(quash "section 528", 12) OR "inherent powers"', False),
    ("Criminal", "Quashing", "FIR quashing / arrest stay (writ)",
     'NEAR(quash "first information report", 8) OR NEAR(quash FIR, 6)', False),
    ("Criminal", "Offence", "Murder (302 IPC / 103 BNS)", '"section 302" OR "302 IPC" OR "302 I.P.C"', False),
    ("Criminal", "Offence", "Rape / sexual offence", 'NEAR("section 376" rape, 10) OR NEAR(rape prosecutrix, 15)', False),
    ("Criminal", "Offence", "POCSO", '"POCSO" OR "Protection of Children from Sexual Offences"', False),
    ("Criminal", "Offence", "NDPS", '"NDPS Act" OR "Narcotic Drugs and Psychotropic Substances"', False),
    ("Criminal", "Offence", "Dowry / 498A", '"498A" OR "498-A" OR "Dowry Prohibition"', False),
    ("Criminal", "Offence", "Dowry death (304B)", '"304B" OR "304-B" OR "dowry death"', False),
    ("Criminal", "Offence", "Cheque bounce (138 NI)", 'NEAR("Negotiable Instruments" 138, 6)', False),
    ("Criminal", "Offence", "Cheating / fraud (420)", '"section 420" OR "420 IPC" OR "420 I.P.C"', False),
    ("Criminal", "Offence", "SC/ST Atrocities Act",
     '"Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities)" OR "SC/ST Act" OR "Atrocities Act"', False),
    ("Criminal", "Evidence", "Circumstantial evidence", '"circumstantial evidence" OR "last seen"', False),
    ("Criminal", "Evidence", "Dying declaration", '"dying declaration"', False),
    # ---- Family ----
    ("Family", "Maintenance", "Maintenance (125 CrPC / 144 BNSS)",
     'NEAR(maintenance "section 125", 8) OR NEAR(maintenance "section 144", 8) OR "interim maintenance"', False),
    ("Family", "Marriage", "Divorce", 'NEAR(divorce "Hindu Marriage Act", 15) OR "decree of divorce"', False),
    ("Family", "Children", "Child custody", 'NEAR(custody child, 4) OR "guardian and wards" OR "welfare of the child"', False),
    # ---- Civil ----
    ("Civil", "Property", "Specific performance", '"specific performance"', False),
    ("Civil", "Property", "Injunction", '"permanent injunction" OR "temporary injunction" OR "Order XXXIX"', False),
    ("Civil", "Property", "Partition", 'NEAR(partition suit, 6) OR "decree for partition"', False),
    ("Civil", "Property", "Adverse possession", '"adverse possession"', False),
    ("Civil", "Succession", "Will / succession", 'NEAR(will testator, 10) OR "probate" OR "succession certificate"', False),
    ("Civil", "Tenancy", "Eviction / rent", 'NEAR(eviction tenant, 8) OR "rent control" OR NEAR(landlord tenant, 4)', False),
    ("Civil", "Compensation", "Motor accident claim (MACT)",
     '"Motor Accident Claims Tribunal" OR NEAR(compensation "Motor Vehicles Act", 15) OR "just compensation"', False),
    ("Civil", "Consumer", "Consumer dispute", '"Consumer Protection Act" OR "deficiency in service"', False),
    # ---- Land ----
    ("Land", "Acquisition", "Land acquisition compensation",
     'NEAR("land acquisition" compensation, 10) OR "Right to Fair Compensation"', False),
    ("Land", "Revenue", "Mutation / revenue entries", 'NEAR(mutation revenue, 8) OR "khatauni" OR "revenue records"', False),
    ("Land", "Revenue", "Zamindari / bhumidhari",
     '"Zamindari Abolition" OR "bhumidhar" OR "bhumidhari"', False),
    # ---- Commercial ----
    ("Commercial", "Arbitration", "Arbitration",
     '"Arbitration and Conciliation Act" OR NEAR(arbitral award, 3) OR NEAR(appointment arbitrator, 4)', False),
    ("Commercial", "Banking", "Bank recovery / SARFAESI", '"SARFAESI" OR "Debts Recovery Tribunal" OR "Securitisation"', False),
    ("Commercial", "Company", "Company / insolvency", '"Insolvency and Bankruptcy Code" OR "Companies Act"', False),
    # ---- Constitutional / prashasan ----
    ("Constitutional", "Contracts", "Tender / government contract",
     'NEAR(tender bid, 8) OR "notice inviting tender" OR "technical bid"', False),
    ("Constitutional", "Education", "Admission / education",
     'NEAR(admission students, 8) OR NEAR(admission college, 6) OR NEAR(university examination, 6)', False),
    ("Constitutional", "Elections", "Elections (panchayat / municipal / assembly)",
     '"election petition" OR NEAR(panchayat election, 6) OR "Representation of the People Act"', False),
    ("Constitutional", "Environment", "Environment / forest",
     '"Forest (Conservation) Act" OR NEAR(environment pollution, 8) OR "Environment (Protection) Act"', False),
    ("Constitutional", "Licensing", "Mining / licence",
     '"mining lease" OR "Mines and Minerals" OR NEAR(licence cancellation, 4)', False),
    ("Constitutional", "Fundamental rights", "Article 14 / 21",
     'NEAR("Article 21" life liberty, 10) OR NEAR("Article 14" arbitrary, 10)', False),
    # ---- Tax / Labour ----
    ("Tax", "Indirect", "GST / VAT", '"Goods and Services Tax" OR "GST" OR "Value Added Tax"', False),
    ("Tax", "Direct", "Income tax", '"Income Tax Act" OR "assessing officer"', False),
    ("Labour", "Industrial", "Industrial dispute / retrenchment",
     '"Industrial Disputes Act" OR "retrenchment" OR "Labour Court"', False),
]

# Nainital HC ke case type se seedha upvishay (text mein shabd na bhi hon): (prefixes, upvishay)
CASE_TOPICS = [
    (("BA1", "BA2", "BA3", "BA4", "BA5"), "Regular bail"),
    (("ABA", "SABA"), "Anticipatory bail"),
    (("BAC",), "Cancellation of bail"),
    (("BAST",), "Suspension of sentence"),
    (("C482", "C528"), "Quashing (482 CrPC / 528 BNSS)"),
    (("WPCRL",), "FIR quashing / arrest stay (writ)"),
    (("HABC",), "Habeas corpus"),
    (("ARBAP",), "Arbitration"),
    (("ITA", "ITR"), "Income tax"),
]

# Mudda (level 4): upvishay ke andar khaas sawaal. {upvishay: [(mudda, FTS query), ...]}
ISSUES = {
    "Compassionate appointment": [
        ("Der se aavedan (delay)", '(NEAR(compassionate delay, 12) OR NEAR(compassionate belated, 12) '
                                   'OR NEAR(compassionate "lapse of time", 12) OR NEAR(compassionate "years after", 12)) '
                                   'NOT "should not be any delay"'),  # Sushma Gosain ki quote: vibhag ki der
        ("Vivahit beti / bahu", '"married daughter" OR NEAR(compassionate daughter in law, 10)'),
        ("Aarthik sthiti (indigence)", 'NEAR(compassionate indigent, 12) OR NEAR(compassionate penury, 12) '
                                       'OR NEAR(compassionate "financial condition", 12) OR "immediate financial"'),
        ("Kaunsi scheme lagegi (mrityu ki tareekh)", 'NEAR(scheme "date of death", 10) OR NEAR(policy "date of death", 10)'),
        ("Parivaar mein pehle se naukri", 'NEAR(compassionate "already employed", 15) OR "gainfully employed" OR NEAR(brother employed, 5) '
                                          'OR NEAR(brother "government service", 6) OR NEAR(brother "govt service", 6) '
                                          'OR NEAR(husband "government service", 6) OR NEAR(sister employed, 5) OR NEAR("5(1)" employed, 12) '
                                          'OR NEAR(family member "government service", 8)'),
        ("Doosri patni / aashrit", '"second wife" OR NEAR(compassionate dependent definition, 12)'),
        ("Pad ka star (higher post)", 'NEAR(compassionate "higher post", 12) OR NEAR(compassionate "class IV", 12) '
                                      'OR NEAR(compassionate "Group D", 12)'),
        ("Dying in Harness Rules 1974 (UP/Uttarakhand)", 'NEAR(harness 1974, 6)'),
    ],
    "Regularisation": [
        ("Umadevi (sanvidhan peeth)", '"Umadevi" OR "Uma Devi"'),
        ("10 saal ki seva", '"ten years" OR "10 years"'),
        ("Swikrit pad (sanctioned post)", '"sanctioned post"'),
    ],
    "Pension": [
        ("Qualifying service", '"qualifying service"'),
        ("Family pension", '"family pension"'),
        ("Old / new pension scheme", '"old pension scheme" OR "new pension scheme" OR "National Pension System"'),
    ],
    "Termination / dismissal": [
        ("Probation par", 'NEAR(probation termination, 8) OR "probationer"'),
        ("Bina jaanch (natural justice)", 'NEAR(termination "without holding", 10) OR NEAR(termination "natural justice", 10)'),
    ],
    "Regular bail": [
        ("Barabari (parity)", 'NEAR(bail parity, 8) OR NEAR(bail "co-accused", 8)'),
        ("Lamba jail (long custody)", 'NEAR(bail "long incarceration", 10) OR NEAR(bail "in custody since", 8) '
                                      'OR NEAR(bail "speedy trial", 10)'),
        ("Aapradhik itihaas", 'NEAR(bail "criminal history", 8) OR NEAR(bail antecedents, 8)'),
    ],
    "NDPS": [
        ("Commercial quantity / Section 37", 'NEAR("commercial quantity" "section 37", 15) OR "rigours of Section 37"'),
        ("Section 50 (talashi)", 'NEAR("section 50" search, 10)'),
    ],
    "Motor accident claim (MACT)": [
        ("Future prospects / multiplier", '"future prospects" OR NEAR(multiplier age, 6)'),
        ("Contributory negligence", '"contributory negligence"'),
    ],
}

# Level 5: court ka nateeja. judgments.disposal (UKHC: 'DISMISSED', SC: 'Appeal(s) allowed' ...) -> naam
OUTCOME = [
    (r"partly|partially", "Aanshik paksh mein"),
    (r"withdrawn|infructuous|abated|closed|not pressed", "Wapas / bekaar"),
    (r"in default|non.?prosecution", "Default mein khaarij"),
    (r"allowed|granted|succeed|bail|accepted", "Paksh mein"),
    (r"dismissed|rejected|declined", "Khilaf"),
    (r"referred|reference", "Bade bench ko"),
    (r"disposed|directions", "Nipataara"),
]
# 'Nipataara' wale faislon ke aakhri hisse se aur saaf nateeja (Uttarakhand HC mein aksar
# "disposed of with direction to consider the representation")
DISPOSED_TAIL = [
    (r"(petition|appeal|application|revision)s?\s+(is|are|stands?)\s+(hereby\s+)?(allowed|granted)|"
     r"released on bail", "Paksh mein"),
    (r"(petition|appeal|application|revision)s?\s+(is|are|stands?)\s+(hereby\s+)?(dismissed|rejected)", "Khilaf"),
    (r"(proceedings|impugned\s+\w+|order\s+dated\s+[\d./-]+|summoning order|charge.?sheet).{0,160}?"
     r"(is|are|stands?|hereby)\s+(quashed|set aside)", "Paksh mein"),
    (r"(consider|decide)\s+the\s+(representation|claim|case)|representation[^.]{0,100}?(considered|decided|disposed of)|"
     r"(make|file|submit|move)\s+(a\s+)?(fresh\s+)?representation", "Nirdesh: vibhag vichaar kare"),
]
