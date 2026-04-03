from __future__ import annotations

import re
from collections import Counter


_COMMON_SUFFIXES = (
    "으로",
    "에서",
    "에게",
    "께서",
    "께",
    "까지",
    "부터",
    "보다",
    "처럼",
    "만큼",
    "으로써",
    "이며",
    "이고",
    "입니다",
    "이다",
    "하다",
    "요",
    "니",
    "다",
    "라",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "도",
    "와",
    "과",
)


def _normalize_token(token: str) -> str:
    for suffix in sorted(_COMMON_SUFFIXES, key=len, reverse=True):
        if len(token) > len(suffix) and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def summarize_passage_text(text: str) -> dict:
    words = []
    for word in re.findall(r"[가-힣A-Za-z]+", text):
        normalized = _normalize_token(word)
        if len(normalized) >= 2:
            words.append(normalized)

    keywords = [word for word, _count in Counter(words).most_common(5)]
    return {
        "summary": text[:120],
        "keywords": keywords,
        "motifs": keywords[:3],
    }
