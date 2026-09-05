# Idea → article type → journal

## Step 1 — Pick the article type from what you actually have

```
Do you have NEW primary data you collected/analyzed?
├─ Yes → Is it a prospective randomized intervention?
│        ├─ Yes → ORIGINAL ARTICLE (trial). CONSORT. Prospective registration. Aim high (JAMA Derm, BJD, JAAD).
│        └─ No  → Prospective cohort / cross-sectional / survey / lab study?
│                 ├─ Clinical/epi → ORIGINAL ARTICLE (observational). STROBE.
│                 └─ Bench/mechanistic → ORIGINAL ARTICLE. JID, Exp Dermatol, J Photochem Photobiol B, Photochem Photobiol Sci.
│        (Small dataset, 1 clean finding? → RESEARCH LETTER instead — faster, tight ref cap.)
│
├─ Retrospective chart / registry data → COHORT or CASE SERIES. STROBE.
│
├─ 1–3 unusual patients / teaching image → CASE REPORT or SERIES. CARE. Patient consent.
│        Targets: JAAD Case Reports, Photodermatol Photoimmunol Photomed, Int J Dermatol (Report), Cutis Photo Challenge.
│
└─ No new data — synthesis or opinion only:
         ├─ Focused answerable question, exhaustive reproducible search
         │        → SYSTEMATIC REVIEW ± meta-analysis. PRISMA 2020. Register PROSPERO first.
         │        Targets: BJD, JAAD, JEADV, Dermatology and Therapy.
         ├─ Broad landscape / mechanism / "state of the field"
         │        → NARRATIVE REVIEW (usually invited — PRE-PITCH the editor).
         │        Targets: an invited slot; or Dermatology and Therapy / J Cosmet Dermatol (accept unsolicited).
         ├─ Controversy, policy, misinformation, regulatory gap, "we should…"
         │        → VIEWPOINT / COMMENTARY / EDITORIAL. No reporting guideline.
         │        Targets: JAMA Derm Viewpoint, JAAD editorial, Australasian J Dermatol.
         └─ Practice-gap teaching piece → CME / clinical review (solicited).
```

## Step 2 — Shortlist journals

From `journals/journals.csv`, filter rows where `article_type` matches Step 1 and
`unsolicited` allows it (or you will pre-pitch), then rank by:

1. **`photoprotection_fit`** (topical landing — 4–5 first).
2. **Impact vs. realism** — pick one "reach" target and one "likely" target.
3. **Speed** — if timeliness matters (misinformation, regulatory news), weight
   turnaround and prefer venues that move fast.
4. **APC** — `oa_model = gold OA` means an APC; confirm you can/ want to cover it.
5. **Audience** — clinicians (JAAD, JDD, Cutis), Europe (BJD, JEADV), high-UV
   region (Australasian JD), cosmetic science (J Cosmet Dermatol), photobiology
   (Photodermatol Photoimmunol Photomed, Photochem Photobiol Sci).

Record 2–3 in `target_journal_1..3` in the backlog, most-preferred first.

## Step 3 — Lock the budget before drafting

Pull from the chosen journal's row and write them at the top of the draft:

- body word limit (and whether it includes abstract/refs/legends)
- abstract type + word limit
- reference cap
- figure + table cap
- required structured headings
- reporting checklist to complete (CONSORT / STROBE / PRISMA / CARE / …)
- trial registration / PROSPERO number if applicable
- cover-letter points: why this journal, what's new, suggested reviewers,
  any prior preprint, AI-use disclosure per that journal's policy

If a spec is still `TBD`, fetch the current Instructions for Authors, fill the row,
and stamp `guidelines_last_checked` before you start writing.

## Step 4 — Have a fallback chain

Decide the resubmission order now (target 1 → 2 → 3) so a rejection triggers an
immediate reformat-and-resend rather than a restart. Note portable-review /
manuscript-transfer offers in the journal row if the publisher supports them.
