#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Project: BCIPitch / A440
# Component: M4.3 Analytical Intelligence Validation v0.1.0
# Developer Seal: CJB-DEV-2026
# ============================================================
"""Evidence challenges, contextual comparisons, forecast accountability.

Only generated synthetic data. This program assesses an M4.1 checkpoint;
it does not modify weights, establish causation, or enable deployment.
Self-computed evidence hashes detect changes relative to stored digests,
not the authenticity of an external source.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import random
import sys

import torch

from chorded_truth import (
    chord, evaluate_later_forecast, load_verified_model, make_evidence,
    scale, sha256_file, validate_evidence,
)
from learned_truth import encode, sequence

SEAL = "CJB-DEV-2026"
MODEL = "A440"
REQUIRED_CONTEXT = ("metric", "period", "basis", "sector", "geography")


def decimal_claim(value):
    """Parse an exact stated decimal, with no float tolerance or bools."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Claim must be a finite decimal")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Claim is not a number") from exc
    if not parsed.is_finite():
        raise ValueError("Nonfinite claim")
    return parsed


def audit_net_change_claim(record, claimed_value):
    """Compare a claimed calculated delta to K04's exact result."""
    facts = scale(record)
    declared = decimal_claim(claimed_value)
    computed = Decimal(facts["net_change"])
    is_equal = declared == computed
    return {
        "claim": "observed_net_change",
        "status": "verified_calculation" if is_equal else "contradicted",
        "declared": str(declared),
        "computed": str(computed),
        "source_id": record["source_id"],
        "source_sha256": record["sha256"],
        "note": "Exact decimal comparison of the declared delta and source-linked calculation",
    }


def compare_contexts(local, peer, local_context, peer_context):
    """Reject incomparable metrics/periods; flag population confounding."""
    local_math, peer_math = scale(local), scale(peer)
    if local["unit"] != peer["unit"]:
        return {"status": "incomparable", "reasons": ["unit_mismatch"], "growth_gap": None}
    if not isinstance(local_context, dict) or not isinstance(peer_context, dict):
        raise ValueError("Comparison contexts must be objects")
    for context in (local_context, peer_context):
        if any(not isinstance(context.get(key), str) or not context[key].strip()
               for key in REQUIRED_CONTEXT):
            raise ValueError("Missing or invalid comparison context")
    blockers = [key + "_mismatch" for key in ("metric", "period", "basis")
                if local_context[key] != peer_context[key]]
    if blockers:
        return {"status": "incomparable", "reasons": blockers, "growth_gap": None}
    confounders = [key + "_mismatch" for key in ("sector", "geography")
                   if local_context[key] != peer_context[key]]
    a, b = Decimal(local_math["first"]), Decimal(peer_math["first"])
    if a <= 0 or b <= 0:
        return {"status": "incomparable", "reasons": ["nonpositive_growth_baseline"],
                "growth_gap": None}
    local_growth = Decimal(local_math["net_change"]) / a
    peer_growth = Decimal(peer_math["net_change"]) / b
    return {
        "status": "qualified_comparison" if not confounders else "conditional_comparison",
        "reasons": confounders,
        "growth_gap": str(local_growth - peer_growth),
        "local_growth": str(local_growth),
        "peer_growth": str(peer_growth),
        "unit": local["unit"],
        "period": local_context["period"],
        "claim": "observed_relative_growth_difference",
        "causality_established": False,
        "local_sha256": local["sha256"],
        "peer_sha256": peer["sha256"],
        "note": "Calculated comparative growth, not a causal or future-trend proof",
    }


def quantile_radius(errors, confidence=0.90):
    """Finite-sample split-conformal radius; exchangeability not guaranteed."""
    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between 0 and 1")
    if not errors or any(isinstance(e, bool) or not isinstance(e, (float, int))
                         or not math.isfinite(e) or e < 0 for e in errors):
        raise ValueError("Expected nonnegative finite calibration errors")
    n = len(errors)
    index = math.ceil((n + 1) * confidence)
    if index > n:
        raise ValueError("Calibration sample too small for requested confidence")
    return sorted(errors)[index - 1]


