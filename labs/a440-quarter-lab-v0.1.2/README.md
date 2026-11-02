# BEACON COMPUTING INITIATIVE

**Project:** BCIPitch / A440 — 20-Endpoint Quarterly Learning Laboratory  
**Version:** v0.1.2 · Research Integration Milestone  
**Developer Seal:** `CJB-DEV-2026`  
**Status:** **Successful user-reported synthetic integration test; NOT production-ready**

## What was demonstrated

Twenty separately configured synthetic endpoint containers emit sales, units, returns, and cost measurements. A shared model container reconciles all twenty records into quarterly net sales and contribution margin, constructs per-source training windows, and trains a compact **6→10→1 neural predictor**. It begins with eight historical quarters (two simulated fiscal years) and closes one additional simulated quarter every **300 seconds** by default. It issues the next-quarter and fiscal-year sales projections through `/ask`.

**This is an end-to-end research integration demonstration, not a secure commercial product.** Source SHA-256 values verify payload self-consistency, not independent source authentication. The lab has no enterprise identity system, tenant separation, model rollback, independent holdout evaluation, or governed candidate promotion. The trained model is **not** the previously verified M4.1 encoder or the proposed Neural Evidence Field. Quarterly model versions are advanced after training, but weight improvements were not independently established.

## Published files

- `endpoint.py` — synthetic, deterministic source-specific API (20 services).
- `model.py` — baseline ingestion, evidence reconciliation, simple neural training, forecasts, persistence, and JSON API. The `A440_STATE_DIR` environment override permits non-root local testing; Docker uses `/state`.
- `test_lab.py` — six local unit/integration tests, including 20-source identity, arithmetic, mutation detection, and forecasting.
- `Dockerfile` — Python 3.12 image running as a non-root user.
- `compose.yaml` — original reproducible 21-service topology; **not recommended alone for resource-constrained hosts**, as it requests restarts and does not cap resources.
- `compose.safe.yaml` — optional research limits (no automatic restarts; 384 MiB model, 96 MiB per endpoint; CPU and PID caps).
- `scripts/start-safe.sh` — preflight, source verification, one shared image build, 5-at-a-time endpoint launch, health checks, and model activation last.
- `docs/INTEGRATION-TEST-2026-11-02.md` — exact observed milestones and limitations.
- `SHA256SUMS` — hashes of distributable source, configuration, tests, docs, and launcher.

**No customer data, company credentials, private checkpoint weights, real model-state volumes, or host-specific logs are published.**

## Verify and run on a clean research machine

Prerequisites: Docker Engine, Docker Compose v2 plugin, Python 3, and a free local TCP port 8080. Docker must be accessible to the current user. The installer does not install dependencies or stop any other project.

```bash
cd labs/a440-quarter-lab-v0.1.2
sha256sum -c SHA256SUMS
bash scripts/start-safe.sh
```

Run the launcher as a **separate Bash process**, not by sourcing it. Its `set -e` must never be pasted into an interactive shell. The script uses the distinct Compose project `bci-a440-quarter-lab`, refuses to replace an existing lab instance, builds one shared image, starts endpoint containers in four batches, and then activates the model. It checks the model API **inside the container** because the isolated network may interfere with host-local port publishing.

To query through the container API even if host networking is isolated:

```bash
docker compose -p bci-a440-quarter-lab -f compose.yaml -f compose.safe.yaml exec -T model python -c 'import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen("http://127.0.0.1:8080/ask",timeout=5)),indent=2))'
```

To stop only this lab (without deleting its Docker volume):

```bash
docker compose -p bci-a440-quarter-lab -f compose.yaml -f compose.safe.yaml stop
```

**Do not use `docker compose down -v` on research state you intend to preserve.** This initial lab's current implementation does not provide verified restart/resume semantics; restarting may reinitialize baseline simulation. Do not restart an existing workstation experiment merely to use the published package.

## Evidence

See [the November 2 integration report](docs/INTEGRATION-TEST-2026-11-02.md). The user reported two complete live quarters, `20 of 20` reconciliation, versions 1→2→3, and quarter-level forecast errors of 0.266% and 5.667%. Results are synthetic, and two observations are insufficient to prove improving forecast skill.

**Further engineering milestone:** A440-N1.2 must establish immutable checkpoint lineage, training-loss histories, candidate/production separation, chronological evaluation and Conductor-governed promotions before any stronger learning claims can be made.
