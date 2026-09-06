# Sunscreen & Photoprotection Publication Pipeline

A personal, single-user workflow to expedite writing and placing sunscreen /
photoprotection manuscripts in dermatology and allied journals.

Four engines:

1. **Surveillance** — weekly automated sweep of PubMed + OpenAlex (per topic) plus
   free trend signals, written to `digests/`.
2. **Ideation** — turn digest signals into scored manuscript ideas in `ideas/backlog.csv`.
3. **Targeting** — match each idea to an article type and 2–3 journals using
   `matching/decision-tree.md` and `journals/journals.csv`.
4. **Expansion** — turn a chosen backlog row into a submission-style brief
   (`ideas/briefs/<id>.md`): an abstract drafted to the target journal's spec plus
   a two-line "why dermatology and the sun-care industry should care". Run
   `scripts/expand-idea-prompt.md` against an idea `id`.
5. **Execution tracking** — move ideas through the lifecycle in `ideas/backlog.csv`.

## Dashboard

A read-only view of the whole pipeline in one HTML file — no server, no
dependencies (Python standard library only):

```
python3 scripts/build-dashboard.py     # writes ./dashboard.html
open dashboard.html
```

Four tabs: **Pipeline board** (`ideas/backlog.csv` by lifecycle status; a card
whose idea has a brief in `ideas/briefs/` gets an "Abstract & significance"
expander),
**Latest digest** (newest `digests/*.md` rendered, with a picker for older ones),
**Topic white-space** (`taxonomy/topics.yaml` staleness × known reviews × backlog
coverage × mentions in the latest digest), **Journal targeting**
(`journals/journals.csv`, filterable, flags `TBD` specs and stale `guidelines_last_checked`).

Re-run the script after editing any source file. `dashboard.html` is gitignored;
regenerate it rather than committing it.

## Repo layout

```
taxonomy/topics.yaml          ~16 sunscreen sub-topics; PubMed + OpenAlex queries per topic
journals/journals.csv         journal x article-type submission-spec table (specs to be filled)
journals/guidelines-notes.md  column definitions + per-journal quirks, editor pre-pitch rules, AI policy
ideas/backlog.csv             scored idea backlog + lifecycle status
ideas/scoring-rubric.md       the 7 scoring criteria, weights, thresholds
matching/decision-tree.md     article-type selection + reporting-guideline map + journal tiering
digests/TEMPLATE.md           format for the weekly surveillance digest
digests/YYYY-MM-DD.md         weekly output
scripts/build-dashboard.py    generates ./dashboard.html from the files above
```

## The weekly digest

Runs unattended as a scheduled Claude cloud agent (set up with `/schedule`).
Each run:

1. For every topic in `taxonomy/topics.yaml`, query **PubMed E-utilities** and
   **OpenAlex** for records newer than the last run (`defaults.lookback_days`).
2. Group new papers under their topic; write a 1–2 line "why it matters / gap?" note.
3. Pull a few free trend items: Google News RSS, Reddit (r/SkincareAddiction,
   r/30PlusSkinCare, r/DermatologyResearch), Google Trends via `pytrends`.
4. Cross-check candidate ideas against `ideas/backlog.csv` so nothing is re-proposed.
5. Write `digests/<date>.md` from `digests/TEMPLATE.md` with 3–5 ranked manuscript
   ideas, each tagged with a suggested article type and 2–3 target journals plus
   their word / reference / figure budgets from `journals/journals.csv`.

### Data sources (all free, no paid APIs)

| Source | Endpoint | Notes |
|---|---|---|
| PubMed / MEDLINE | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` | `esearch` + `efetch`/`esummary`. 3 req/s without a key. |
| OpenAlex | `https://api.openalex.org/works` | No key. Put your email in `mailto=` for the faster pool. |
| Google News | `https://news.google.com/rss/search?q=...` | RSS. |
| Reddit | `https://www.reddit.com/r/<sub>/new.json` | Public JSON; set a descriptive User-Agent. |
| Google Trends | `pytrends` (unofficial) | Rate-limited; use sparingly. |

### Optional one-time setup

Register a free NCBI account and create an **API key** — raises the PubMed limit
from 3 to 10 requests/second. Not required to start. Add it as an env var the
scheduled agent can read; never commit it.

## Maintenance cadence

- **Weekly** — review the new digest, move 1–3 ideas into `ideas/backlog.csv`.
- **Monthly** — re-score the backlog, prune `parked`/`killed`.
- **Quarterly** — re-pull journal Instructions for Authors; update `journals/journals.csv`
  and set `guidelines_last_checked`.
- **As needed** — add or retire topics in `taxonomy/topics.yaml`; bump `last_reviewed`
  and refresh `known_reviews` when you assess a topic for white space.

## Guardrails

- **Verify every citation and factual claim yourself.** Digest summaries are leads, not facts.
- **AI-use disclosure** — each journal's policy is recorded per row in `journals.csv`
  (`ai_policy_summary`). Comply with it; follow ICMJE authorship rules.
- **Predatory-journal screen** — before adding a journal, confirm it is MEDLINE/Scopus
  indexed and in DOAJ (if open access). Note the check in `guidelines-notes.md`.
- **Narrative reviews are usually invite-only** — pre-pitch the editor before drafting.
  The `unsolicited` column flags this.
- **No Google Scholar scraping** — it has no API and scraping breaks its terms; OpenAlex
  is the sanctioned substitute.

## Idea lifecycle (`status` in `ideas/backlog.csv`)

`idea` -> `pitched` -> `drafting` -> `submitted` -> `revision` -> `accepted` -> `published`
Side states: `parked` (revisit later), `killed` (abandon, keep the record).

