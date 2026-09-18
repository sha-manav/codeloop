# CodeLoop — Coder Guidelines

**Version 1.1 — imaging convention confirmed after the spot-check session (2026-09-18).**
For the certified professional coder working on CodeLoop. Applies to the spot-check, the pilot, batches 1–3, and the final holdout coding. Rule questions go in the questions log (§9); the owner answers in writing and updates this document between batches. This file is committed to the project repository and its hash is recorded; a rule never changes mid-batch.

---

## 1. What this is and what your job is

CodeLoop is a research project. An AI system reads a doctor–patient conversation and the clinical note that resulted from it, then drafts the codes for an outpatient office visit. You review the drafts and correct them. Your corrections are the standard the system is measured against and the signal it learns from. Nobody is grading you; the system is being graded against you.

Three things follow from that:

- **Code the way you would for a real professional claim, under the rules in this document.** Where a rule here differs from your usual practice or a particular payer's policy, the rule here wins, because the system is measured against it.
- **Be consistent.** Consistency matters more than any single hard call. If you make a judgment call, make the same call the next time the situation comes up.
- **Don't help the AI.** If the draft is wrong, change it. If you can't say the draft is wrong, leave it. Use the `judgment` reason only when both answers are defensible.

The encounters are scripted or role-played from a public research dataset. Names are fictional and there is no real patient. Notes are sometimes thin, odd, or internally inconsistent. Code what is documented; do not correct the note. If the note and the transcript conflict, the note wins.

## 2. Ground rules

