"""Counts only: how often does retrieval on test land in the sessions Reactive AI wrote, rather than public ones?

A diagnostic for whether dev recall transfers (D17), not a signal the submission uses. The base rate is the share of
new sessions in a test history, about 22%. Prints aggregates, never any test text.

Run: uv run --project pipeline python -I -m memchal.diag_new --config bm25,nemotron3,nemotron3+bm25
"""

import argparse
import hashlib
import json

import numpy as np

from .data import CACHE, DATA, histories, questions, read_jsonl
from .embed import Cached, encode_queries, load_model
from .retrieve import Bm25, chunks_of, rrf, session_scores


def content_key(session):
    """Session ids differ between splits, so sessions are compared by a hash of their turns."""
    text = "\n".join(f"{t['role']}:{t['content']}" for t in session["turns"])
    return hashlib.sha1(text.encode()).digest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="bm25")
    args = ap.parse_args()
    configs = args.config.split(",")
    public = set()
    for split in ("dev", "dev-large"):
        for history in read_jsonl(DATA / split / "histories.jsonl"):
            public |= {content_key(s) for s in history["sessions"]}
    qs = questions("test")
    by_history = {}
    for q in qs:
        by_history.setdefault(q["history_id"], []).append(q)
    dense = sorted({p for c in configs for p in c.split("+") if p != "bm25"})
    caches = {name: Cached("test", name) for name in dense}
    query = {}
    for name in dense:
        vectors = encode_queries(load_model(name), [q["question"] for q in qs])
        query[name] = {q["question_id"]: v for q, v in zip(qs, vectors)}
    totals = {c: {"top1": 0, "top5": 0.0, "top10": 0.0, "any5": 0} for c in configs}
    newly = {c: [] for c in configs}
    new_ids = {}
    base, n = [], 0
    for history in histories("test"):
        ids = [s["session_id"] for s in history["sessions"]]
        new = np.array([content_key(s) not in public for s in history["sessions"]])
        new_ids.update({sid: bool(flag) for sid, flag in zip(ids, new)})
        base.append(new.mean())
        chunks = chunks_of(history)
        index = Bm25(chunks)
        vectors = {name: caches[name].for_history(history) for name in dense}
        for q in by_history.get(history["history_id"], []):
            n += 1
            for config in configs:
                lists = [index.scores(q["question"]) if p == "bm25" else vectors[p] @ query[p][q["question_id"]]
                         for p in config.split("+")]
                scores = lists[0] if len(lists) == 1 else rrf(*lists)
                ranked = np.argsort(-session_scores(chunks, scores, len(ids)), kind="stable")
                t = totals[config]
                t["top1"] += int(new[ranked[0]])
                t["top5"] += float(new[ranked[:5]].mean())
                t["top10"] += float(new[ranked[:10]].mean())
                t["any5"] += int(new[ranked[:5]].any())
    print(json.dumps({"questions": n, "base_rate_new": round(float(np.mean(base)), 3)}))
    for config, t in totals.items():
        print(json.dumps({"config": config, "top1_new": round(t["top1"] / n, 3), "top5_share_new": round(t["top5"] / n, 3),
                          "top10_share_new": round(t["top10"] / n, 3), "top5_has_new": round(t["any5"] / n, 3)}), flush=True)
    ledger = CACHE / "ledger" / "test" / "nemotron3-qwen3.8_27b-nvfp4.jsonl"
    if ledger.exists():
        rows = list(read_jsonl(ledger))
        cited = [f["id"] for r in rows for f in r["facts"]]
        print(json.dumps({"ledger_questions": len(rows), "empty": sum(not r["facts"] for r in rows),
                          "sessions_per_question": round(sum(len({f["id"] for f in r["facts"]}) for r in rows) / max(len(rows), 1), 2),
                          "facts_in_new_sessions": round(sum(new_ids[c] for c in cited) / max(len(cited), 1), 3),
                          "dropped_quotes": sum(r["dropped"] for r in rows), "mean_seconds": round(sum(r["seconds"] for r in rows) / max(len(rows), 1), 1)}))


if __name__ == "__main__":
    main()
