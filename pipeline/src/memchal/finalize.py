"""Merge runs into one predictions.jsonl for the test split and check it. Prints counts only, never test text.

Later runs named on the command line replace earlier ones question by question, but only with an answered row, and an
abstention never replaces an answer: a question abstains only if every run did. So a failed rerun can't damage a good
answer. Every line stays Reactor's own answer through our code.

Run: uv run --project pipeline python -I -m memchal.finalize --runs test-R1 test-R2 --out pipeline/runs/predictions-final.jsonl
"""

import argparse
import json
from collections import Counter

from .cite import DEFAULT
from .data import histories, load_results, questions, RUNS, usable, write_jsonl
from .score import official, to_prediction


def merge(run_names):
    merged, source = {}, {}
    for name in run_names:
        for qid, row in load_results(RUNS / name / "results.jsonl").items():
            kept = merged.get(qid)
            answered = kept is not None and usable(kept) and not kept.get("abstained")
            if kept is None or (usable(row) and not (row.get("abstained") and answered)):
                merged[qid], source[qid] = row, name
    return merged, source


def check(predictions, split):
    """Everything the evaluator refuses or scores as zero, as readable counts."""
    qs = {q["question_id"]: q for q in questions(split)}
    problems = official.validate(predictions, set(qs))
    sessions = {h["history_id"]: {s["session_id"] for s in h["sessions"]} for h in histories(split)}
    by_id = {p["question_id"]: p for p in predictions}
    missing = len(set(qs) - set(by_id))
    foreign = sum(c not in sessions[qs[p["question_id"]]["history_id"]] for p in predictions for c in p["citations"])
    return {"problems": len(problems), "first_problem": problems[0] if problems and split != "test" else None,
            "questions": len(qs), "predictions": len(predictions), "missing": missing, "foreign_citations": foreign,
            "abstained": sum(p["abstain"] for p in predictions),
            "answered_uncited": sum(not p["abstain"] and not p["citations"] for p in predictions),
            "empty_answers": sum(not p["abstain"] and not p["answer"].strip() for p in predictions),
            "marker_left_in_answer": sum("FINAL ANSWER" in p["answer"].upper() or "INSUFFICIENT_EVIDENCE" in p["answer"].upper()
                                         for p in predictions),
            "mean_citations": round(sum(len(p["citations"]) for p in predictions) / max(len(predictions), 1), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rule", default=DEFAULT)
    args = ap.parse_args()
    merged, source = merge(args.runs)
    predictions = [to_prediction(row, args.rule) for row in merged.values()]
    write_jsonl(args.out, predictions)
    print(json.dumps({"from_run": Counter(source.values()), **check(predictions, args.split)}))


if __name__ == "__main__":
    main()
