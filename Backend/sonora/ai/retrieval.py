"""Lexical retrieval (BM25) over transcript passages for the lecture chat.

Keeps answers grounded in the relevant part of long lectures without an embedding model
or vector database. No stemming, so it works for German and English alike.
"""

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sonora.ai.timestamps import format_timestamp

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_STOPWORD_TEXT = """
    a an and are as at be but by can could did do does for from had has have how i if in into
    is it its me my of on or our so than that the their them then there these they this to
    was we were what when where which who why will with would you your
    aber als am an auch auf aus bei bin bis das dass dein dem den der des die doch du ein eine
    einem einen einer eines er es für hat hatte ich ihr im in ist ja kann mit nach nicht noch
    nur ob oder sich sie sind so und uns vom von vor war waren warum was wenn wer wie wir wird
    wo zu zum zur über
"""
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if len(w) > 1 and w not in _STOPWORDS]


@dataclass(frozen=True, slots=True)
class Passage:
    start: float
    text: str  # "[mm:ss] ..." lines


def build_passages(segments: Sequence[Mapping[str, Any]], max_chars: int = 700) -> list[Passage]:
    """Groups consecutive segments into passages of roughly ``max_chars``."""
    passages: list[Passage] = []
    lines: list[str] = []
    start = 0.0
    size = 0
    for segment in segments:
        line = f"[{format_timestamp(segment['start'])}] {segment['text']}"
        if lines and size + len(line) > max_chars:
            passages.append(Passage(start, "\n".join(lines)))
            lines, size = [], 0
        if not lines:
            start = float(segment["start"])
        lines.append(line)
        size += len(line) + 1
    if lines:
        passages.append(Passage(start, "\n".join(lines)))
    return passages


class BM25:
    def __init__(self, documents: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self._k1, self._b = k1, b
        self._freqs = [Counter(doc) for doc in documents]
        self._lengths = [len(doc) for doc in documents]
        self._avg_length = (sum(self._lengths) / len(documents)) if documents else 0.0
        doc_freq = Counter(term for doc in documents for term in set(doc))
        n = len(documents)
        self._idf = {t: math.log(1 + (n - df + 0.5) / (df + 0.5)) for t, df in doc_freq.items()}

    def scores(self, query: Sequence[str]) -> list[float]:
        results = []
        for freqs, length in zip(self._freqs, self._lengths, strict=True):
            norm = self._k1 * (1 - self._b + self._b * length / (self._avg_length or 1))
            score = 0.0
            for term in query:
                tf = freqs.get(term, 0)
                if tf:
                    score += self._idf[term] * tf * (self._k1 + 1) / (tf + norm)
            results.append(score)
        return results


def rank_passages(passages: Sequence[Passage], query: str) -> list[Passage]:
    """Passages sharing at least one term with ``query``, best match first."""
    terms = tokenize(query)
    if not terms or not passages:
        return []
    scores = BM25([tokenize(p.text) for p in passages]).scores(terms)
    ranked = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)
    return [passages[i] for i in ranked if scores[i] > 0]
