# BEACON COMPUTING INITIATIVE
# A440 Neural Variant — N1 Agent-Integrated Evidence Field

**Developer Seal:** CJB-DEV-2026  
**Status:** Research prototype specification / synthetic integration validated; Docker runtime unverified in this environment.  
**Architecture naming:** A440 Neural Variant (A440-NV). Historical Tonal Network Model publication filenames remain unchanged solely for provenance.

## Computational contract

A440-NV is a contract-driven Neural Evidence Field (NEF) composed of a versioned foundational model, a persistent Observed State, a separately represented Projected State, and sparse learnable relation edges. Nine reusable collection-interface identities can serve any number of contract-approved endpoints. A Data Acquisition Contract binds every endpoint to exactly specified metric type, unit, range, cadence, retention, tenant identity and learning eligibility. Eight-element Octets, when used, describe temporal context rather than a maximum of eight source identities.

**Evidence rule:** Source-specific observations enter the append-only ledger if and only if contract and integrity checks pass. One day's Chorded Truth is constructed if and only if its required distinct evidence inputs are complete and deterministic business consistency checks pass. Twenty different metrics are twenty distinct contributions; they are not twenty independent attestations of the same underlying fact.

**Learning rule:** Working evidence updates immediately, but neural parameters change if and only if an isolated candidate passes validation and regression gates. Forecasts remain separate from verified outcomes. Train/validation and frozen holdout windows are specified before evaluation.

## N1 Docker research lab — initial contract

- 20 independent Docker endpoint containers, each responsible for exactly one synthetic daily metric and an immutable endpoint ID.
- 9 logical acquisition-agent identities, assigned through 20 fixed simulated contracts.
- 730-day synthetic backfill (2024-11-01 to 2026-10-31): 14,600 individual observations and 730 complete daily Chords.
- Chronological training 2024-11 through 2026-04; validation 2026-05 through 2026-07; reserved 2026-08 through 2026-10 holdout, excluded from training, selection, and operational comparison.
- Fiscal calendar begins November 1. Simulated FY2027 Q1 (2026-11-01 through 2027-01-31) completes in **300 real seconds** by default; first 255 seconds collect observations; remaining 45 seconds reserved for candidate learning. A late or incomplete run delays publication.
- Sparse, nonlinear 27-input/27-node learnable relation graph, trained for causal next-day net-sales prediction, with original/approved parameter initialization. Trained candidate is promoted only if it beats daily/weekly persistence comparators and satisfies a historical regression guard.
- A440 introduces itself on GET /welcome (all 20 metric names), reports progress on GET /clock, presents a reconciled report on GET /report and answers quarterly sales/next quarter/fiscal-year questions using deterministic source-grounded text via GET /ask.
- SQLite WAL append-only evidence registry, independent source identity, SHA-256 event-content checks, source manifests, archived versioned candidates and SHA-256-verified active checkpoint recovery.
- **Research restrictions:** synthetic-only numbers; no authenticated external enterprise feeds, no claim of general conversational intelligence, no independently calibrated annual-forecast intervals. SHA hashes detect changes but are not source signatures.

## Verification record

Local execution environment (not Docker): 11 unit tests passed; 20 independent endpoint processes completed an accelerated 24-second FY2027-Q1 cycle. In that deterministic simulation, net sales were $797,215.53, candidate next-quarter projection $713,845.51, FY2027 projection $2,973,216.88. The candidate passed **local synthetic** validation and promotion gates; the original holdout remained unused. Restart restored the approved SHA-256-checked model state and retained the quarter report. These figures do not demonstrate external generalization or deployed enterprise functionality.

**Delivery:** Standalone source package should be installed beneath `labs/a440-neural-variant-20/`, preserving all older milestone sources and checkpoint directories. Docker startup requires validation on the customer's local Docker Compose v2 host; do not assume the container build or network connectivity has been verified by the local Python tests.

**Next gates:** Docker Compose smoke test, independent source authentication, endpoint permission enforcement, actual fiscal-calendar evaluation, forecast calibration, audited lineage, controlled model rollback, and a new locked generalization evaluation plan.