def demonstrate_controls(model, model_hash):
    """Adversarial control cases. Synthetic injections do not use model weights."""
    positive = make_evidence([10, 11, 12, 13, 14, 15, 16, 17], "m43-source-a")
    peer = make_evidence([20, 21, 22, 23, 24, 25, 26, 27], "m43-source-b")
    good = audit_net_change_claim(positive, "7")
    bad = audit_net_change_claim(positive, "8")
    tampered = json.loads(json.dumps(positive))
    tampered["points"][3]["value"] = 999
    tamper_blocked = False
    try:
        validate_evidence(tampered)
    except ValueError:
        tamper_blocked = True

    context = {"metric": "units_sold", "period": "synthetic-Q1",
               "basis": "net", "sector": "retail", "geography": "test-region"}
    qualified = compare_contexts(positive, peer, context, context)
    mismatch = dict(context, period="synthetic-Q2")
    invalid = compare_contexts(positive, peer, context, mismatch)
    other_sector = compare_contexts(positive, peer, context, dict(context, sector="wholesale"))

    class DeliberatelyWrongPattern(torch.nn.Module):
        def forward(self, a, b):
            n = a.shape[0]
            return {
                "pattern": torch.tensor([[-20.0, 20.0, -20.0]]).repeat(n, 1),
                "comparison": torch.zeros(n, 2),
                "rule": torch.zeros(n, 4),
                "forecast": torch.zeros(n, 1),
            }

    forced = chord(positive, peer, DeliberatelyWrongPattern(), "injected-test-model")
    forced_detected = forced["arpeggio"]["L09"]["status"] == "contradicted"
    model_result = chord(positive, peer, model, model_hash)
    cause_unresolved = model_result["chord"]["causality_established"] is False
    controls = {
        "valid_math_claim_accepted": good["status"] == "verified_calculation",
        "false_math_claim_contradicted": bad["status"] == "contradicted",
        "changed_source_record_blocked": tamper_blocked,
        "matching_context_accepted": qualified["status"] == "qualified_comparison",
        "different_period_blocked": invalid["status"] == "incomparable",
        "different_sector_flagged": other_sector["status"] == "conditional_comparison",
        "injected_model_contradiction_detected": forced_detected,
        "unproven_cause_remains_unresolved": cause_unresolved,
    }
    return {
        "checks": controls,
        "all_passed": all(controls.values()),
        "declarations": {"accurate": good, "contradictory": bad},
        "context_cases": {"qualified": qualified, "period_mismatch": invalid,
                          "sector_mismatch": other_sector},
        "injected_pattern_fixture": {"uses_trained_model": False,
                                     "detected": forced_detected},
        "integrity_note": "Synthetic self-hashes are not third-party authentication",
    }


def collect_cases(model, model_hash, domains, each, seed):
    """Return forecasts + withheld outcomes; the model never receives t=8."""
    rng = random.Random(seed)
    rows = []
    for rule in range(4):
        for j in range(each):
            domain = domains[j % len(domains)]
            peer_rule = rule if j % 2 == 0 else (rule + 1 + rng.randrange(3)) % 4
            local = sequence(rule, domain, rng)
            peer = sequence(peer_rule, domain + 20, rng)
            evidence = make_evidence(local[:8], f"sim-{seed}-local-{rule}-{j}")
            other = make_evidence(peer[:8], f"sim-{seed}-peer-{rule}-{j}")
            answer = chord(evidence, other, model, model_hash)
            forecast = float(answer["arpeggio"]["L11"]["value"])
            first_eight = local[:8]
            _, _, spread = encode(first_eight)
            observed_ninth = float(local[8])
            # Outcome is intentionally examined only AFTER the prediction returns.
            scored = evaluate_later_forecast(answer, observed_ninth)
            context = {"metric": "synthetic_process_output",
                       "period": "synthetic-8-tick-window", "basis": "raw_units",
                       "sector": "generated_maths", "geography": f"synthetic-domain-{domain}"}
            peer_context = dict(context, geography=f"synthetic-domain-{domain + 20}")
            comparison = compare_contexts(evidence, other, context, peer_context)
            correct_rule = (peer_rule == rule)
            predicted_same = answer["arpeggio"]["L10"]["value"] == "same_rule_family"
            rows.append({
                "family": rule, "domain": domain,
                "local_source_sha256": evidence["sha256"],
                "peer_source_sha256": other["sha256"],
                "calculated_difference": str(scale(evidence)["net_change"]),
                "context_status": comparison["status"],
                "comparison_confounders": comparison["reasons"],
                "predicted_rule": answer["arpeggio"]["L12"]["value"],
                "prediction_original_units": forecast,
                "actual_original_units": scored["actual"],
                "normalized_abs_error": abs(forecast - observed_ninth) / spread,
                "absolute_error": scored["absolute_error"],
                "persistence_absolute_error": abs(first_eight[-1] - observed_ninth),
                "linear_absolute_error": abs(2 * first_eight[-1] - first_eight[-2] - observed_ninth),
                "spread": spread,
                "true_peer_same_family": correct_rule,
                "predicted_peer_same_family": predicted_same,
                "model_pattern_contradiction": bool(answer["chord"]["contradictions"]),
                "cause_unresolved": answer["chord"]["causality_established"] is False,
                "outcome_was_withheld": True,
            })
    return rows


