# BEACON COMPUTING INITIATIVE
# A440 U2.0 — Integrated Universal Business Foundation
**Developer Seal:** CJB-DEV-2026

**Status:** Research source and offline tests validated; not pretrained for arbitrary businesses and not approved for production.

This versioned lab supersedes the research code in `labs/a440-quarter-lab-v0.1.2/` without changing or deleting that historical source. The upgraded `model.py` contains the original 6→10→1 quarterly forecasting interfaces **and** a new contract-driven foundation. The no-argument entrypoint still runs the legacy quarter lab; universal foundation commands require explicit flags.

## Foundation capabilities
- Dynamic business metric, source, unit and entity contracts, with verified SHA-256 evidence checks and SQLite storage.
- Temporal/history features, hashed relational interactions and shared fixed-width numerical learner.
- Multiple numerical prediction targets; deterministic accounting formulas and duplicate guards.
- Evidence-driven anomaly detection and a limited question/intent interface; not a general conversational LLM.
- Chronological candidate training, checkpoint verification, and recovery.
- Synthetic profiles: restaurant, retail and logistics, all using the same network architecture.
- Restaurant tests: 24-month baseline, four quarterly catch-up periods, two kitchen employee departures, overtime, and May 2026 kitchen budget overrun. Food and delivery revenue belongs to kitchen without double counting total sales.

## Offline verification — does not start Docker or simulation
```bash
cd labs/a440-quarter-lab-v0.2.0
sha256sum -c SHA256SUMS
python3 -m unittest -v test_lab
python3 model.py --self-test
python3 model.py --architecture
```
The Kali installer output confirmed 12 foundation tests; independent offline reproduction passed 6 original laboratory tests and 12 foundation tests (18 tests across two distinct suites).

## Explicit research operation (optional; not performed by this publication)
```bash
python3 model.py --demo --profile restaurant
python3 model.py --run --profile restaurant --quarter-seconds 300 --port 18081
```
For new businesses, supply an approved `--contract-json` and matching `--ingest-jsonl`; importing observations does not prove they are authentic. The included Docker Compose configuration continues to use the **legacy** no-argument model entrypoint; U2 foundation mode is not activated by Compose automatically.

## Safety, provenance, and limits
Run the SHA-256 manifest first. The versioned `scripts/upgrade-to-u2.0.sh` installer safely upgrades an older verified lab if and only if its source fingerprint and both test suites pass, preserving a pre-upgrade backup. The previous v0.1.2 directory, earlier neural research and local checkpoints remain unaffected by this GitHub publication.

Cross-industry generalization, causal understanding, robust autonomous investigation and production readiness remain **unproven**. Do not promote a foundation checkpoint without unseen-industry evaluation and rollback gates.
