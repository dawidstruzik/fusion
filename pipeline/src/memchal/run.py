"""Ask Reactor a set of questions with our evidence, resumably: one Reactor history per dataset history.

Writes pipeline/runs/<run>/results.jsonl, one line per attempt (the last line for a question wins), and config.json.
On the test split, prints counts only: no question or answer text may reach a coding agent's context.

Run: uv run --project pipeline python -I -m memchal.run --run gold-notes --split dev200 --slice heldout80 --pack gold
"""

import argparse
import json
import time

from . import reactor
from .data import RUNS, gold as load_gold, histories, load_results, named_slice, questions, usable
from .evidence import Evidence
from .hints import GEMMA4, QWEN27, QWEN27_MLX, QWEN27_POD

ATTEMPTS = 3
MODELS = {"gguf": QWEN27, "mlx": QWEN27_MLX, "pod": QWEN27_POD, "gemma4": GEMMA4}


def attempt(q, passages, style, reactor_history, hint=None):
    """One call. Returns (row, reactor_history). Retries stay in the same Reactor history (Kosti, 31 Oct 00:17: no
    resets between questions of one dataset history); a new one only when the agent no longer has ours."""
    ref = reactor.new_ref()
    text = reactor.message(q["question"], passages, ref, q["question_date"], style=style, hint=hint)
    row = {"question_id": q["question_id"], "history_id": q["history_id"], "question": q["question"], "ref": ref,
           "chars": len(text), "at": time.strftime("%H:%M:%S")}
    try:
        reactor_history = reactor_history or reactor.new_history()
        row["reactor_history"] = reactor_history
        result = reactor.ask(text, ref, reactor_history)
    except reactor.client.Refused as exc:
        row.update(status="refused", code=exc.code, error=str(exc), retries=getattr(exc, "retries", 0))
        return row, None if exc.code in ("history_changed", "history_required") else reactor_history
    except reactor.client.TimedOut as exc:
        row.update(status="timeout", other_replies=exc.other_replies, retries=getattr(exc, "retries", 0))
        return row, reactor_history
    except (reactor.client.NoAnswer, OSError) as exc:
        row.update(status=type(exc).__name__, error=str(exc))
        return row, reactor_history
    cited, unknown = reactor.client.citations(result["answer"], passages)
    row.update(status="answered", answer=result["answer"], reply=result["reply"], latency_s=result["latency_s"],
               retries=result["retries"], other_replies=result["other_replies"], labels=[c["label"] for c in cited],
               cited=[c["id"] for c in cited], unknown_labels=unknown,
               abstained=bool(reactor.client._INSUFFICIENT.match(result["answer"])))
    if not usable(row):
        row["status"] = "empty_answer"
    return row, reactor_history


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--split", default="dev200")
    ap.add_argument("--slice", help="a named slice from pipeline/data/splits.json; default all questions")
    ap.add_argument("--pack", default="gold", help="gold, bm25, or a fusion name known to memchal.evidence")
    ap.add_argument("--budget", type=int, default=14000)
    ap.add_argument("--style", default="notes", choices=["notes", "direct", "prior", "both"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--first-histories", type=int, help="only the questions of the first N dataset histories")
    ap.add_argument("--history", help="only the questions of this dataset history")
    ap.add_argument("--only", nargs="+", help="only these question ids, or a JSON file listing them")
    ap.add_argument("--redo", action="store_true", help="ask again even if this run already has a usable answer")
    ap.add_argument("--abstained-in", help="only the questions this earlier run abstained on: a second look")
    ap.add_argument("--ledger-model", default="gguf", choices=sorted(MODELS))
    ap.add_argument("--extra", type=int, help="characters of unquoted sessions in a ledger pack")
    ap.add_argument("--ledger-wait", type=int, default=0, help="seconds to wait for memchal.precompute before computing a ledger here")
    args = ap.parse_args()
    secret_split = args.split == "test"

    wanted = set(named_slice(args.slice)) if args.slice else None
    qs = [q for q in questions(args.split) if wanted is None or q["question_id"] in wanted]
    if args.abstained_in:
        abstained = {qid for qid, row in load_results(RUNS / args.abstained_in / "results.jsonl").items() if row.get("abstained")}
        qs = [q for q in qs if q["question_id"] in abstained]
    if args.history:
        qs = [q for q in qs if q["history_id"] == args.history]
    if args.only:
        only = json.load(open(args.only[0])) if args.only[0].endswith(".json") else args.only
        qs = [q for q in qs if q["question_id"] in set(only)]
    if args.first_histories:
        keep = list(dict.fromkeys(q["history_id"] for q in qs))[: args.first_histories]
        qs = [q for q in qs if q["history_id"] in keep]
    if args.limit:
        qs = qs[: args.limit]
    golds = load_gold(args.split)
    out_dir = RUNS / args.run
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(vars(args), indent=1) + "\n")
    results_path = out_dir / "results.jsonl"
    evidence = Evidence(args.pack, args.budget, args.split, golds, ledger_model=MODELS[args.ledger_model],
                        ledger_wait=args.ledger_wait, **({"extra": args.extra} if args.extra is not None else {}))
    evidence.query_vectors(qs)
    with reactor.reactor_lock(), open(results_path, "a", encoding="utf-8") as out:
        # Only now: another process may have been answering these while this one waited for the lock.
        earlier = load_results(results_path)
        done = set() if args.redo else {qid for qid, row in earlier.items() if usable(row)}
        resume_history = {row["history_id"]: row["reactor_history"] for row in earlier.values() if row.get("reactor_history")}
        todo = [q for q in qs if q["question_id"] not in done]
        by_history = {}
        for q in todo:
            by_history.setdefault(q["history_id"], []).append(q)
        print(json.dumps({"questions": len(qs), "already_answered": len(qs) - len(todo),
                          "histories": len(by_history)}), flush=True)
        for history in histories(args.split, by_history):
            reactor_history = resume_history.get(history["history_id"])
            view = evidence.view(history)
            for q in by_history[history["history_id"]]:
                found = view.evidence(q)
                passages = found["passages"]
                for n in range(ATTEMPTS):
                    row, reactor_history = attempt(q, passages, args.style, reactor_history, hint=found["hint"])
                    row["passages"] = passages
                    row["ledger"] = found["ledger"]
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    if row["status"] == "answered":
                        break
                if secret_split:
                    print(json.dumps({"status": row["status"], "latency_s": row.get("latency_s"), "chars": row["chars"],
                                      "n_passages": len(passages), "n_cited": len(row.get("cited") or []),
                                      "abstained": row.get("abstained")}), flush=True)
                else:
                    print(json.dumps({"qid": q["question_id"], "status": row["status"], "s": row.get("latency_s"),
                                      "chars": row["chars"], "answer": (row.get("answer") or "")[:120],
                                      "gold": str(golds.get(q["question_id"], {}).get("answer"))[:80]},
                                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
