"""Offline retrieval comparison on dev, with no Reactor: does the evidence survive into the pack?

For each question: session recall at 5 and 10, the share of gold sessions present in the pack, whether all of them
are, and whether the gold answer's words appear in the pack (when they appear in the gold sessions at all, because
many gold answers are computed and never stated). Printed per question type.

Run: uv run --project pipeline python -I -m memchal.evalret --split dev200 --slice tune --histories 100 --config bm25
"""

import argparse
import json
import time

import numpy as np

from .data import histories, named_slice, questions, gold as load_gold
from .embed import Cached, encode_queries, history_ids_for, load_model
from .pack import pack
from .retrieve import Bm25, chunks_of, rrf, session_scores


def norm(text):
    return " " + " ".join("".join(ch if ch.isalnum() else " " for ch in text.lower()).split()) + " "


def answer_found(answer, text):
    return norm(answer) in norm(text)


def score_config(config, q_vecs, q, view):
    """Chunk scores for one configuration: "bm25", "<model>" or "<model>+bm25"."""
    parts = config.split("+")
    lists = []
    for part in parts:
        if part == "bm25":
            lists.append(view["bm25"].scores(q["question"]))
        else:
            lists.append(view["vectors"][part] @ q_vecs[part][q["question_id"]])
    return lists[0] if len(lists) == 1 else rrf(*lists)


def evaluate(config, split, slice_name, n_histories, budget, cap=0.45):
    parts = [p for p in config.split("+") if p != "bm25"]
    wanted = set(named_slice(slice_name)) if slice_name else None
    ids = set(history_ids_for(split, slice_name, n_histories))
    qs = [q for q in questions(split) if q["history_id"] in ids and (wanted is None or q["question_id"] in wanted)]
    golds = load_gold(split)
    caches = {p: Cached(split, p) for p in parts}
    q_vecs = {}
    for p in parts:
        if caches[p].query_vectors:
            q_vecs[p] = caches[p].query_vectors
            continue
        model = load_model(p)
        vecs = encode_queries(model, [q["question"] for q in qs])
        q_vecs[p] = {q["question_id"]: v for q, v in zip(qs, vecs)}
        del model
    by_history = {}
    for q in qs:
        by_history.setdefault(q["history_id"], []).append(q)
    rows = []
    started = time.time()
    for history in histories(split, by_history):
        chunks = chunks_of(history)
        view = {"bm25": Bm25(chunks), "vectors": {p: c.for_history(history) for p, c in caches.items()}}
        ids_in_order = [s["session_id"] for s in history["sessions"]]
        for q in by_history[history["history_id"]]:
            g = golds[q["question_id"]]
            if g["abstain"]:
                continue
            scores = score_config(config, q_vecs, q, view)
            gold_set = set(g["evidence"])
            ranking = np.argsort(-session_scores(chunks, scores, len(ids_in_order)), kind="stable")
            ranked_ids = [ids_in_order[i] for i in ranking]
            passages = pack(history, np.argsort(-scores, kind="stable"), budget, session_cap=cap, chunks=chunks)
            in_pack = {p["id"] for p in passages}
            text = " ".join(p["text"] for p in passages)
            gold_text = " ".join(t["content"] for s in history["sessions"] if s["session_id"] in gold_set
                                 for t in s["turns"])
            stated = answer_found(g["answer"], gold_text)
            rows.append({"type": g["question_type"], "r5": len(gold_set & set(ranked_ids[:5])) / len(gold_set),
                         "r10": len(gold_set & set(ranked_ids[:10])) / len(gold_set),
                         "in_pack": len(gold_set & in_pack) / len(gold_set), "all_in_pack": gold_set <= in_pack,
                         "n_pack": len(in_pack), "stated": stated, "answer_in_pack": stated and answer_found(g["answer"], text)})
    summary = {}
    for kind in sorted({r["type"] for r in rows}) + ["all"]:
        rs = [r for r in rows if kind in ("all", r["type"])]
        stated = [r for r in rs if r["stated"]]
        summary[kind] = {"n": len(rs), "r5": round(np.mean([r["r5"] for r in rs]), 3),
                         "r10": round(np.mean([r["r10"] for r in rs]), 3),
                         "in_pack": round(np.mean([r["in_pack"] for r in rs]), 3),
                         "all_in_pack": round(np.mean([r["all_in_pack"] for r in rs]), 3),
                         "n_pack": round(np.mean([r["n_pack"] for r in rs]), 1),
                         "answer_in_pack": round(np.mean([r["answer_in_pack"] for r in stated]), 3) if stated else None}
    return {"config": config, "budget": budget, "seconds": round(time.time() - started), "summary": summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help='comma-separated, e.g. "bm25,gemma300,gemma300+bm25"')
    ap.add_argument("--split", default="dev200")
    ap.add_argument("--slice")
    ap.add_argument("--histories", type=int)
    ap.add_argument("--budget", type=int, default=14000)
    ap.add_argument("--cap", type=float, default=0.45, help="the most of the budget one session may take")
    args = ap.parse_args()
    for config in args.config.split(","):
        result = evaluate(config, args.split, args.slice, args.histories, args.budget, args.cap)
        print(json.dumps({k: result[k] for k in ("config", "budget", "seconds")}), flush=True)
        for kind, row in result["summary"].items():
            print(f"  {kind:26s} {row}", flush=True)


if __name__ == "__main__":
    main()
