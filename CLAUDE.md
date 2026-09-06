# CLAUDE.md

Personal, single-user workflow for drafting and placing sunscreen /
photoprotection manuscripts. Not a shipped product — no test suite, no CI, no
build system. Don't add engineering ceremony unless asked.

Start with [README.md](README.md) for the four engines (Surveillance, Ideation,
Targeting, Execution tracking), the repo layout, and the weekly digest flow.
This file only covers what the README doesn't make obvious.

## Conventions

- **Scripts are Python 3 standard library only** — no `pip install`, no
  dependencies. `scripts/build-dashboard.py` must stay stdlib-only.
- **`dashboard.html` is generated and gitignored** — regenerate with
  `python3 scripts/build-dashboard.py`, never commit it. (`index.html` at repo
  root is a separate, committed build for GitHub Pages.)
- **The dashboard is read-only except when served by `scripts/serve-dashboard.py`**
  — that script re-renders `build_html(..., editable=True)` on `localhost` and
  accepts a single `POST /api/idea` that patches `status` / `next_action` on one
  `backlog.csv` row (rewriting just that line). Keep the static builds
  (`dashboard.html`, `index.html`) read-only; `editable` defaults to `False`.
- Never commit secrets — `.env`, `*.key`, `secrets.*` are gitignored. The digest
  runner uses public APIs (PubMed E-utilities, OpenAlex) that need no key.
- Dates are absolute `YYYY-MM-DD` everywhere (filenames, CSV fields, YAML).

## Where things are defined

- Idea backlog schema + lifecycle `status` values: `ideas/backlog.csv` header,
  scoring in `ideas/scoring-rubric.md`. `EX-*` rows are examples — leave them
  until real ideas exist.
- Journal submission-spec columns: `journals/journals.csv` header, explained in
  `journals/guidelines-notes.md`.
- Surveillance topics + per-topic PubMed/OpenAlex queries: `taxonomy/topics.yaml`
  (the file's own header comment documents the query fields and the "cutaneous
  guard" pattern for broad topics). `id` here = `topic_id` in `backlog.csv`.
- Article-type / journal selection logic: `matching/decision-tree.md`.
- Per-idea expanded briefs: `ideas/briefs/<idea-id>.md` (committed, like digests),
  shape in `ideas/briefs/TEMPLATE.md`, produced by following
  `scripts/expand-idea-prompt.md` against an idea `id`. On the dashboard the
  Pipeline-board card gets a button that opens the brief full-width in a reader
  overlay. Abstract results are framed as *anticipated*, not
  data; delete the `EX-*` demo brief once real ideas exist.

## Weekly digest

- Prompt: `scripts/digest-prompt.md`. Runner: `scripts/run-weekly-digest.sh`
  (launchd `com.stevenwang.sunscreen-digest`, Mondays 06:00 local; also runs as a
  scheduled Claude cloud agent).
- Output: `digests/<date>.md` from `digests/TEMPLATE.md`, with 3–5 ranked ideas
  cross-checked against `ideas/backlog.csv` so nothing is re-proposed.
- Run logs land in `scripts/logs/` (gitignored).

## After editing any source file

Re-run `python3 scripts/build-dashboard.py` if you want the local dashboard to
reflect the change.
