"""Compute a split's fact ledgers ahead of a Reactor run, with no Reactor: they're cached by memchal.evidence.

On dev it also prints the ledger's recall of gold sessions, overall and per type. On test, counts only.

Run: uv run --project pipeline python -I -m memchal.precompute --split dev200 --slice paired46 --pack ledger:bm25
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .data import gold as load_gold, histories, named_slice, questions
from .evidence import Evidence
from .hints import GEMMA4, QWEN27, QWEN27_MLX, QWEN27_POD

MODELS = {"gguf": QWEN27, "mlx": QWEN27_MLX, "pod": QWEN27_POD, "gemma4": GEMMA4}


def report(rows):
    for kind in sorted({r["type"] for r in rows}) + ["all"]:
        rs = [r for r in rows if kind in ("all", r["type"])]
        gold = sum(r["gold"] for r in rs)
        print(kind, json.dumps({"n": len(rs), "wide": round(sum(r["in_wide"] for r in rs) / max(gold, 1), 3),
                                "ledger": round(sum(r["in_ledger"] for r in rs) / max(gold, 1), 3),
                                "pack": round(sum(r["in_pack"] for r in rs) / max(gold, 1), 3),
                                "all_in_pack": round(float(np.mean([r["in_pack"] == r["gold"] for r in rs])), 3),
                                "ledger_sessions": round(float(np.mean([r["sessions"] for r in rs])), 2),
                                "empty": sum(r["sessions"] == 0 for r in rs), "dropped": sum(r["dropped"] for r in rs),
                                "pack_chars": round(float(np.mean([r["chars"] for r in rs])))}), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev200")
    ap.add_argument("--slice")
    ap.add_argument("--pack", required=True)
    ap.add_argument("--budget", type=int, default=14000)
    ap.add_argument("--model", default="gguf", choices=sorted(MODELS))
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    wanted = set(named_slice(args.slice)) if args.slice else None
    qs = [q for q in questions(args.split) if wanted is None or q["question_id"] in wanted]
    golds = load_gold(args.split)
    evidence = Evidence(args.pack, args.budget, args.split, golds, ledger_model=MODELS[args.model])
    evidence.query_vectors(qs)
    by_history = {}
    for q in qs:
        by_history.setdefault(q["history_id"], []).append(q)
    rows = []
    with ThreadPoolExecutor(args.workers) as pool:
        for history in histories(args.split, by_history):
            view = evidence.view(history)
            mine = by_history[history["history_id"]]
            wides = {q["question_id"]: view.wide(q) for q in mine}
            list(pool.map(lambda q: evidence.ledgers.get(q, wides[q["question_id"]]), mine))
            for q in mine:
                found = view.evidence(q)
                ledger = evidence.ledgers.rows[q["question_id"]]
                cited = {f["id"] for f in ledger["facts"]}
                row = {"type": "test", "gold": 0, "in_wide": 0, "in_ledger": 0, "in_pack": 0, "sessions": len(cited),
                       "dropped": ledger["dropped"], "chars": sum(len(p["text"]) for p in found["passages"])}
                if golds:
                    g = golds[q["question_id"]]
                    gold_set = set(g["evidence"])
                    row.update(type="abstain" if g["abstain"] else g["question_type"], gold=len(gold_set),
                               in_wide=len(gold_set & {p["id"] for p in wides[q["question_id"]]}),
                               in_ledger=len(gold_set & cited), in_pack=len(gold_set & {p["id"] for p in found["passages"]}))
                rows.append(row)
    report(rows)


if __name__ == "__main__":
    main()
