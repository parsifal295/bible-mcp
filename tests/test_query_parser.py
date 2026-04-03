from bible_mcp.query.parser import parse_reference


def test_parse_reference_supports_korean_short_book_name() -> None:
    parsed = parse_reference("창 1:1-3")
    assert parsed.book == "Genesis"
    assert parsed.chapter == 1
    assert parsed.start_verse == 1
    assert parsed.end_verse == 3


def test_parse_reference_supports_chapter_only_input() -> None:
    parsed = parse_reference("로마서 8장")
    assert parsed.book == "Romans"
    assert parsed.chapter == 8
    assert parsed.start_verse is None
    assert parsed.end_verse is None


def test_parse_reference_supports_canonical_english_name_outside_demo_slice() -> None:
    parsed = parse_reference("Exodus 3:14")
    assert parsed is not None
    assert parsed.book == "Exodus"
    assert parsed.chapter == 3
    assert parsed.start_verse == 14
    assert parsed.end_verse == 14


def test_parse_reference_supports_digit_prefixed_english_book_name() -> None:
    parsed = parse_reference("2 Corinthians 5:17")
    assert parsed is not None
    assert parsed.book == "2 Corinthians"
    assert parsed.chapter == 5
    assert parsed.start_verse == 17
    assert parsed.end_verse == 17


def test_parse_reference_supports_korean_alias_for_digit_prefixed_book_name() -> None:
    parsed = parse_reference("사무엘상 3:1")
    assert parsed is not None
    assert parsed.book == "1 Samuel"
    assert parsed.chapter == 3
    assert parsed.start_verse == 1
    assert parsed.end_verse == 1


def test_parse_reference_supports_korean_reference_without_space() -> None:
    parsed = parse_reference("창1:1")
    assert parsed is not None
    assert parsed.book == "Genesis"
    assert parsed.chapter == 1
    assert parsed.start_verse == 1
    assert parsed.end_verse == 1


def test_parse_reference_supports_korean_short_book_without_space() -> None:
    parsed = parse_reference("요3:16")
    assert parsed is not None
    assert parsed.book == "John"
    assert parsed.chapter == 3
    assert parsed.start_verse == 16
    assert parsed.end_verse == 16


def test_parse_reference_supports_chapter_only_input_without_space() -> None:
    parsed = parse_reference("롬8장")
    assert parsed is not None
    assert parsed.book == "Romans"
    assert parsed.chapter == 8
    assert parsed.start_verse is None
    assert parsed.end_verse is None
