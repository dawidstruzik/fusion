"""Send public text to Reactor verbatim, in its own new history, between runs. Never challenge data.

Reads a JSON list of messages and saves the client's raw reply for each. Waits its turn on the Reactor lock.

Run: uv run --project pipeline python -I -m memchal.ask_public --run use-case-reactor --messages FILE.json
"""

import argparse
import json

from . import reactor
from .data import RUNS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--messages", required=True)
    args = ap.parse_args()
    with open(args.messages, encoding="utf-8") as fh:
        messages = json.load(fh)
    out_dir = RUNS / args.run
    out_dir.mkdir(parents=True, exist_ok=True)
    with reactor.reactor_lock(), open(out_dir / "results.jsonl", "a", encoding="utf-8") as out:
        history = reactor.new_history()
        for text in messages:
            result, retries = reactor.client.ask_retrying(reactor.BASE, reactor.AGENT, reactor.KEY, text, timeout=600,
                                                          ref=None, history=history)
            row = {"status": "reply", "history_id": history, "text": text, **result, "retries": retries}
            out.write(json.dumps(row) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
