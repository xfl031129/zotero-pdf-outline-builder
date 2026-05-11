from zotero_pdf_outline_builder.outline import (
    BuildOptions,
    extract_from_headings,
    heading_confidence,
    iter_text_lines,
    merge_heading_continuations,
    split_inline_heading,
    TextLine,
    OutlineEntry,
    normalize_entries,
    suppress_lettered_entries_for_numeric_style,
    suppress_numbered_entries_for_lettered_style,
    recover_missing_sequence_entries,
    build_outline_for_pdf,
    level_from_title,
    parse_toc_text,
    roman_to_int,
)


def test_parse_toc_text_with_dotted_leaders():
    text = """
    Table of Contents
    Abstract ........ iii
    1 Introduction ........ 1
    2.1 Prior Work ........ 8
    References ........ 42
    """

    entries = parse_toc_text(text)

    assert entries == [
        (1, "Abstract", "iii"),
        (1, "1 Introduction", "1"),
        (2, "2.1 Prior Work", "8"),
        (1, "References", "42"),
    ]


def test_roman_to_int():
    assert roman_to_int("iii") == 3
    assert roman_to_int("IX") == 9
    assert roman_to_int("xiv") == 14


def test_level_from_title():
    assert level_from_title("1 Introduction") == 1
    assert level_from_title("2.1 Prior Work") == 2
    assert level_from_title("3.2.4 Ablation") == 3
    assert level_from_title("A. Robot Design") == 2
    assert level_from_title("I. Local Planner") == 2
    assert level_from_title("I. INTRODUCTION") == 1
    assert level_from_title("0 d p hy d hy") == 1


def test_heading_detection_skips_paper_title_and_keeps_second_level(tmp_path):
    import fitz

    pdf = tmp_path / "paper.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "A Very Important Paper Title About Robots", fontsize=20)
    page.insert_text((72, 150), "Abstract", fontsize=14)
    page.insert_text((72, 180), "This is normal body text for estimating the font size.", fontsize=10)
    page = doc.new_page()
    page.insert_text((72, 72), "1 Introduction", fontsize=14)
    page.insert_text((72, 115), "1.1 Contributions", fontsize=12)
    page.insert_text((72, 140), "A. Robot Design", fontsize=10)
    page.insert_text((72, 170), "More normal body text for this section.", fontsize=10)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    try:
        entries = extract_from_headings(doc, BuildOptions().min_confidence)
    finally:
        doc.close()

    titles = [entry.title for entry in entries]
    levels = {entry.title: entry.level for entry in entries}
    assert "A Very Important Paper Title About Robots" not in titles
    assert "Abstract" in titles
    assert "1 Introduction" in titles
    assert "1.1 Contributions" in titles
    assert "A. Robot Design" in titles
    assert levels["1.1 Contributions"] == 2
    assert levels["A. Robot Design"] == 2


def test_two_column_order_and_multiline_heading_merge(tmp_path):
    import fitz

    pdf = tmp_path / "columns.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((54, 120), "A. Left Column Heading", fontsize=10)
    page.insert_text((54, 150), "Left body text comes after the left heading.", fontsize=10)
    page.insert_text((320, 80), "B. Right Column Heading With Multiple Words Reaching", fontsize=10)
    page.insert_text((320, 92), "Lines", fontsize=10)
    page.insert_text((320, 124), "Right body text comes after the right heading.", fontsize=10)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    try:
        page = doc.load_page(0)
        lines = list(iter_text_lines(page, 0, merge_headings=True, body_size=10.0))
    finally:
        doc.close()

    texts = [line.text for line in lines]
    assert texts.index("A. Left Column Heading") < texts.index(
        "B. Right Column Heading With Multiple Words Reaching Lines"
    )
    assert "B. Right Column Heading With Multiple Words Reaching Lines" in texts


def test_centered_multiline_roman_heading_merge(tmp_path):
    import fitz

    pdf = tmp_path / "centered.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((130, 120), "III. VERY LONG CENTERED SECTION TITLE", fontsize=10)
    page.insert_text((210, 132), "CONTINUED HERE", fontsize=10)
    page.insert_text((54, 170), "Normal body text begins here.", fontsize=10)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    try:
        page = doc.load_page(0)
        lines = list(iter_text_lines(page, 0, merge_headings=True, body_size=10.0))
    finally:
        doc.close()

    assert "III. VERY LONG CENTERED SECTION TITLE CONTINUED HERE" in [line.text for line in lines]


def test_split_inline_roman_heading_from_body_text():
    line = TextLine(
        text="III. THREE-PHASE BALANCE CONTROL SYSTEM ToensurestableoperationoftheWBR",
        page=0,
        bbox=(300, 500, 560, 512),
        max_size=10,
        avg_size=10,
        bold=False,
    )

    split = split_inline_heading(line)

    assert split.text == "III. THREE-PHASE BALANCE CONTROL SYSTEM"
    assert split.x1 < line.x1


