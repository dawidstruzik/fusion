"""The challenge's splits on disk, and the paths everything else shares."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "external/data"
RUNS = ROOT / "pipeline/runs"
SPLITS_FILE = ROOT / "pipeline/data/splits.json"
CACHE = ROOT / "external/cache"


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def questions(split):
    return list(read_jsonl(DATA / split / "questions.jsonl"))


def gold(split):
    """Gold by question id. Test has none: {} there."""
    path = DATA / split / "gold.jsonl"
    return {g["question_id"]: g for g in read_jsonl(path)} if path.exists() else {}


def histories(split, ids=None):
    """Yield histories, only those in ``ids`` when given (stops early once all are found)."""
    wanted = set(ids) if ids is not None else None
    for history in read_jsonl(DATA / split / "histories.jsonl"):
        if wanted is None or history["history_id"] in wanted:
            yield history
            if wanted is not None:
                wanted.discard(history["history_id"])
                if not wanted:
                    return


def load_results(path):
    """A run's results by question id, the latest attempt for each, in the order they were written. A last line cut
    off by a crash is ignored; a broken line anywhere else is an error."""
    latest = {}
    if not Path(path).exists():
        return latest
    with open(path, encoding="utf-8") as fh:
        lines = [line for line in fh if line.strip()]
    for n, line in enumerate(lines):
        try:
            row = json.loads(line)
        except ValueError:
            if n == len(lines) - 1:
                break
            raise
        latest.pop(row["question_id"], None)
        latest[row["question_id"]] = row
    return latest


_LABELS = re.compile(r"\[\s*E\d+(?:\s*[,;]\s*E\d+)*\s*\]")


def usable(row):
    """An answer we can submit: Reactor answered, and said something beyond citation labels, or abstained."""
    if row.get("status") != "answered":
        return False
    return bool(row.get("abstained")) or bool(_LABELS.sub("", row.get("answer") or "").strip(" .,;:\n\t"))


def named_slice(name):
    """Question ids of a slice in pipeline/data/splits.json."""
    return json.loads(SPLITS_FILE.read_text())[name]
