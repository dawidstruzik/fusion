"""Score a run's results with the challenge's own score.py, then settle what it leaves unjudged with the local judge.

Writes the run's predictions.jsonl and scored.jsonl. "matched" is score.py's floor, "judged" adds the local judge.

Run: uv run --project pipeline python -I -m memchal.score --run gold-notes --split dev200
     add --only-common other-run to compare two runs on the questions both have answered
"""

import argparse
import importlib.util
import json

from . import cite, judge
from .data import DATA, ROOT, RUNS, load_results, questions, usable, write_jsonl


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


official = _load("official_score", ROOT / "external/memory-challenge/score.py")
kit = _load("kit_predictions", ROOT / "external/memory-challenge/reactor/predictions.py")


def to_prediction(row, rule=cite.DEFAULT):
    if not usable(row):
        return {"question_id": row["question_id"], "abstain": True, "answer": "", "citations": []}
    if row["abstained"]:
        return {"question_id": row["question_id"], "abstain": True, "answer": "", "citations": cite.choose(row, rule)}
    return {"question_id": row["question_id"], "abstain": False, "answer": kit.strip_labels(row["answer"]),
            "citations": cite.choose(row, rule)}


def compare_citation_rules(rows, split):
    golds = {g["question_id"]: g for g in official.read_jsonl(DATA / split / "gold.jsonl")}
    answerable = [row for qid, row in rows.items() if not golds[qid]["abstain"] and row["status"] == "answered"]
    for rule in cite.RULES:
        f1 = [official.evidence_f1(cite.choose(row, rule), golds[row["question_id"]]["evidence"]) for row in answerable]
        n_cited = [len(cite.choose(row, rule)) for row in answerable]
        print(f"citations {rule:20s} evidence_f1={sum(f1) / max(len(f1), 1):.3f} cited_per_question={sum(n_cited) / max(len(n_cited), 1):.2f}")


def score_rows(rows, split):
    """Per-question results for answered rows, with a ``final`` verdict: correct or wrong, nothing unjudged."""
    golds = {g["question_id"]: g for g in official.read_jsonl(DATA / split / "gold.jsonl")}
    text = {q["question_id"]: q["question"] for q in questions(split)}
    results = []
    for qid, row in rows.items():
        g, p = golds[qid], to_prediction(row)
        result = official.score_question(p, g)
        result["final"] = result["answer"]
        if result["answer"] == "unjudged":
            result["final"] = "correct" if judge.judge(text[qid], g["answer"], g["question_type"], p["answer"]) else "wrong"
        result["answer_text"], result["gold"] = p["answer"], g["answer"]
        result["question"] = text[qid]
        results.append(result)
    return results


def table(results):
    groups = {}
    for r in results:
        groups.setdefault("abstain" if r["gold_abstain"] else r["question_type"], []).append(r)
    groups = dict(sorted(groups.items()))
    groups["all"] = results
    for name, rs in groups.items():
        f1 = [r["evidence_f1"] for r in rs if r["evidence_f1"] is not None]
        answerable = [r for r in rs if not r["gold_abstain"]]
        print(f"{name:26s} n={len(rs):3d} matched={sum(r['answer'] == 'correct' for r in rs) / len(rs):.3f} "
              f"judged={sum(r['final'] == 'correct' for r in rs) / len(rs):.3f} "
              f"evidence_f1={(sum(f1) / len(f1)) if f1 else 0:.3f} "
              f"false_abstain={sum(not r['abstain_ok'] for r in answerable)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--split", default="dev200")
    ap.add_argument("--only-common", help="another run: score only the questions both have answered")
    ap.add_argument("--wrong", action="store_true", help="also list wrong answers (dev only)")
    args = ap.parse_args()
    out_dir = RUNS / args.run
    rows = load_results(out_dir / "results.jsonl")
    write_jsonl(out_dir / "predictions.jsonl", [to_prediction(row) for row in rows.values()])
    print({"rows": len(rows), "answered": sum(r["status"] == "answered" for r in rows.values()),
           "abstained": sum(bool(r.get("abstained")) for r in rows.values())})
    if args.split == "test":
        return
    if args.only_common:
        other = load_results(RUNS / args.only_common / "results.jsonl")
        rows = {qid: row for qid, row in rows.items() if other.get(qid, {}).get("status") == "answered"}
    results = score_rows(rows, args.split)
    write_jsonl(out_dir / "scored.jsonl", results)
    table(results)
    compare_citation_rules(rows, args.split)
    if args.wrong:
        for r in results:
            if r["final"] != "correct":
                print(json.dumps({k: r[k] for k in ("question_type", "question", "gold", "answer_text", "evidence_f1")},
                                 ensure_ascii=False))


if __name__ == "__main__":
    main()
