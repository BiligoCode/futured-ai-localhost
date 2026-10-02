# Lara Assessments — Research notes

Date: 2026-10-02
Feeds: [`2026-10-02-assessments-design.md`](2026-10-02-assessments-design.md)

What the literature says about AI grading of (handwritten) exams, copying detection and AI-writing detection, what
we measured ourselves on the hackathon Bedrock account, and the design consequences. Every design rule in the spec
traces back to one of the numbered findings here.

## 1. Models we can actually call

`bedrock:ListFoundationModels` lists ~110 models, but the IAM user may only invoke **on-demand** models; every
cross-region inference profile (Claude, Nova, GPT, Grok, Llama 4, Pixtral) returns `AccessDeniedException`.

| Need | Callable on-demand | Not callable |
|---|---|---|
| Vision (reading scans) | `qwen.qwen3-vl-235b-a22b`, `moonshotai.kimi-k2.5`, `mistral.mistral-large-3-675b-instruct`, `google.gemma-3-27b-it`, `mistral.ministral-3-14b-instruct`, `mistral.magistral-small-2509`, `nvidia.nemotron-nano-12b-v2`, `writer.palmyra-vision-7b` | `us.amazon.nova-*`, `us.anthropic.*`, `us.openai.*`, `us.meta.llama4-*`, `us.mistral.pixtral-*` |
| Text reasoning | `zai.glm-5` (Lara's default), `deepseek.v3.2`, `mistral.mistral-large-3-675b-instruct`, `moonshotai.kimi-k2.5`, `qwen.qwen3-vl-235b-a22b` (also text) | as above |
| Embeddings | `amazon.titan-embed-text-v2:0` | `cohere.embed-multilingual-v3`, `cohere.embed-v4:0` |

`zai.glm-5` rejects image blocks (`ValidationException`), so reading scans needs a separate vision model.

### 1.1 Handwriting bake-off (our test)

Input: the scanned middle-school worksheet in Henkel et al. (2025, Fig. 1) — real handwriting with overwritten
digits, a crossed-out answer and a handwritten student ID. Same JSON transcription prompt, temperature 0.

| Model | Time | Student ID | Q9 (overwritten) | Q10 final | Problems |
|---|---|---|---|---|---|
| Qwen3-VL 235B | 17.4 s | `A001450` | 200 | 7/2000 | none serious; missed one strike-through |
| Kimi K2.5 | 11.1 s | `H001950` | 208 (sees `~~200~~`) | 7/1000 | reads overwrite differently |
| Mistral Large 3 | 9.5 s | `M001450` | 208 | 7/2000 | **invented a strike-through** in Q8 (`~~24~~`) |
| Gemma 3 27B | 11.2 s | `H001950` | 7/1000 | 7/1000 | **misread printed text** (858 → 658) |
| Palmyra Vision 7B | — | — | — | — | degenerate repetition |
| Nemotron Nano 12B | — | — | — | — | transliterated Greek (`Swto`) |

Qwen3-VL and Kimi K2.5 are the two credible readers, and they **disagree exactly where a human would hesitate**
(the overwritten digits). That is what makes a second, independent reading valuable: agreement is evidence the
reading is right; disagreement is precisely the case a professor must look at.
Qwen3-VL is also the strongest open model on handwriting benchmarks (OmniHandwritingOCR, 2026: best aggregate
among MLLMs; Qwen3-VL technical report: >70 % accuracy on 32 of 39 OCR languages).

### 1.2 Grading bake-off (our test)

Input: a Greek four-question exam (true/false, multiple choice, numeric, open) with a typed transcript. Truth:
Q1 `Σ` = Σωστό = correct · Q2 `γ` = wrong (key `β`) · Q3 `49` = wrong (key 50) · Q4 ≈ 4–5 / 6.

| Model | Time | Q1 | Q2 | Q3 | Q4 | Notes |
|---|---|---|---|---|---|---|
| GLM-5 | 8.1 s | ✓ | ✓ | ✓ | 5 | odd Greek word ("μόνιμοι" for "μονάδες") |
| Mistral Large 3 | 3.0 s | ✓ | ✓ | ✓ | 4 | concise, clean Greek |
| DeepSeek V3.2 | 16.0 s | ✓ | **✗ marked `γ` correct** | ✓ | 5 | |
| Qwen3-VL 235B | 26.6 s | ✓ | **✗ marked `γ` correct** | ✓ | 5 | |
| Kimi K2.5 | 9.4 s | **✗ "Σ is not a valid answer"** | ✓ | ✓ | 4 | |

**Three of five strong models made a grading error on a question with a definitive answer**, and the open
question got 4 or 5 depending on the model. Henkel et al. (2025) report the same failure class ("model description
of answer: 15 — GPT-4.1 grade: FALSE" for a correct 15).

### 1.3 Embeddings

Titan v2 on Greek: a near-copy scores 0.94 (good), but a *paraphrase* scores 0.33 while a different sentence on the
same topic scores 0.67. For Greek it is effectively lexical, so it adds nothing over n-gram overlap and cannot
catch paraphrased copying. **Not used.**

## 2. AI-assisted grading — literature

1. **Separate "seeing" from "judging".** Henkel et al., *Seeing the Big Picture* (2025): near-human accuracy on
   arithmetic with objective answers (95 %, κ = 0.90) but grading hallucinations where the model judged a correctly
   read answer wrong; MLLMs "see" well but struggle to evaluate. Two-stage designs make each step checkable.
   [arXiv 2510.05538](https://arxiv.org/abs/2510.05538)
2. **Reference answers and rubrics are necessary but not sufficient.** *Evaluating GPT-4 at Grading Handwritten
   Solutions in Math Exams* (2024): correct answer + rubric beat no context, yet accuracy stayed at
   47 % exact / MAE 7.7 %; failures: reading handwriting, validating reasoning, misreading rubric intent. They
   recommend confirming legibility before grading and rubrics written for the model.
   [arXiv 2411.05231](https://arxiv.org/abs/2411.05231)
3. **Criterion-level grading is more stable, but runs still vary.** VLM criterion-level grading of 485 handwritten
   exam answers (2026): fine-tuned Qwen2.5-VL reached QWK 0.73 vs examiner (human pairs 0.55), yet 50–64 % of
   criteria changed marks across five sampled runs. → temperature 0, criterion-level scoring, and visible
   confidence. [arXiv 2609.14284](https://arxiv.org/abs/2609.14284)
4. **Human stays in charge of grouping and final marks.** Gradescope's AI-assisted grading only *suggests* answer
   groups; instructors review, adjust and apply the rubric.
   [Gradescope guide](https://guides.gradescope.com/hc/en-us/articles/24838908062093)

**Consequences for Lara:** the vision model only transcribes; the student's final answer to a definitive question
(true/false, multiple choice, number) is *extracted* by the model and *compared to the key in code*; the model never
sees the key for questions it only has to read (no "reading what it expects"); open questions are scored per rubric
criterion; temperature 0; a second independent reading of every definitive answer on a scan; every suggested mark
is editable and nothing is final until the professor marks the paper reviewed.

## 3. Copying between students — literature

5. **Identical wrong answers are the classic signal.** Two students choosing the *same wrong option* is far rarer
   than choosing the same right one. Harpp & Hogan (1993) EEIC/EIC ratio; Harpp, Hogan & Jennings (1996): with ≥ 30
   questions, class average < 80 % and ≥ 6 exact errors in common, the ratio ≈ 1 flagged suspicious pairs almost
   perfectly; Wollack's ω and the K/K2/S1/S2 indices model the expected number of matching wrong answers under
   independence. Nelson (2006) warns HHJ misses copying from strong students (few errors to share).
   [Harpp & Hogan summary](https://assess.com/harpp-and-hogan-1993-response-similarity-index/),
   [HHJ 1996](https://assess.com/harpp-hogan-and-jennings-1996-response-similarity-index/),
   [Two new statistics to detect answer copying](https://research.utwente.nl/en/publications/two-new-statistics-to-detect-answer-copying/)
6. **Text overlap: k-gram fingerprints.** Schleimer, Wilkerson & Aiken, *Winnowing* (2003), behind MOSS: hash
   word/character k-grams, keep a guaranteed sample; any shared passage longer than k + w − 1 is found. At ≤ 100
   papers we can afford *all* shingles, so we keep the idea (shingles, shared runs) without the sampling.
   [Winnowing](https://sschleimer.warwick.ac.uk/Maths/winnowing.html)
7. **Similarity must be judged against the class, not in absolute terms.** Everyone answers the same questions,
   often from the same lecture notes; shared phrasing that half the class uses is not evidence. (Same reason
   the K-indices condition on the class's answer distribution.) → rarity-weighted overlap and robust z-scores
   against all pairs.
8. **Paraphrased copying keeps the content.** Shared *unusual* content — the same idiosyncratic mistake, the same
   made-up example values, the same skipped questions — survives rewording. → the grader records each answer's
   specific mistakes, and a per-question pass clusters them; pairs sharing rare clusters are flagged.
9. **Document metadata.** Academic-integrity work on contract cheating uses author fields, creation/modification
   dates, editing software and XMP history; XMP `DocumentID` survives "Save as" and identical IDs across two
   students mean one file was derived from the other; a single indication is not proof, several are.
   [ENAI 2022, Johnson et al.](https://academicintegrity.eu/conference/proceedings/2022/johnson_et_al22.pdf),
   [ENAI metadata hints](https://academicintegrity.eu/materials/public/uploads/296/Metadaten_Hinweise_Outsourcing_en.pdf),
   [PDF Association: PDF forensics and the metadata conundrum](https://pdfa.org/presentation/pdf-forensics-and-the-metadata-conundrum/)

## 4. AI-written text — literature

10. **Excess vocabulary.** Kobak et al. (2024/2025) found an abrupt post-ChatGPT rise of *style words* in 14 M
    PubMed abstracts — *delves* (×28), *underscores* (×10.9), *showcasing* (×10.2), *potential, findings, crucial,
    across, additionally, comprehensive, enhancing, exhibited, insights, notably, particularly, within* — 66 % of
    them verbs. [arXiv 2406.07016](https://arxiv.org/abs/2406.07016)
11. **Stylometry works on ~10 sentences, not on fragments.** Function-word types, lemma type-token ratio, POS
    n-grams and punctuation separate human and LLM text at up to 0.98–0.99 accuracy on 10-sentence samples
    (2025); features become unreliable on short passages; AI *editing* of human text leaves
    almost no stylometric footprint (2026). → no verdict below a minimum amount of text; say so in the UI.
    [arXiv 2507.00838](https://arxiv.org/abs/2507.00838), [arXiv 2608.27855](https://arxiv.org/abs/2608.27855)
12. **Em dashes and lexical richness.** Cross-linguistic profiles of ChatGPT-4o show higher lexical richness and
    density, rarer vocabulary and a preference for the em dash. [ACL StyGenAI 2026](https://aclanthology.org/2026.stygenai-1.5.pdf)
13. **Detectors are biased.** Liang et al. (2023): seven detectors flagged 61 % of non-native (TOEFL) essays as AI
    (5 % for native essays) because simple vocabulary has low perplexity. → Lara never calls a score proof, never
    uses "low perplexity" style features, and compares against the class.
    [arXiv 2304.02819](https://arxiv.org/abs/2304.02819)
14. **Invisible characters.** Some OpenAI models were reported (2025) to emit U+202F (narrow no-break space) and
    zero-width characters in long answers; these are not produced by typing. Weak-to-moderate signal; absence
    proves nothing. [futurezone](https://futurezone.at/digital-life/so-entfernt-man-wasserzeichen-aus-chatgpt-texten-unicode-zeichen-entdecken-unsichtbare-ki-chatbot/403034253)
15. **Copy-paste artifacts are near-proof.** Text copied from chat assistants can carry leftovers: "As an AI
    language model", "I hope this helps", ChatGPT citation markers (`contentReference[oaicite:…]`, `turn0search…`),
    `utm_source=chatgpt.com` on links, markdown asterisks and headings in a Word document.
16. **Statistical watermarks cannot be checked without the vendor's key.** SynthID-Text / Kirchenbauer-style
    watermarks bias token choice; detection needs the generator's secret. Lara says so instead of pretending.
17. **Images can carry provenance.** C2PA manifests (JUMBF boxes) in JPEG/PNG/PDF; a generative image carries a
    `c2pa.created` action with IPTC digital source type `trainedAlgorithmicMedia`.
    [C2PA guidance](https://spec.c2pa.org/specifications/specifications/2.3/guidance/Guidance.html)
18. **Hidden prompts work both ways.** A professor caught 32 of 35 students with a white-text instruction in an
    exam prompt ("mention Madagascar"); conversely, students hide white text in submissions to manipulate AI graders.
    [report](https://letsdatascience.com/news/professor-uses-hidden-prompt-to-flag-ai-cheating-32bb2575),
    [Too Easily Fooled?](https://arxiv.org/abs/2508.13214) → Lara reads only *visible* text, reports hidden text as
    a finding, and treats all student text as data.

**Consequences for Lara:** the AI-likeness score is a noisy-OR of explained signals (artifacts, invisible
characters, excess style vocabulary in English and Greek, em-dash rate on typed text, formulaic structure,
over-elaboration relative to the class, the grader's own reading), damped when there is little text, shown with
its evidence and a standing caution. Handwritten papers get no punctuation-based signals (a pen does not
distinguish an em dash from a hyphen).
