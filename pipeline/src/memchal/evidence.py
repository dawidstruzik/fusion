"""What evidence a question gets: its gold sessions (the reader's ceiling) or a retrieval configuration.

A configuration is "gold" or "<retrieval>" or "ledger:<retrieval>", where retrieval is "bm25", "<model>" or
"<model>+bm25". With a ledger, a local model first reads a wide pack; the sessions it quotes go to Reactor with the
quotes as a hint, plus a little of the next-best sessions in case it missed one.
"""

import json
import re
import threading
import time
from datetime import datetime
from itertools import zip_longest

import numpy as np

from . import hints
from .data import CACHE
from .embed import Cached, encode_queries, load_model
from .pack import pack
from .retrieve import Bm25, chunks_of, rrf

WIDE_BUDGET = 40000
WIDE_CAP = 0.25
EXTRA_BUDGET = 2500
MIN_PER_SESSION = 1600
MIXED_SPLITS = {"prior"}


def parse_date(value):
    """The benchmark's "2023/05/20 (Sat) 02:21" as a datetime."""
    return datetime.strptime(value[:10] + value[-6:], "%Y/%m/%d %H:%M")


def with_age(passages, question_date):
    """Add each passage's age to its date, worked out here: the reader shouldn't have to do date arithmetic."""
    now = parse_date(question_date).date()
    out = []
    for p in passages:
        days = (now - parse_date(p["date"]).date()).days
        age = "same day as the question" if days == 0 else f"{days} days before the question"
        out.append({**p, "date": f"{p['date']}, {age}"})
    return out


def _squash(text):
    return re.sub(r"\s+", " ", text).strip().lower()


class Ledgers:
    """Ledgers by question, kept on disk: they cost a local model's time and the answer depends on them."""

    def __init__(self, split, config, model, wait=0):
        if split == "test" and model.startswith("pod:"):
            raise ValueError("test data stays on this Mac (D15)")
        self.model, self.wait = model, wait
        safe = re.sub(r"[^a-z0-9+_.-]", "_", f"{config}-{model}".lower())
        self.path = CACHE / "ledger" / split / f"{safe}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.rows = {}
        self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    if line.endswith("\n"):  # another process may be halfway through the last line
                        row = json.loads(line)
                        self.rows[row["question_id"]] = row

    def _cached(self, q):
        row = self.rows.get(q["question_id"])
        if row is None:  # another process may be computing them ahead of this one
            self._load()
            row = self.rows.get(q["question_id"])
        return row

    def get(self, q, wide):
        row = self._cached(q)
        deadline = time.time() + self.wait
        while row is None and time.time() < deadline:  # asking too would make the local model do it twice
            time.sleep(5)
            row = self._cached(q)
        if row is None:
            row = {"question_id": q["question_id"], **hints.extract(q["question"], q["question_date"], wide, self.model,
                                                                    q.get("source", hints.SOURCE))}
            with self.lock:
                self.rows[q["question_id"]] = row
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row


class Evidence:
    def __init__(self, name, budget, split, golds, ledger_model=hints.QWEN27, extra=EXTRA_BUDGET, ledger_wait=0):
        self.name, self.budget, self.split, self.golds, self.extra = name, budget, split, golds, extra
        self.balance = split in MIXED_SPLITS
        self.use_ledger = name.startswith("ledger:")
        self.retrieval = name.split(":", 1)[1] if self.use_ledger else name
        self.ledgers = Ledgers(split, self.retrieval, ledger_model, ledger_wait) if self.use_ledger else None
        self.dense = [p for p in self.retrieval.split("+") if p not in ("bm25", "gold")]
        self.caches = {p: Cached(split, p) for p in self.dense}

    def query_vectors(self, questions):
        """Fill in query vectors a pod hasn't made, with the model on this Mac."""
        for name, cache in self.caches.items():
            missing = [q for q in questions if q["question_id"] not in cache.query_vectors]
            if missing:
                vectors = encode_queries(load_model(name), [q["question"] for q in missing])
                cache.query_vectors.update({q["question_id"]: v for q, v in zip(missing, vectors)})

    def view(self, history):
        return HistoryView(self, history)


