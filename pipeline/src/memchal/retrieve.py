"""Retrieval over one history: windows of turns as the unit of search, BM25 and dense rankings fused by rank."""

from dataclasses import dataclass

import bm25s
import numpy as np
import Stemmer

WINDOW = 900
OVERLAP = 150
RRF_K = 60
_stemmer = Stemmer.Stemmer("english")


@dataclass
class Chunk:
    """A window of one turn. ``start`` and ``end`` are character offsets in the turn's text."""

    session: int
    turn: int
    start: int
    end: int
    text: str


def turn_windows(content):
    """(start, end) windows covering a turn. Long assistant turns are split: answers sit deep inside long lists."""
    if len(content) <= WINDOW + OVERLAP:
        return [(0, len(content))]
    out, start = [], 0
    while start < len(content):
        end = min(start + WINDOW, len(content))
        if len(content) - end < OVERLAP:
            end = len(content)
        out.append((start, end))
        if end == len(content):
            break
        start = end - OVERLAP
    return out


def session_chunks(session, session_index=0):
    return [Chunk(session_index, t, s, e, f"{turn['role']}: {turn['content'][s:e]}")
            for t, turn in enumerate(session["turns"]) for s, e in turn_windows(turn["content"])]


def chunks_of(history):
    return [c for i, s in enumerate(history["sessions"]) for c in session_chunks(s, i)]


def _tokens(texts):
    return bm25s.tokenize(texts, stopwords="en", stemmer=_stemmer, show_progress=False)


class Bm25:
    def __init__(self, chunks):
        self.index = bm25s.BM25()
        self.index.index(_tokens([c.text for c in chunks]), show_progress=False)
        self.size = len(chunks)

    def scores(self, query):
        """A score for every chunk, in chunk order."""
        tokens = _tokens([query])
        ids, values = self.index.retrieve(tokens, k=self.size, show_progress=False, sorted=False)
        out = np.zeros(self.size)
        out[ids[0]] = values[0]
        return out


def ranks(scores):
    order = np.argsort(-scores, kind="stable")
    out = np.empty(len(scores), dtype=np.int64)
    out[order] = np.arange(len(scores))
    return out


def rrf(*score_lists, weights=None):
    """Reciprocal-rank fusion of score arrays over the same chunks."""
    weights = weights or [1.0] * len(score_lists)
    return sum(w / (RRF_K + 1 + ranks(s)) for w, s in zip(weights, score_lists))


def session_scores(chunks, chunk_scores, n_sessions, top=3):
    """A session's score is the sum of its best ``top`` chunks, so one lucky window doesn't outrank a real match."""
    per_session = [[] for _ in range(n_sessions)]
    for c, score in zip(chunks, chunk_scores):
        per_session[c.session].append(score)
    return np.array([sum(sorted(v, reverse=True)[:top]) for v in per_session])
