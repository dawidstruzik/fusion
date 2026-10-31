"""Several corpora as one split, so that one search covers them all: the histories, the embeddings already made for
each, and the app's message index. A session keeps its own vectors, so nothing is embedded twice.

Run: uv run --project pipeline python -I -m memchal.combine --corpora ietf-tls patents --out prior --list "the IETF tls list and US patents"
"""

import argparse
import json

import numpy as np

from .data import DATA, ROOT, histories, read_jsonl, write_jsonl
from .embed import Cached, cache_dir
from .evidence import parse_date

CORPUS = ROOT / "pipeline/corpus"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpora", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--list", required=True, help="how the app names what was searched")
    ap.add_argument("--model", default="nemotron3")
    args = ap.parse_args()

    sessions, vectors, offsets, count = [], [], {}, 0
    for corpus in args.corpora:
        cached = Cached(corpus, args.model)
        sessions += next(histories(corpus, [corpus]))["sessions"]
        vectors.append(cached.vectors)
        offsets.update({sid: [start + count, n] for sid, (start, n) in cached.offsets.items()})
        count += len(cached.vectors)
    sessions.sort(key=lambda s: (parse_date(s["date"]), s["session_id"]))
    write_jsonl(DATA / args.out / "histories.jsonl", [{"history_id": args.out, "sessions": sessions}])
    (DATA / args.out / "questions.jsonl").touch()
    out = cache_dir(args.out, args.model)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "vectors.npy", np.concatenate(vectors))
    (out / "offsets.json").write_text(json.dumps(offsets))

    rows = [{"kind": "email", **row} for corpus in args.corpora for row in read_jsonl(CORPUS / corpus / "messages.jsonl")]
    rows.sort(key=lambda r: (r["date"], r["id"]))
    write_jsonl(CORPUS / args.out / "messages.jsonl", rows)
    summary = {"name": args.out, "list": args.list, "messages": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"]}
    (CORPUS / args.out / "corpus.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "sessions": len(sessions), "windows": count}))


if __name__ == "__main__":
    main()
