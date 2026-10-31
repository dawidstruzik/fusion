"""One question through the local steps, printing one JSON object per line as each step starts and finishes, and stopping before Reactor. Nothing is sent.

Same question and cutoff as memchal.ask, same pre-read cache: a repeated question skips the local model.

Lines: {"event": "start" or "done", "step": name, "text": what it does or did, "seconds": time taken or null}. Check adds "quotes", "kept" and "dropped".

Run: uv run --project pipeline python -I -m memchal.trace --corpus prior --cutoff 2016-02-11 --question "..."
"""

import json
import os
import sys
import time

# The JSON lines keep the real stdout. Everything else that writes there, Python or C, before or during the
# imports below, goes to stderr instead.
_lines = os.fdopen(os.dup(1), "w", encoding="utf-8")
os.dup2(2, 1)


def emit(event, step, text, seconds=None, **extra):
    _lines.write(json.dumps({"event": event, "step": step, "text": text, "seconds": seconds, **extra}, ensure_ascii=False) + "\n")
    _lines.flush()


import argparse  # noqa: E402
import hashlib  # noqa: E402
import re  # noqa: E402

from . import hints  # noqa: E402
from .ask import BUDGET, EXTRA  # noqa: E402
from .cases import SOURCE, SOURCES, before, question_date  # noqa: E402
from .data import histories  # noqa: E402
from .evidence import Evidence, with_age  # noqa: E402
from .hints import QWEN27_MLX  # noqa: E402


def finish(step, started, text, **extra):
    emit("done", step, text, round(time.time() - started, 1), **extra)


def size(passages):
    return sum(len(p["text"]) for p in passages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--cutoff", required=True, help="YYYY-MM-DD: only documents from before this date are searched")
    ap.add_argument("--question", required=True)
    args = ap.parse_args()
    digest = hashlib.sha1(f"{args.cutoff} {args.question}".encode()).hexdigest()[:12]
    q = {"question_id": f"live-{digest}", "history_id": args.corpus, "question": args.question,
         "question_date": question_date(args.cutoff), "source": SOURCES.get(args.corpus, SOURCE)}

    started = time.time()
    emit("start", "Load", f"Loading documents from before {args.cutoff}")
    history = before(next(histories(args.corpus, [args.corpus])), args.cutoff)
    evidence = Evidence("ledger:nemotron3", BUDGET, args.corpus, {}, ledger_model=QWEN27_MLX, extra=EXTRA)
    view = evidence.view(history)
    finish("Load", started, f"{len(history['sessions']):,} documents before {args.cutoff}, {len(view.chunks):,} windows")

    started = time.time()
    emit("start", "Embed", "Turning the question into a vector with Nemotron 3 Embed 1B")
    evidence.query_vectors([q])
    finish("Embed", started, "The question, with Nemotron 3 Embed 1B on this Mac")

    started = time.time()
    emit("start", "Search", "Searching the windows")
    order = view.ranked(q)
    wide = view.wide(q, order)
    finish("Search", started, f"{len(wide)} passages for the pre-read, {size(wide):,} characters")

    started = time.time()
    cached = evidence.ledgers._cached(q)
    emit("start", "Pre-read", "Fetching the saved reading of this question" if cached else f"Qwen on this Mac is reading {len(wide)} passages")
    row = evidence.ledgers.get(q, wide)
    note = f"Saved reading, the first took {row['seconds']} s" if cached else f"Qwen on this Mac wrote {row.get('output_tokens')} tokens"
    finish("Pre-read", started, note)

    facts = row["facts"]
    quotes = []
    for fact in facts:
        patent = re.search(r"patent/([^/]+)", fact["id"])
        quotes.append({"source": patent.group(1) if patent else "Email", "quote": fact["quote"]})
    emit("done", "Check", f"{len(facts)} quotes found word for word in their passages, {row['dropped']} dropped",
         quotes=quotes, kept=len(facts), dropped=row["dropped"])

    started = time.time()
    emit("start", "Pack", "Packing the passages for Reactor")
    passages = with_age(view._after_ledger(order, facts), q["question_date"])
    hint = hints.hint_text(facts, passages)
    finish("Pack", started, f"{len(passages)} passages, oldest first, {size(passages) + len(hint or ''):,} characters")

    emit("done", "Reactor", "Ready for Reactor. Not sent.")


if __name__ == "__main__":
    main()
