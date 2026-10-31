// Shared with the server through `import type` only, so nothing from server/ reaches the bundle.

export type Evidence = {
  id: string
  kind: 'email' | 'patent'
  date: string | null // for a patent, the filing date
  granted: string | null
  figure: string | null // a local URL for a patent's first drawing
  // A patent's `from` is its number, `subject` its title, `text` its abstract.
  from: string | null
  subject: string | null
  list: string | null
  url: string | null
  text: string
  marks: [number, number][]
}

export type Status = 'found' | 'not_found' | 'failed' | 'ready' | 'queued' | 'running'

export type Finding = {
  id: string
  element: string
  question: string
  status: Status
  answer: string | null
  evidence: Evidence[] // cited, dated before the cutoff, earliest first
  rejected: Evidence[] // cited, but dated on or after the cutoff, or undated
  read: number // passages Reactor read for this question
  readPatents: number // how many of those are patents
  latencyS: number | null
  savedAt: string | null // null means it was asked live in this sitting
  startedAt?: number
  followUp?: boolean // asked in the case, but not an element of the claim
  error?: string
}

// What was ranked for this case's cutoff, not the whole corpus.
export type Scope = {
  list: string
  messages: number
  first: string
  last: string
}

export type Case = {
  id: string
  run: string | null
  title: string
  claim: string
  cutoff: string
  corpus: string
  scope: Scope | null
  history: string | null
  elements: Finding[]
}
