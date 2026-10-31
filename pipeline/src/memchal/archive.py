"""One public IETF mailing list as a split the pipeline can read: one history, one session per message, oldest first.

A session's id is the message's public URL, so a citation opens in a browser. The archive names a message by the
urlsafe base64 of SHA-1(Message-ID + list name), as in make_hash in ietf-tools/mailarch. Its monthly index pages then
confirm that each URL really exists: a message missing from them is dropped, because it couldn't be cited.

The archive's mbox export needs a login, so the mail comes from the public monthly files. Everything under raw/ is
untrusted data, which is why this runs with -I.

Run: uv run --project pipeline python -I -m memchal.archive
"""

import base64
import hashlib
import json
import mailbox
import re
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from .data import DATA, ROOT, write_jsonl

LIST = "tls"
SPLIT = "ietf-tls"
CORPUS = ROOT / "pipeline/corpus" / SPLIT
FIRST, LAST = (2014, 1), (2018, 12)
ROLE = "user"
MAIL_URL = "https://www.ietf.org/ietf-ftp/ietf-mail-archive/{list}/{month}.mail"
INDEX_URL = "https://mailarchive.ietf.org/arch/browse/static/{list}/{month}/"
MESSAGE_URL = "https://mailarchive.ietf.org/arch/msg/{list}/{hash}/"
USER_AGENT = "hack-night-archive-builder"  # no contact details, on purpose
PAUSE = 1.0

FOOTER = re.compile(rf"^(_{{10,}}\s*\n)?\s*{LIST} mailing list\s*\n\s*{LIST}@ietf\.org\b.*\Z", re.I | re.M | re.S)
PGP_HEADER = re.compile(r"^-----BEGIN PGP SIGNED MESSAGE-----\n(\S+: .*\n)*\n?", re.M)
PGP_SIGNATURE = re.compile(r"^-----BEGIN PGP SIGNATURE-----.*?(^-----END PGP SIGNATURE-----\s*$|\Z)", re.M | re.S)
QUOTED = re.compile(r"^\s{0,4}(>|[A-Za-z]{1,6}>(\s|>|$)|\|\s|\]\s?\S)")
ATTRIBUTION = re.compile(r"(\b(wrote|writes)|<\S+@\S+>)\s*:\s*$|^Excerpts from ", re.I)
LEAD_IN = re.compile(r"\b(said|says|schrieb|escribió|écrit)\s*:\s*$", re.I)
OPENER = re.compile(r"^\s*(on|at|le|am|el)\s", re.I)
ORIGINAL = re.compile(r"^\s*([-‐_]+\s*original message\s*[-‐_]+|original message\s*$)", re.I)
HEADER_START = re.compile(r"^\s*\*?From:\*?\s")
HEADER_END = re.compile(r"^\s*\*?Subject:\*?\s")
HEADER_OTHER = re.compile(r"^\s*\*?(Sent|Date|To):\*?\s")
FORWARD = re.compile(r"forwarded message|begin forwarded|forwarded by", re.I)
DELIMITER = re.compile(r"^(- )?-- $")  # the standard one, with its trailing space
BARE_DELIMITER = re.compile(r"^--\s*$")
SHORT_SIGNATURE = re.compile(r"^--\s?\S.{0,40}$")
CLOSING_NAME = re.compile(r"^-[A-Z][\w.]*( [A-Z][\w.]*)?\s*$")  # "-Ekr" as the last line, not a bullet
BOILERPLATE = re.compile(r"^\s*(sent from (my|outlook|mail)\b.*|get outlook for .*|\[ charset .* converting\.\.\. \]\s*)$", re.I)
INVISIBLE = re.compile("[​‎‏﻿]")
ONLY_RULE = re.compile(r"^\s*[_\-=*~]+\s*$")


def _months(first, last):
    year, month = first
    while (year, month) <= last:
        yield f"{year}-{month:02d}"
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _fetch(url, path):
    """Download once: a file already on disk is kept, so a rerun only asks for what's missing."""
    if path.exists():
        return False
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    partial = path.with_suffix(".partial")
    partial.write_bytes(data)
    partial.rename(path)
    return True


