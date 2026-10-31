// Turns saved Reactor runs into cases. The date check lives here, in code: a cited message
// only counts as prior art if it has a date and that date is before the cutoff.
import { Glob } from 'bun'
import type { Case, Evidence, Finding, Scope } from '../src/types.ts'

const pipelineDir = process.env.PIPELINE_DIR ?? new URL('../../pipeline', import.meta.url).pathname
const runsDir = `${pipelineDir}/runs`
const corpusDir = `${pipelineDir}/corpus`

// The case the app opens on, ahead of the others, whichever run of it is shown.
const DEMO_CASE = 'esni'

type Passage = { id: string; date?: string; text?: string }
type LedgerRow = { id?: string; quote?: string }
type ResultRow = {
  question_id: string
  question?: string
  status: string
  answer?: string
  abstained?: boolean
  cited?: string[]
  passages?: Passage[]
  ledger?: LedgerRow[] | null
  latency_s?: number
  at?: string
  reactor_history?: string
}
type MessageRow = {
  id: string
  kind?: 'email' | 'patent'
  url?: string
  date?: string
  granted?: string
  from?: string
  subject?: string
  list?: string
  body?: string
}
type CaseFile = {
  title: string
  claim: string
  cutoff: string
  corpus: string
  searched: { messages: number; first: string; last: string }
  elements: { question_id: string; element: string }[]
}

// test-* runs hold test data: agents and this app must never read them.
function assertReadable(run: string) {
  if (!/^[\w.-]+$/.test(run) || /^test/i.test(run)) throw new Error(`refusing to read run ${run}`)
}

async function readJsonl<T>(path: string): Promise<T[]> {
  const file = Bun.file(path)
  if (!(await file.exists())) return []
  const text = await file.text()
  return text
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as T)
}

async function readResults(run: string): Promise<Map<string, ResultRow>> {
  assertReadable(run)
  const rows = await readJsonl<ResultRow>(`${runsDir}/${run}/results.jsonl`)
  // One line per attempt: the last line for a question wins.
  return new Map(rows.map((row) => [row.question_id, row]))
}

export function isoDate(value: string | undefined): string | null {
  const match = value?.match(/^(\d{4})[-/](\d{2})[-/](\d{2})/)
  return match ? `${match[1]}-${match[2]}-${match[3]}` : null
}

// The ledger's own check ignores case and collapses whitespace, so this matches the same way.
function findLoose(text: string, quote: string): [number, number] | null {
  const starts: number[] = []
  let loose = ''
  for (let i = 0; i < text.length; i++) {
    const char = text.charAt(i)
    const isSpace = /\s/.test(char)
    if (isSpace && loose.endsWith(' ')) continue
    const lower = char.toLowerCase()
    starts.push(i)
    loose += isSpace ? ' ' : lower.length === 1 ? lower : char
  }
  const needle = quote.trim().replace(/\s+/g, ' ').toLowerCase()
  const at = needle ? loose.indexOf(needle) : -1
  if (at < 0) return null
  return [starts[at] as number, (starts[at + needle.length - 1] as number) + 1]
}

function marksFor(text: string, quotes: string[]): [number, number][] {
  return quotes
    .map((quote) => findLoose(text, quote))
    .filter((mark) => mark !== null)
    .sort((a, b) => a[0] - b[0])
}

function cleanAnswer(answer: string | undefined): string | null {
  if (!answer || answer.includes('INSUFFICIENT_EVIDENCE')) return null
  // Reactor's labels only make sense next to its evidence pack. Taking them out mustn't leave a
  // broken sentence: "is [E3], Eric's message" and a closing "with further such descriptions in
  // [E4][E7]", which the app's list of cited documents already shows.
  return answer
    .replace(/\bis (?:\[E\d+\])+,\s*/g, 'is ')
    .replace(/,?\s*\bwith further [^,.]*\bin\s*(?:\[E\d+\])+/g, '')
    .replace(/\s*\[E\d+\]/g, '')
    .replace(/\s*[–—]\s*/g, ', ')
    .trim()
}

type Source = { corpus: string; index: Map<string, MessageRow>; figures: Figures }

function toFinding(row: ResultRow, element: string, cutoff: string, source: Source): Finding {
  const { corpus, index, figures } = source
  const passages = new Map((row.passages ?? []).map((passage) => [passage.id, passage]))
  const cited = (row.cited ?? []).map((id): Evidence => {
    const passage = passages.get(id)
    const message = index.get(id)
    // Passage text is cut excerpts; the message card shows what the author wrote.
    const text = message?.body ?? passage?.text ?? ''
    const quotes = (row.ledger ?? []).filter((l) => l.id === id).map((l) => l.quote ?? '')
    const figure = figures[id]?.[0]
    return {
      id,
      kind: message?.kind ?? 'email',
      date: isoDate(message?.date) ?? isoDate(passage?.date),
      granted: isoDate(message?.granted),
      figure: figure ? `/api/figure?corpus=${encodeURIComponent(corpus)}&path=${encodeURIComponent(figure)}` : null,
      from: message?.from ?? null,
      subject: message?.subject ?? null,
      list: message?.list ?? null,
      url: message?.url ?? null,
      text,
      marks: marksFor(text, quotes),
    }
  })
  const countsAsPrior = (e: Evidence) => e.date !== null && e.date < cutoff
  const evidence = cited
    .filter(countsAsPrior)
    .sort((a, b) => (a.date as string).localeCompare(b.date as string))
  const rejected = cited.filter((e) => !countsAsPrior(e))
  const status =
    row.status !== 'answered' ? 'failed' : row.abstained || !evidence.length ? 'not_found' : 'found'
  return {
    id: row.question_id,
    element,
    question: row.question ?? element,
    status,
    answer: status === 'found' ? cleanAnswer(row.answer) : null,
    evidence,
    rejected,
    read: row.passages?.length ?? 0,
    readPatents: (row.passages ?? []).filter((passage) => index.get(passage.id)?.kind === 'patent').length,
    latencyS: row.latency_s ?? null,
    savedAt: row.at ?? null,
  }
}

