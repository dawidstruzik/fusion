"""A local judge for answers score.py's phrase match can't decide, on dev only: no gold exists for test.

The prompts are LongMemEval's own judge prompts, per question type. The model runs on this Mac through Ollama, so
no challenge data leaves it. Verdicts are cached in external/cache/judge.jsonl by question, gold answer and answer.
"""

import hashlib
import json
import urllib.request

from .data import CACHE

MODEL = "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M"
URL = "http://localhost:11434/api/chat"
CACHE_FILE = CACHE / "judge.jsonl"

_BASE = ("I will give you a question, a correct answer, and a response from a model. Please answer yes if the response "
         "contains the correct answer. Otherwise, answer no. ")
_STEPS = ("If the response is equivalent to the correct answer or contains all the intermediate steps to get the "
          "correct answer, you should also answer yes. If the response only contains a subset of the information "
          "required by the answer, answer no. ")
_TEMPORAL = ("In addition, do not penalize off-by-one errors for the number of days. If the question asks for the "
             "number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when "
             "the answer is 18), the model's response is still correct. ")
_UPDATE = ("If the response contains some previous information along with an updated answer, the response should be "
           "considered as correct as long as the updated answer is the required answer.")
_TAIL = "\n\nQuestion: {question}\n\nCorrect Answer: {answer}\n\nModel Response: {response}\n\nIs the model response correct? Answer yes or no only."
TEMPLATES = {
    "single-session-user": _BASE + _STEPS + _TAIL,
    "single-session-assistant": _BASE + _STEPS + _TAIL,
    "multi-session": _BASE + _STEPS + _TAIL,
    "temporal-reasoning": _BASE + _STEPS + _TEMPORAL + _TAIL,
    "knowledge-update": _BASE + _UPDATE + _TAIL,
}


def _ask(prompt):
    body = json.dumps({"model": MODEL, "stream": False, "think": False, "options": {"temperature": 0, "num_predict": 8},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    request = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())["message"]["content"].strip()


def _load_cache():
    if not CACHE_FILE.exists():
        return {}
    with open(CACHE_FILE, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return {row["key"]: row["correct"] for row in rows}


_cache = None


def judge(question, gold_answer, question_type, response):
    """True when the local model accepts the response as correct."""
    global _cache
    if _cache is None:
        _cache = _load_cache()
    key = hashlib.sha1(json.dumps([question, gold_answer, response]).encode()).hexdigest()
    if key not in _cache:
        reply = _ask(TEMPLATES[question_type].format(question=question, answer=gold_answer, response=response))
        _cache[key] = reply.lower().lstrip("* \n").startswith("yes")
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "correct": _cache[key], "reply": reply[:40]}) + "\n")
    return _cache[key]