def download(raw):
    raw.mkdir(parents=True, exist_ok=True)
    for month in _months(FIRST, LAST):
        for url, name in ((MAIL_URL, f"{month}.mail"), (INDEX_URL, f"index-{month}.html")):
            if _fetch(url.format(list=LIST, month=month), raw / name):
                print(f"fetched {name}", flush=True)
                time.sleep(PAUSE)


def archive_hash(message_id):
    digest = hashlib.sha1(message_id.encode("utf-8"))
    digest.update(LIST.encode("utf-8"))
    return base64.urlsafe_b64encode(digest.digest()).decode("ascii").rstrip("=")


def known_hashes(raw):
    pattern = re.compile(rf"/arch/msg/{LIST}/([A-Za-z0-9_-]+)/")
    return {h for path in raw.glob("index-*.html") for h in pattern.findall(path.read_text(encoding="utf-8", errors="replace"))}


def _header(value):
    """A header as readable text: encoded words decoded, whitespace squeezed, broken encodings tolerated."""
    if value is None:
        return ""
    try:
        text = str(make_header(decode_header(str(value))))
    except (LookupError, ValueError, UnicodeError):
        text = str(value)
    return re.sub(r"\s+", " ", text).strip()


def _author(message):
    name, address = parseaddr(_header(message["From"]))
    return name.strip(" \"'") or address.split("@")[0] or "unknown"


def _subject(message):
    return re.sub(rf"\[{LIST}\]\s*", "", _header(message["Subject"]), flags=re.I).strip() or "(no subject)"


def _parsed_date(value):
    try:
        date = parsedate_to_datetime(re.sub(r"\s+", " ", str(value)).strip())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)


