// Runs the Bun API server and Vite together. If either exits, or on Ctrl-C /
// SIGTERM, both are stopped.
const procs = [
  Bun.spawn(['bun', '--watch', 'server/index.ts'], { stdio: ['inherit', 'inherit', 'inherit'] }),
  Bun.spawn(['bunx', 'vite'], { stdio: ['inherit', 'inherit', 'inherit'] }),
]

let stopping = false
function stop(code: number) {
  if (stopping) return
  stopping = true
  for (const p of procs) p.kill('SIGTERM')
  Promise.all(procs.map((p) => p.exited)).then(() => process.exit(code))
  setTimeout(() => {
    for (const p of procs) p.kill('SIGKILL')
    process.exit(code)
  }, 3000).unref()
}

process.on('SIGINT', () => stop(130))
process.on('SIGTERM', () => stop(143))
for (const p of procs) p.exited.then((code) => stop(code ?? 1))