def summarize(model, model_hash, calibration_count=32, test_count=32, seed=1430):
    if calibration_count < 3 or test_count < 1:
        raise ValueError("At least 3 calibration and 1 test example per family required")
    if calibration_count > 1024 or test_count > 1024:
        raise ValueError("Example counts must be at most 1024 per family")
    controls = demonstrate_controls(model, model_hash)
    # Distinct domain IDs: M4.1 train=(0..3), validation=(4,5), test=(6,7).
    # New calibration=(8,9), evaluation=(10,11).
    calibration = collect_cases(model, model_hash, (8, 9), calibration_count, seed)
    testing = collect_cases(model, model_hash, (10, 11), test_count, seed + 1)
    radius = quantile_radius([r["normalized_abs_error"] for r in calibration], 0.90)
    n = len(testing)
    def avg(key):
        return sum(row[key] for row in testing) / n
    covered = sum(r["normalized_abs_error"] <= radius for r in testing)
    matched = sum(r["true_peer_same_family"] == r["predicted_peer_same_family"]
                  for r in testing)
    baseline_correct = max(sum(r["true_peer_same_family"] for r in testing),
                           sum(not r["true_peer_same_family"] for r in testing))
    realized = {
        "cases": n,
        "calibration_cases": len(calibration),
        "calibration_domains": [8, 9],
        "evaluation_domains": [10, 11],
        "m41_training_domains": [0, 1, 2, 3],
        "m41_validation_domains": [4, 5],
        "m41_original_test_domains": [6, 7],
        "L11_mae_original_units": avg("absolute_error"),
        "persistence_mae_original_units": avg("persistence_absolute_error"),
        "linear_extrapolation_mae_original_units": avg("linear_absolute_error"),
        "forecast_better_than_persistence": avg("absolute_error") < avg("persistence_absolute_error"),
        "forecast_better_than_linear": avg("absolute_error") < avg("linear_absolute_error"),
        "L10_context_match_accuracy": matched / n,
        "majority_context_baseline_accuracy": baseline_correct / n,
        "L10_better_than_majority": matched > baseline_correct,
        "injected_contradictions_detected": int(controls["checks"]["injected_model_contradiction_detected"]),
        "real_model_pattern_contradictions": sum(r["model_pattern_contradiction"] for r in testing),
        "causal_claims_left_unresolved": sum(r["cause_unresolved"] for r in testing),
        "forecast_interval": {
            "method": "split_conformal_absolute_normalized_error",
            "nominal_coverage": 0.90,
            "calibrated_normalized_radius": radius,
            "observed_held_out_coverage": covered / n,
            "mean_interval_width_original_units": avg("spread") * 2 * radius,
            "reliability_note": "Domains 8-9 calibrate and 10-11 evaluate; independent domains may violate exchangeability, so no guaranteed coverage claim",
        },
        "evidence_controls_passed": controls["all_passed"],
        "deployment_approved": False,
    }
    quality_passed = (realized["forecast_better_than_persistence"]
                      and realized["forecast_better_than_linear"]
                      and realized["L10_better_than_majority"]
                      and realized["forecast_interval"]["observed_held_out_coverage"] >= 0.85)
    return {"controls": controls, "summary": realized,
            "quality_targets_met": quality_passed,
            "interpretation": "Research metrics only; passing these tests does not approve deployment",
            "examples": testing[:8]}


def run(checkpoint, outdir, calibration_count=32, test_count=32, seed=1430):
    checkpoint = Path(checkpoint).resolve()
    outdir = Path(outdir).resolve()
    if outdir.exists() and any(outdir.iterdir()):
        raise FileExistsError("Refusing nonempty output directory")
    model, model_hash = load_verified_model(checkpoint)
    result = summarize(model, model_hash, calibration_count, test_count, seed)
    report = {"project": "BCIPitch", "model": MODEL,
              "milestone": "A440-M4.3", "version": "0.1.0",
              "developer_seal": SEAL, "checkpoint_sha256": model_hash,
              "scenario": "independent_synthetic_environment_challenge",
              "research_integrity_passed": result["controls"]["all_passed"],
              "deployment_approved": False,
              "limitations": [
                  "Synthetic self-hashed evidence; no independent source attestation",
                  "Known four rule families; cannot infer general algorithm discovery",
                  "Uncalibrated neural classification scores",
                  "Conformal coverage not assured across shifted nonexchangeable environments",
                  "Comparative trend is descriptive, not a causal conclusion",
                  "No external market data, real tenant records or automatic model promotion",
              ], **result}
    outdir.mkdir(parents=True, exist_ok=True)
    report_path = outdir / "analytical_validation_results.json"
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (outdir / "SHA256SUMS").write_text(
        f"{sha256_file(report_path)}  {report_path.name}\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="BCIPitch A440 M4.3 synthetic analytical audit")
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--calibration-per-rule", type=int, default=32)
    parser.add_argument("--test-per-rule", type=int, default=32)
    parser.add_argument("--seed", type=int, default=1430)
    args = parser.parse_args(argv)
    try:
        report = run(args.checkpoint, args.outdir,
                     args.calibration_per_rule, args.test_per_rule, args.seed)
        print(json.dumps({"milestone": report["milestone"],
                          "controls": report["controls"]["checks"],
                          "quality_targets_met": report["quality_targets_met"],
                          "summary": report["summary"],
                          "deployment_approved": False}, indent=2))
        print(f"[BCI][PASS] M4.3 report integrity manifest: {args.outdir / 'SHA256SUMS'}")
        return 0 if report["research_integrity_passed"] else 1
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"[BCI][FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
