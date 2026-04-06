from __future__ import annotations


def build_passage_answering_prompt() -> str:
    return (
        "If the user asks for a specific Bible verse or passage, call "
        "lookup_passage. When lookup_passage succeeds, return the full "
        "passage_text exactly as provided. Do not summarize, paraphrase, or "
        "shorten the verse text unless the user explicitly asks for a summary, "
        "explanation, or devotional reflection. If you answer a topical "
        "question by citing Bible references, fetch each cited reference with "
        "lookup_passage and show the full passage text for each cited reference "
        "by default. Whenever your answer includes Bible verses or scripture "
        "references for any reason, fetch them with lookup_passage and show the "
        "full passage text for every cited reference before adding any "
        "explanation or application. Do not replace cited verses with one-line "
        "summaries. Do not cite bare references or replace scripture with "
        "summary lines. Use summarize_passage only when the user explicitly "
        "asks for a summary after the passage text is shown."
    )
