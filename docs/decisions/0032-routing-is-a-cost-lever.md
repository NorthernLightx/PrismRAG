# ADR 0032: Routing is a cost lever, not an accuracy lever

Status: accepted (supersedes [0013](./0013-routing-is-the-accuracy-lever.md))

## Context

ADR 0013 concluded that per-query routing is where retrieval accuracy comes
from, and the README's headline (+35 % recall@10) rests on it. That conclusion
was drawn on MMLongBench-Doc: 20 documents, 107 in-corpus queries, and a
confidence interval of roughly ±0.06. At that width a +0.05 effect is
undetectable, so "routing is the lever" was consistent with the data without
being tested against the obvious alternative: always running both legs.

MMDocIR ([2501.08828](https://arxiv.org/abs/2501.08828)) has the power the old
set lacked: 1,127 queries over 218 documents and 4,837 pages at
`--page-cap 60`, with page **and** bounding-box evidence labels. Its documents
overlap MMLongBench-Doc's, so every number below is reported on the 1,029
queries whose documents are absent from the committed MMLongBench baseline
corpus. Contamination turned out not to matter: the 98 overlapping queries score 0.759
against 0.800 clean, slightly *worse*, so there is no tuning advantage to
subtract.

## Decision

Fuse text and visual on every query. Keep the classifier, but treat it as a
switch for saving work rather than for gaining accuracy. On this hardware it
does not currently save any.

## What was measured

Retrieval, recall@10, n=1,029, identical corpus and reranker across arms:

| arm | recall@10 | median latency |
|---|---|---|
| text-only | 0.460 ±0.030 | 4,265 ms |
| classifier router | 0.621 ±0.030 | 5,860 ms |
| **always-hybrid** | **0.784 ±0.025** | 5,843 ms |
| visual-only | 0.800 ±0.024 | 983 ms |

Always-hybrid beats the classifier by **+0.163 (+26 %)**, better on 191 queries
and worse on 3. The loss is entirely in the routing decision: on the 555
queries the classifier sends to the text leg it scores 0.436 where the visual
leg alone reaches 0.784, while on the 572 it routes to hybrid it matches
visual-only to within 0.010.

**The cost defence fails too.** Router and always-hybrid have the same median
latency, 5,860 ms against 5,843 ms. The reranked text leg runs on every query
either way and accounts for ~4.3 s of that; once pages are pre-encoded (ADR
0028) the visual leg's marginal cost is close to zero. Routing therefore buys
half the recall for the same wall clock.

Answer correctness, n=150 stratified, `gemma-4-26b` reading, graded with
`judge_answer_correctness`:

| subset | n | always-hybrid | router | p |
|---|---|---|---|---|
| retrieval differs | 18 | **0.333** | 0.000 | 0.016 |
| retrieval identical | 132 | 0.294 | 0.317 | 0.18 |

The retrieval gain does convert, but only on the ~12 % of queries where routing
changes what is retrieved; on the rest the arms receive identical context and
tie, which is the control. Full-set delta is +0.020 and not significant:
averaging over the 88 % that cannot differ buries the effect. Scaling the
discordant-slice gain to the corpus projects roughly **+0.06** absolute answer
correctness. That is a projection from n=18, not a measurement.

## Three ways it could have been an artefact

Each of these could have explained the result away. None did:

- **Query mix.** Reweighting to 100 % factual questions still leaves
  visual-only ahead, 0.739 against text's 0.472. The corpus being
  figure-heavy is not the cause.
- **Corpus text density.** On the text-richest quartile of documents the gap is
  *widest* (0.833 against 0.508), so thin text layers are not the cause either.
- **Page budget.** The text leg's ten chunks collapse to 8.28 distinct pages
  while the visual leg returns ten. Handicapping the visual leg to eight pages
  costs it 0.019 of a 0.34 gap; at four pages it still scores 0.730.

## Consequences

- The shipped default should fuse both legs. `--force-route hybrid` exists on
  `eval_run` to measure it; the serving default is a separate change.
- The README's "+35 %" remains true of the router against text-only, and is now
  the weaker of two available numbers.
- The reader, not retrieval, is the binding constraint: even handed the right
  page it answers correctly a third of the time. That agrees with
  [0025](./0025-structured-extraction-augments-reading.md).
- Untested and not claimed: prose corpora with no layout to exploit, corpora
  past ~5k pages, and per-query cost when every query needs a vision-capable
  reader.
