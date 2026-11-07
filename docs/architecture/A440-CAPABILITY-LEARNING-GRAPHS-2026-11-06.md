# BEACON COMPUTING INITIATIVE
# BCIPitch / A440 - Evidence and Capability Learning Graphs

**Developer Seal:** `CJB-DEV-2026`  
**Status:** M2.16.3 Stage 2 tests PASS; Stage 3 real-data integration HOLD  
**Date:** 2026-11-06  
**Neural training:** NOT AUTHORIZED  
**Neural mapping:** NOT QUALIFIED

This document describes BCIPitch / A440 evidence qualification and neural capability-learning research only. It does not authorize training or imply a deployed or integrated management layer.

## 1. Evidence pipeline and tested foundation

```mermaid
flowchart TD
    A["Authorized public data"] --> B["Typed contracts, provenance and source hashes"]
    B --> C["3,414 evidence atoms"]
    C --> D["Original immutable semantic graph"]
    D --> E["374 supported temporal bonds"]
    C --> F["Deterministic Semantic Bond Engine"]
    F --> G["Stage 2: 63 tests and 14 subtests passed"]
    F -. "No newly sealed real-data graph" .-> H["Stage 3: HOLD"]
    H -. "Only after qualification and SHA-256" .-> I["Versioned qualified graph"]
    classDef pass fill:#073c49,stroke:#00c7db,color:#fff
    classDef hold fill:#512133,stroke:#da7389,color:#fff
    class C,E,G pass
    class H hold
```

| Source (2025) | Accepted atoms | Qualification |
| --- | ---: | --- |
| USGS earthquakes M5+ | 2,130 | Irregular, logarithmic magnitude events |
| NYC TLC monthly reports | 908 | Mixed monthly metrics, review-only for neural feature compilation |
| USGS streamflow | 365 | Daily mean, nonadditive physical rate |
| BLS unemployment | 11 | Monthly percent rate, missing marker excluded |
| **Total** | **3,414** | **No new neural training authorization** |

Locally reported Stage 1 integrity verified the original 3,414-atom / 374-temporal-bond snapshot. The last Stage 3 audit found **one snapshot only**, no integration report, no additional verified real-data bond types. The snapshot and data are local research artifacts, not published in this documentation commit.

## 2. Semantic bonding is not neural learning

```mermaid
flowchart TD
    A["Candidate evidence relationship"] --> B{"Same tenant, identity and claim scope?"}
    B -- "No" --> R["Reject with reason"]
    B -- "Yes" --> C{"Units, timestamps and measures compatible?"}
    C -- "No" --> R
    C -- "Yes" --> D{"Origin independence and uncertainty qualified?"}
    D -- "Yes" --> E["Evaluate relation / contradiction"]
    D -- "No" --> U["Unknown or rejected; do not infer truth"]
    A --> F["Explicit hypothesis plus verification test"]
    F --> V["UNVERIFIED hypothesis"]
    E --> X["Explain and link source evidence"]
    U --> X
    R --> X
    V --> X
    classDef pass fill:#073c49,stroke:#00c7db,color:#fff
    classDef hold fill:#512133,stroke:#da7389,color:#fff
    class E,X pass
    class R,U,V hold
```

Local inspection found `Identity`, `Tolerance`, `MeasurementOrigin`, `BondEngine.shared/evaluate/build`, `relationship_id`, and `explain`. The Stage 2 suite passed **63 tests, 14 subtests, zero reported failures**. These tests exercise deterministic evidence rules; they do **not** prove neural generalization or real-data bonding beyond the original temporal relationships.

## 3. Planned neural capability learning

```mermaid
flowchart TD
    A["New immutable qualified evidence snapshot"] --> B["Labeled positive and negative relation examples"]
    B --> C["Entity-, source-, and chronology-separated partitions"]
    C --> D{"Authorization, provenance, leakage and evaluation gates pass?"}
    D -- "No" --> H["HOLD: no training"]
    D -- "Yes" --> E["Copy preserved A440 foundation"]
    E --> F["Conductor: train isolated research candidate"]
    F --> G["Independent blind evaluation on unfamiliar evidence"]
    G --> I{"Transfer and safety gates passed?"}
    I -- "No" --> J["HOLD: do not promote"]
    I -- "Yes" --> K["Eligible for explicit promotion review"]
    classDef hold fill:#512133,stroke:#da7389,color:#fff
    class H,J hold
```

This is the proposed M2.16.4 methodology. It has **not been executed or validated**. A440 currently uses a native research feedforward model with 128 inputs (96 historical plus 32 semantic), followed by 32, 32, and 1 output units. The evidence graph is external to the model, **not** a graph neural network. No checkpoint promotion can occur merely because a rule-based evaluation passed.

## 4. Current acceptance ledger

| Gate | Observed result | Decision |
| --- | --- | --- |
| Four typed public data sources | 3,414 accepted atoms | Local ingestion PASS |
| Initial semantic graph | 374 supported temporal bonds | Original integrity PASS |
| Deterministic bond tests | 63 tests and 14 subtests PASS | Stage 2 test gate PASS |
| Real-data bond integration | No new snapshot/report in latest audit | Stage 3 HOLD |
| Generalizable neural relationship learning | No qualified training/evaluation result | M2.16.4 NOT STARTED |

**Acceptance if and only if:** Each new real-data relationship resolves to qualified evidence and a sealed source reference; any neural learning is separately authorized and independently evaluated; model lineage, tenant isolation and rollback are preserved. Otherwise hold.

## 5. Integrity

This file and its README index entry are recorded in `docs/architecture/A440-CAPABILITY-LEARNING-SHA256SUMS` with SHA-256 hashes calculated on the published UTF-8 bytes. Source research data and neural checkpoints remain unchanged by this documentation update. The Developer Seal `CJB-DEV-2026` is project metadata, not a cryptographic signing key.

*Observe accurately. Preserve faithfully. Analyze transparently. Communicate securely. Act deliberately.*
