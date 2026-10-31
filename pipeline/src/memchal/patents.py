"""US patents close to TLS as a split the pipeline can read: one history, one session per patent, oldest first.

A session's id is the patent's Google Patents URL, so a citation opens in a browser. The tables come from the final
PatentsView release on Zenodo, read straight from their zip files. They must already be in raw/: this doesn't download
anything. Everything under raw/ is untrusted data, which is why this runs with -I.

Run: uv run --project pipeline python -I -m memchal.patents
"""

import csv
import hashlib
import io
import json
import re
import statistics
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone

from .data import DATA, ROOT, write_jsonl

SPLIT = "patents"
LIST = "US patents"
CORPUS = ROOT / "pipeline/corpus" / SPLIT
RAW = DATA / SPLIT / "raw/zenodo-15783125"
RECORD_URL = "https://zenodo.org/records/15783125"
DOI = "10.5281/zenodo.15783125"
GROUPS = ("H04L63/0428", "H04L63/166", "H04L63/0823", "H04L9/3263", "H04L9/0841", "H04L9/0844")
FIRST, LAST = "2005-01-01", "2018-12-31"
ROLE = "user"
PATENT_URL = "https://patents.google.com/patent/{number}/en"


def _rows(name):
    """A zipped table's rows as dicts, without extracting it. An abstract can run long, so no field limit applies."""
    csv.field_size_limit(sys.maxsize)
    with zipfile.ZipFile(RAW / name) as archive, archive.open(archive.namelist()[0]) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""), delimiter="\t", quotechar='"')


def _text(value):
    """A field on one line: the tables keep some hard line breaks and runs of spaces from the source XML."""
    return re.sub(r"\s+", " ", (value or "").replace("\x00", "")).strip()


def in_field():
    """{patent_id: the groups of the cut it holds, at any CPC position} and how many rows each group matched."""
    matched, groups = {}, Counter()
    for row in _rows("g_cpc_current.tsv.zip"):
        if row["cpc_group"] in GROUPS:
            matched.setdefault(row["patent_id"], set()).add(row["cpc_group"])
            groups[row["cpc_group"]] += 1
    return matched, groups


def convert():
    """(patents oldest first, counts of what was dropped by reason, counts of notable handling)."""
    matched, groups = in_field()
    dropped, notes, patents = Counter(), Counter(), {}
    notes["in the CPC groups"] = len(matched)
    notes.update({f"rows for {group}": count for group, count in groups.items()})
    for row in _rows("g_patent.tsv.zip"):
        pid = row["patent_id"]
        if pid not in matched:
            continue
        if row["patent_type"] != "utility":
            dropped[f"not a utility patent ({row['patent_type']})"] += 1
        elif not FIRST <= row["patent_date"] <= LAST:
            dropped["granted outside the range"] += 1
        elif row["withdrawn"] != "0":
            dropped["withdrawn"] += 1
        elif not _text(row["patent_title"]):
            dropped["no title"] += 1
        else:
            patents[pid] = row
    dropped["in the CPC table but not in g_patent"] = len(matched) - sum(dropped.values()) - len(patents)

    abstracts = {}
    for row in _rows("g_patent_abstract.tsv.zip"):
        pid = row["patent_id"]
        if pid in patents:
            if pid in abstracts:
                notes["repeated abstract rows, first kept"] += 1
            else:
                abstracts[pid] = _text(row["patent_abstract"])

    filed = {}
    for row in _rows("g_application.tsv.zip"):
        if row["patent_id"] in patents:
            filed.setdefault(row["patent_id"], row["filing_date"])

    rows = []
    for pid, row in patents.items():
        if not abstracts.get(pid):
            dropped["no abstract"] += 1
            continue
        number = f"US{pid}{row['wipo_kind']}"
        notes[f"kind {row['wipo_kind']}"] += 1
        # The table has typos like 1074-08-14, so a filing date must fall in a sane range or the grant date stands in.
        date = filed.get(pid, "")
        if not "1970-01-01" <= date <= row["patent_date"]:
            notes["no usable filing date, grant date used"] += 1
            date = row["patent_date"]
        rows.append({
            "id": PATENT_URL.format(number=number),
            "date": datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc),
            "granted": row["patent_date"],
            "number": number,
            "title": _text(row["patent_title"]),
            "abstract": abstracts[pid],
        })
    rows.sort(key=lambda row: (row["date"], row["id"]))
    return rows, +dropped, notes


