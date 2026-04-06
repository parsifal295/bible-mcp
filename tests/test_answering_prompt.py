from bible_mcp.client_patterns.answering import build_passage_answering_prompt


def test_build_passage_answering_prompt_requires_full_passage_text_for_reference_queries() -> None:
    prompt = build_passage_answering_prompt()

    assert "If the user asks for a specific Bible verse or passage" in prompt
    assert "call lookup_passage" in prompt
    assert "return the full passage_text exactly as provided" in prompt
    assert "Do not summarize, paraphrase, or shorten the verse text" in prompt
    assert "Use summarize_passage only when the user explicitly asks for a summary" in prompt


def test_build_passage_answering_prompt_requires_full_text_for_cited_scripture_in_topic_answers() -> None:
    prompt = build_passage_answering_prompt()

    assert "If you answer a topical question by citing Bible references" in prompt
    assert "fetch each cited reference with lookup_passage" in prompt
    assert "show the full passage text for each cited reference by default" in prompt
    assert "Do not replace cited verses with one-line summaries" in prompt


def test_build_passage_answering_prompt_requires_full_text_for_any_scripture_reference_in_answers() -> None:
    prompt = build_passage_answering_prompt()

    assert "Whenever your answer includes Bible verses or scripture references for any reason" in prompt
    assert "show the full passage text for every cited reference" in prompt
    assert "Do not cite bare references or replace scripture with summary lines" in prompt
    assert "before adding any explanation or application" in prompt
