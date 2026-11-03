# BEACON COMPUTING INITIATIVE
**A440 U2.1 — Shared, Business-Independent Foundation**
Developer Seal: `CJB-DEV-2026`

## Changed
- U2.1 SHA-256 verified architecture, with U2.0 no-argument runtime and legacy function compatibility.
- Separate residual heads per tenant+metric, alongside learned shared semantic-role heads. This provides specialized outputs while retaining transfer structure; it does **not** prove cross-industry generalization.
- Temporal features for prior 3, 6, and 12-month changes and rolling context. Always based only on available historical observations.
- SHA-256 checked append-only individual employee shift records with employee IDs, roles, scheduled, actual, and overtime hours. Synthetic restaurant catch-up generated shift records only from month 24 onward; baseline monthly totals do not imply available employee-level records.
- Two kitchen employee departures simulated in January and March 2026. May 2026 kitchen budget overrun and kitchen revenue attribution remain verified formula results.
- Six-month research candidate gate using two-quarter rolling validation and per-metric regression veto. The panel is **not a truly untouched holdout**, because selection and historical reuse can occur across successive candidate evaluations.
- Generic deterministic metric comparisons and source provenance, without invented causal conclusions.
- U2.1 checkpoint version label corrected. U2.0 saved checkpoints deliberately **not** automatically migrated or overwritten; new default state directory.

## Testing, without running a simulation
The source passed 6 original legacy tests, 20 original extended tests, 12 U2.0 foundation tests, and 12 U2.1 enhancement tests: **50/50**. All tests were run locally against this generated source using isolated temporary stores. No business pretraining, Docker deployment, or live business connectors were invoked.

## Install using one guarded script
Download `BCI-A440-U2.1-One-Script-Upgrade.sh` to `~/Downloads`. Verify its SHA-256 using the supplied `.sha256` file, then run:

```bash
cd ~/Downloads
sha256sum -c BCI-A440-U2.1-One-Script-Upgrade.sh.sha256 && bash BCI-A440-U2.1-One-Script-Upgrade.sh
```

Your installation must match the recorded U2.0 SHA-256 before replacement:
`5fe7d953b2c863deb4d5e1e05ddc684306089bffec79fdebc56d5d6102725f7d`.

The installer stages the upgraded model and test files, checks integrity, runs 38 + 12 offline tests, copies and hashes the U2.0 source to `~/Documents/A440-U2.1-Backups/`, and **if and only if everything passes**, atomically installs U2.1. It writes `A440-U2.1-SHA256SUMS` inside the Quarter Lab. It does not start the simulation.

## Verify installation

```bash
cd ~/Documents/A440-Docker-Lab/bci_quarter_lab
sha256sum -c A440-U2.1-SHA256SUMS
python3 model.py --architecture
```

## Research limitations
A fixed-width hashed encoder + role+metric heads is not a pretrained universal business LLM. Individual staff overtime is observable only for intervals with actual shift records. The simulated shift ledger has no real personnel information. Hashes do not authenticate external producers. Candidate validation requires separately locked unseen business and time holdouts, uncertainty analysis and regression tests before production approval.

## Model file SHA-256
`b79c6c73ff85a5ed3c71cc094930827cb260fb82f7b59e4a85730a2d8124976e`
