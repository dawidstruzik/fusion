# Fusion

Describe your idea. Fusion searches US patents and technical mailing lists together and, for each part of the idea, shows similar documents earliest first, with a link anyone can open, or "not found in what we searched". Reactor writes every answer; the pipeline in `../pipeline` retrieves the evidence. It's a first pass, not a legal opinion.

Vite, React and TypeScript in `src/`, a Bun API server in `server/`.

## Run it

| Script | What it does |
| --- | --- |
| `bun install` | Installs dependencies and Playwright's Chromium. |
| `bun run dev` | Starts the API server (port 8787) and Vite (http://127.0.0.1:5173). Both listen on 127.0.0.1 only. |
| `bun run record` | With `dev` running, records the demo path at 1440x900 to `demo/backup.webm`. |
| `bun run build` | Type-checks everything and builds the client to `dist/`. |

## Where the data comes from

- Saved answers: every `../pipeline/runs/<run>/case.json` with its `results.jsonl`, joined to `../pipeline/corpus/<corpus>/messages.jsonl`. Runs whose names start with `test` hold test data and are refused in code.
- A `both-<case>` run (patents and emails) replaces `prior-<case>` (emails only) once every part has an answer. Until then the emails-only run stays the demo, so the app works without patents.
- Patent drawings: `../pipeline/corpus/<corpus>/figures/figures.json`, served from disk, never from the web.
- Live questions: `server/index.ts` spawns `memchal.ask` from the pipeline, which takes Reactor's lock. A question takes 2 to 3 minutes. Off unless `APP_LIVE=1` is set; without it a typed idea shows its parts and says live runs are off. The server takes a question only from the app's own page: `127.0.0.1` or `localhost` on Vite's port, or the address in `APP_ORIGIN` (for teammates, the tailnet URL).

## The rule that matters

A cited document counts as prior art only if it has a date and that date is before the cutoff. For a patent the date is its filing date. `server/cases.ts` checks this in code, whatever Reactor's answer says.

Secrets stay in `server/` and the pipeline. Everything in `src/` ships to the browser.
