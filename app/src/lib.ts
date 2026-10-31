import type { Case, Evidence, Finding } from './types'

function utc(date: string) {
  return new Date(`${date}T00:00:00Z`)
}

export function longDate(date: string) {
  return utc(date).toLocaleDateString('en-US', { dateStyle: 'long', timeZone: 'UTC' })
}

export function today() {
  return new Date().toISOString().slice(0, 10)
}

function plural(count: number, word: string) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

export function beforeYourDate(date: string, cutoff: string) {
  const a = utc(date)
  const b = utc(cutoff)
  let months = (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + b.getUTCMonth() - a.getUTCMonth()
  if (b.getUTCDate() < a.getUTCDate()) months -= 1
  if (months >= 1) {
    const years = Math.floor(months / 12)
    const rest = months % 12
    const parts = [years ? plural(years, 'year') : '', rest ? plural(rest, 'month') : '']
    return `${parts.filter(Boolean).join(', ')} before your date`
  }
  return `${plural(Math.round((+b - +a) / 86_400_000), 'day')} before your date`
}

// The parts of an idea. A claim marks its own with a colon after the preamble and semicolons
// between steps; prose has sentences. A preamble that ends in "comprising" has nothing to search.
export function splitIdea(idea: string) {
  return idea
    .replace(/^\s*Modeled on \S+\.\s+/i, '')
    .replace(/^\s*\d+\.\s*/, '')
    .split(/;|:\s|\n+|(?<=[.!?])\s+/)
    .map((part) => part.trim().replace(/^and\s+/i, '').replace(/[.,]$/, '').trim())
    .filter((part) => part && !/\b(comprising|including|consisting of)$/i.test(part))
}

export function kindWord(e: Evidence) {
  return e.kind === 'patent' ? 'Patent, filed' : 'Email'
}

export function filedAndGranted(e: Evidence) {
  if (!e.date) return null
  return e.granted ? `Filed ${longDate(e.date)}, granted ${longDate(e.granted)}` : `Filed ${longDate(e.date)}`
}

export function displayName(from: string | null) {
  return from?.replace(/\s*<[^>]*>/, '').replace(/@\S+/, '').replace(/^"|"$/g, '') ?? null
}

// A list name with a space already reads as a source, such as "US patents and the tls mailing list".
export function sourceName(list: string) {
  return /\s/.test(list) ? list : `the ${list} mailing list`
}

export function scopeSentence(c: Case, finding: Finding) {
  if (!c.scope) return 'The search scope for this case is not available.'
  const { messages, list, first, last } = c.scope
  const noun = /\s/.test(list) ? 'documents' : 'messages'
  const ranked = `We ranked ${messages.toLocaleString('en-US')} ${noun} in ${sourceName(list)}, dated ${longDate(first)} to ${longDate(last)}`
  const { read, readPatents } = finding
  const mix = readPatents ? `: ${plural(readPatents, 'patent')} and ${plural(read - readPatents, 'email')}` : ''
  return `${ranked}, and Reactor read the ${read} closest${mix}.`
}

function chartEntry(c: Case, finding: Finding) {
  const earliest = finding.evidence[0]
  if (finding.status === 'not_found') {
    return `${finding.element}\nNot found in what we searched. ${scopeSentence(c, finding)}`
  }
  if (finding.status !== 'found' || !earliest?.date) return `${finding.element}\nNot answered yet.`
  const words = earliest.marks.map(([from, to]) => `"${earliest.text.slice(from, to)}"`).join(' ')
  const when = earliest.kind === 'patent' ? filedAndGranted(earliest) : `${longDate(earliest.date)}, email`
  return [
    finding.element,
    `${when}, ${beforeYourDate(earliest.date, c.cutoff)}`,
    [displayName(earliest.from), earliest.subject].filter(Boolean).join(', '),
    earliest.url ?? 'No public link',
    words,
    scopeSentence(c, finding),
  ]
    .filter(Boolean)
    .join('\n')
}

export function claimChart(c: Case) {
  const head = `${c.title}\nBefore ${longDate(c.cutoff)}\nFirst pass, not a legal opinion.`
  return [head, ...c.elements.map((finding) => chartEntry(c, finding))].join('\n\n')
}
