"""Reactor: the organizers' client, our wording of the message, and the shared lock. Only this module calls Reactor."""

import fcntl
import importlib.util
import json
import secrets
import time
from contextlib import contextmanager

from .data import ROOT

_spec = importlib.util.spec_from_file_location("client", ROOT / "external/memory-challenge/reactor/client.py")
client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(client)

CREDS = json.loads((ROOT / "secret.json").read_text())
BASE, AGENT, KEY = CREDS["base_url"], CREDS["agent_id"], CREDS["access_key"]
LOCK = ROOT / "external/reactor.lock"
MAX_CHARS = 16000
TEMPLATE_ROOM = 1900

_CLIENT_ASK = "Answer from the evidence above and cite each passage you use by its label, e.g. [E1]."
_CLIENT_TAIL = "Anything you send before that line is an interim note, not the answer."

DIRECT = "Answer from the evidence above. Give one short, direct answer: no hedging, no list of alternatives."
NOTES = (
    "Work from the evidence above only. Before the answer, write brief notes: one line for each passage that bears on "
    "the question, saying what it states and its date. Then give the answer as one plain sentence that states every "
    "specific the evidence gives about it (names, places, amounts, dates), with no hedging.\n"
    "- A value that changed over time: the answer is the latest value as of the question date, even if the later "
    "passage only mentions it in passing. Passages stating the older value still count as support, so cite them too.\n"
    "- Counting or adding up: list every distinct item with its passage in the notes first, then give the total.\n"
    "- Dates and durations: use the dates in the passages and the question date, and work them out in the notes.\n"
    "- If the passages are about something similar but not the exact thing asked, the information is not there: "
    "answer INSUFFICIENT_EVIDENCE.")
PRIOR = (
    "Work from the evidence above only. These are messages from a public technical mailing list, each from before the "
    "question date. Before the answer, write brief notes: one line for each passage that bears on the question, saying "
    "what it states, who wrote it and its date. Then give the answer as one plain sentence: name the earliest passage "
    "that describes the thing asked, with its author and date, and say in a few words what it describes.\n"
    "- A passage counts only if it describes the exact thing asked. The same topic, or a similar but different idea, "
    "doesn't count.\n"
    "- If no passage describes it, answer INSUFFICIENT_EVIDENCE.")
BOTH = (
    "Work from the evidence above only. These are US patents and messages from a public technical mailing list, each "
    "from before the question date. Before the answer, write brief notes: one line for each passage that bears on the "
    "question, saying what it states, who wrote it or its patent number, and its date. Then go through your notes by date "
    "and give the answer as one plain sentence, starting \"In what we read,\": name the oldest passage that describes the "
    "thing asked, with its author or patent number and its date, and say in a few words what it describes. Cite every "
    "passage that describes it, patents and messages alike.\n"
    "- A passage counts only if it describes the exact thing asked. The same topic, or a similar but different idea, "
    "doesn't count.\n"
    "- If no passage describes it, answer INSUFFICIENT_EVIDENCE.")


def message(question, passages, ref, question_date, style="notes", hint=None):
    """The client's template with our instructions, labels on the final line, and any hint from local code."""
    text = client.build_message(question, passages, ref, client.parse_question_date(question_date))
    ask = {"direct": DIRECT, "notes": NOTES, "prior": PRIOR, "both": BOTH}[style]
    if hint:
        ask = f"{hint}\n{ask}"
    text = text.replace(_CLIENT_ASK, ask)
    return text.replace(
        _CLIENT_TAIL,
        f"End that line with the labels of the passages the answer rests on, e.g. "
        f"# FINAL ANSWER [ref:{ref}]: Tuesday [E2][E4]\n{_CLIENT_TAIL}")


def new_ref():
    return secrets.token_hex(4)


@contextmanager
def reactor_lock():
    """One caller at a time: the runs and the app's live questions take turns on our one agent."""
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


@contextmanager
def reactor_lock_now():
    """The same lock for a caller that can't wait: raises BlockingIOError if a run or another question holds it."""
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def new_history(tries=6):
    for n in range(tries):
        try:
            return client.new_history(BASE, AGENT, KEY, timeout=60)["history_id"]
        except (ConnectionRefusedError, OSError):
            if n == tries - 1:
                raise
            time.sleep(10 * (n + 1))


def ask(text, ref, history, timeout=600):
    """One question, with Kosti's suggested 600 s wait (Discord, 31 Oct 00:17): latency grows within a history.
    Returns the client's result with ``retries``; ``previous_pending`` backs off inside the client."""
    result, retries = client.ask_retrying(BASE, AGENT, KEY, text, timeout=timeout, ref=ref, history=history)
    result["retries"] = retries
    return result
