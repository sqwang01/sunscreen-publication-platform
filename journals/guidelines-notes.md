# Journal database — column definitions & working notes

`journals/journals.csv` has one row per **journal x article type**. Numeric and
volatile fields are seeded as `TBD` — fill them from each journal's current
*Instructions for Authors* (IFA) and stamp `guidelines_last_checked`.

## Column definitions

| Column | Meaning |
|---|---|
| `journal` | Full journal title. |
| `publisher` | Publishing house. |
| `society` | Owning/affiliated society, or `n/a`. |
| `article_type` | The submission category as the journal names it. |
| `unsolicited` | `yes` = open submissions; `mostly invited` / `check with editor` = pre-pitch required. |
| `abstract_format` | `structured`, `unstructured`, or `none`. |
| `abstract_words` | Max abstract words. |
| `body_words` | Max main-text words (exclude abstract/refs/legends unless the IFA says otherwise — note which). |
| `references_max` | Max references. |
| `figures_tables_max` | Combined figure + table cap. |
| `structured_body` | `yes` if fixed IMRaD-style headings are mandatory. |
| `reporting_guideline` | Checklist to submit with the manuscript (see map below). |
| `trial_registration` | Whether prospective trial registration is required. |
| `apc_usd` | Article processing charge for open access, in USD (approx). |
| `oa_model` | `subscription`, `hybrid`, or `gold OA`. |
| `reference_style` | Citation style. Verify — several journals use a house variant. |
| `photoprotection_fit` | Subjective 1–5: how naturally sunscreen/photoprotection work lands here. |
| `submission_portal` | Editorial Manager / ScholarOne Manuscripts / other. |
| `guidelines_url` | Direct link to the IFA page. |
| `guidelines_last_checked` | Date the specs in this row were last verified (YYYY-MM-DD). |
| `notes` | Anything else — indexing caveats, section quirks, typical turnaround. |

## Reporting-guideline map (by study design, not journal)

| Design | Guideline | Also |
|---|---|---|
| Randomized controlled trial | CONSORT | prospective registration; CONSORT abstract |
| Observational (cohort/case-control/cross-sectional) | STROBE | |
| Systematic review / meta-analysis | PRISMA 2020 | register in PROSPERO before starting |
| Case report / small series | CARE | patient consent statement |
| Diagnostic accuracy | STARD | |
| Animal study | ARRIVE 2.0 | |
| Qualitative | SRQR or COREQ | |
| Survey | follow STROBE + report response rate; CROSS if available | |

## Fields to always double-check per journal

- Whether **word count includes** the abstract, references, table/figure legends.
- Whether **narrative reviews are invited only** (`unsolicited` flag) — if so, send a
  one-paragraph pre-pitch to the editor with scope, proposed length, and why now.
- **Reference cap** for Letters / Research Letters is often very tight (5–10).
- **AI-use disclosure** wording — record it in `ai_policy_summary` and follow it.
- **Preprint policy** — some journals accept prior preprints, a few still don't.
- **Predatory screen** — confirm MEDLINE/Scopus indexing and (for OA) DOAJ listing
  before adding a new journal to the file. Note the check here.

## Verifying specs — publisher sites block automated fetching

Wiley (`onlinelibrary.wiley.com`), Elsevier (`sciencedirect.com`), and Springer
(`link.springer.com`) return **403 / auth redirects** to the digest agent's fetcher.
So the weekly agent generally **cannot auto-read those Instructions-for-Authors pages**.
Practical rule: rows for JAMA Network and Oxford Academic journals can often be
auto-verified; Wiley/Elsevier/Springer rows need a **manual pass** (open the URL in
`guidelines_url`, fill the `TBD`s, stamp `guidelines_last_checked`). The agent should
flag which `TBD` rows a proposed idea depends on rather than trying to scrape them.

## Per-journal detail (verified 2026-09-05 unless noted)

- **JAMA Dermatology** — fully populated. Original Investigation / Systematic Review:
  3000 w, structured abstract 350 w, 50–75 refs, ≤5 figs+tables. **Viewpoint**: 1200 w
  (1000 with a small table/figure), ≤7 refs, no abstract — best fit for misinformation /
  regulation / policy pieces; **AI/LLM may not draft opinion pieces or letters**.
  Research Letter: 800 w, ≤10 refs, ≤2 items, IMRaD headings. Portal: manuscripts.jamaderm.com.
  `.docx` only, double-spaced, Data Sharing Statement required.
- **British Journal of Dermatology** — fully populated. Original Article: 3000 w
  (4000 qualitative), structured abstract 350 w, figures ≤6 panels each. **Prospective
  trial registration is mandatory — unregistered trials are rejected outright.**
  Research Letter: 750 w, ≤8 refs, no subheadings ("most prestigious form of BJD
  correspondence"). Image Correspondence: ≤100 w caption, ≤2 refs, ≤3 panels.
  ORCID required from Aug 2026; AI disclosure required from Aug 2025. Portal: ScholarOne.
- **JAAD** — Original Article: **≤2500 w** (excl abstract/refs/figs/tables), abstract
  ≤200 w, **Capsule Summary (3 bullets) required**, no figure/table limit. CME/reviews
  are essentially all solicited; practical unsolicited routes are Original Article and
  Notes & Comments / Research Letter. Remaining caps still `TBD` (Elsevier site blocked).
- **Photodermatology, Photoimmunology & Photomedicine** — Original abstract structured
  (Background/purpose, Methods, Results, Conclusion), ≤250 w; no firm main-text cap
  stated (verify). **Letter to the Editor: ≤1000 w INCLUDING references, ≤10 refs,
  ≤2 figures+tables.** Invited Commentary/Editorial: 2000 w incl abstract + legends,
  excl refs. Smallest audience of the set but the most topically aligned.
- **Dermatology and Therapy (Adis)** — accepts unsolicited narrative reviews and is
  fast (~2-week review), **but charges a mandatory Rapid Service Fee of about
  US $7,675 / €5,950 / £5,120 on acceptance** (gold OA, CC-BY-NC). Given the
  free/low-cost preference, treat this as a last-resort target, not a default.
- **Dermatologic Therapy / Clinical, Cosmetic and Investigational Dermatology** —
  re-confirm current indexing status each time before submitting.
