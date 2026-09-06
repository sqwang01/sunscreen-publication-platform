You are expanding one backlog idea into a submission-style brief for a sunscreen &
photoprotection publication pipeline. You run in the repo working directory. Your
job: write `ideas/briefs/<IDEA_ID>.md` for the idea ID you were given, and change
nothing else.

## Input

An idea `id` from `ideas/backlog.csv` (e.g. `EX-1`). If none was given, list the
ids and ask which one.

## Steps

1. Read: `ideas/briefs/TEMPLATE.md`, `ideas/backlog.csv`, `ideas/scoring-rubric.md`,
   `matching/decision-tree.md`, `journals/journals.csv`, `journals/guidelines-notes.md`,
   `taxonomy/topics.yaml`. Also read the latest `digests/*.md` if the idea traces to
   one, for the "why now" signal.

2. Pull the backlog row for `<IDEA_ID>`: `working_title`, `topic_id`,
   `proposed_article_type`, `evidence_on_hand`, `target_journal_1..3`, `status`,
   `next_action`, and the seven `score_*` values.

3. Find the `journals.csv` row where `journal == target_journal_1` AND
   `article_type` matches the proposed type. Take `abstract_format`, `abstract_words`,
   `body_words`, `references_max`, `figures_tables_max`, `structured_body`,
   `reporting_guideline`, `unsolicited`, `guidelines_last_checked`.
   - If `abstract_words` is `TBD` or blank, size the abstract to **250 words** and
     say the cap is unverified.
   - If `abstract_format` is `structured` (or `structured_body == yes`), use the
     journal's structured headings; the digest/decision-tree name them. Otherwise
     write one flowing paragraph.

4. Draft the abstract from the template:
   - Ground every sentence in what the idea and topic actually claim. Do **not**
     fabricate numeric results, effect sizes, sample sizes, or p-values.
   - The results sentence is framed as **anticipated** — the expected direction and
     what would support or refute it — for Original Articles. For Reviews, describe
     the synthesis and the gap it fills. For Viewpoints, state the argument and the
     recommended action.
   - Stay at or under the word cap. Put the running count at the end.

5. Write the **Why this matters** two lines:
   - dermatology: counseling, diagnosis, guideline wording, or research-priority impact.
   - sun-care industry: formulation, label/SPF claims, test-method standards, or
     consumer messaging impact.
   Each one line, specific to this idea — no boilerplate.

6. Fill **Draft-readiness notes** from the backlog row, the rubric (criterion 6 =
   competing work to check), and the journal budget. Set "Editor pre-pitch required"
   to yes when the chosen journal row's `unsolicited` is `no` / `check with editor`
   and the type is a narrative review.

7. Save as `ideas/briefs/<IDEA_ID>.md`. Keep the trailing scaffold disclaimer.
   Do not edit `backlog.csv` or regenerate the dashboard — the user does that
   (`python3 scripts/build-dashboard.py`, and `-o index.html` for the Pages build).

## Guardrails

- Verify nothing yourself — this brief is a set of leads and a drafting scaffold
  for the user to check. Anticipated results are hypotheses, not findings.
- No invented citations. If you name prior work, mark it "verify".
- Match the target journal's AI-use policy note in `journals.csv` when the user
  later drafts — flag it in the notes if the row records one.
