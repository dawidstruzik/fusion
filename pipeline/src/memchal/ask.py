"""One live question over a corpus, for the app: prints one results-format JSON line on stdout, everything else on stderr.

Exits 3 with a short message if Reactor is busy, 1 if it gave no usable answer. A follow-up passes back the printed
reactor_history; once any other history has started on our agent that one is closed, and the row says so.

Run: uv run --project pipeline python -I -m memchal.ask --corpus ietf-tls --cutoff 2016-01-01 --question "..." [--history H]
"""

import argparse
import contextlib
import hashlib
import json
import sys

from . import reactor
from .cases import SOURCE, SOURCES, before, question_date
from .data import RUNS, histories, usable
from .evidence import Evidence
from .hints import QWEN27_MLX
from .run import attempt

BUDGET, EXTRA = 24000, 12000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--cutoff", required=True, help="YYYY-MM-DD: only messages from before this date are searched")
    ap.add_argument("--question", required=True)
    ap.add_argument("--history", help="the reactor_history of an earlier question in this case")
    args = ap.parse_args()
    # Same question and cutoff, same id: its ledger comes from the cache the second time.
    digest = hashlib.sha1(f"{args.cutoff} {args.question}".encode()).hexdigest()[:12]
    q = {"question_id": f"live-{digest}", "history_id": args.corpus, "question": args.question,
         "question_date": question_date(args.cutoff), "source": SOURCES.get(args.corpus, SOURCE)}
    try:
        with reactor.reactor_lock_now(), contextlib.redirect_stdout(sys.stderr):
            history = before(next(histories(args.corpus, [args.corpus])), args.cutoff)
            evidence = Evidence("ledger:nemotron3", BUDGET, args.corpus, {}, ledger_model=QWEN27_MLX, extra=EXTRA)
            evidence.query_vectors([q])
            found = evidence.view(history).evidence(q)
            style = "both" if args.corpus in SOURCES else "prior"
            row, _ = attempt(q, found["passages"], style, args.history, hint=found["hint"])
    except BlockingIOError:
        print("Reactor is busy with another run or question.", file=sys.stderr)
        sys.exit(3)
    row.update(passages=found["passages"], ledger=found["ledger"], cutoff=args.cutoff)
    out = RUNS / f"live-{args.corpus}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "results.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False))
    if row.get("code") in ("history_changed", "history_required"):
        print("That history is closed: start a new case.", file=sys.stderr)
    sys.exit(0 if usable(row) else 1)


if __name__ == "__main__":
    main()
