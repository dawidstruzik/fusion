"""A prior-art case: one claim, one cutoff date, its elements asked in turn in one Reactor history.

A case becomes one more history in the corpus's split, holding only the messages from before the cutoff, so retrieval
can't see anything later and the embeddings already cached per message still apply. Its run folder gets case.json for
the app, including what was actually searched.

The case file, pipeline/cases/<case>.json:
{"title": "...", "claim": "...", "cutoff": "YYYY-MM-DD", "corpus": "ietf-tls",
 "elements": [{"element": "short label", "question": "the question Reactor gets"}]}

Run: uv run --project pipeline python -I -m memchal.cases --case grease
Then: uv run --project pipeline python -I -m memchal.run --run prior-grease --split ietf-tls --history grease --pack ledger:nemotron3 --ledger-model mlx --budget 24000 --extra 12000 --style prior

With --corpus prior, the same case searches patents and emails together, in a run named both-<case>, with --style both.
"""

import argparse
import json
from datetime import datetime

from .data import DATA, ROOT, RUNS, histories, questions, write_jsonl
from .evidence import parse_date

CASES = ROOT / "pipeline/cases"
SOURCE = "a public technical mailing list"
SOURCES = {"prior": "US patents and a public technical mailing list"}


def before(history, cutoff):
    """The history's sessions from before the cutoff date, as a history of its own."""
    limit = datetime.strptime(cutoff, "%Y-%m-%d")
    return {"history_id": history["history_id"], "sessions": [s for s in history["sessions"] if parse_date(s["date"]) < limit]}


def question_date(cutoff):
    return datetime.strptime(cutoff, "%Y-%m-%d").strftime("%Y/%m/%d (%a) 00:00")


def searched(sessions):
    """What the "not found" sentence may claim: the messages retrieval ranked."""
    return {"messages": len(sessions), "first": parse_date(sessions[0]["date"]).strftime("%Y-%m-%d"),
            "last": parse_date(sessions[-1]["date"]).strftime("%Y-%m-%d")}


def add_case(name, corpus=None):
    case = json.loads((CASES / f"{name}.json").read_text(encoding="utf-8"))
    run = f"both-{name}" if corpus else f"prior-{name}"
    corpus, cutoff = corpus or case["corpus"], case["cutoff"]
    all_histories = list(histories(corpus))
    full = next(h for h in all_histories if h["history_id"] == corpus)
    sessions = before(full, cutoff)["sessions"]
    write_jsonl(DATA / corpus / "histories.jsonl",
                [h for h in all_histories if h["history_id"] != name] + [{"history_id": name, "sessions": sessions}])
    ids = [f"{name}-{n}" for n in range(1, len(case["elements"]) + 1)]
    rows = [{"question_id": qid, "history_id": name, "question": element["question"], "question_date": question_date(cutoff),
             "source": SOURCES.get(corpus, SOURCE)} for qid, element in zip(ids, case["elements"])]
    write_jsonl(DATA / corpus / "questions.jsonl", [q for q in questions(corpus) if q["history_id"] != name] + rows)
    out = RUNS / run
    out.mkdir(parents=True, exist_ok=True)
    # Last, and all at once: the app picks up any case.json it finds.
    (out / "case.tmp").write_text(json.dumps({
        "title": case["title"], "claim": case["claim"], "cutoff": cutoff, "corpus": corpus,
        "elements": [{"question_id": qid, "element": element["element"]} for qid, element in zip(ids, case["elements"])],
        "searched": searched(sessions)}, indent=1) + "\n", encoding="utf-8")
    (out / "case.tmp").rename(out / "case.json")
    return searched(sessions)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--corpus", help="search this corpus instead of the case file's, in a both-<case> run")
    args = ap.parse_args()
    print(json.dumps(add_case(args.case, args.corpus)))


if __name__ == "__main__":
    main()
