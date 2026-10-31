import { useEffect, useMemo, useRef, useState } from 'react'
import {
  beforeYourDate,
  claimChart,
  displayName,
  filedAndGranted,
  kindWord,
  longDate,
  scopeSentence,
  splitIdea,
} from './lib'
import type { Case, Evidence, Finding, Scope } from './types'

// hack-main's figure for a live question: embedder load, ledger and Reactor, 2 to 3 minutes.
const SECONDS_PER_QUESTION = 150
const REFRESH_MS = 15_000

type Draft = { text: string; cutoff: string }

// Every date a case's cited documents carry, earliest first.
function citedDates(c: Case) {
  const dates = c.elements.flatMap((finding) => finding.evidence.map((e) => e.date))
  return dates.filter((date) => date !== null).sort()
}

// A hash route, so the browser's back button works: `#/` is home, `#/idea/<id>` one idea.
function routeCase() {
  const match = location.hash.match(/^#\/idea\/(.+)$/)
  return match ? decodeURIComponent(match[1] as string) : null
}

function ideaHref(id: string) {
  return `#/idea/${encodeURIComponent(id)}`
}

// Fresh saved cases, keeping what only this page has: follow-ups and live cases.
function mergeSaved(fresh: Case[], old: Case[]) {
  const withFollowUps = fresh.map((c) => {
    const followUps = old.find((o) => o.id === c.id)?.elements.filter((f) => f.followUp) ?? []
    return { ...c, elements: [...c.elements, ...followUps] }
  })
  return [...withFollowUps, ...old.filter((c) => c.run === null)]
}

// Open a case on the first answer that shows the record's own words.
function openingFinding(c: Case | null) {
  return c?.elements.find((f) => f.evidence[0]?.marks.length) ?? c?.elements[0] ?? null
}

function pending(element: string): Finding {
  return {
    id: crypto.randomUUID(),
    element,
    question: element,
    status: 'queued',
    answer: null,
    evidence: [],
    rejected: [],
    read: 0,
    readPatents: 0,
    latencyS: null,
    savedAt: null,
  }
}

export default function App() {
  const [cases, setCases] = useState<Case[] | null>(null)
  const [live, setLive] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [caseId, setCaseId] = useState(routeCase)
  const [findingId, setFindingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft>({ text: '', cutoff: '' })

  useEffect(() => {
    fetch('/api/cases')
      .then(async (res) => {
        const body = await res.json()
        if (!res.ok) throw new Error(body.error)
        setCases(body.cases)
        setLive(body.live)
      })
      .catch((error: Error) => setLoadError(error.message))
  }, [])

  useEffect(() => {
    const follow = () => setCaseId(routeCase())
    window.addEventListener('hashchange', follow)
    return () => window.removeEventListener('hashchange', follow)
  }, [])

  // A run is still answering: pick up each answer as it lands.
  const runActive = !!cases?.some((c) => c.run && c.elements.some((f) => f.status === 'queued' && !f.followUp))
  useEffect(() => {
    if (!runActive) return
    const timer = setInterval(async () => {
      const res = await fetch('/api/cases').catch(() => null)
      if (!res?.ok) return
      const { cases: fresh } = (await res.json()) as { cases: Case[] }
      setCases((old) => mergeSaved(fresh, old ?? []))
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [runActive])

  const current = cases?.find((c) => c.id === caseId) ?? null
  const finding = current?.elements.find((f) => f.id === findingId) ?? openingFinding(current)
  const running = !!cases?.some((c) => c.elements.some((f) => f.status === 'running' || f.status === 'queued'))
  const parts = useMemo(() => splitIdea(draft.text), [draft.text])

  function patchCase(id: string, patch: (c: Case) => Case) {
    setCases((all) => all?.map((c) => (c.id === id ? patch(c) : c)) ?? all)
  }

  function patchFinding(id: string, fid: string, next: Partial<Finding>) {
    patchCase(id, (c) => ({
      ...c,
      elements: c.elements.map((f) => (f.id === fid ? { ...f, ...next } : f)),
    }))
  }

  // One question at a time, in the case's history. Returns the history for the next question,
  // or null if the question didn't run.
  async function runFinding(c: Pick<Case, 'id' | 'cutoff' | 'corpus'>, target: Finding, history: string | null) {
    patchFinding(c.id, target.id, { status: 'running', startedAt: Date.now() })
    const res = await fetch('/api/ask', {
      method: 'POST',
      body: JSON.stringify({
        question: target.question,
        element: target.element,
        cutoff: c.cutoff,
        corpus: c.corpus,
        history,
      }),
    }).catch(() => null)
    const body = res
      ? ((await res.json()) as { error?: string; finding: Finding; history: string | null; scope: Scope })
      : { error: "The API server didn't answer." }
    if (!res?.ok || !('finding' in body)) {
      patchFinding(c.id, target.id, { status: 'failed', error: body.error })
      return null
    }
    patchFinding(c.id, target.id, { ...body.finding, id: target.id })
    patchCase(c.id, (old) => ({ ...old, scope: body.scope, history: body.history }))
    return body.history ?? ''
  }

  async function runIdea() {
    const id = crypto.randomUUID()
    const elements = parts.map((part) => ({ ...pending(part), question: `Did anyone describe this: ${part}?` }))
    const fresh: Case = {
      id,
      run: null,
      title: `Your idea, ${elements.length} parts`,
      claim: draft.text,
      cutoff: draft.cutoff,
      corpus: cases?.[0]?.corpus ?? 'ietf-tls',
      scope: null,
      history: null,
      elements,
    }
    setCases((all) => [...(all ?? []), fresh])
    setFindingId(elements[0]?.id ?? null)
    setDraft({ text: '', cutoff: '' })
    location.hash = ideaHref(id)
    let history: string | null = ''
    for (const element of elements) {
      if (history === null) {
        patchFinding(id, element.id, { status: 'failed', error: 'An earlier part stopped this run.' })
        continue
      }
      history = await runFinding(fresh, element, history || null)
    }
  }

  async function followUp(question: string) {
    if (!current) return
    const next = { ...pending(question), followUp: true }
    patchCase(current.id, (c) => ({ ...c, elements: [...c.elements, next] }))
    setFindingId(next.id)
    await runFinding(current, next, current.history)
  }

  if (loadError) return <p className="fatal">{loadError} Restart the API server and reload.</p>
  if (!cases) return <p className="fatal">Reading saved answers.</p>

  if (!current || !finding) {
    return (
      <Home
        cases={cases}
        draft={draft}
        parts={parts}
        live={live}
        busy={running}
        onDraft={(next) => setDraft((d) => ({ ...d, ...next }))}
        onRun={runIdea}
      />
    )
  }

  return (
    <div className="shell">
      <aside className="rail">
        <div className="rail-top">
          <a className="name" href="#/">
            Fusion
          </a>
          <a className="light-button" href="#/">
            New idea
          </a>
        </div>

        <div className="idea">
          <h1 className="idea-title">{current.title}</h1>
          <p className="idea-text">{current.claim}</p>
          <p className="cutoff">Before {longDate(current.cutoff)}</p>
        </div>

        <CaseRail c={current} selected={finding.id} onSelect={setFindingId} />
      </aside>

      <main className="desk">
        <FindingView key={finding.id} c={current} finding={finding} live={live} busy={running} onAsk={followUp} />
      </main>
    </div>
  )
}

function Home(props: {
  cases: Case[]
  draft: Draft
  parts: string[]
  live: boolean
  busy: boolean
  onDraft: (next: Partial<Draft>) => void
  onRun: () => void
}) {
  const { cases, draft, parts, live, busy, onDraft, onRun } = props
  const [tried, setTried] = useState(false)
  const minutes = Math.ceil((parts.length * SECONDS_PER_QUESTION) / 60)

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!live) setTried(true)
    else if (!busy && parts.length && draft.cutoff) onRun()
  }

  const note = tried
    ? 'Live search is off for this demo. Open a previous search below.'
    : live && parts.length
      ? `${parts.length} ${parts.length === 1 ? 'part' : 'parts'}, about ${minutes} minutes.`
      : null

  return (
    <div className="home">
      <span className="name home-name">Fusion</span>
      <main className="home-column">
        <h1 className="home-title">Did anyone think of it first?</h1>
        <form className="home-box" onSubmit={submit}>
          <textarea
            aria-label="Describe your idea"
            placeholder="Describe your idea"
            value={draft.text}
            onChange={(event) => onDraft({ text: event.target.value })}
          />
          <div className="home-row">
            <label className="home-date">
              Before
              <input
                type="date"
                value={draft.cutoff}
                onChange={(event) => onDraft({ cutoff: event.target.value })}
              />
            </label>
            <button type="submit" className="home-go" disabled={live && (busy || !parts.length || !draft.cutoff)}>
              {busy ? 'Reactor is busy' : 'Search'}
            </button>
          </div>
        </form>
        {note ? (
          <p className="home-note" role={tried ? 'status' : undefined}>
            {note}
          </p>
        ) : null}
        {cases.length ? (
          <section>
            <h2 className="saved-heading">Previous searches</h2>
            <ul className="saved-list">
              {cases.map((c) => {
                const earliest = citedDates(c)[0]
                return (
                  <li key={c.id}>
                    <a className="saved" href={ideaHref(c.id)}>
                      <span className="saved-title">{c.title.split(',')[0]}</span>
                      <span className="saved-date">
                        {earliest ? `Earliest cited ${earliest.slice(0, 4)}` : 'Nothing cited'}
                      </span>
                    </a>
                  </li>
                )
              })}
            </ul>
          </section>
        ) : null}
      </main>
    </div>
  )
}

function CaseRail(props: { c: Case; selected: string | null; onSelect: (id: string) => void }) {
  const { c, selected, onSelect } = props
  const [copied, setCopied] = useState(false)
  const parts = c.elements.filter((f) => !f.followUp)
  const found = parts.filter((f) => f.status === 'found').length

  function move(event: React.KeyboardEvent<HTMLUListElement>) {
    const step = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    event.preventDefault()
    const at = c.elements.findIndex((f) => f.id === selected)
    const next = c.elements[Math.min(c.elements.length - 1, Math.max(0, at + step))]
    if (!next) return
    onSelect(next.id)
    event.currentTarget.querySelector<HTMLButtonElement>(`[data-id="${next.id}"]`)?.focus()
  }

  async function copy() {
    await navigator.clipboard.writeText(claimChart(c))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <p className="tally">
        Documents found for {found} of {parts.length} parts.
      </p>
      <ul className="elements" onKeyDown={move}>
        {c.elements.map((f) => (
          <li key={f.id}>
            <button
              type="button"
              data-id={f.id}
              className="element"
              aria-current={f.id === selected}
              onClick={() => onSelect(f.id)}
            >
              <span className="element-text">{f.element}</span>
              <RailStatus finding={f} />
            </button>
          </li>
        ))}
      </ul>

      <div className="rail-foot">
        <button type="button" className="light-button" onClick={copy}>
          {copied ? 'Copied' : 'Copy claim chart'}
        </button>
      </div>
    </>
  )
}

function useSeconds(since: number | undefined) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!since) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [since])
  return since ? Math.max(0, Math.round((now - since) / 1000)) : 0
}

