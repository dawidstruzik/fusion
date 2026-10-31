// Serves the monitoring page and streams one local trace at a time. It never calls Reactor.
// Run: bun run pipeline/monitor/server.ts
import { resolve } from "node:path";

const PIPELINE = resolve(import.meta.dir, "..");
const MODULES = resolve(PIPELINE, "../app/node_modules");
const FONTS: Record<string, string> = {
  "/fonts/archivo.woff2": `${MODULES}/@fontsource-variable/archivo/files/archivo-latin-wght-normal.woff2`,
  "/fonts/space-mono-400.woff2": `${MODULES}/@fontsource/space-mono/files/space-mono-latin-400-normal.woff2`,
  "/fonts/space-mono-700.woff2": `${MODULES}/@fontsource/space-mono/files/space-mono-latin-700-normal.woff2`,
};

let child: ReturnType<typeof spawnTrace> | null = null;

function spawnTrace(question: string, cutoff: string) {
  // Its own process group, so that stopping it also stops whatever uv started.
  return Bun.spawn(
    ["uv", "run", "--project", PIPELINE, "python", "-I", "-m", "memchal.trace", "--corpus", "prior", `--cutoff=${cutoff}`, `--question=${question}`],
    { stdin: "ignore", stdout: "pipe", stderr: "inherit", detached: true },
  );
}

function stopChild() {
  const running = child;
  if (!running) return;
  const signal = (name: NodeJS.Signals) => {
    try {
      process.kill(-running.pid, name);
    } catch {} // already gone
  };
  signal("SIGTERM");
  setTimeout(() => signal("SIGKILL"), 3000).unref();
}

function refuse(status: number, text: string) {
  return Response.json({ error: text }, { status });
}

async function run(req: Request) {
  if (!req.headers.get("content-type")?.startsWith("application/json")) return refuse(415, "Send JSON.");
  const body = await req.json().catch(() => null);
  const question = typeof body?.question === "string" ? body.question.trim() : "";
  const cutoff = typeof body?.cutoff === "string" ? body.cutoff : "";
  if (!question || question.length > 2000) return refuse(400, "Write a question of at most 2,000 characters.");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(cutoff)) return refuse(400, "Pick a date.");
  if (child) return refuse(409, "Another run is going. Wait for it to finish.");

  const running = spawnTrace(question, cutoff);
  child = running;
  let gone = false;
  const clientGone = () => {
    gone = true;
    stopChild();
  };
  req.signal.addEventListener("abort", clientGone);

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader = running.stdout.getReader();
      const send = (bytes: Uint8Array) => {
        if (!gone) controller.enqueue(bytes);
      };
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          send(value);
        }
        const code = await running.exited;
        if (code !== 0) {
          console.error(`trace exited with ${code}`);
          send(new TextEncoder().encode(JSON.stringify({ event: "error", text: "The run failed." }) + "\n"));
        }
      } catch (error) {
        console.error(error);
      } finally {
        await running.exited;
        child = null;
        if (!gone) controller.close();
      }
    },
    cancel: clientGone,
  });
  return new Response(stream, { headers: { "content-type": "application/x-ndjson", "cache-control": "no-store" } });
}

for (const name of ["SIGINT", "SIGTERM"] as const) {
  process.on(name, () => {
    stopChild();
    process.exit(0);
  });
}

// idleTimeout 0: the pre-read can stay silent for over a minute.
Bun.serve({
  hostname: "127.0.0.1",
  port: 8790,
  idleTimeout: 0,
  async fetch(req) {
    // A web page elsewhere must not be able to start runs here, by a rebound name or a cross-site request.
    const host = req.headers.get("host") ?? "";
    if (!["127.0.0.1:8790", "localhost:8790"].includes(host)) return refuse(403, "Open it at http://127.0.0.1:8790.");
    const origin = req.headers.get("origin");
    if (origin && origin !== `http://${host}`) return refuse(403, "Open it at http://127.0.0.1:8790.");
    const { pathname } = new URL(req.url);
    if (pathname === "/run") return req.method === "POST" ? run(req) : refuse(405, "Use POST.");
    if (pathname === "/") return new Response(Bun.file(`${import.meta.dir}/index.html`));
    const font = FONTS[pathname];
    if (font && (await Bun.file(font).exists())) return new Response(Bun.file(font), { headers: { "content-type": "font/woff2" } });
    return new Response("Not found", { status: 404 });
  },
});
console.error("Monitor on http://127.0.0.1:8790");
