# BEACON COMPUTING INITIATIVE

**Component:** A440 / BCIPitch 20-Endpoint Integration Test  
**Developer Seal:** `CJB-DEV-2026`  
**Recorded date:** 2026-11-02  
**Evidence provenance:** User-reported Kali Linux workstation outputs; independent reproduction of the Docker run is not claimed.

## Test scope

A synthetic financial simulation with **20 individually configured HTTP endpoint services**, one shared model service, eight baseline historical quarters and an accelerated five-minute quarter clock. Expected reconciled metrics: sales, units, returns, costs, net sales, contribution margin. All figures are invented for research; no real-world business endpoint or private information was ingested.

## Observed milestones

1. Docker Engine `28.5.2+dfsg4` and Docker Compose `2.40.3-3` were available on the user workstation. Compose configuration validation passed.
2. An initial host-side unit test failed because the source used Docker-only `/state`; the state-directory environment override repaired the local test. Six unit tests passed and the refreshed manifest verified.
3. The 20 endpoint services and model ran inside the staged Compose lab. The model's initial `/ask` reported `status: running`, 20 required source contributions, baseline eight historical quarters, and `model_version: 1`.
4. After the first completed live quarter (quarter index 8), the service reported `model_version: 2`, `latest_period: live`, 20/20 reconciled sources and the next-quarter sales forecast.
5. After the second completed live quarter (quarter index 9), the service reported `model_version: 3` and 10 total quarterly records.
6. A read-only state audit reported four saved model-parameter groups (`b`, `c`, `v`, `w`) and a successful SHA-256 check of `a440_state.json` against its stored manifest. The hash for the v3 saved state was `44d0b847f27980469e1458125a4fdb8048b3f07ea71546f467e13ff50120a198` (not a published artifact; no independent attestation).

## Forecast accountability (USD, synthetic)

| Forecast issuer | Quarter index | Prior forecast | Actual | Absolute error | Absolute percentage error |
|---|---:|---:|---:|---:|---:|
| v1 | 8 | $377,937.35 | $378,946.69 | $1,009.34 | 0.266% |
| v2 | 9 | $394,679.72 | $418,388.00 | $23,708.28 | 5.667% |

The quarter-9 **persistence baseline** would forecast $378,946.69, for an absolute error of $39,441.31; the v2 model forecast had lower error for that one quarter. This observation does **not** demonstrate statistically reliable skill or improvement from training.

**Two-quarter WAPE:** $(1,009.34 + 23,708.28) / (378,946.69 + 418,388.00) × 100 ≈ **3.10%**.

## What was and was not validated

**Supported by the recorded evidence:** a functioning initial baseline query, two completed accelerated live-quarter reports, self-consistent 20-source reconciliation reported by the model, version counter progression, saved-state integrity, and matching previously issued forecasts to newly reported outcomes. Local six-test suite passed after the state-path patch.

**Not yet established:** independent digital identity for endpoints; tamper-evident, external evidence attestation; business-data correctness; isolation of customer tenants; weight-change proof per version; immutable checkpoints; validation-controlled promotion; generalization beyond the deterministic synthetic source generator; or reproducible independent Docker CI on a clean host. Source hashes are not cryptographic signatures. Since `/quarter/<index>` is generated deterministically on demand, the lab relies on the model clock—not endpoint-side embargo—for the no-future-data policy.

## Deployment posture

**Research only.** `deployment_approved: false`. The model currently trains in place after each quarter and lacks rollback; it must not be used for real enterprise decisions. A440-N1.2's Conductor validation and checkpoint lineage remain future work.
