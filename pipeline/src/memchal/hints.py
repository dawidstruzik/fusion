"""The fact ledger: a local model reads a wide pack and lists quoted facts with their sources, for Reactor to check.

It never answers. Code keeps only the facts whose quote really is in the passage it names. The ledger then decides
which sessions reach Reactor first, and goes into Reactor's message as a checkable list. Runs on this Mac through
Ollama, so no challenge data leaves it.
"""

import json
import re
import time
import urllib.request

URL = "http://localhost:11434/api/chat"
POD_URL = "http://localhost:8801/v1/chat/completions"  # an SSH tunnel to the dev pod: dev data only (D15)
QWEN27 = "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M"
GEMMA4 = "gemma4:e4b-mlx"
QWEN27_MLX = "qwen3.8:27b-nvfp4"
QWEN27_POD = "pod:Qwen/Qwen3.8-27B"
CONTEXT = 24000
SOURCE = "the user's past chats"

PROMPT ="""You extract facts for another reader. You do not answer the question.

Question: {question}
Question date: {date}

Excerpts from {source}. Each has a label, the session's date, and who is speaking:
{excerpts}

List every statement in the excerpts that could help answer the question: each separate item if the question counts or adds things up, older and newer values if something changed, and things that look similar but may be different. Skip excerpts that have nothing to do with the question.

Return only JSON, in this shape:
{{"facts": [{{"label": "E3", "quote": "exact words copied from that excerpt, at most 25 words", "fact": "what it states, one short sentence", "when": "the date the event happened, worked out from the session date if the excerpt says something like last week, otherwise empty"}}]}}
If nothing bears on the question, return {{"facts": []}}."""


def _post(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(response.read())


def _chat(model, prompt, max_tokens=1600):
    """(text, prompt tokens, output tokens) from Ollama on this Mac, or from the dev pod for a "pod:" model."""
    messages = [{"role": "user", "content": prompt}]
    if model.startswith("pod:"):
        reply = _post(POD_URL, {"model": model[4:], "messages": messages, "temperature": 0, "max_tokens": max_tokens,
                                "chat_template_kwargs": {"enable_thinking": False}})
        usage = reply.get("usage", {})
        return reply["choices"][0]["message"]["content"], usage.get("prompt_tokens"), usage.get("completion_tokens")
    reply = _post(URL, {"model": model, "stream": False, "think": False, "format": "json", "messages": messages,
                        "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": CONTEXT}})
    return reply["message"]["content"], reply.get("prompt_eval_count"), reply.get("eval_count")


def _parse_facts(text):
    """The "facts" list from a model's reply, tolerating fences or a thinking block around the JSON."""
    start, end = text.find('{"facts"'), text.rfind("}")
    if start < 0:
        start = text.find("{")
    try:
        facts = json.loads(text[start: end + 1]).get("facts", [])
    except ValueError:
        return _finished_facts(text[start:])
    return facts if isinstance(facts, list) else []


def _finished_facts(text):
    """The facts completed before a reply was cut off at the token limit: often the questions with the most to quote."""
    decoder, facts = json.JSONDecoder(), []
    at = text.find("[") + 1
    while at > 0:
        at = text.find("{", at) + 1
        try:
            item, length = decoder.raw_decode(text[at - 1:])
        except ValueError:
            break
        facts.append(item)
        at += length - 1
    return facts


def _squash(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def _verified(items, passages):
    """Keep only the facts whose quote really is in the passage they name. Returns (facts, how many were dropped)."""
    facts, dropped = [], 0
    for item in items:
        if not isinstance(item, dict):
            continue
        match = re.search(r"\d+", str(item.get("label", "")))
        n = int(match.group()) if match else 0
        quote = str(item.get("quote", ""))
        if not 1 <= n <= len(passages) or not quote.strip() or _squash(quote) not in _squash(passages[n - 1]["text"]):
            dropped += 1
            continue
        facts.append({"id": passages[n - 1]["id"], "quote": quote.strip(), "fact": str(item.get("fact", "")).strip(),
                      "when": str(item.get("when", "")).strip()})
    return facts, dropped


def extract(question, question_date, passages, model=QWEN27, source=SOURCE):
    """Facts verified against ``passages``: {"id", "quote", "fact", "when"}, plus timing and what was dropped."""
    excerpts = "\n\n".join(f"[E{n}] (date: {p['date']})\n{p['text']}" for n, p in enumerate(passages, 1))
    started = time.time()
    text, tokens_in, tokens_out = _chat(model, PROMPT.format(question=question, date=question_date, source=source,
                                                             excerpts=excerpts))
    seconds = round(time.time() - started, 1)
    facts, dropped = _verified(_parse_facts(text), passages)
    return {"facts": facts, "dropped": dropped, "seconds": seconds, "model": model, "prompt_tokens": tokens_in,
            "output_tokens": tokens_out}


def hint_text(facts, passages):
    """The ledger as Reactor reads it, with labels of the final pack. Facts from sessions outside the pack are left out."""
    label = {p["id"]: f"E{n}" for n, p in enumerate(passages, 1)}
    lines = [f"- [{label[f['id']]}] \"{f['quote']}\"" + (f" (happened: {f['when']})" if f["when"] else "")
             for f in facts if f["id"] in label]
    if not lines:
        return None
    return ("A local tool pulled these quotes from the passages. It can miss things and misread them, so check each "
            "one against its passage:\n" + "\n".join(lines))