class HistoryView:
    def __init__(self, evidence, history):
        self.e, self.history = evidence, history
        self.chunks = chunks_of(history)
        self.bm25 = Bm25(self.chunks)
        self.vectors = {name: cache.for_history(history) for name, cache in evidence.caches.items()}

    def scores(self, q):
        lists = []
        for part in self.e.retrieval.split("+"):
            if part in ("bm25", "gold"):
                lists.append(self.bm25.scores(q["question"]))
            else:
                lists.append(self.vectors[part] @ self.e.caches[part].query_vectors[q["question_id"]])
        return lists[0] if len(lists) == 1 else rrf(*lists)

    def ranked(self, q):
        """Chunks best first. In a split mixing kinds of source, the kinds take turns, so that strong matches in one
        can't crowd the other out of the pack."""
        order = np.argsort(-self.scores(q), kind="stable")
        if not self.e.balance:
            return order
        sessions, kinds = self.history["sessions"], {}
        for i in order:
            kinds.setdefault(sessions[self.chunks[int(i)].session]["session_id"].split("/")[2], []).append(i)
        return [i for turn in zip_longest(*kinds.values()) for i in turn if i is not None]

    def evidence(self, q):
        """{"passages": [...], "hint": str or None, "ledger": facts or None} for one question."""
        scores = self.scores(q)
        gold = self.e.golds.get(q["question_id"], {}).get("evidence") or []
        if self.e.name == "gold" and gold:
            return {"passages": with_age(self._gold(scores, gold), q["question_date"]), "hint": None, "ledger": None}
        order = self.ranked(q)
        if not self.e.use_ledger:
            return {"passages": with_age(pack(self.history, order, self.e.budget, chunks=self.chunks), q["question_date"]),
                    "hint": None, "ledger": None}
        facts = self.e.ledgers.get(q, self.wide(q, order))["facts"]
        passages = with_age(self._after_ledger(order, facts), q["question_date"])
        return {"passages": passages, "hint": hints.hint_text(facts, passages), "ledger": facts}

    def wide(self, q, order=None):
        """The wide pack the ledger's model reads."""
        order = self.ranked(q) if order is None else order
        return with_age(pack(self.history, order, WIDE_BUDGET, session_cap=WIDE_CAP, chunks=self.chunks), q["question_date"])

    def _gold(self, scores, gold):
        """Only the gold sessions, each with room for its share, so that the run measures the reader alone."""
        sessions = self.history["sessions"]
        allowed = {i for i, s in enumerate(sessions) if s["session_id"] in set(gold)}
        order = [i for i in np.argsort(-scores, kind="stable") if self.chunks[int(i)].session in allowed]
        return pack(self.history, order, self.e.budget, session_cap=min(1.0, 1.3 / len(allowed)), chunks=self.chunks)

    def _after_ledger(self, order, facts):
        """The sessions the ledger quotes come first, quoted windows before the rest. With no facts, the plain pack."""
        sessions = self.history["sessions"]
        index = {s["session_id"]: i for i, s in enumerate(sessions)}
        cited = {index[f["id"]] for f in facts if f["id"] in index}
        if not cited:
            return pack(self.history, order, self.e.budget, chunks=self.chunks)
        quotes = {index[f["id"]]: [] for f in facts if f["id"] in index}
        for f in facts:
            if f["id"] in index:
                quotes[index[f["id"]]].append(_squash(f["quote"]))
        def quoted(c):
            turn = _squash(sessions[c.session]["turns"][c.turn]["content"])
            return c.session in cited and any(quote in turn for quote in quotes[c.session])
        first = [i for i in order if quoted(self.chunks[int(i)])]
        then = [i for i in order if self.chunks[int(i)].session in cited and not quoted(self.chunks[int(i)])]
        # Every quoted session needs room for a window and its neighbor, even when a counting question quotes many.
        core_budget = min(self.e.budget, max(self.e.budget - self.e.extra, MIN_PER_SESSION * len(cited)))
        # With two kinds of source the extra room stays, so that a pack of quoted emails still holds some patents.
        if self.e.balance:
            core_budget = self.e.budget - self.e.extra
        cap = min(1.0, max(1.3 / len(cited), MIN_PER_SESSION / core_budget))
        core = pack(self.history, first + then, core_budget, session_cap=cap, chunks=self.chunks)
        others = [i for i in order if self.chunks[int(i)].session not in cited]
        extra = pack(self.history, others, self.e.budget - core_budget, session_cap=0.5, chunks=self.chunks)
        return sorted(core + extra, key=lambda p: parse_date(p["date"]))
