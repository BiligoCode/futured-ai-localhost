# Lara Assessments — documentation

Status: **implemented** (October 2026); what was measured is in the evaluation notes.

AI-assisted grading of scanned or typed exam papers and projects: exact grading of questions with definitive
answers, criterion-level suggestions for open questions, student and class summaries, a copying score, an
AI-likeness score and document forensics — plus the dashboard shell (sidebar, overview, section pages).

| File | What it is |
|---|---|
| [`2026-10-02-assessments-research.md`](2026-10-02-assessments-research.md) | Research notes: which Bedrock models the account can call, our handwriting and grading bake-offs, the literature on AI grading, copying detection and AI-text detection, with sources and the design consequences. |
| [`2026-10-02-assessments-design.md`](2026-10-02-assessments-design.md) | The design spec: decisions, dashboard, screens, data model, pipeline, AI contracts, scoring, copying and AI scores, forensics, safeguards, API, web, errors, testing, configuration. |
| [`2026-10-02-assessments-plan.md`](2026-10-02-assessments-plan.md) | The implementation plan: ordered tasks with files, interfaces and the review-focus tests. |
| [`2026-10-02-assessments-evaluation.md`](2026-10-02-assessments-evaluation.md) | Evaluation notes: the synthetic 12- and 36-paper classes, every live run against the real models, what each run changed and why, the AI-likeness calibration, and the limits of the numbers. |

The slides feature is documented in `docs/slides/`; the animation pipeline in `docs/superpowers/`.
