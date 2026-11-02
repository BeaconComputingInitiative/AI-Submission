# BEACON COMPUTING INITIATIVE
# BCIPitch — A440 Neural Research

**Developer Seal:** CJB-DEV-2026
**Experiments:** M2.1, M2.2, M2.3
**Status:** Experimental CPU benchmarks

## M2.1 — Controlled minibatch comparison

| Strategy | Mean Test MSE | Std. deviation | Mean time (s) |
|---|---:|---:|---:|
| baseline32 | 0.00346239 | 0.00035345 | 0.2606 |
| random8 | 0.00488433 | 0.00089891 | 0.2458 |
| octet8 | 0.00453530 | 0.00074140 | 0.2489 |

M2.1 compares conventional batching and feature-balanced
eight-entry groups with equal optimizer-step budgets.
Equal steps do not imply equal examples processed.

## M2.2 — Learned harmonic tournament

| Model | Parameters | Mean Test MSE | Mean time (s) |
|---|---:|---:|---:|
| baseline8 | 1249 | 0.00466150 | 0.2995 |
| harmonic_octet | 8513 | 0.00340111 | 0.5933 |

M2.2 introduces the learned 8 → 4 → 2 → 1 hierarchy.
The original harmonic network has more parameters
than its reference model.

## M2.3 — Parameter matching and relational learning

| Task | Model | Parameters | Test MSE | Permutation delta |
|---|---|---:|---:|---:|
| independent | baseline | 2641 | 0.00469520 | 0.00000001 |
| independent | harmonic | 2773 | 0.00828696 | 0.01393575 |
| relational | baseline | 2641 | 0.06681668 | 0.00000002 |
| relational | harmonic | 2773 | 0.07640760 | 0.04526705 |

## Interpretation and limitations

- Findings concern synthetic numerical tasks only.
- Parameter matching is approximate.
- The study uses a limited number of seeds.
- Octet ordering may affect the harmonic architecture.
- No results establish enterprise-scale performance.
- The recorded results do not demonstrate a trained LLM.

## Artifact policy

Research source and JSON reports are publishable.
Checkpoint weights remain local during this stage.
Local checkpoint integrity must be verified separately.

**Developer Seal:** CJB-DEV-2026
