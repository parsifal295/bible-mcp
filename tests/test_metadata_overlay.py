from bible_mcp.vendor.metadata_overlay import load_metadata_overlay


def test_load_metadata_overlay_contains_core_korean_people_and_places() -> None:
    overlay = load_metadata_overlay()

    abraham = overlay.people["abraham_58"]
    assert abraham.canonical_slug == "abraham"
    assert abraham.display_name == "아브라함"
    assert "Abraham" in abraham.aliases
    assert "아브람" in abraham.aliases

    assert overlay.people["isaac_616"].display_name == "이삭"
    assert overlay.people["jacob_683"].display_name == "야곱"
    assert overlay.people["jesus_904"].display_name == "예수"

    assert overlay.places["bethlehem_218"].display_name == "베들레헴"
    assert overlay.places["jerusalem_636"].display_name == "예루살렘"
    assert overlay.places["nazareth_878"].display_name == "나사렛"
    assert overlay.places["galilee_433"].display_name == "갈릴리"
    assert overlay.places["jerusalem_636"].description is None