def test_math_and_body_number_lines_are_not_headings():
    body_size = 10.0
    math_line = TextLine(
        text="M−1 S⊤",
        page=0,
        bbox=(100, 100, 140, 112),
        max_size=10,
        avg_size=10,
        bold=True,
    )
    body_line = TextLine(
        text="4 s. In the vertical impact test, the robot quickly recovers even",
        page=0,
        bbox=(300, 200, 560, 212),
        max_size=10,
        avg_size=10,
        bold=False,
    )
    numbered_body_line = TextLine(
        text="2. We assume",
        page=0,
        bbox=(54, 260, 120, 272),
        max_size=10,
        avg_size=10,
        bold=False,
    )
    measurement_line = TextLine(
        text="1.7 TB",
        page=0,
        bbox=(54, 280, 90, 292),
        max_size=8,
        avg_size=8,
        bold=False,
    )
    date_line = TextLine(
        text="12 FEBRUARY 2016",
        page=0,
        bbox=(54, 300, 150, 312),
        max_size=8.5,
        avg_size=8.5,
        bold=False,
    )
    question_line = TextLine(
        text="1. Can an RT-1 learn to perform a large number of instructions",
        page=0,
        bbox=(54, 320, 320, 332),
        max_size=10,
        avg_size=10,
        bold=False,
    )
    what_question_line = TextLine(
        text="5. What are the important and practical decisions in the design",
        page=0,
        bbox=(54, 330, 320, 342),
        max_size=10,
        avg_size=10,
        bold=False,
    )
    author_list_line = TextLine(
        text="B. P. Abbott et al.*",
        page=0,
        bbox=(54, 345, 180, 357),
        max_size=10,
        avg_size=10,
        bold=False,
    )
    valid_numbered_line = TextLine(
        text="4 Why Self-Attention",
        page=0,
        bbox=(54, 360, 180, 372),
        max_size=12,
        avg_size=12,
        bold=False,
    )
    valid_line = TextLine(
        text="B. Parallel Kalman Filter (PKF)",
        page=0,
        bbox=(40, 300, 180, 312),
        max_size=10,
        avg_size=10,
        bold=False,
    )

    assert heading_confidence(math_line.text, math_line, body_size)[0] == 0
    assert heading_confidence(body_line.text, body_line, body_size)[0] == 0
    assert heading_confidence(numbered_body_line.text, numbered_body_line, body_size)[0] == 0
    assert heading_confidence(measurement_line.text, measurement_line, body_size)[0] == 0
    assert heading_confidence(date_line.text, date_line, body_size)[0] == 0
    assert heading_confidence(question_line.text, question_line, body_size)[0] == 0
    assert heading_confidence(what_question_line.text, what_question_line, body_size)[0] == 0
    assert heading_confidence(author_list_line.text, author_list_line, body_size)[0] == 0
    assert heading_confidence(valid_numbered_line.text, valid_numbered_line, body_size)[0] > 0
    assert heading_confidence(valid_line.text, valid_line, body_size)[0] > 0


def test_plain_methods_table_cell_is_not_section_but_heading_is():
    body_size = 10.0
    table_cell = TextLine(
        text="Methods",
        page=0,
        bbox=(200, 300, 245, 310),
        max_size=8.0,
        avg_size=8.0,
        bold=False,
    )
    heading = TextLine(
        text="METHODS",
        page=0,
        bbox=(80, 120, 140, 132),
        max_size=10.5,
        avg_size=10.5,
        bold=False,
    )

    assert heading_confidence(table_cell.text, table_cell, body_size)[0] == 0
    assert heading_confidence(heading.text, heading, body_size)[0] > 0


def test_i_letter_subsection_and_person_name_sentence_are_not_top_level():
    body_size = 10.0
    i_subsection = TextLine(
        text="I. Local Planner",
        page=0,
        bbox=(54, 220, 140, 232),
        max_size=10,
        avg_size=10,
        bold=False,
    )
    roman_section = TextLine(
        text="I. INTRODUCTION",
        page=0,
        bbox=(120, 220, 210, 232),
        max_size=10,
        avg_size=10,
        bold=False,
    )
    person_sentence = TextLine(
        text="M. Li and J. Ammanabrolu from MSUM developed a prototype with an IMU sensing",
        page=0,
        bbox=(54, 250, 300, 262),
        max_size=10,
        avg_size=10,
        bold=False,
    )

    assert heading_confidence(i_subsection.text, i_subsection, body_size)[1] == "lettered"
    assert heading_confidence(roman_section.text, roman_section, body_size)[1] == "numbered"
    assert heading_confidence(person_sentence.text, person_sentence, body_size)[0] == 0


