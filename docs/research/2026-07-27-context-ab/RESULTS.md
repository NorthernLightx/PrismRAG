# Feed-more A/B: k=10 vs k=5 pages (2026-07-27)

Tests the surviving generation-side lever from the 2026-05-29 campaign: recall@10
exceeds recall@5 by ~0.08 on the committed depth-50 dump, and the May page-count
sweep (k=1/3/5, gemma-4-31b) was monotonic — so feeding the top-10 pages instead
of top-5 should convert some of that extra gold-page presence into answers.

## Setup

- Retrieval: committed depth-50 w1 dump (`data/eval/runs/depth50-20260525-015216`),
  same fused ranking for both arms; only the page cut differs (top-5 vs top-10
  unique pages, rank order).
- Generation: `nvidia/nemotron-nano-12b-v2-vl:free` via OpenRouter, both arms.
  The May reference model (`gemma-4-31b-it:free`) was upstream-rate-limited for
  a second consecutive day, so the A/B ran on the strongest free vision model
  available. Same prompt, temperature, and path per arm.
- Scoring: official three-stage protocol, `gemma3:4b` extractor (local Ollama),
  consistent with every prior number in this series.
- Runs: `exp_k5_nemotron[_scored].json`, `exp_k10_nemotron[_scored].json`
  (148/149 answered per arm; 1 free-tier failure each).

## Result — NULL

Paired on the 108 answerable queries both arms answered:

| arm | mean score |
|---|---|
| k=5 | 0.1959 |
| k=10 | 0.1952 |

Delta **−0.0007**, 95 % CI **[−0.062, +0.061]** — dead flat, well inside the
±0.08 judge-noise kill band. 94 of 108 queries scored identically; 8 improved,
6 worsened. Doubling the pages fed changed nothing.

## Read

The kill criterion fires: no default changes from this experiment. Top-5 stays.

One honest caveat limits the scope of the kill. The 12B reader converts pages
at ~0.20 absolute — far below the 31B's 0.35 in May — so a floor effect can't
be excluded: a model this weak may fail the extra gold pages for the same
reasons it fails the original five, masking a lift a stronger reader would
show. The May evidence for feed-more (monotonic k-sweep, whole-doc +0.12) came
from the 31B tier. So the precise claim is: **feed-more is dead at the
free-tier 12B class, and unproven above it.** Re-running this A/B once a
31B-class free vision model is reachable again is the cheap follow-up; nothing
ships on the assumption it would win.