function RailStatus({ finding }: { finding: Finding }) {
  const seconds = useSeconds(finding.status === 'running' ? finding.startedAt : undefined)
  const earliest = finding.evidence[0]
  if (finding.status === 'found' && earliest?.date) {
    return (
      <span className="element-date">
        {longDate(earliest.date)}
        <span className="element-kind">, {earliest.kind === 'patent' ? 'patent' : 'email'}</span>
      </span>
    )
  }
  if (finding.status === 'running') return <span className="element-none">Reading, {seconds} s</span>
  if (finding.status === 'queued') return <span className="element-none">Waiting</span>
  if (finding.status === 'failed') return <span className="element-none">Reactor didn't answer</span>
  if (finding.status === 'not_found') return <span className="element-none">Not found</span>
  return null
}

function FindingView(props: {
  c: Case
  finding: Finding
  live: boolean
  busy: boolean
  onAsk: (question: string) => void
}) {
  const { c, finding, live, busy, onAsk } = props
  const [shownId, setShownId] = useState(finding.evidence[0]?.id ?? null)
  const shown = finding.evidence.find((e) => e.id === shownId) ?? finding.evidence[0]

  return (
    <div className="finding">
      <h2 className="element-title">{finding.element}</h2>

      {finding.status === 'found' && shown ? (
        <>
          {finding.answer ? <p className="answer">{finding.answer}</p> : null}
          <Provenance finding={finding} />
          <p className="provenance">{scopeSentence(c, finding)}</p>
          <Sheet
            key={shown.id}
            evidence={shown}
            cutoff={c.cutoff}
            earliest={shown.id === finding.evidence[0]?.id}
          />
          <Results evidence={finding.evidence} shownId={shown.id} onShow={setShownId} />
        </>
      ) : finding.status === 'running' || finding.status === 'queued' ? (
        <Waiting finding={finding} />
      ) : (
        <NotFound c={c} finding={finding} />
      )}

      {live ? <FollowUp busy={busy} onAsk={onAsk} /> : null}
    </div>
  )
}

