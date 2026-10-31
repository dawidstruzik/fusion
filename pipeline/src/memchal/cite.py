"""Which sessions a prediction cites. Reactor's labels come first; our code adds sessions that really support the answer.

Kosti, Discord, 30 Oct 23:25: "your code can select supporting sessions from the retrieved evidence: just make sure
they actually support Reactor's answer rather than blindly falling back to the top-ranked result."
"""

import re

RULES = ("reactor", "ledger", "reactor+ledger", "reactor-or-ledger")
DEFAULT = "reactor+ledger"  # best evidence F1 on dev: 0.920 against 0.904 for Reactor's labels alone (C2-wide, 24 questions)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("the a an of to in on for and or is was were it that this with at by from you your my i they he she we "
            "as be been are has had have about".split())


def _words(text):
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def _unique(ids):
    return list(dict.fromkeys(ids))


def ledger_sessions(row):
    in_pack = {p["id"] for p in row.get("passages") or []}
    return _unique(f["id"] for f in row.get("ledger") or [] if f["id"] in in_pack)


def supporting(row, answer):
    """Passages holding most of the answer's own words: the fallback when neither Reactor nor the ledger names one."""
    target = _words(re.sub(r"\[E\d+\]", " ", answer))
    if not target:
        return []
    scored = [(len(target & _words(p["text"])) / len(target), p["id"]) for p in row.get("passages") or []]
    best = max((s for s, _ in scored), default=0)
    return _unique(pid for s, pid in scored if s >= 0.6 and s == best)


def choose(row, rule=DEFAULT):
    """Session ids to cite for one answered row, under a rule we compare on dev."""
    reactor = _unique(row.get("cited") or [])
    ledger = ledger_sessions(row)
    if row.get("abstained"):
        return ledger  # evidence F1 counts on every answerable question, also when abstaining wrongly
    if rule == "reactor":
        chosen = reactor
    elif rule == "ledger":
        chosen = ledger or reactor
    elif rule == "reactor+ledger":
        chosen = _unique(reactor + ledger)
    elif rule == "reactor-or-ledger":
        chosen = reactor or ledger
    else:
        raise ValueError(rule)
    return chosen or supporting(row, row.get("answer") or "")
