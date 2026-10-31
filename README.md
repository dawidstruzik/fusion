# Fusion

Describe your idea and see what came before it, in US patents and the mailing lists where engineers first discuss ideas. Built at the START Warsaw x Poland Tech Week Hackathon for Reactive AI's Memory Retrieval Challenge. Reactor, Reactive AI's agent, writes every answer.

- `pipeline/`: the engine, the benchmark harness and the commands to rebuild the data. Start with `pipeline/README.md`.
- `app/`: the web app. Start with `app/README.md`.

## Setup

You need [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh), [Ollama](https://ollama.com) with `qwen3.8:27b-nvfp4`, and for anything that calls Reactor, Reactive AI's `memory-challenge` repo and data under `external/`, plus your own team's credentials in a git-ignored `secret.json` at the repo root.

No credentials, corpora, runs or challenge data are in this repository. The app reads saved answers from `pipeline/runs/` and documents from `pipeline/corpus/`, so build those first with the commands in `pipeline/README.md`, then run `bun install` and `bun run dev` in `app/`.

The app runs locally: a live question needs a local GPU for search and pre-reading, and Reactor credentials.

## License

Our code is under the MIT license, in `LICENSE`. Data credits are in `pipeline/README.md`.