function Provenance({ finding }: { finding: Finding }) {
  if (finding.latencyS === null) return null
  const seconds = Math.round(finding.latencyS)
  return (
    <p className="provenance">
      Written by Reactor in {seconds} s. {finding.savedAt ? 'This is a saved answer.' : 'Asked live.'}
    </p>
  )
}

function Results(props: { evidence: Evidence[]; shownId: string; onShow: (id: string) => void }) {
  const { evidence, shownId, onShow } = props
  if (evidence.length < 2) return null
  return (
    <div className="results">
      <p className="results-note">Reactor cited {evidence.length} documents, in date order.</p>
      <ol>
        {evidence.map((e) => (
          <li key={e.id}>
            <button type="button" className="result" aria-current={e.id === shownId} onClick={() => onShow(e.id)}>
              <span className="result-date">{e.date ? longDate(e.date) : 'No date'}</span>
              <span>{kindWord(e)}</span>
              <span className="result-clip">{displayName(e.from)}</span>
              <span className="result-clip">{e.subject}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}

function Waiting({ finding }: { finding: Finding }) {
  const seconds = useSeconds(finding.status === 'running' ? finding.startedAt : undefined)
  return (
    <div className="none">
      <p className="none-line">{finding.status === 'running' ? 'Reactor is reading.' : 'Waiting its turn.'}</p>
      <p className="none-scope">
        {finding.status === 'running'
          ? `${seconds} s so far. A live question takes 2 to 3 minutes.`
          : 'Reactor answers one part at a time, in order.'}
      </p>
    </div>
  )
}

function Sheet(props: { evidence: Evidence; cutoff: string; earliest: boolean }) {
  const { evidence, cutoff, earliest } = props
  const firstMark = useRef<HTMLElement>(null)
  const body = useRef<HTMLDivElement>(null)

  // Scroll to the marked words on a whole line, so the first visible line is never cut in half.
  useEffect(() => {
    const mark = firstMark.current
    const box = body.current
    if (!mark || !box) return
    const line = parseFloat(getComputedStyle(box).lineHeight)
    box.scrollTop = Math.round((mark.offsetTop - box.clientHeight / 3) / line) * line
  }, [])

  const from = displayName(evidence.from)
  const date = evidence.date as string
  const gap = beforeYourDate(date, cutoff)
  const patent = evidence.kind === 'patent'
  const lead = [patent ? 'Filed.' : '', earliest ? 'Earliest cited.' : ''].filter(Boolean).join(' ')

  return (
    <article className={patent ? 'sheet sheet-patent' : 'sheet'}>
      <div className={patent ? 'sticker sticker-patent' : 'sticker'}>
        <strong>{longDate(date)}</strong>
        {lead ? <span>{lead}</span> : null}
        <span>{gap}.</span>
      </div>
      {patent ? (
        <div className="patent-head">
          <div className="patent-number">{from}</div>
          <div className="patent-title">{evidence.subject}</div>
          <div className="patent-filed">{filedAndGranted(evidence)}</div>
        </div>
      ) : (
        <div className="headers">
          {from ? <div>From: {from}</div> : null}
          {evidence.subject ? <div>Subject: {evidence.subject}</div> : null}
          {evidence.list ? <div>List: {evidence.list}</div> : null}
        </div>
      )}
      <div className="body" tabIndex={0} ref={body}>
        <MarkedText text={evidence.text} marks={evidence.marks} firstMark={firstMark} />
      </div>
      <div className="source">
        {evidence.url ? (
          <a href={evidence.url} target="_blank" rel="noreferrer">
            {evidence.url.replace(/^https?:\/\//, '')}
          </a>
        ) : (
          <span>No public link.</span>
        )}
        {evidence.figure ? (
          <a href={evidence.figure} target="_blank" rel="noreferrer">
            Patent drawing
          </a>
        ) : null}
      </div>
    </article>
  )
}

function MarkedText(props: {
  text: string
  marks: [number, number][]
  firstMark: React.RefObject<HTMLElement | null>
}) {
  const { text, marks, firstMark } = props
  const parts: React.ReactNode[] = []
  let at = 0
  marks.forEach(([from, to], index) => {
    if (from < at) return
    parts.push(text.slice(at, from))
    parts.push(
      <mark key={from} ref={index === 0 ? firstMark : undefined}>
        {text.slice(from, to)}
      </mark>,
    )
    at = to
  })
  parts.push(text.slice(at))
  return <>{parts}</>
}

function NotFound({ c, finding }: { c: Case; finding: Finding }) {
  if (finding.status === 'failed') {
    return (
      <div className="none">
        <p className="none-line">Reactor didn't answer this one.</p>
        <p className="none-scope">{finding.error ?? 'Nothing is claimed either way.'}</p>
      </div>
    )
  }
  const late = finding.rejected.find((e) => e.date)
  const undated = finding.rejected.some((e) => !e.date)
  return (
    <div className="none">
      <p className="none-line">Not found in what we searched.</p>
      <p className="none-scope">{scopeSentence(c, finding)}</p>
      {late?.date ? (
        <p className="none-scope">
          Reactor cited a document from {longDate(late.date)}, which isn't before your date, so it
          doesn't count.
        </p>
      ) : null}
      {undated ? (
        <p className="none-scope">Reactor cited a document with no date, so it can't count as prior art.</p>
      ) : null}
    </div>
  )
}

function FollowUp({ busy, onAsk }: { busy: boolean; onAsk: (question: string) => void }) {
  const [text, setText] = useState('')

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!text.trim() || busy) return
    onAsk(text.trim())
    setText('')
  }

  return (
    <form className="follow-up" onSubmit={submit}>
      <input
        aria-label="Follow-up question"
        placeholder="Ask a follow-up about this idea"
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <button type="submit" className="action" disabled={busy}>
        {busy ? 'Reactor is busy' : 'Ask Reactor'}
      </button>
    </form>
  )
}
