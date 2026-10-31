"""Build dev200: dev-large histories cut to 200 sessions, the size of a test history, keeping every gold session.

Abstention questions have no gold sessions, so each keeps the 20 sessions that share the most words with it: near
misses are what makes abstaining hard. Also writes the question slices in pipeline/data/splits.json: tune and heldout
are split by history, and heldout80 is a fixed sample of heldout in the proportions of the question types.

Run: uv run --project pipeline python -m memchal.dev200
"""

import hashlib
import json
import random
import re
import sys

from .data import DATA, SPLITS_FILE, gold, histories, questions, write_jsonl

SIZE = 200
OUT = DATA / "dev200"
TOKEN = re.compile(r"[a-z0-9']+")
STOP = set("the a an of to in on for and or is was what when where who how many much did do does i my me you your "
           "it that this with at by from have has had be been are were which".split())


def words(text):
    return {w for w in TOKEN.findall(text.lower()) if w not in STOP}


def session_words(session):
    return words(" ".join(t["content"] for t in session["turns"]))


def cut(history, qs, golds):
    keep = set()
    for q in qs:
        g = golds[q["question_id"]]
        keep |= set(g["evidence"])
        if g["abstain"]:
            target = words(q["question"])
            ranked = sorted(history["sessions"], key=lambda s: -len(target & session_words(s)))
            keep |= {s["session_id"] for s in ranked[:20]}
    rng = random.Random(history["history_id"])
    rest = [s["session_id"] for s in history["sessions"] if s["session_id"] not in keep]
    rng.shuffle(rest)
    keep |= set(rest[: max(SIZE - len(keep), 0)])
    return {"history_id": history["history_id"], "sessions": [s for s in history["sessions"] if s["session_id"] in keep]}


def side(history_id):
    return "heldout" if hashlib.sha1(history_id.encode()).digest()[0] % 2 else "tune"


def slices(qs, golds):
    out = {"tune": [], "heldout": []}
    for q in qs:
        out[side(q["history_id"])].append(q["question_id"])
    rng = random.Random(80)
    by_type = {}
    for qid in out["heldout"]:
        g = golds[qid]
        by_type.setdefault("abstain" if g["abstain"] else g["question_type"], []).append(qid)
    total = len(out["heldout"])
    sample = []
    for kind in sorted(by_type):
        ids = sorted(by_type[kind])
        rng.shuffle(ids)
        sample += ids[: max(round(80 * len(ids) / total), 3)]
    out["heldout80"] = sorted(sample)
    # The paired Reactor runs: 8 of each type and 6 abstentions, whole-question counts rather than proportions, so
    # the weak types get as many calls as the strong ones. Then a sample no tuning decision ever looks at.
    rng = random.Random(46)
    paired, untouched = [], []
    for kind in sorted(by_type):
        ids = sorted(by_type[kind])
        rng.shuffle(ids)
        n = 6 if kind == "abstain" else 8
        paired += ids[:n]
        untouched += ids[n: n + (2 if kind == "abstain" else 6)]
    out["paired46"] = sorted(paired)
    out["untouched32"] = sorted(untouched)
    return out


def main():
    qs, golds = questions("dev-large"), gold("dev-large")
    if "--slices-only" not in sys.argv:
        by_history = {}
        for q in qs:
            by_history.setdefault(q["history_id"], []).append(q)
        write_jsonl(OUT / "histories.jsonl", (cut(h, by_history[h["history_id"]], golds) for h in histories("dev-large")))
        write_jsonl(OUT / "questions.jsonl", qs)
        write_jsonl(OUT / "gold.jsonl", golds.values())
    SPLITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    made = slices(qs, golds)
    SPLITS_FILE.write_text(json.dumps(made, indent=0) + "\n")
    print({k: len(v) for k, v in made.items()})


if __name__ == "__main__":
    main()
