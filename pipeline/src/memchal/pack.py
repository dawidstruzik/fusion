"""Turn ranked chunks into evidence passages under a character budget: one dated passage per session, oldest first."""

from .retrieve import chunks_of

HEADER = 62  # "[E12] (source: s_xxxxxxxxxxxx, date: 2023/05/20 (Sat) 02:21) "
GAP = "[...]"
SHORT_TURN = 1200
MIN_NEIGHBOR = 240


def _add(spans, start, end):
    """Merge [start, end) into a sorted list of spans. Returns the characters newly covered."""
    before = sum(e - s for s, e in spans)
    merged = []
    for s, e in sorted(spans + [(start, end)]):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    spans[:] = merged
    return sum(e - s for s, e in spans) - before


def _cost_of_spans(spans_by_turn, session):
    cost = HEADER
    for t, spans in spans_by_turn.items():
        cost += len(session["turns"][t]["role"]) + 3 + sum(e - s + len(GAP) for s, e in spans)
    return cost


def _render(session, spans_by_turn):
    lines, previous = [], None
    for t in sorted(spans_by_turn):
        turn = session["turns"][t]
        if previous is not None and t != previous + 1:
            lines.append(GAP)
        parts = [turn["content"][s:e].strip() for s, e in spans_by_turn[t]]
        lead = GAP + " " if spans_by_turn[t][0][0] > 0 else ""
        tail = " " + GAP if spans_by_turn[t][-1][1] < len(turn["content"]) else ""
        lines.append(f"{turn['role']}: {lead}{f' {GAP} '.join(parts)}{tail}")
        previous = t
    return "\n".join(lines)


def _neighbor(session, t, spans_by_turn):
    """Keep a window readable: the user turn before an assistant window, the start of the reply after a user window."""
    turns = session["turns"]
    role = turns[t]["role"]
    other = t - 1 if role == "assistant" else t + 1
    if not 0 <= other < len(turns):
        return
    length = len(turns[other]["content"])
    wanted = (0, min(length, MIN_NEIGHBOR)) if role == "user" else (max(0, length - MIN_NEIGHBOR), length)
    _add(spans_by_turn.setdefault(other, []), *wanted)


def pack(history, order, budget, session_cap=0.45, chunks=None):
    """Passages for the chunks in rank order ``order``, until ``budget`` characters are used.

    A session stops growing at ``session_cap`` of the budget, so one long session can't crowd out the others that a
    multi-session question needs. Returns passages oldest first: {"id", "date", "text"}.
    """
    chunks = chunks if chunks is not None else chunks_of(history)
    sessions = history["sessions"]
    chosen = {}
    used = 0
    cap = budget * session_cap
    for index in order:
        c = chunks[int(index)]
        session = sessions[c.session]
        turn = session["turns"][c.turn]
        spans_by_turn = chosen.get(c.session, {})
        trial = {t: list(v) for t, v in spans_by_turn.items()}
        start, end = (0, len(turn["content"])) if len(turn["content"]) <= SHORT_TURN else (c.start, c.end)
        _add(trial.setdefault(c.turn, []), start, end)
        _neighbor(session, c.turn, trial)
        cost_new = _cost_of_spans(trial, session)
        cost_old = _cost_of_spans(spans_by_turn, session) if spans_by_turn else 0
        if cost_new > cap or used + cost_new - cost_old > budget:
            continue
        chosen[c.session] = trial
        used += cost_new - cost_old
    return [{"id": sessions[i]["session_id"], "date": sessions[i]["date"], "text": _render(sessions[i], chosen[i])}
            for i in sorted(chosen)]