def test_person_with_multiple_initials_and_references_truncation():
    body_size = 10.0
    person_sentence = TextLine(
        text="M. R. Botre from MIT-World Peace University, in India, developed a prototype",
        page=0,
        bbox=(54, 250, 300, 262),
        max_size=10,
        avg_size=10,
        bold=False,
    )
    entries = [
        OutlineEntry(1, "1 INTRODUCTION", 1, 0.9, "numbered"),
        OutlineEntry(1, "REFERENCES", 5, 0.9, "section"),
        OutlineEntry(2, "A. Fake Reference Heading", 6, 0.9, "lettered"),
    ]

    assert heading_confidence(person_sentence.text, person_sentence, body_size)[0] == 0
    assert [entry.title for entry in normalize_entries(entries, page_count=6)] == [
        "1 INTRODUCTION",
        "REFERENCES",
    ]


def test_lettered_heading_does_not_merge_body_sentence_but_keeps_title_case_continuation(tmp_path):
    import fitz

    pdf = tmp_path / "survey_like.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((54, 120), "A. ROBOCANE", fontsize=10)
    page.insert_text((64, 136), "Zhang and Ye from Virginia Commonwealth University", fontsize=10)
    page.insert_text((320, 120), "E. ISANA", fontsize=10)
    page.insert_text((330, 136), "Intelligent Situation Awareness and Navigation Aid", fontsize=10)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    try:
        page = doc.load_page(0)
        lines = list(iter_text_lines(page, 0, merge_headings=True, body_size=10.0))
    finally:
        doc.close()

    texts = [line.text for line in lines]
    assert "A. ROBOCANE" in texts
    assert "A. ROBOCANE Zhang and Ye from Virginia Commonwealth University" not in texts
    assert "E. ISANA" in texts
    assert "E. ISANA Intelligent Situation Awareness and Navigation Aid" not in texts


def test_multiline_heading_continuation_requires_last_line_to_fill_column():
    lines = [
        TextLine(
            text="B. Long Heading Reaches The End Of The Column",
            page=0,
            bbox=(320, 100, 558, 112),
            max_size=10,
            avg_size=10,
            bold=False,
            order=0,
            column=1,
        ),
        TextLine(
            text="Continuation",
            page=0,
            bbox=(320, 114, 382, 126),
            max_size=10,
            avg_size=10,
            bold=False,
            order=1,
            column=1,
        ),
        TextLine(
            text="Additional Body Style Phrase",
            page=0,
            bbox=(320, 138, 455, 150),
            max_size=10,
            avg_size=10,
            bold=False,
            order=2,
            column=1,
        ),
    ]

    merged = merge_heading_continuations(lines, page_width=612, body_size=10.0)
    texts = [line.text for line in merged]

    assert "B. Long Heading Reaches The End Of The Column Continuation" in texts
    assert "Additional Body Style Phrase" in texts
    assert all("Continuation Additional Body" not in text for text in texts)


def test_numeric_style_suppresses_lettered_false_positives():
    entries = [
        OutlineEntry(1, "1 INTRODUCTION", 1, 0.9, "numbered"),
        OutlineEntry(2, "1.1 Setup", 1, 0.9, "numbered"),
        OutlineEntry(1, "2 METHODS", 2, 0.9, "numbered"),
        OutlineEntry(2, "2.1 Data", 2, 0.9, "numbered"),
        OutlineEntry(2, "H. Mori et al. [95]", 3, 0.5, "lettered"),
    ]

    filtered = suppress_lettered_entries_for_numeric_style(entries)

    assert [entry.title for entry in filtered] == [
        "1 INTRODUCTION",
        "1.1 Setup",
        "2 METHODS",
        "2.1 Data",
    ]


def test_lettered_style_suppresses_numbered_false_positives():
    entries = [
        OutlineEntry(1, "I. INTRODUCTION", 1, 0.9, "numbered"),
        OutlineEntry(2, "A. Robot Design", 2, 0.5, "lettered"),
        OutlineEntry(2, "B. Control Framework", 3, 0.5, "lettered"),
        OutlineEntry(1, "2. Sensor Label", 3, 0.5, "numbered"),
        OutlineEntry(2, "C. Experiments", 4, 0.5, "lettered"),
        OutlineEntry(1, "II. CONCLUSION", 5, 0.9, "numbered"),
    ]

    filtered = suppress_numbered_entries_for_lettered_style(entries)

    assert [entry.title for entry in filtered] == [
        "I. INTRODUCTION",
        "A. Robot Design",
        "B. Control Framework",
        "C. Experiments",
        "II. CONCLUSION",
    ]