def _date(message):
    """(UTC date, where it came from), chosen the way the archive does (get_date in mailarch), so that the date we
    give is the one the linked page shows: the server's latest Received header, then the Date header, then the
    envelope. A sender's wrong clock can't move a message in a question about what came first."""
    received = message.get_all("Received") or []
    date = _parsed_date(received[0].split(";")[-1]) if received else None
    if date is not None:
        return date, "Received"
    date = _parsed_date(message["Date"]) if message["Date"] else None
    if date is not None:
        return date, "Date"
    parts = (message.get_from() or "").split()
    try:
        return datetime.strptime(" ".join(parts[-5:]), "%a %b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc), "envelope"
    except ValueError:
        return None, None


class _HtmlText(HTMLParser):
    """Visible text of an HTML-only message, without what it quotes."""

    SKIP = {"script", "style", "head", "blockquote"}
    BREAK = {"p", "div", "br", "li", "tr", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        self.skipping += tag in self.SKIP
        if tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        self.skipping -= tag in self.SKIP and self.skipping > 0

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def _decoded(part):
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def body_of(message):
    """The message's own text parts: plain if there is any, otherwise its HTML as text. Attachments are left out."""
    plain, html = [], []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() == "text/plain":
            plain.append(_decoded(part))
        elif part.get_content_type() == "text/html":
            html.append(_decoded(part))
    if "".join(plain).strip():
        return "\n".join(plain)
    reader = _HtmlText()
    reader.feed("\n".join(html))
    return "".join(reader.parts)


def _cut_quoted_headers(lines):
    """Everything from an "Original Message" line or a From/Sent/To/Subject block on is the message being replied to.
    A forward stays: this list holds no other copy of it."""
    for i, line in enumerate(lines):
        if any(FORWARD.search(earlier) for earlier in lines[max(0, i - 3): i + 1]):
            continue
        if ORIGINAL.match(line):
            return lines[:i]
        if HEADER_START.match(line):
            block = lines[i + 1: i + 7]
            if any(HEADER_END.match(b) for b in block) and any(HEADER_OTHER.match(b) for b in block):
                return lines[:i]
    return lines


def _cut_quotes(lines):
    """Drop quoted lines and the "On ... wrote:" line that introduces them, keeping replies written between quotes."""
    quoted = {i for i, line in enumerate(lines) if QUOTED.match(line)}
    drop = set(quoted)
    for end, line in enumerate(lines):
        if end in quoted:
            continue
        after = next((i for i in range(end + 1, len(lines)) if lines[i].strip()), None)
        if not ATTRIBUTION.search(line) and not (LEAD_IN.search(line) and after in quoted):
            continue
        start = end
        for earlier in (end - 2, end - 1):
            if earlier >= 0 and OPENER.match(lines[earlier]) and all(x.strip() for x in lines[earlier: end]):
                start = earlier
                break
        drop.update(range(start, end + 1))
    return [line for i, line in enumerate(lines) if i not in drop]


def _cut_signature(lines):
    """A signature starts at a "-- " line, or a bare "--", if only a short block follows, or at a closing "-- Name".
    A delimiter right above a short line is one too, however much follows: top-posters' clients leave the message they
    replied to below it, unquoted."""
    for i, line in enumerate(lines):
        after = sum(1 for x in lines[i + 1:] if x.strip())
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        named = 0 < len(next_line) <= 40 and not next_line.startswith("--")
        if ((DELIMITER.match(line) and (after <= 40 or named)) or (BARE_DELIMITER.match(line) and (after <= 15 or named))
                or (SHORT_SIGNATURE.match(line) and after <= 2) or (CLOSING_NAME.match(line) and after == 0)):
            return lines[:i]
    return lines


def clean_body(text):
    """What the author wrote: no list footer, PGP armor, quoted text, signature or "Sent from my phone"."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = INVISIBLE.sub("", text)  # some phones lead lines with these, which hides them from the patterns below
    text = re.sub(r"^>From ", "From ", text, flags=re.M)  # mbox's escape of a line starting "From ", not a quote
    text = PGP_HEADER.sub("", FOOTER.sub("", text))
    text = PGP_SIGNATURE.sub("", text)
    lines = _cut_signature(_cut_quotes(_cut_quoted_headers(text.split("\n"))))
    lines = [line.rstrip() for line in lines if not BOILERPLATE.match(line)]
    while lines and (not lines[-1].strip() or ONLY_RULE.match(lines[-1])):
        lines.pop()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _message_id(message):
    return re.sub(r"\s+", " ", _header(message["Message-ID"])).strip().strip("<>")


def convert(raw):
    """(messages oldest first, counts of what was dropped by reason, counts of notable handling)."""
    known = known_hashes(raw)
    first, last = datetime(FIRST[0], FIRST[1], 1, tzinfo=timezone.utc), datetime(
        LAST[0] + (LAST[1] == 12), LAST[1] % 12 + 1, 1, tzinfo=timezone.utc)
    seen, dropped, notes, rows = set(), Counter(), Counter(), []
    for month in _months(FIRST, LAST):
        for message in mailbox.mbox(raw / f"{month}.mail", create=False):
            notes["read"] += 1
            message_id = _message_id(message)
            if not message_id:
                dropped["no Message-ID, so no URL can be derived"] += 1
                continue
            if message_id in seen:
                dropped["same Message-ID as an earlier message"] += 1
                continue
            seen.add(message_id)
            date, date_source = _date(message)
            if date is None:
                dropped["no usable date"] += 1
                continue
            if not first <= date < last:
                dropped["dated outside the range"] += 1
                continue
            digest = archive_hash(message_id)
            if digest not in known:
                dropped["URL not in the archive's monthly index"] += 1
                continue
            body = clean_body(body_of(message))
            if not body:
                dropped["nothing left after removing quotes and signature"] += 1
                continue
            notes[f"date from {date_source}"] += 1
            rows.append({"id": MESSAGE_URL.format(list=LIST, hash=digest), "date": date,
                         "from": _author(message), "subject": _subject(message), "body": body})
    rows.sort(key=lambda row: (row["date"], row["id"]))
    return rows, dropped, notes


def session_of(row):
    return {
        "session_id": row["id"],
        "date": row["date"].strftime("%Y/%m/%d (%a) %H:%M"),
        "turns": [{"turn_id": "t_" + hashlib.sha1(row["id"].encode()).hexdigest()[:12], "role": ROLE,
                   "content": f"From: {row['from']}\nSubject: {row['subject']}\n\n{row['body']}"}],
    }


def _iso(date):
    return date.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_corpus(rows):
    """The same messages for the app: one line per session, with the citation and the fields split out."""
    write_jsonl(CORPUS / "messages.jsonl", [{"id": r["id"], "url": r["id"], "date": _iso(r["date"]), "from": r["from"],
                                             "subject": r["subject"], "list": LIST, "body": r["body"]} for r in rows])
    summary = {"name": SPLIT, "list": LIST, "messages": len(rows), "first": _iso(rows[0]["date"]), "last": _iso(rows[-1]["date"])}
    (CORPUS / "corpus.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def manifest(sessions, dropped, notes, raw):
    fetched = sorted(p.stat().st_mtime for p in raw.iterdir())
    when = [datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") for t in (fetched[0], fetched[-1])]
    sizes = [len(s["turns"][0]["content"]) for s in sessions]
    lines = [
        f"# ietf-{LIST}: the IETF {LIST} mailing list",
        "",
        "Built by `pipeline/src/memchal/archive.py`. Rerun it to rebuild; files already in `raw/` aren't downloaded again.",
        "",
        f"- Source: {MAIL_URL.format(list=LIST, month='YYYY-MM')}, one public mbox file per month, no login.",
        f"- Citations checked against: {INDEX_URL.format(list=LIST, month='YYYY-MM')}",
        f"- Range asked for: {FIRST[0]}-{FIRST[1]:02d} through {LAST[0]}-{LAST[1]:02d}, by each message's UTC date.",
        f"- Date range in the data: {sessions[0]['date']} to {sessions[-1]['date']} UTC.",
        f"- Fetched: {when[0]} to {when[1]}.",
        f"- Messages read: {notes['read']}. Kept: {len(sessions)}. Dropped: {sum(dropped.values())}.",
        f"- Characters: {sum(sizes)} in total, median {int(statistics.median(sizes))} per message.",
        "",
        "## Dropped",
        "",
        *[f"- {count}: {reason}." for reason, count in dropped.most_common()],
        "",
        "## Format",
        "",
        f"`histories.jsonl` holds one history, `{SPLIT}`, with one session per message, oldest first. `session_id` is the",
        "message's URL on mailarchive.ietf.org: the urlsafe base64, without padding, of SHA-1(Message-ID + list name).",
        "`date` is in UTC and chosen as the archive chooses it, so that it matches the linked page: the latest Received",
        f"header ({notes['date from Received']} messages), then the Date header ({notes['date from Date']}), then the "
        f"envelope ({notes['date from envelope']}).",
        "",
        "Each session has one turn. Its content is `From: Name`, `Subject: ...`, a blank line and the body, with the",
        "`[TLS]` subject tag, list footer, PGP armor, quoted lines, reply attributions, signatures and attachments removed.",
        "Forwarded text stays, since it may be the only copy on this list. HTML-only messages are converted to text.",
        "",
        "`questions.jsonl` is empty on purpose, and `raw/` holds untrusted downloads: read them with `python -I`.",
    ]
    (DATA / SPLIT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    raw = DATA / SPLIT / "raw"
    download(raw)
    rows, dropped, notes = convert(raw)
    sessions = [session_of(row) for row in rows]
    write_jsonl(DATA / SPLIT / "histories.jsonl", [{"history_id": SPLIT, "sessions": sessions}])
    (DATA / SPLIT / "questions.jsonl").touch()
    write_corpus(rows)
    manifest(sessions, dropped, notes, raw)
    print(f"read {notes['read']}, kept {len(sessions)}, dropped {dict(dropped)}, notes {dict(notes)}")


if __name__ == "__main__":
    main()
