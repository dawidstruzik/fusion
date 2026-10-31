"""Offline check of the fact ledger on tuning questions, with no Reactor: does it find the gold sessions, and how fast?

Run: uv run --project pipeline python -I -m memchal.ledger_eval --model qwen27 --per-type 6 --wide 40000
"""

import argparse
import json
import random
import time

import numpy as np

from . import hints
from .data import gold as load_gold, histories, named_slice, questions
from .evidence import with_age
from .pack import pack
from .retrieve import Bm25, chunks_of

MODELS = {"qwen27": hints.QWEN27, "gemma4": hints.GEMMA4, "qwen27mlx": hints.QWEN27_MLX}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen27", choices=sorted(MODELS))
    ap.add_argument("--per-type", type=int, default=6)
    ap.add_argument("--wide", type=int, default=40000)
    args = ap.parse_args()
    golds = load_gold("dev200")
    tune = set(named_slice("tune"))
    by_type = {}
    for q in questions("dev200"):
        g = golds[q["question_id"]]
        if q["question_id"] in tune:
            by_type.setdefault("abstain" if g["abstain"] else g["question_type"], []).append(q)
    rng = random.Random(6)
    sample = []
    for kind in sorted(by_type):
        rng.shuffle(by_type[kind])
        sample += by_type[kind][: args.per_type]
    wanted = {q["history_id"] for q in sample}
    rows = []
    for history in histories("dev200", wanted):
        chunks = chunks_of(history)
        index = Bm25(chunks)
        for q in [q for q in sample if q["history_id"] == history["history_id"]]:
            g = golds[q["question_id"]]
            order = np.argsort(-index.scores(q["question"]), kind="stable")
            passages = with_age(pack(history, order, args.wide, session_cap=0.25, chunks=chunks), q["question_date"])
            ledger = hints.extract(q["question"], q["question_date"], passages, model=MODELS[args.model])
            cited = {f["id"] for f in ledger["facts"]}
            gold_set = set(g["evidence"])
            row = {"type": "abstain" if g["abstain"] else g["question_type"], "gold_in_wide": len(gold_set & {p["id"] for p in passages}),
                   "gold": len(gold_set), "gold_in_ledger": len(gold_set & cited), "ledger_sessions": len(cited),
                   "facts": len(ledger["facts"]), "dropped": ledger["dropped"], "s": ledger["seconds"],
                   "in": ledger["prompt_tokens"], "out": ledger["output_tokens"]}
            rows.append(row)
            print(json.dumps(row), flush=True)
    for kind in sorted({r["type"] for r in rows}) + ["all"]:
        rs = [r for r in rows if kind in ("all", r["type"])]
        print(kind, {"n": len(rs), "gold_recall": round(sum(r["gold_in_ledger"] for r in rs) / max(sum(r["gold"] for r in rs), 1), 3),
                     "wide_recall": round(sum(r["gold_in_wide"] for r in rs) / max(sum(r["gold"] for r in rs), 1), 3),
                     "ledger_sessions": round(np.mean([r["ledger_sessions"] for r in rs]), 1),
                     "dropped": sum(r["dropped"] for r in rs), "facts": sum(r["facts"] for r in rs),
                     "seconds": round(np.mean([r["s"] for r in rs]), 1)}, flush=True)


if __name__ == "__main__":
    main()
