# BEACON COMPUTING INITIATIVE
Developer Seal: CJB-DEV-2026

# A440 research development update — 2026-11-05

**Status:** research only; no production authorization. This note summarizes user-reported local execution and verification. Local checkpoint files, downloaded source data and run-specific binaries have **not** been uploaded to GitHub.

## Native temporal foundation and lineage

- Started with a versioned A440 4→32→32→1 Octet foundation. A function-preserving expansion introduced six event-time channels (10 inputs); original inference parity was verified.
- Established history-only daily, weekly and monthly research features: eight daily values, eight weekly observed-day means, eight monthly observed-day means, 16 coverage ratios and seven elapsed daily gaps (**47 additional channels**).
- The expanded **57→32→32→1** native architecture retains all original weights. New input columns were zero-initialized; exact output parity held over 2,048 probes and the 355 retail history vectors.
- The six original temporal channels are **inactive** for calendar reporting-period anchors; such anchors are not verified collection timestamps.
- The 47-channel representation preserves incomplete-period coverage explicitly and does not impute unobserved days.

## Initial retail research result (M2.12.5)

- 355 qualified examples; train/validation/calibration/test: 213/53/35/54.
- Trained **1,504 native first-layer input weights**, with original weights frozen and no adapters.
- Test MAE: **12,311.95** versus prior-eight-observation mean **13,249.56** (about **7.08%** reduction).
- Calibration MAE: **13,988.73** versus baseline **13,753.41** (regression).
- Original candidate checkpoint SHA-256: `b5f8410530fe93817a6d4b6f4b11f38b86199311b3d98a9e6539982367e00a47`.
- Trained retail checkpoint SHA-256: `3e15fcc12175497fad3f44f6f0fde162bc1c663c7d86ee08b614389ddbdb7795`.

## Multi-source automation and dynamic interpretation (M2.12.7–M2.13.3)

- Implemented SHA-gated source enrollment, chronological qualification, day/week/month feature construction, multi-source training and separate research artifacts.
- Implemented a dynamic schema interpreter for field discovery, categorical long-form layouts (e.g. `date,mode,count`), numerical validation and provenance, replacing hard-coded field assumptions. This is **not** yet a universal live environmental interpreter.
- Acquired and audited three daily research series for 2023–2024: MTA subway ridership, NYC 311 request counts, and Open-Meteo ERA5-derived precipitation **reanalysis estimates**, not station observations.
- User-reported execution: all three sources passed validation, audit automatically started training, and the research run completed successfully.
- M2.12.7 shared run: **1,464 qualified examples** (488 per source), 54 epochs completed, best epoch 39, all original model weights frozen and no adapters.
- Local checkpoint: `experiments/A440-M2.12.7-multisource-core-multisource-001/A440-v0.3.2-multisource-research.pt`. Local `SHA256SUMS` verification and report/checkpoint consistency passed.

## Held-out test performance (per domain; lower MAE is better)

| Domain | Prior-eight mean MAE | A440 v0.3.2 MAE | Approx. reduction |
| --- | ---: | ---: | ---: |
| MTA subway (passengers) | 698,020.21 | 456,707.00 | 34.57% |
| NYC 311 (requests) | 1,451.19 | 1,225.46 | 15.56% |
| Open-Meteo ERA5 (mm) | 3.2525 | 3.24175 | 0.33% |

**Limitations:** NYC 311 persistence MAE (1,188.28) is better than A440's 1,225.46 test MAE; precipitation calibration degraded (model 2.54549 vs prior-eight mean 1.78385). Cross-source leave-one-domain-out validation was not performed. Rolling temporal windows can overlap chronological split boundaries. Results are for research, not production or general-purpose forecasting claims.

## Refinement roadmap

1. Keep v0.3.2 immutable as a research reference; do not promote it automatically.
2. Improve intermittent / zero-heavy precipitation modeling and per-domain baseline comparisons.
3. Run leave-one-domain-out and temporal embargo tests; report negative transfer and uncertainty calibration.
4. Expand the adaptive interpreter from acquisition to a consent-scoped, read-only live environmental observation runtime with schema evolution and explicit event-time provenance.
5. Qualify further independent public datasets, then train and evaluate a *new* checkpoint without overwriting prior lineage.
6. Publish source code and reproducible manifests separately from local datasets and trained binaries after source-license and privacy review.

**Principle:** new evidence enters learning **if and only if** authorization, provenance, schema, chronology, privacy and objective-specific quality gates pass. Candidate checkpoint promotion requires an independent evaluation gate.