1. **The note is the record.** Code only what the signed clinical note supports. The transcript is there to help you read the note; it is not documentation. If a fact appears only in the transcript (for example, which side of the body), do not code it. The system is supposed to raise a *provider query* in that situation; §5 explains how to record it.
2. **Code sets.** ICD-10-CM FY2027: treat every visit as if the date of service is on or after October 1, 2026. CPT 2026. HCPCS Level II, October 2026 release.
3. **Every edit needs a reason** (§4). The reason is not a formality; reasons are how corrections get grouped into problems for the engineers to fix.
4. **No outside help on the cases.** Do not look these encounters up online (some have published codes; those are not this project's standard), do not paste them into any AI tool, and do not discuss individual cases with anyone else on the project. Your codebooks, references and payer manuals are all fine.
5. **Time is measured.** Work one encounter at a time from open to approve. Take breaks between encounters, not in the middle of one. Don't rush and don't linger; work at your normal pace.

## 3. What to code

### Diagnoses (ICD-10-CM)

- Code every condition documented as assessed, managed, or affecting care at this visit. Chronic conditions under ongoing management count.
- Do not code conditions that are resolved and not affecting care. Use history (Z) codes only when the history is documented and affects current care.
- Uncertain diagnoses ("possible", "probable", "suspected", "rule out", "consistent with") are not coded in the outpatient setting. Code the symptoms or findings to the highest degree of certainty documented.
- Symptoms integral to a documented definitive diagnosis are not coded separately.
- Specificity and laterality only as documented in the note. If the side is not documented, use the unspecified-side code (and see §5).
- Mark each diagnosis **active** or **historical**.
- **First-listed:** the condition chiefly responsible for the services provided at this visit.

### Procedure lines (CPT/HCPCS)

One category is in scope in this phase: **plain-film imaging (X-rays) performed at this visit, in this office.**

- Bill it only when the note documents that the imaging was obtained at this visit in this office. Imaging that was ordered, planned, done elsewhere, done previously, or merely reviewed is not billable here. If the draft bills it, remove it with reason `unsupported`.
- **Convention (confirmed at the spot-check): bill the professional component.** These notes document the interpretation but not that the practice supplied the equipment and technical acquisition, so every X-ray line carries modifier **26**. Never bill the global code and never add TC.
- Select the code by anatomy and the documented number of views. If the number of views is not documented, the label is the most conservative code that fits the documented anatomy (fewest views), and you record that you would query (§5).
- Use RT or LT (alongside 26) when the code is side-specific and the side is documented in the note. Bilateral studies: two lines, RT and LT. Do not use modifier 50 on X-rays.
- Units: one per study.
- Diagnosis pointers: point each line at the diagnosis or symptom that justifies the study.

### Out of scope — don't spend time on it

- **E/M visit levels and modifier 25.** Do not add them. If you add them anyway they are ignored.
- **Everything else** (injections, in-office labs, ECGs, procedures, vaccines, drugs) is not scored in this phase. If a draft contains one, it is a system error; remove it with the reason that fits. If you would normally bill one that the draft lacks, you may add it — it is recorded for a later phase but not scored — but don't let it slow you down.

## 4. The review screen

The note is on the left with the transcript below it (collapsible). The draft is on the right. Clicking a code highlights the passages the system cited for it.

Actions on each drafted field: **Accept**, **Edit**, **Remove**. **Add** creates a new diagnosis or line. Every Edit, Add and Remove requires exactly one reason:

| Reason | Use when | Example |
|---|---|---|
| `missed` | The note supports a code or field the draft does not have. (Add) | Note documents hypertension managed at the visit; the draft has no I10. |
| `unsupported` | The note does not establish the condition or service at all. (Remove) | Draft bills a knee X-ray; the note only says outside films were reviewed. |
| `guideline` | The note supports it, but a coding rule changes or forbids it. (Edit or Remove) | Draft codes "probable pneumonia" as pneumonia; draft codes flank pain alongside the kidney stone it is attributed to. |
| `query_needed` | The note is insufficient to support the value the draft chose; you are changing it to the conservative value. (Edit) | Draft codes the right side, but the side appears only in the transcript; draft picks a multi-view X-ray code and the note does not say how many views. |
| `specificity` | The note documents the detail; the draft ignored it. Right condition, wrong specificity, laterality, or active/historical status. (Edit) | Note says right knee osteoarthritis; draft has the unspecified-knee code. |
| `wrong_value` | A different condition or service entirely, or a wrong unit count, modifier, or diagnosis pointer. (Edit) | Draft codes cellulitis where the note documents a contusion; a line points at the wrong diagnosis. |
| `judgment` | Both answers are defensible; you would have done it differently. (Edit, Remove, Add) | A borderline "affects care" chronic condition; a code you would sequence differently. |

**When more than one reason fits**, ask in this order and stop at the first yes:
1. Does the note fail to establish the condition or service at all? → `unsupported`
2. Is a coding rule the reason it changes? → `guideline`
3. Is the fix "the note doesn't say"? → `query_needed`
4. Is the fix "the note says, and the draft ignored it"? → `specificity` (or `wrong_value` if it's a different concept, unit, modifier, or pointer)
5. Otherwise → `judgment`

**Evidence passages.** Every highlighted passage gets a grade, **Supported** or **Unsupported**, including passages on fields you go on to edit or remove. Supported means: this passage, read on its own, supports the code or field as drafted, including its status and specificity. Unsupported covers everything else: the passage supports a different condition or a different specificity, it is irrelevant, or it is a transcript passage cited for a billable field.

**Provider queries.** The draft may include questions the system says it would send to the provider. Grade each **Warranted** or **Unwarranted**. Warranted means you would send that question to the provider before filing the claim. Unwarranted means you would not: the answer is already in the note, the answer would not change the coding, or it is not a question a coder would ask.

**Approve** when every field has been accepted, edited, or removed, every passage is graded, and every query is graded.

## 5. Recording "I would query the provider"

Situations: a fact appears only in the transcript; the side, the number of views, or another detail needed for the code is not documented; the draft chose a value the note cannot support.

- If the draft's value is **not** the conservative one → **Edit** it to the conservative value, reason `query_needed`.
- If the draft already contains a provider query about it → grade that query **Warranted**.
- If the draft's value is already the conservative one and there is no query → **Accept** it, and write the encounter ID, the field, and "would query" in your questions log.

**Conservative** means the value that can be filed on the documentation as written: the unspecified-side code, the less specific code, the fewest views, the fewest units, no additional modifier.

## 6. Blind encounters

In each batch, five encounters are marked **blind**. Do these five first. The screen shows only the note and transcript, with no draft. Code the whole encounter from scratch (diagnoses with status, first-listed, any in-scope X-ray line), then press **Submit blind label**. The draft then appears, and you review it exactly as usual: every change with a reason, passages graded, queries graded, approve.

Your reviewed version is the official label; your blind version is kept separately. When reviewing, judge the draft on its merits; do not try to reproduce your blind version.

## 7. Session 1: the spot-check

About two hours, 30 encounters, done before any batch. For each encounter the screen lists services an automated pass flagged as possibly performed at the visit (mostly X-rays).

- **Confirm** a flag only if the note documents the service as performed at this visit, in this office, and it would be billable as a professional service. "Reviewed", "ordered", "outside films", "recent X-ray showed" are all **Deny**.
- List any billable service the pass missed, in any category, not just imaging.
- Comments are optional but useful.

This session decides which service categories are in scope for the whole project, so be strict rather than generous. At the end, tell the owner two things: for the imaging you confirmed, whether a practice like this would bill the global code or the professional component only; and any service categories you expected to see that did not appear.

## 8. Final holdout coding (after the last batch)

Forty encounters, coded from scratch, blind, with no draft, under the same rules. About ten hours. These are scored once and never revisited, so do not discuss them with anyone.

## 9. Questions log and rule changes

Keep a running log with the encounter ID, the field, and the question. Send it to the owner at the end of every session. Questions about a rule are answered in writing and added to this document with a new version number and date; the change takes effect at the next batch, never mid-batch. Never invent a new rule mid-batch: make the conservative call, log it, and move on.

## 10. Practical

- One encounter at a time. Approve before moving on.
- Sessions of two to three hours work well.
- Expected pace after the pilot is roughly 8–12 minutes per review encounter and 15–20 per blind encounter. There is no target; the pace is measured, not rewarded.
- Tell the owner when you finish a session so the event log can be backed up.

---

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-09-17 | Initial draft; imaging convention (global billing) and undocumented-views rule pending confirmation after the spot-check. |
| 1.1 | 2026-09-18 | Imaging convention set to professional component (modifier 26 on every X-ray line) on the CPC's recommendation; undocumented-views rule (fewest views, would query) confirmed. |