// An element the run hasn't reached yet.
function waiting(id: string, element: string): Finding {
  return {
    id,
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

const indexes = new Map<string, { modified: number; rows: Map<string, MessageRow> }>()

async function readIndex(corpus: string): Promise<Map<string, MessageRow>> {
  const path = `${corpusDir}/${corpus}/messages.jsonl`
  const modified = Bun.file(path).lastModified
  const cached = indexes.get(corpus)
  if (cached?.modified === modified) return cached.rows
  const rows = await readJsonl<MessageRow>(path)
  const index = new Map(rows.map((row) => [row.id, row]))
  indexes.set(corpus, { modified, rows: index })
  return index
}

// Drawings for the patents a run cites, on disk, because the stage Wi-Fi can't be trusted.
type Figures = Record<string, string[]>

async function readFigures(corpus: string): Promise<Figures> {
  const file = Bun.file(`${corpusDir}/${corpus}/figures/figures.json`)
  return (await file.exists()) ? ((await file.json()) as Figures) : {}
}

async function readSource(corpus: string): Promise<Source> {
  return { corpus, index: await readIndex(corpus), figures: await readFigures(corpus) }
}

// Only a path figures.json lists can be served, so nothing else on disk is reachable.
export async function figureFile(corpus: string, path: string) {
  if (!/^[\w.-]+$/.test(corpus)) return null
  const listed = Object.values(await readFigures(corpus)).flat()
  if (!listed.includes(path)) return null
  const file = Bun.file(`${corpusDir}/${corpus}/figures/${path}`)
  return (await file.exists()) ? file : null
}

async function readList(corpus: string) {
  const file = Bun.file(`${corpusDir}/${corpus}/corpus.json`)
  return ((await file.json()) as { list: string }).list
}

async function readScope(file: CaseFile): Promise<Scope> {
  return { list: await readList(file.corpus), ...file.searched }
}

// A live answer, with the same date check as a saved one. With a cutoff, only messages
// before it are ranked, so the scope is counted from the index for that cutoff.
export async function toLiveAnswer(row: ResultRow, element: string, cutoff: string, corpus: string) {
  const source = await readSource(corpus)
  const dates = [...source.index.values()]
    .map((message) => isoDate(message.date))
    .filter((date) => date !== null && date < cutoff)
    .sort() as string[]
  const scope: Scope = {
    list: await readList(corpus),
    messages: dates.length,
    first: dates[0] ?? cutoff,
    last: dates.at(-1) ?? cutoff,
  }
  return {
    finding: { ...toFinding(row, element, cutoff, source), savedAt: null },
    history: row.reactor_history ?? null,
    scope,
  }
}

async function loadCaseRun(run: string): Promise<Case> {
  assertReadable(run)
  const file = (await Bun.file(`${runsDir}/${run}/case.json`).json()) as CaseFile
  const results = await readResults(run)
  const source = await readSource(file.corpus)
  const elements = file.elements.map(({ question_id, element }) => {
    const row = results.get(question_id)
    return row ? toFinding(row, element, file.cutoff, source) : waiting(question_id, element)
  })
  return {
    id: run,
    run,
    title: file.title,
    claim: file.claim,
    cutoff: file.cutoff,
    corpus: file.corpus,
    scope: await readScope(file),
    history: [...results.values()].at(-1)?.reactor_history ?? null,
    elements,
  }
}

export async function loadCases(): Promise<Case[]> {
  const runs: string[] = []
  for await (const path of new Glob('*/case.json').scan(runsDir)) {
    const run = path.split('/')[0]
    if (run && !/^test/i.test(run)) runs.push(run)
  }
  const loaded = await Promise.all(runs.sort().map(loadCaseRun))
  const name = (c: Case) => (c.run as string).replace(/^(both|prior)-/, '')
  // A patents-and-emails run replaces the emails-only run of the same case once Reactor has answered
  // every element. Until then, or if it never does, the emails-only run stays the demo.
  const finished = (c: Case) => c.elements.every((f) => f.status === 'found' || f.status === 'not_found')
  const isBoth = (c: Case) => (c.run as string).startsWith('both-')
  const replaced = new Set(loaded.filter((c) => isBoth(c) && finished(c)).map(name))
  const shown = loaded.filter((c) => (isBoth(c) ? finished(c) : !replaced.has(name(c))))
  return shown.sort((a, b) => Number(name(b) === DEMO_CASE) - Number(name(a) === DEMO_CASE))
}
