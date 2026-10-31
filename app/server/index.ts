// API server. It reads saved answers from pipeline/runs and asks live questions through the
// pipeline, which holds Reactor's lock. Secrets stay on the server side: anything imported by
// the client ends up in the browser bundle.
import { figureFile, loadCases, loadTimeline, toLiveAnswer } from './cases.ts'

const port = Number(process.env.API_PORT ?? 8787)
const repo = new URL('../..', import.meta.url).pathname
// Off unless set: a question takes Reactor's lock and closes its current history, so a teammate
// pressing Ask between pipeline runs would break the run.
const liveEnabled = process.env.APP_LIVE === '1'
const BUSY = 'Reactor is busy with another run. Try again when it finishes.'
// A browser always sends Origin on a POST. Only our own page may start a Reactor call, so a website
// open in the same browser can't, even by pointing its own domain at this machine. APP_ORIGIN is
// the page's address for teammates, such as the tailnet URL.
const vitePort = process.env.APP_PORT ?? 5173
const allowedOrigins = new Set([
  `http://127.0.0.1:${vitePort}`,
  `http://localhost:${vitePort}`,
  ...(process.env.APP_ORIGIN ? [process.env.APP_ORIGIN] : []),
])

// memchal.ask's exit codes and its one closed-history line. All its logging goes to stderr, so
// stderr goes to this server's log, never to the page, and loose matches on it would misfire.
function explain(code: number, stderr: string) {
  if (code === 3) return BUSY
  if (stderr.includes('That history is closed')) {
    return 'Reactor has moved on from this case. Start a new idea to ask in a fresh session.'
  }
  if (code === 1) return 'Reactor gave no usable answer to this one. Nothing is claimed either way.'
  return "The question didn't run. The API server's log has the reason."
}

type AskBody = {
  question?: unknown
  element?: unknown
  cutoff?: unknown
  corpus?: unknown
  history?: unknown
}

async function ask({ question, element, cutoff, corpus, history }: AskBody) {
  if (typeof question !== 'string' || !question.trim() || question.length > 2000) {
    return Response.json({ error: 'Write a question first.' }, { status: 400 })
  }
  if (typeof cutoff !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(cutoff)) {
    return Response.json({ error: 'The date should look like 2011-06-01.' }, { status: 400 })
  }
  if (typeof corpus !== 'string' || !/^[\w.-]+$/.test(corpus)) {
    return Response.json({ error: 'That source is not available.' }, { status: 400 })
  }
  const proc = Bun.spawn(
    [
      'uv',
      'run',
      '--project',
      `${repo}pipeline`,
      'python',
      '-I',
      '-m',
      'memchal.ask',
      `--corpus=${corpus}`,
      `--cutoff=${cutoff}`,
      `--question=${question}`,
      ...(typeof history === 'string' && history ? [`--history=${history}`] : []),
    ],
    { cwd: repo, stdout: 'pipe', stderr: 'pipe' },
  )
  const [out, err, code] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ])
  if (code !== 0) {
    console.error(err)
    return Response.json({ error: explain(code, err) }, { status: 503 })
  }
  const row = JSON.parse(out.trim().split('\n').at(-1) as string)
  const label = typeof element === 'string' && element ? element : question
  return Response.json(await toLiveAnswer(row, label, cutoff, corpus))
}

// Local only: /api/ask can start a Reactor call under our key. Teammates come through Vite's proxy.
const server = Bun.serve({
  hostname: '127.0.0.1',
  port,
  routes: {
    '/api/health': {
      GET: () => Response.json({ ok: true }),
    },
    '/api/cases': {
      GET: async () => {
        try {
          return Response.json({ cases: await loadCases(), live: liveEnabled })
        } catch (error) {
          console.error(error)
          return Response.json({ error: 'Saved answers could not be read.' }, { status: 500 })
        }
      },
    },
    '/api/timeline': {
      GET: async (req) => {
        const timeline = await loadTimeline(new URL(req.url).searchParams.get('corpus') ?? '')
        return timeline ? Response.json(timeline) : Response.json({ error: 'not found' }, { status: 404 })
      },
    },
    '/api/figure': {
      GET: async (req) => {
        const params = new URL(req.url).searchParams
        const file = await figureFile(params.get('corpus') ?? '', params.get('path') ?? '')
        return file ? new Response(file) : Response.json({ error: 'not found' }, { status: 404 })
      },
    },
    '/api/ask': {
      POST: async (req, srv) => {
        if (!allowedOrigins.has(req.headers.get('origin') ?? '')) {
          return Response.json({ error: 'not allowed' }, { status: 403 })
        }
        if (!liveEnabled) return Response.json({ error: BUSY }, { status: 503 })
        srv.timeout(req, 0) // A live question takes minutes.
        try {
          return await ask((await req.json()) as AskBody)
        } catch (error) {
          console.error(error)
          return Response.json({ error: "The question didn't run. The API server's log has the reason." }, { status: 500 })
        }
      },
    },
  },
  fetch: () => Response.json({ error: 'not found' }, { status: 404 }),
})

console.log(`API on http://127.0.0.1:${server.port}, live questions ${liveEnabled ? 'on' : 'off'}`)
