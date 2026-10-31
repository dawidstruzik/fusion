# memchal: answering questions about long histories, with Reactor writing every answer

Our entry for Reactive AI's Memory Retrieval Challenge, and the engine behind Fusion, our application. Given a user's 200 past chat sessions and a question, find the sessions that matter, have Reactor answer from them with citations, and abstain when the answer isn't there. Fusion points the same engine at US patents and a public technical mailing list.

Every final answer is written by Reactor. The answering pipeline uses only local models and Reactor, and on the test data everything except Reactor runs on one laptop. A rented GPU only sped up experiments on dev, which is public LongMemEval.

## How it works

1. **Search.** Each session is cut into windows of turns, from both speakers, and ranked by a local embedder (Nemotron 3 Embed 1B). On 260 dev questions, 99.2% of the sessions that hold the answer landed in a pack of 40,000 characters, against 95.0% for BM25.
2. **Fact ledger.** A local model (Qwen3.8 27B) reads that wide pack and lists quotes that bear on the question, each with its source. It never answers. Our code keeps a quote only if those exact words are in the passage it names, so an invented fact can't get through.
3. **Evidence pack.** 24,000 characters: the sessions the ledger quotes first, then up to 12,000 characters of the next-best sessions in case the ledger missed one, all in date order. Each passage carries its date and its age in days, computed in code, so Reactor doesn't do date arithmetic.
4. **Reactor.** One message per question: the evidence, the ledger as a list of quotes to check against the passages, and instructions to take brief notes before answering. Reactor writes the answer and cites passages by label, or answers `INSUFFICIENT_EVIDENCE`. One Reactor history per dataset history, never reset within it.
5. **Citations.** Reactor's labels, plus the sessions the ledger quoted. Evidence F1 on dev chose this rule.
6. **Second look.** Questions Reactor abstained on get one more call with a bigger pack. An abstention never replaces an answer when runs are merged.

## Running it

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/), the challenge's data in `external/data/`, its repo in `external/memory-challenge/`, Reactor credentials in `secret.json` at the repo root, and [Ollama](https://ollama.com) with the ledger's model, `qwen3.8:27b-nvfp4`. Run from the repo root.

```sh
# Embed a split on this machine
uv run --project pipeline python -I -m memchal.embed --model nemotron3 --split test

# Optional: work out ledgers ahead of the run, so the local model and Reactor run side by side
uv run --project pipeline python -I -m memchal.precompute --split test --pack ledger:nemotron3 --model mlx

# Ask Reactor; results land in pipeline/runs/<run>/results.jsonl, and a rerun resumes
uv run --project pipeline python -I -m memchal.run --run test-R1 --split test --pack ledger:nemotron3 --ledger-model mlx --budget 24000 --extra 12000 --ledger-wait 900

# Rerun a few questions: --only takes ids or a JSON file listing them, and --redo asks again even after a usable answer
uv run --project pipeline python -I -m memchal.run --run test-R3 --split test --only <id> <id> --pack ledger:nemotron3 --ledger-model mlx --budget 24000 --extra 12000

# Second look at what a run abstained on
uv run --project pipeline python -I -m memchal.run --run test-R2 --split test --abstained-in test-R1 --pack ledger:nemotron3 --ledger-model mlx --budget 27000 --extra 15000

# Merge runs into predictions.jsonl and check the format
uv run --project pipeline python -I -m memchal.finalize --runs test-R1 test-R3 test-R2 --out predictions.jsonl
```

Measuring on dev, with no hosted model:

```sh
uv run --project pipeline python -I -m memchal.dev200                    # dev-large cut to 200 sessions per history
uv run --project pipeline python -I -m memchal.evalret --slice tune --config nemotron3   # retrieval only
uv run --project pipeline python -I -m memchal.score --run <run>         # score.py plus a local judge
```

`memchal.judge` settles what `score.py`'s phrase match leaves unjudged: LongMemEval's own judge prompts, on a local model.

## The application's data

Fusion reads `pipeline/runs/<run>/results.jsonl` and `pipeline/corpus/`, and asks live questions through `memchal.ask`. See `app/README.md`.

```sh
# The IETF tls list: downloads the public monthly mail files and index pages
uv run --project pipeline python -I -m memchal.archive

# US patents close to TLS: reads the PatentsView tables already in external/data/patents/raw/zenodo-15783125/
uv run --project pipeline python -I -m memchal.patents

# Embed each, then search them as one corpus without embedding anything twice
uv run --project pipeline python -I -m memchal.embed --model nemotron3 --split ietf-tls
uv run --project pipeline python -I -m memchal.embed --model nemotron3 --split patents
uv run --project pipeline python -I -m memchal.combine --corpora ietf-tls patents --out prior --list "US patents and the tls mailing list"

# One demo case, pipeline/cases/<case>.json, over the combined corpus
uv run --project pipeline python -I -m memchal.cases --case esni --corpus prior
uv run --project pipeline python -I -m memchal.precompute --split prior --pack ledger:nemotron3 --model mlx
uv run --project pipeline python -I -m memchal.run --run both-esni --split prior --history esni --pack ledger:nemotron3 --ledger-model mlx --budget 24000 --extra 12000 --style both --ledger-wait 900

# One live question
uv run --project pipeline python -I -m memchal.ask --corpus prior --cutoff 2018-07-02 --question "..."
```

Patents hold a title and an abstract only, and their date is the filing date. In a combined corpus, patents and emails take turns in the search results, so neither crowds the other out.

## Modules

| Module | Job |
|---|---|
| `retrieve.py` | Windows of turns, BM25, rank fusion |
| `embed.py` | Embeddings, cached per session |
| `hints.py` | The fact ledger and its quote check |
| `pack.py` | Ranked windows to dated passages under a character budget |
| `evidence.py` | What a question gets: gold sessions, plain retrieval, or the ledger |
| `reactor.py` | The organizers' client, our wording, the one-at-a-time lock |
| `run.py` | Resumable runs through Reactor |
| `cite.py` | Which sessions a prediction cites |
| `score.py`, `judge.py` | Scoring on dev |
| `finalize.py` | Merge runs, write and check `predictions.jsonl` |
| `archive.py`, `patents.py` | Build a corpus from the IETF archive or the patent tables |
| `combine.py`, `cases.py` | Search several corpora as one; a demo case as a history cut off at its date |
| `ask.py` | One live question, for the app |

## Data credit and license

The patent data is the United States Patent and Trademark Office's "Final release of PatentsView metadata, pre-grant and granted (12/31/2024)", Zenodo, doi:10.5281/zenodo.15783125, CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). We selected patents by CPC group and date, and squeezed whitespace in their text. USPTO says PatentsView data is provided for research purposes and isn't the official USPTO record.

The mailing list data is the public archive of the IETF tls list. The challenge's data and client belong to Reactive AI, and neither is in this archive.

Our code is under the MIT license, in `LICENSE`.
