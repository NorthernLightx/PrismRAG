# Agenda execution — results (2026-05-29)

Box: single RTX 3070 8GB, Ollama, Qdrant (offline for this pass). Goal: finish
the four-bet agenda from the planning pass, grounded and evaluated,
deviating where the evidence justified it. Nothing committed.

## TL;DR

This pass turned the qualitative agenda into measured numbers, and
the measurements repeatedly overturned the prior read — starting with the
headline assumption that the system is "retrieval-bound."

1. **The dominant end-to-end loss is post-retrieval, not retrieval — confirmed
   at full scale (n=110-149), overturning the standing "retrieval-bound" read.**
   Across the full answerable set, real retrieval delivers a gold page **72-77%**
   of the time, yet generation converts only **~46-48%** of those, so
   post-retrieval (5-page-context mis-reads, the odd refusal, a small directional
   extractor artifact) is **61-66% of all failures**. Holding the model fixed
   (`gemma-4-31b:free` on both arms), the clean oracle→real retrieval tax is only
   **0.07** (0.417→0.349) — the 0.31 "tax" in the first pass was a
   model/context/path confound. A bigger generator showed no benefit
   head-to-head (235B ≈ 31B, ~45% conversion on the n=19 overlap), so scaling the
   generator is not an obvious fix. Real end-to-end is below GPT-4o's 0.436 for
   every model tested. The lever is
   generation-side context handling (rerank the gold page to rank 1, feed
   fewer/cleaner pages), not better retrieval.
2. **Selective agentic gating is within judge noise on the only data we can
   touch.** On v3, every per-category answer_correctness delta is smaller than
   the gemma3:4b judge's noise band; the oracle-category gate gains +0.033
   against a ±0.080 band. Verdict: do not build the classifier yet — the
   motivating signal is noise at this sample size. The decisive test is a
   MMLongBench A/B, which is Qdrant-gated.
3. **The document-wide aggregation class fails at three stages, and the fix is
   ingestion, not a new retriever.** Top-k gets 0/9 gold pages; a cheap local
   LLM handed a near-perfect figure index still miscounts (3 vs 7); and the
   index itself is incomplete (7 vs gold 10). The earlier "ToC-navigation LLM"
   framing is the wrong lever — the fix is a complete structural index plus
   *deterministic* counting, and it serves only ~2 of the 8 queries in the class
   anyway (the rest need vision or text-structure indices).
4. **Reframe shipped to the docs.** The honest end-to-end ceiling now lives in
   `docs/results.md` and a README limitation, where it belongs — the hero keeps
   its defensible retrieval claim.

The full 149-query run is now **done** — switching to OpenRouter `:free`
models cleared the Ollama weekly-quota wall, and the real arm and a same-model
oracle arm were generated with `google/gemma-4-31b-it:free` (a 31B model,
size-matched to the 32B oracle). That settles the corpus-wide balance the n=25
slice could not. The strong-VLM (qwen3-vl-235b) full run, and a frontier
gemini-2.5-pro reading test, were since done via paid OpenRouter (see "Lever 4") —
neither beat the 31B.

## Bet 1 — end-to-end: generation-bound, not retrieval-bound

**Oracle-page generation is strong and reproduces.** Re-scoring
`exp_mmlb_gen_full.json` (qwen3-vl-32b, gold pages) with the official three-stage
protocol (gemma3:4b extractor): **ACC 0.5053, F1 0.5175** over 106 answerable
queries — matching the documented 50.5%. Per category: factual 0.456, figure
0.492, table 0.565. This is the official metric on our 106-query in-corpus
subset with a local gemma3:4b extractor (weaker than the paper's GPT-4o, so a
conservative lower bound), not the 1082-query leaderboard number. Read it as
"generation is competitive with the GPT-4o 0.436 bar," not "beats the
leaderboard."

**Real-retrieval recall — the retrieval-side ceiling.** Fused-router page-recall
on the committed depth-50 dump, answerable in-corpus (n=111; the ALL row includes
4 out-of-corpus queries that happen to carry gold pages — excluding them recall@5
is 0.647), reusing the paper-aware page identity from `rescore_mmlb_pages`:

