"""Cross-encoder reranking of the top chunks, as sentence-transformers CrossEncoder models on MPS."""

import numpy as np

MODELS = {"qwenrr": "Qwen/Qwen3-Reranker-0.6B"}
BATCH = 16


def load(name):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(MODELS[name], device="mps")


def rerank(model, query, texts):
    return np.asarray(model.predict([(query, t) for t in texts], batch_size=BATCH, show_progress_bar=False), dtype=np.float64)


def apply(model, query, chunks, scores, top=40):
    """Chunk order with the top ``top`` chunks reordered by the reranker, the rest unchanged below them."""
    order = np.argsort(-scores, kind="stable")
    head = order[:top]
    reranked = rerank(model, query, [chunks[int(i)].text for i in head])
    return np.concatenate([head[np.argsort(-reranked, kind="stable")], order[top:]])
