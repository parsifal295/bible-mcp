from __future__ import annotations


def fuse_scores(keyword_score: float, semantic_score: float) -> float:
    return round((keyword_score * 0.6) + (semantic_score * 0.4), 6)