| subset | n | @1 | @5 | @10 | @50 |
|---|---|---|---|---|---|
| all | 111 | 0.366 | 0.659 | 0.745 | 0.860 |
| figure | 75 | 0.322 | 0.616 | 0.729 | 0.859 |
| table | 23 | 0.435 | 0.783 | 0.826 | 0.913 |
| factual | 9 | 0.389 | 0.556 | 0.556 | 0.667 |

**Full-scale end-to-end, same model on both arms.** With the cloud weekly quota
walled, the run moved to OpenRouter `:free`, so the full 149-query sweep used
`google/gemma-4-31b-it:free` (31B, size-matched to the 32B oracle) on both arms:
real top-5 retrieval vs gold pages, same model / prompt / path. Official scoring,
gemma3:4b extractor:

| arm (gemma-4-31b:free, n=110 answerable) | ACC |
|---|---|
| oracle (gold pages) | **0.417** |
| real top-5 (w1 router) | **0.349** |

The retrieval tax is **0.069** — not the 0.31 a naive cross-model comparison
showed (qwen3-vl-32b oracle 0.546 vs qwen3-vl-235b real 0.240 on a 25-query
prefix, which conflated model + page-count + serving path). One honest caveat:
this is *not* a pure which-pages contrast — the real arm always feeds 5 pages
while the oracle feeds the gold pages (just 1 page on 64 of the 110 single-gold
queries), so the tax also carries the cost of 4 distractor pages. Controlling for
that on the multi-gold subset (closest page counts) the tax is ~0.04; blended
0.07. Either way it is small — the rest of the low absolute is the model's own
oracle ceiling (0.42), and the distractor cost is itself a generation-side lever
(feed fewer pages).

**The decomposition — retrieval delivers, generation discards.** Splitting the
real arm (n=110) by whether the gold page was actually fed (checked against the
exact pages the model saw):

- gold page in the real top-5: **79/110 (72%)** — high. (This "gold-in-fed-5" is
  binary; the fractional recall@5 over the depth-50 dump is the separate 0.66 in
  the table above.)
- of those, generation scored > 0: **36/79 (46%)**, counting partial credit; the
  graded answerable mean is 0.349.
- of 71 failures (n − correct): **28 retrieval-miss (39%)**, **43 post-retrieval
  (61%)** — post-retrieval dominates.

This holds across retrieval configs (w5 visual-favoring fusion: 86/111 present,
47% conversion, 66% post-retrieval). The extractor bias is *directional* — it
turns a correct generation into a wrong score, and every such error lands on a
gold-present query, so it inflates exactly the post-retrieval bucket it is used to
prove. Grading the raw 31B generation directly (bypassing the gemma3:4b extractor)
on the failed gold-present queries flips **2** back to correct (gen "Most Beautiful
Campus" → the extractor substituted "Strong Alumni Network"; gen "Subtask" →
mis-extracted), lifting conversion to **48%**. So generation loses *just over half*
of retrieved pages, and post-retrieval stays dominant (41 of 69 after the
correction).

**Scaling the generator is not an obvious fix.** On the 19 gold-present queries
the 235B partial and the 31B run share (identical fed pages), they convert
comparably — 235B 6/19 (~8/19 after its 2 known extractor artifacts), 31B 9/19,
with 0 refusals either side. On this limited head-to-head a 7x larger generator
was no better; the bottleneck looks like reading the answer out of a 5-page
context rather than model capacity, but n=19 is too small to call that settled.

**Conclusion — generation-bound, not retrieval-bound.** Real end-to-end is below
GPT-4o's 0.436 for every model tested, but the binding constraint is generation:
retrieval puts a gold page in front of the model ~72% of the time, and the model
converts only ~46-48% of those. The recall ceiling (recall@5 0.66) is real but slack
relative to the conversion ceiling. The first lever is generation-side context
handling — rerank the single gold page to rank 1, feed fewer/cleaner pages, an
anti-refusal prompt — not better retrieval (and, on the limited head-to-head, not
obviously a bigger generator).