def session_of(row):
    return {
        "session_id": row["id"],
        "date": row["date"].strftime("%Y/%m/%d (%a) %H:%M"),
        "turns": [{"turn_id": "t_" + hashlib.sha1(row["id"].encode()).hexdigest()[:12], "role": ROLE,
                   "content": f"Patent: {row['number']}\nTitle: {row['title']}\n\n{row['abstract']}"}],
    }


def _iso(date):
    return date.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_corpus(rows):
    """The same patents for the app: one line per session, with the citation and the fields split out."""
    write_jsonl(CORPUS / "messages.jsonl", [{"id": r["id"], "url": r["id"], "date": _iso(r["date"]), "granted": r["granted"],
                                             "from": r["number"], "subject": r["title"], "list": LIST, "kind": "patent",
                                             "body": r["abstract"]} for r in rows])
    summary = {"name": SPLIT, "list": LIST, "messages": len(rows), "first": _iso(rows[0]["date"]), "last": _iso(rows[-1]["date"])}
    (CORPUS / "corpus.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def manifest(sessions, dropped, notes):
    fetched = sorted(p.stat().st_mtime for p in RAW.glob("*.zip"))
    when = [datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") for t in (fetched[0], fetched[-1])]
    sizes = [len(s["turns"][0]["content"]) for s in sessions]
    kinds = ", ".join(f"{count} {key[5:]}" for key, count in sorted(notes.items()) if key.startswith("kind "))
    lines = [
        f"# {SPLIT}: US patents close to TLS",
        "",
        "Built by `pipeline/src/memchal/patents.py`. Rerun it to rebuild from the tables in `raw/`, which it doesn't download.",
        "",
        f"- Source: United States Patent and Trademark Office, \"Final release of PatentsView metadata, pre-grant and granted (12/31/2024)\", Zenodo, doi:{DOI}, {RECORD_URL}.",
        "- Tables: `g_patent.tsv.zip`, `g_patent_abstract.tsv.zip`, `g_application.tsv.zip` and `g_cpc_current.tsv.zip`, no login.",
        "- License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Credit the source above when reusing this data. The text was changed only by squeezing whitespace, and the patents were selected as below.",
        "- USPTO says PatentsView data is provided for research purposes and isn't the official USPTO record.",
        f"- Cut: US utility grants from {FIRST} through {LAST} by grant date, holding any of {', '.join(GROUPS)} at any CPC position, as of the release.",
        f"- Date range in the data: {sessions[0]['date']} to {sessions[-1]['date']}, the filing date, shown at midnight UTC.",
        f"- Fetched: {when[0]} to {when[1]}.",
        f"- In the CPC groups: {notes['in the CPC groups']}. Kept: {len(sessions)} ({kinds}). Dropped: {sum(dropped.values())}.",
        f"- Characters: {sum(sizes)} in total, median {int(statistics.median(sizes))} per patent.",
        "",
        "## Dropped",
        "",
        *[f"- {count}: {reason}." for reason, count in dropped.most_common()],
        "",
        "## Format",
        "",
        f"`histories.jsonl` holds one history, `{SPLIT}`, with one session per patent, oldest first. `session_id` is the",
        f"patent's URL, {PATENT_URL.format(number='US{patent_id}{wipo_kind}')}. `date` is the filing date of the application,",
        f"or the grant date for the {notes['no usable filing date, grant date used']} without a usable one. A priority claim can make the effective date earlier still.",
        "",
        "Each session has one turn. Its content is `Patent: US...`, `Title: ...`, a blank line and the abstract. Claims aren't included.",
        "",
        "`questions.jsonl` is empty on purpose, and `raw/` holds untrusted downloads: read them with `python -I`.",
    ]
    (DATA / SPLIT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    rows, dropped, notes = convert()
    sessions = [session_of(row) for row in rows]
    write_jsonl(DATA / SPLIT / "histories.jsonl", [{"history_id": SPLIT, "sessions": sessions}])
    (DATA / SPLIT / "questions.jsonl").write_text("", encoding="utf-8")
    write_corpus(rows)
    manifest(sessions, dropped, notes)
    print(f"kept {len(sessions)}, dropped {dict(dropped)}, notes {dict(notes)}")


if __name__ == "__main__":
    main()
