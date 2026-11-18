"""Scoring functions from the plan's Evaluation section (used by the Phase 2 bake-off)."""
from __future__ import annotations

import re
import unicodedata


def normalize_words(text: str) -> list[str]:
    """Whitespace, ligature and hyphenation normalization before word comparison."""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)  # join end-of-line hyphenation
    t = t.replace("­", "")
    return re.findall(r"\w+(?:[.,']\w+)*", t.lower())


def lcs_len(a: list[str], b: list[str]) -> int:
    """Longest common subsequence length, O(len(a)*len(b)) time, O(len(b)) memory."""
    if len(a) < len(b):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def body_score(extracted: str, truth: str) -> float:
    """LCS of word sequences over the longer sequence: penalizes order errors, omissions and junk."""
    a, b = normalize_words(extracted), normalize_words(truth)
    if not a and not b:
        return 1.0
    return lcs_len(a, b) / max(len(a), len(b))


def _cell(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip().replace("−", "-")


def table_score(extracted: list[list[str]], truth: list[list[str]]) -> float:
    """Share of ground-truth cells exactly equal at the same (row, col) after whitespace normalization."""
    total = sum(len(r) for r in truth)
    if total == 0:
        return 1.0 if not extracted else 0.0
    ok = 0
    for i, row in enumerate(truth):
        for j, c in enumerate(row):
            if i < len(extracted) and j < len(extracted[i]) and _cell(extracted[i][j]) == _cell(c):
                ok += 1
    return ok / total