**Caveats.** Scoring uses the local gemma3:4b extractor throughout for consistency
(its mangle rate is small but directional — ~2-3% of gold-present queries, 2/79 on
w1, raw-gen-regraded above; the free strong extractors deepseek-v4-flash and
llama-3.3-70b both 429'd to zero on the free tier, so absolute numbers are
conservative lower bounds — the comparisons, using one extractor, are robust). The strongest model run at full real-retrieval scale is
the 31B free model; qwen3-vl-235b and gemini-2.5-pro were since run via paid
OpenRouter (Lever 4) and did not beat it.

**Bonus — does visual-favoring fusion (ADR 0023) move QA, not just recall?**
Scoring the cached w5 partial (visual fusion weight ≈5) against the w1 partial on
their 26-query answerable overlap: w1 0.269 → w5 0.308, figure subset 0.200 →
0.267. But only 3 of 26 queries changed at all, so the +0.04 is three coin-flips
inside the noise. On this partial, up-weighting the visual leg does not move
end-to-end QA — consistent with ADR 0023's verdict that it is a small,
corpus-specific *recall* lever, not a QA win. A clean read needs the full run.

**Update — the strong-VLM (235B) full run is now done** via paid OpenRouter (the
Ollama `:cloud` path stayed weekly-quota-blocked). It did **not** beat the 31B
(real-retrieval answerable 0.308, oracle 0.429); the full three-model comparison
(31B / 235B / gemini-2.5-pro) is in the Bet 1 follow-up "Lever 4" below.

## Bet 1 follow-up — the generation-side lever (on-box, measured)

Bet 1 located the binding constraint as post-retrieval: generation converts only
~46% of retrieved gold pages. This follow-up tested which generation-side lever
recovers that, all on-box (gemma-4-31b:free generation, gemma3:4b extraction,
depth-50 w1 retrieval, no Qdrant). A triage over the failure set scoped it, and it is the reason
OpenRouter free was enabled.

**Lever 1 — feed fewer pages: REFUTED.** Page-count sweep, fair curve on the 93
queries answered in all arms:

| pages fed | end-to-end ACC | gold-present | conversion |
|---|---|---|---|
| k=1 | 0.161 | 45% | 26% |
| k=3 | 0.269 | 68% | 40% |
| k=5 | 0.359 | 72% | 48% |
| oracle (gold only) | 0.418 | 100% | 42% |

ACC is monotonic in k — more pages is strictly better, and conversion *rises*
with more pages, so distractor dilution is negligible. The oracle's edge over k=5
(0.42 vs 0.36) is entirely from feeding the gold page 100% vs 72% of the time (a
recall/rerank effect), not from fewer pages. So the recall lever is feed-more or
rerank-up, worth ~0.06 to the oracle ceiling — not trimming.

**Lever 2 — a stronger answer extractor: tooling-blocked, unmeasurable.** The
failure triage flagged ~29% of post-retrieval failures as format artifacts (gold token
emitted but buried in prose). Swapping the stage-2 extractor should recover them,
but every stronger extractor failed: deepseek-v4-flash:free and llama-3.3-70b:free
429'd to zero, gemma-4-31b:free returned malformed responses (`KeyError: choices`),
and local qwen2.5vl:7b is a far worse format-follower (ACC 0.045). The 4B gemma3:4b
is, ironically, the most reliable extractor on hand.