def test_figure_text_near_caption_is_not_promoted_to_outline(tmp_path):
    import fitz

    pdf = tmp_path / "figure_text.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((170, 86), "I. INTRODUCTION", fontsize=10)
    for index in range(10):
        page.insert_text((54, 125 + index * 13), "This body sentence provides a stable body font estimate.", fontsize=10)
    page.insert_text((238, 330), "ROBOT STATE", fontsize=13)
    page.insert_text((205, 500), "Fig. 1. Overview of the robot state estimator.", fontsize=8)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    try:
        entries = extract_from_headings(doc, min_confidence=0.30)
    finally:
        doc.close()

    titles = [entry.title for entry in entries]
    assert "I. INTRODUCTION" in titles
    assert "ROBOT STATE" not in titles


def test_ocr_roman_two_marker_is_canonicalized(tmp_path):
    import fitz

    pdf = tmp_path / "roman_ocr.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((150, 110), "I. INTRODUCTION", fontsize=10)
    for index in range(10):
        page.insert_text((54, 150 + index * 14), "This body sentence provides a stable body font estimate.", fontsize=9)
    page.insert_text((80, 320), "IL FIVE-BAR WHEEL-LEGGED ROBOT ARCHITECTURE", fontsize=8)
    page.insert_text((330, 160), "III. IMPLEMENTATION OF SIMULATION", fontsize=10)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    try:
        entries = extract_from_headings(doc, min_confidence=0.30)
    finally:
        doc.close()

    titles = [entry.title for entry in entries]
    assert "II. FIVE-BAR WHEEL-LEGGED ROBOT ARCHITECTURE" in titles
    assert "IL FIVE-BAR WHEEL-LEGGED ROBOT ARCHITECTURE" not in titles


def test_first_page_lower_left_author_bio_is_not_outline(tmp_path):
    import fitz

    pdf = tmp_path / "author_bio.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((150, 110), "I. INTRODUCTION", fontsize=10)
    for index in range(10):
        page.insert_text((54, 150 + index * 14), "This body sentence provides a stable body font estimate.", fontsize=9)
    page.insert_text(
        (54, 620),
        "John Doe received the B.S. degree from Example University in 2020.",
        fontsize=10.5,
    )
    page.insert_text((54, 635), "Corresponding author: john@example.edu", fontsize=10.5)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    try:
        entries = extract_from_headings(doc, min_confidence=0.30)
    finally:
        doc.close()

    titles = [entry.title for entry in entries]
    assert "I. INTRODUCTION" in titles
    assert all("John Doe" not in title for title in titles)
    assert all("Corresponding author" not in title for title in titles)


def test_missing_lettered_sequence_recovers_from_raw_pool():
    entries = [
        OutlineEntry(2, "I. ANSVIP", 7, 0.5, "lettered", order=10),
        OutlineEntry(2, "K. NAIST Project", 8, 0.5, "lettered", order=30),
        OutlineEntry(1, "REFERENCES", 9, 0.9, "section", order=1),
        OutlineEntry(2, "J. Journal Reference", 10, 0.5, "lettered", order=1),
    ]
    pool = [
        OutlineEntry(2, "J. Lodz University of Technology (LUT) Project", 8, 0.42, "recovered", order=20),
        OutlineEntry(2, "H. Mori et al. [95]", 8, 0.42, "recovered", order=21),
    ]

    recovered = recover_missing_sequence_entries(entries, pool)

    assert [entry.title for entry in recovered] == [
        "I. ANSVIP",
        "J. Lodz University of Technology (LUT) Project",
        "K. NAIST Project",
        "REFERENCES",
        "J. Journal Reference",
    ]


def test_existing_outline_is_reused_without_force(tmp_path):
    import fitz

    pdf = tmp_path / "with_outline.pdf"
    out = tmp_path / "with_outline.out.pdf"
    debug = tmp_path / "with_outline.debug.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.set_toc([[1, "Existing Section", 1]])
    doc.save(pdf)
    doc.close()

    result = build_outline_for_pdf(pdf, out, BuildOptions(force=False), debug_pdf_path=debug)

    assert result.entries[0].source == "existing"
    assert result.entries[0].title == "Existing Section"
    assert out.exists()
    assert debug.exists()


def test_normalize_repairs_first_level_and_drops_structured_font_front_matter():
    entries = [
        OutlineEntry(4, "Author Name, University", 1, 0.4, "font"),
        OutlineEntry(1, "28 January 2026", 1, 0.7, "numbered"),
        OutlineEntry(2, "2.1 A Real Subsection", 2, 0.9, "numbered"),
        OutlineEntry(1, "REFERENCES", 3, 0.9, "section"),
    ]

    normalized = normalize_entries(entries, page_count=3)

    assert normalized[0].level == 1
    assert normalized[0].title == "2.1 A Real Subsection"
    assert all("Author" not in entry.title for entry in normalized)
    assert all("January" not in entry.title for entry in normalized)
