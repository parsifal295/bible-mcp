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