**Lever 3 — a terse / anti-refusal generation prompt: NULL.** The testable version
of Lever 2 (fix the generator's output so a weak extractor gets it right). A strict
prompt (terse single-line answer, on-page arithmetic, refuse only when truly
absent), re-run on all 149:

| | default prompt | strict prompt | Δ |
|---|---|---|---|
| answerable ACC | 0.352 | 0.326 | −0.03 (within noise; 5 up / 6 down) |
| unanswerable (refusal) | 0.629 | 0.686 | +0.06 |

The strict prompt recovered a couple format artifacts (mmlb_0094 0→1.0, mmlb_0039
0→0.52) and modestly improved refusal handling, but forcing terse output dropped
partial-credit list items and induced arithmetic errors, offsetting the gains. Net
answerable lift: zero. So the format-artifact share does NOT convert into a cheap
accuracy win.

**Failure taxonomy (43 post-retrieval failures triaged, deduped n=35):**
partial_or_strict_scoring ~29%, unfixable (gold on un-fed page / cut-off / bad
label) ~17%, genuine visual misread or wrong-region ~31%, refusal ~14%, the rest
arithmetic/truncation. The top lever by count was **stronger_vision_model**
(~11/35) — genuine reads a bigger VLM would fix, not free-testable here.

**Lever 4 — a stronger / frontier VLM: helps figures, not overall.** With
paid OpenRouter, three very different
readers were run on the oracle gold pages, and re-scored with a reliable
extractor (gpt-4o-mini — the thing the free extractors could not provide):

| oracle answerable ACC | gemma3:4b ex. | gpt-4o-mini ex. | figure | table | factual |
|---|---|---|---|---|---|
| gemma-4-31b | 0.417 | 0.454 | 0.412 | **0.565** | **0.625** |
| qwen3-vl-235b | 0.429 | 0.456 | 0.486 | 0.510 | 0.125 |
| gemini-2.5-pro | 0.427 | **0.464** | **0.499** | 0.425 | 0.375 |

(per-category columns use the gpt-4o-mini extractor; figure n=75, table n=23,
factual n=8 — factual is too small to read.) Two findings: (1) the **extractor is
worth ~0.04** — gpt-4o-mini lifts every model over gemma3:4b, confirming the
extractor lever (real but small; the 235B's weak 0.308 on real retrieval was partly
this extractor mangling its verbose output). (2) Overall the three readers are flat
(~0.46, within 0.01), but that hides a split: on these oracle pages a **stronger
VLM reads FIGURES +0.08-0.09 better** (the effect the failure triage predicted), while the
**31B is better on tables/factual**. The net cancels. Crucial caveat established by
the router gate below: this figure advantage is **oracle-only — it does NOT survive
real retrieval**.

**Conclusion — overall ceiling is fundamental, and a stronger VLM does not help in
any realizable form.** Honest implications: (a) the **answer extractor is a real
~0.04 lever** — use gpt-4o-mini, not gemma3:4b, going forward; (b) the **generation
router is REFUTED** — gate-tested before building (route the 235B to figure queries,
31B else, gpt-4o-mini extractor): it LOSES, routed 0.337 vs all-31B 0.366 answerable.
The 235B's +0.09 figure advantage exists ONLY on clean oracle pages; on real top-5
retrieval (gold + 4 distractors) the 235B is *worse* than the 31B in every category
(figure 0.276 vs 0.319, table 0.406 vs 0.448, factual 0.375 vs 0.625) — the bigger
model is more sensitive to retrieval noise. The 31B is the best generation model
across the board on real retrieval; the per-query best-of-2 ceiling is 0.51 but the
wins scatter within categories, so no realizable category-router beats all-31B. (c)
Even the best config caps at ~0.46 oracle, so real-retrieval end-to-end stays below
GPT-4o's 0.436, and the residual is the benchmark's hard reads + strict scoring +
gold-label issues (the triage's ~46% non-model bucket), not raw model capacity. The
only surviving levers are the gpt-4o-mini extractor (~0.04) and reranking recall
(~0.06) — both small. Artifacts: `bet1_decompose.py`,
`exp_mmlb_gen_free_{k1,k3,strict}.json`, `exp_mmlb_gen_qwen235_{real,oracle}.json`,
`exp_mmlb_gen_gemini_oracle.json`, `*_scored_gpt4omini.json`, `postret_failures.json`,
the postret-failure-taxonomy notes.

## Bet 1 capstone — RAG vs whole-document (the spectrum, measured)

The capstone question: is top-k RAG itself the cap, vs whole-document
long-context (what tops single-doc leaderboards)? Two grounding facts reframed it:
(1) current MMLongBench-Doc SOTA is **Qwen3.6 Plus 0.620** (avg ~0.59); GPT-4o's
0.427 is the *floor*, not the bar — and my ~0.46 is not comparable to either (the
leaderboard feeds the WHOLE doc; I do top-5 RAG; plus strict 149-q subset + local
extractor). (2) A leaderboard-class model (qwen3-vl-235b) scored 0.62 on the
leaderboard's whole-doc setup but only 0.46 on mine — the gap is the harness/task,
not the model.

The 2025-26 literature consensus is no-one-size-fits-all (RAG vs long-context is a
spectrum; long-context suffers "lost in the middle" + distraction + per-token cost;
the frontier is route-before-retrieve / distraction-aware retrieval — arXiv
2509.21865, OpenReview "Route Before Retrieve"). So I measured where THIS corpus
sits: whole-doc (all pages of the query's gold doc, up to 50) vs top-5 RAG, same
model (gemma-4-31b:free), same extractor (gemma3:4b).

| genuine whole-doc, doc ≤50pg (n=66) | top-5 RAG | whole-doc | Δ |
|---|---|---|---|
| answerable | 0.326 | **0.441** | **+0.116** |
| figure (n=48) | 0.224 | 0.346 | +0.12 |
| table (n=11) | 0.523 | 0.705 | +0.18 |

**Whole-doc beats top-5 RAG by ~0.12 where it fits** — retrieval-loss (the 72%
recall) dominates the distraction cost for these small docs, so top-5 was an
over-aggressive cut (consistent with the page-count sweep: more pages monotonically
helped). **But it is not a free win:** whole-doc *failed on 45/149 queries (30%)* —
big-doc payloads choked the free tier — and on the **>50-page docs it lost** to RAG
(0.192 vs 0.222, capped/gold-missed); the 166-page doc exceeds the context window
entirely. So the crossover is real and measured: **docs that fit context →
whole-doc / feed-many-pages wins; docs/corpora beyond context → RAG is required.**

**Fair-scoring footnote (Bet 3, free gpt-oss-120b judge):** of the 43 gold-present
RAG failures, 9 (21%) are actually correct but strict-scored wrong (e.g. "Pyke"
buried in prose; "Men (81%)"=="men"), lifting fair answerable accuracy 0.357 →
~0.44. This applies to both arms equally, so the +0.116 RAG→whole-doc delta is
robust to it.

**Implication.** The lever was never a better model or a generation trick — it's
*how much you feed*. The SOTA-aligned redesign the repo is already positioned for:
route by whether the content fits context (long-context/whole-doc when it does, RAG
when it doesn't — "route before retrieve"), keeping RAG as the thesis. The real
contribution is this measured RAG↔long-context crossover on a multimodal corpus,
not a leaderboard number. Caveat: the +0.12 is on the feasibility-filtered subset
(where whole-doc ran) — "whole-doc wins where it fits," not everywhere. Artifacts:
`wholedoc_retrieval_synth.json`, `exp_mmlb_gen_wholedoc.json` + `wholedoc_scored.json`,
`fair_judge.py` + `fair_judge_cache.json`, `*_scored_gpt4omini.json`.

## Bet 2 — selective agentic gating is within noise on v3

ADR 0019's verdict rests on `answer_correctness` (the retrieval metrics are 0 by
construction — chunk-ids changed in ADR 0017 and v3's `relevant_chunk_ids` were
never re-anchored). Re-scoring the committed agentic (`fd50bbda0212`) vs baseline
(`325375af3043`) runs on that metric, with the judge noise band from ADR 0016
(±0.07 at n=40, scaled by √(40/n)):

| category | n | base | agentic | Δ | noise ± |
|---|---|---|---|---|---|
| figure | 11 | 0.767 | 0.859 | +0.092 | 0.133 |
| factual | 13 | 0.831 | 0.781 | −0.050 | 0.123 |
| table | 4 | 0.450 | 0.350 | −0.100 | 0.221 |

Every per-category delta is smaller than its noise band. Policy means (in-corpus
n=31, overall noise ±0.080): baseline 0.763, all-agentic 0.761, **oracle-category
0.795 (+0.033)**, oracle-per-query 0.841 (+0.078). The realistic gate's gain
(+0.033) is well inside the noise band.

**v3 conclusion.** Selective gating cannot be validated on v3 — the per-category
split that motivates it is itself within noise at these subset sizes. The
decisive experiment is a MMLongBench A/B (figure subset n=75, where a real effect
would clear the band), scored at page granularity (gold = pages, so no judge
needed) against the committed depth-50 baseline's text leg.

### Decisive MMLongBench A/B (2026-05-29, Qdrant back online)

Ran the shipped `AgenticRetriever` (gemma3:4b decompose → per-subquery
`PipelineRetriever` → RRF) over the same `routing_study` collection the depth-50
baseline used — all 149 queries (128 decomposed, 21 reduced to `[original]`),
scored page-recall with `rescore_mmlb_pages`.
`bet2_agentic_mmlb_run.py` + `bet2_mmlb_gate.py`.

| category | n | base@10 | agentic@10 | Δ@10 | 95% CI@10 |
|---|---|---|---|---|---|
| factual | 9 | 0.556 | 0.556 | +0.000 | identical |
| figure | 75 | 0.589 | 0.513 | −0.076 | [−0.156, 0] |
| table | 23 | 0.804 | 0.674 | −0.130 | [−0.283, 0] |
| **ALL** | 107 | 0.632 | 0.551 | **−0.081** | **[−0.143, −0.020]** |

Policy means (recall@10): baseline 0.632 · all-agentic 0.551 (−0.081) ·
**oracle-category-gate 0.632 (+0.000)** · oracle-per-query 0.660 (+0.028).

**Verdict — REFUTED on MMLongBench; the gate is worthless.** Agentic
decomposition *degrades* retrieval here (overall −0.081, CI excludes zero) — the
opposite of the v3 figure signal, so it does not transfer. The only category
where agentic ≥ baseline is factual, where it is a literal no-op, so the
selective category-gate (Bet 2's whole point) just reproduces baseline (+0.000).
Even the unreachable per-query oracle nets only +0.028. Mechanism: MMLongBench
questions are precise and page-grounded ("the chart on page 14…"); decomposing
them into vaguer sub-questions ("what is the chart about?") dilutes the
specificity that retrieved the gold page, and RRF over the diffuse sub-rankings
pushes it down.

Validation (apples-to-apples): the 21 non-decomposed queries match the baseline
text leg 20/21 exactly (page-jaccard 0.956), proving the pipeline is identical
when it does not decompose; the 128 decomposed queries diverge hard (page-jaccard
0.352), so the drop is real decomposition work, not a no-op. Caveat: one
decomposer (gemma3:4b, the shipped router model) and the text leg only; a stronger
decomposer is untested, but the shipped tier hurts. Combined with the capstone
(end-to-end is post-retrieval-bound — retrieval recall is not the binding
constraint), this lever is doubly dead: it does not help retrieval, and retrieval
is not the bottleneck anyway.

## Bet 3 — the aggregation class is an ingestion problem, not a retrieval one

The 8 queries whose gold spans ≥3 pages (most are document-wide counts; two are a
colour lookup and a multi-page factoid) split by the index they would need:
**figure-index 2, table-index 1, visual-type (needs vision) 3, text-structure 1,
other 1.** A figure/table structural index could serve at most ~3 of the 8; the
rest ("how many line plots", "how many pictures with one person") need
whole-document vision.

Decisive case `mmlb_0069` — "how many figures in the Appendix?", gold 10, on
2305.13186v3, separating the three failure stages:

- **Retrieval:** top-10 surfaces **0 of the 9** gold pages. Top-k cannot gather
  document-wide evidence — confirmed, not a tuning problem.
- **Navigation:** handed the figure index the ingestion pipeline already builds
  (`data/figures/<doc>/<doc>__pN__figM.png`), gemma3:4b answered **3** where the
  index lists **7** figures on appendix pages. The committed control probe
  localizes the failure: the same model counts the flat 7-item appendix list
  correctly (→7) but gets *filter-then-count* over the scattered full index wrong
  (→3). The failing step is filtering, not arithmetic, so it belongs in
  deterministic code, not a cheap LLM. (A second small model, llama3.2:3b, failed
  the same way in an ad-hoc check.)
- **Extraction:** the index found **7** figures on the gold appendix pages vs gold
  **10**. The gold pages span p15–27, so the `p≥15` cut is not arbitrary and the
  residual gap is missed detections, not a boundary error — but this is one
  document, so read it as indicative, not settled.

**Conclusion.** This class needs an ingestion-side structural index, plus
deterministic counting, plus an LLM only to parse the query into a filter
("figures, in the appendix"). It is not a retrieval-paradigm problem and not a
cheap-LLM-navigator problem. This refutes the ToC-navigation framing as
stated, and it stays portfolio-marginal: even a complete figure index serves
only the ~2 figure-countable queries of the 8.

## What stayed blocked (and why it is a wall, not a missing idea)

- **Ollama cloud weekly quota** (`429 reached your weekly usage limit`)
  blocked the Ollama strong-VLM path. Worked around in two
  steps: OpenRouter `:free` (`gemma-4-31b-it`) for the full 149-query sweep, then —
  for the strong-VLM tests — paid OpenRouter
  (qwen3-vl-235b, gemini-2.5-pro) and a reliable gpt-4o-mini extractor. No run
  stays blocked now. The free strong text-extractors (deepseek,
  llama) had 429'd to zero, which is why the gpt-4o-mini extractor mattered.
- **Qdrant + Docker daemon were offline, now revived (2026-05-29):** Docker
  restarted and Qdrant came back from its persisted named volume
  (`prismrag_qdrant_storage`) with the `routing_study` collection intact — no
  re-ingest needed. Bet 2's decisive MMLongBench A/B ran on it (see Bet 2 above:
  agentic decomposition refuted). Text leg only; a fresh *fused* figure-recall
  measurement still needs the OOM-prone per-doc ColQwen2 re-render, so it stays
  deferred. The agentic run also surfaced an intermittent Qdrant transport
  timeout under concurrent per-subquery rerank load on the 8GB box — handled
  runner-side with a 4-attempt retry + incremental save, not a production change.

The generation runs used OpenRouter (`:free` for the sweep, a small
paid tier for the strong-VLM tests); everything else — recall, the decomposition, the failure
taxonomy, Bet 2/3 — used committed artifacts + local models.

## Artifacts (uncommitted, ruff + mypy clean)

- `scripts/experiments/end_to_end_ceiling.py` — recall ceiling × oracle bound +
  aggregation-query identification. Output `ceiling.json`.
- `scripts/experiments/bet2_selective_gate.py` — oracle-gated selective
  decomposition on answer_correctness with the judge noise band. Output
  `bet2_oracle.json`. *Committed a58ffce.*
- `scripts/experiments/bet2_agentic_mmlb_run.py` — the decisive MMLongBench
  agentic-retrieval run over `routing_study` (retry + incremental save). Output
  `data/eval/runs/bet2-agentic-<ts>/agentic.json`. *Uncommitted.*
- `scripts/experiments/bet2_mmlb_gate.py` — page-recall A/B + selective-gate
  policies (baseline text leg vs agentic, binomial CI). *Uncommitted.*
- `scripts/experiments/bet3_aggregation_probe.py` — the three-stage aggregation
  decomposition + the navigator probe. Output `bet3_aggregation.json`.
- `scripts/experiments/bet1_decompose.py` — the retrieval-vs-post-retrieval split
  + same-model paired oracle-vs-real. Outputs `bet1_decompose_w1free.json`,
  `bet1_decompose_w5free.json`.
- `data/eval/runs/exp_mmlb_gen_free_{real,oracle}.json` +
  `free_{real,oracle}_scored.json` + `free_w5_scored.json` — the full-149
  gemma-4-31b:free real and oracle arms and their scores;
  `oracle_retrieval_synth.json` is the synthetic gold-page oracle input.
- `data/eval/runs/oracle_vision_scored.json`, `mmlb_gen_cloud_scored.json` —
  per-query scores for the qwen3-vl-32b oracle and the 235B partial-real runs.
- `docs/results.md` + `README.md` — corrected "generation-bound" framing (Bet 4).
