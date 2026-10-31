"""Dense embeddings for every chunk of a split, one cache per model, keyed by session so that shared sessions embed once.

A session id names the same content in every history, so chunks are cached per session id in one array:
external/cache/emb/<split>/<model>/{vectors.npy, offsets.json}. Vectors are normalized, so a dot product is a cosine.

Run: uv run --project pipeline python -I -m memchal.embed --model gemma300 --split dev200 --slice-histories 100
"""

import argparse
import gzip
import json
import random
import time

import numpy as np

from .data import CACHE, histories, named_slice, questions
from .retrieve import session_chunks

MODELS = {
    "gemma300": {"hf": "unsloth/embeddinggemma-300m", "kind": "st-prompts"},  # google's repo is gated, this mirror isn't
    "gemma2": {"hf": "google/embeddinggemma-2", "kind": "st-prompts",
               "config_kwargs": {"vision_config": None, "audio_config": None}},
    "nemotron1": {"hf": "nvidia/llama-nemotron-embed-1b-v2", "kind": "st-prompts"},
    "nemotron3": {"hf": "nvidia/Nemotron-3-Embed-1B-BF16", "kind": "st-prompts"},
    "qwen06": {"hf": "Qwen/Qwen3-Embedding-0.6B", "kind": "st-prompts", "left_pad": True},
}
BATCH = 32


def load_model(name):
    from sentence_transformers import SentenceTransformer
    import torch

    spec = MODELS[name]
    kwargs = {"device": "mps", "trust_remote_code": False,
              "model_kwargs": {"torch_dtype": torch.bfloat16, "attn_implementation": "sdpa"}}
    if spec.get("config_kwargs"):
        kwargs["config_kwargs"] = spec["config_kwargs"]
    if spec.get("left_pad"):
        kwargs["tokenizer_kwargs"] = {"padding_side": "left"}
    return SentenceTransformer(spec["hf"], **kwargs)


def encode_documents(model, texts):
    out = model.encode_document(texts, batch_size=BATCH, normalize_embeddings=True, convert_to_numpy=True,
                                show_progress_bar=False)
    return np.asarray(out, dtype=np.float32)


def encode_queries(model, texts):
    out = model.encode_query(texts, batch_size=BATCH, normalize_embeddings=True, convert_to_numpy=True,
                             show_progress_bar=False)
    return np.asarray(out, dtype=np.float32)


def cache_dir(split, name):
    return CACHE / "emb" / split / name


def history_ids_for(split, slice_name, n_histories):
    wanted = set(named_slice(slice_name)) if slice_name else None
    ids = sorted({q["history_id"] for q in questions(split) if wanted is None or q["question_id"] in wanted})
    if n_histories:
        random.Random(100).shuffle(ids)  # questions.jsonl is ordered by type: a prefix would miss whole types
        return ids[:n_histories]
    return ids


def build(name, split, ids):
    out = cache_dir(split, name)
    out.mkdir(parents=True, exist_ok=True)
    offsets = {}
    texts = []
    for history in histories(split, ids):
        for session in history["sessions"]:
            if session["session_id"] not in offsets:
                chunks = session_chunks(session)
                offsets[session["session_id"]] = [len(texts), len(chunks)]
                texts += [c.text for c in chunks]
    print(json.dumps({"model": name, "sessions": len(offsets), "chunks": len(texts)}), flush=True)
    model = load_model(name)
    # Longest first: batches of similar length waste less padding, and the speed estimate is pessimistic at the start.
    order = np.argsort([-len(t) for t in texts], kind="stable")
    dim = None
    vectors = None
    started = time.time()
    step = 2048
    for start in range(0, len(texts), step):
        batch = order[start: start + step]
        encoded = encode_documents(model, [texts[i] for i in batch])
        if vectors is None:
            dim = encoded.shape[1]
            vectors = np.lib.format.open_memmap(out / "vectors.npy", mode="w+", dtype=np.float32,
                                                shape=(len(texts), dim))
        vectors[batch] = encoded
        rate = (start + len(batch)) / (time.time() - started)
        print(json.dumps({"done": start + len(batch), "per_s": round(rate, 1)}), flush=True)
    vectors.flush()
    (out / "offsets.json").write_text(json.dumps(offsets))
    print(json.dumps({"model": name, "dim": dim, "seconds": round(time.time() - started)}), flush=True)


class Cached:
    """Chunk vectors of a model for one split, and query vectors when a pod made them."""

    def __init__(self, split, name):
        path = cache_dir(split, name)
        shared = path.parent
        self.vectors = np.load(path / "vectors.npy", mmap_mode="r")
        own = path / "offsets.json"
        self.offsets = json.loads((own if own.exists() else shared / "offsets.json").read_text())
        self.query_vectors = {}
        if (path / "qvectors.npy").exists():
            qids = json.loads((shared / "qids.json").read_text())
            self.query_vectors = dict(zip(qids, np.load(path / "qvectors.npy")))

    def for_history(self, history):
        parts = []
        for session in history["sessions"]:
            start, count = self.offsets[session["session_id"]]
            parts.append(np.asarray(self.vectors[start: start + count]))
        return np.concatenate(parts)


def prepare(split, ids):
    """Write what a dev-only GPU pod needs to embed a split: every unique session's chunks, and the questions."""
    out = CACHE / "emb" / split
    out.mkdir(parents=True, exist_ok=True)
    offsets, count = {}, 0
    with gzip.open(out / "texts.jsonl.gz", "wt", encoding="utf-8") as fh:
        for history in histories(split, ids):
            for session in history["sessions"]:
                if session["session_id"] not in offsets:
                    chunks = session_chunks(session)
                    offsets[session["session_id"]] = [count, len(chunks)]
                    count += len(chunks)
                    for c in chunks:
                        fh.write(json.dumps(c.text) + "\n")
    (out / "offsets.json").write_text(json.dumps(offsets))
    qs = [q for q in questions(split) if q["history_id"] in set(ids)]
    with gzip.open(out / "queries.jsonl.gz", "wt", encoding="utf-8") as fh:
        for q in qs:
            fh.write(json.dumps(q["question"]) + "\n")
    (out / "qids.json").write_text(json.dumps([q["question_id"] for q in qs]))
    print(json.dumps({"sessions": len(offsets), "chunks": count, "questions": len(qs)}), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=sorted(MODELS))
    ap.add_argument("--split", default="dev200")
    ap.add_argument("--slice", help="only histories of this question slice")
    ap.add_argument("--histories", type=int, help="only the first N of those histories")
    ap.add_argument("--prepare", action="store_true", help="write the texts for a pod instead of embedding here")
    args = ap.parse_args()
    ids = history_ids_for(args.split, args.slice, args.histories)
    if args.prepare:
        prepare(args.split, ids)
    else:
        build(args.model, args.split, ids)


if __name__ == "__main__":
    main()
