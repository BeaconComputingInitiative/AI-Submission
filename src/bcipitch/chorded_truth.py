#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Project: BCIPitch / A440
# Component: M4.2 Chorded Truth Research Engine v0.1.0
# Developer Seal: CJB-DEV-2026
# ============================================================
"""Reconcile source-linked synthetic calculations with M4.1 neural claims.

This demo uses synthetic self-hashed evidence only. Hashes establish data
integrity relative to a stored digest, not authenticity of external sources.
No causal explanations, business conclusions or production promotion.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys

import torch

from learned_truth import LearnedTruth, encode, sequence

ROOT = Path(__file__).resolve().parents[2]
SEAL = "CJB-DEV-2026"
RULES = ("linear", "quadratic", "compound", "periodic")
PATTERNS = ("increasing", "decreasing", "oscillatory")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_evidence(values, source_id, unit="synthetic-units"):
    if len(values) != 8:
        raise ValueError("An M4.2 inference evidence record requires eight observations")
    body = {
        "source_id": source_id,
        "source_kind": "synthetic",
        "unit": unit,
        "points": [{"tick": i, "value": v} for i, v in enumerate(values)],
    }
    body["sha256"] = sha256_bytes(canonical(body).encode("utf-8"))
    validate_evidence(body)
    return body


def validate_evidence(record):
    if not isinstance(record, dict):
        raise ValueError("Evidence must be a dictionary")
    required = {"source_id", "source_kind", "unit", "points", "sha256"}
    if set(record) != required:
        raise ValueError("Evidence schema mismatch")
    if (record["source_kind"] != "synthetic" or
            not isinstance(record["source_id"], str) or
            not record["source_id"].strip() or
            not isinstance(record["unit"], str) or
            not record["unit"].strip()):
        raise ValueError("Only identified synthetic evidence is supported")
    points = record["points"]
    if not isinstance(points, list) or len(points) != 8:
        raise ValueError("Exactly eight observations are required")
    last_tick = None
    for p in points:
        if not isinstance(p, dict) or set(p) != {"tick", "value"}:
            raise ValueError("Malformed observation")
        tick, value = p["tick"], p["value"]
        if isinstance(tick, bool) or not isinstance(tick, int):
            raise ValueError("Ticks must be integers")
        if last_tick is not None and tick <= last_tick:
            raise ValueError("Observation ordering violation")
        last_tick = tick
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Observations must be numerical")
        if not math.isfinite(value) or abs(value) > 1e12:
            raise ValueError("Invalid observation magnitude")
    declared = record["sha256"]
    if not isinstance(declared, str) or len(declared) != 64:
        raise ValueError("Missing evidence digest")
    unsigned = {k: v for k, v in record.items() if k != "sha256"}
    expected = sha256_bytes(canonical(unsigned).encode("utf-8"))
    if declared != expected:
        raise ValueError("Source digest mismatch: possible alteration")
    return True


def scale(record):
    """K01–K08 basic deterministic checks; not the complete Scale library."""
    validate_evidence(record)
    vals = [Decimal(str(p["value"])) for p in record["points"]]
    diffs = [vals[i+1] - vals[i] for i in range(7)]
    change = vals[-1] - vals[0]
    if sum(diffs) != change:
        raise ValueError("Difference invariant failed")
    change_ratio = None if vals[0] == 0 else change / abs(vals[0])
    return {
        "status": "verified_calculation",
        "scope": "synthetic_input_only",
        "source_id": record["source_id"],
        "evidence_sha256": record["sha256"],
        "unit": record["unit"],
        "first": str(vals[0]),
        "last": str(vals[-1]),
        "net_change": str(change),
        "fractional_change_from_abs_baseline": (
            None if change_ratio is None else str(change_ratio)
        ),
        "mean": str(sum(vals) / len(vals)),
        "median": str(statistics.median(vals)),
        "finite_differences": [str(d) for d in diffs],
        "invariants": {
            "strictly_increasing_ticks": True,
            "telescoping_differences": True,
            "source_digest_matches": True,
        },
        "note": "Calculated from a matching synthetic record; no external source authenticity is implied",
    }


def load_verified_model(checkpoint_path):
    checkpoint_path = Path(checkpoint_path).resolve()
    manifest_path = checkpoint_path.parent / "SHA256SUMS"
    if not checkpoint_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Missing M4.1 checkpoint or its SHA256SUMS")
    digest = sha256_file(checkpoint_path)
    entries = [line.split() for line in manifest_path.read_text().splitlines()
               if line.strip() and not line.startswith("#")]
    matching = [row[0] for row in entries if len(row) == 2 and
                row[1] == checkpoint_path.name]
    if len(matching) != 1 or matching[0] != digest:
        raise ValueError("M4.1 checkpoint fails SHA-256 verification")
    saved = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if saved.get("developer_seal") != SEAL or saved.get("architecture") != "A440-M4.1-FourHead-v0.1":
        raise ValueError("M4.1 checkpoint identity mismatch")
    model = LearnedTruth()
    model.load_state_dict(saved["state_dict"], strict=True)
    model.eval()
    return model, digest


def chord(local, comparison, model, model_hash):
    local_math = scale(local)
    comparison_math = scale(comparison)
    if local["unit"] != comparison["unit"]:
        raise ValueError("Comparison units are inconsistent")
    a = [p["value"] for p in local["points"]]
    b = [p["value"] for p in comparison["points"]]
    xa, center, spread = encode(a)
    xb, _, _ = encode(b)
    with torch.no_grad():
        pred = model(torch.tensor([xa], dtype=torch.float32),
                     torch.tensor([xb], dtype=torch.float32))
        scores = {name: torch.softmax(pred[name], dim=1)[0]
                  for name in ("pattern", "comparison", "rule")}
        p_idx = int(scores["pattern"].argmax())
        c_idx = int(scores["comparison"].argmax())
        r_idx = int(scores["rule"].argmax())
        next_norm = float(pred["forecast"][0, 0])
    future_estimate = center + next_norm * spread
    net_change = Decimal(local_math["net_change"])
    pattern_label = PATTERNS[p_idx]
    contradicted = ((pattern_label == "increasing" and net_change < 0) or
                    (pattern_label == "decreasing" and net_change > 0))
    # Oscillation describes shape and cannot be falsified by a single net change.
    pattern_status = "contradicted" if contradicted else "learned_hypothesis"
    findings = [
        {"claim": "observed_net_change", "status": "verified_calculation",
         "value": local_math["net_change"], "evidence_sha256": local["sha256"]},
        {"claim": "L09_pattern", "status": pattern_status,
         "value": pattern_label, "model_score_uncalibrated": float(scores["pattern"][p_idx])},
        {"claim": "L10_context_relationship", "status": "learned_hypothesis",
         "value": "same_rule_family" if c_idx == 1 else "different_rule_family",
         "model_score_uncalibrated": float(scores["comparison"][c_idx])},
        {"claim": "L11_next_observation", "status": "learned_hypothesis",
         "value": future_estimate, "unit": local["unit"],
         "uncertainty": "not_calibrated; point estimate only"},
        {"claim": "L12_candidate_rule_family", "status": "learned_hypothesis",
         "value": RULES[r_idx], "model_score_uncalibrated": float(scores["rule"][r_idx])},
        {"claim": "causal_explanation", "status": "unresolved",
         "value": None, "reason": "No intervention or independent causal evidence supplied"},
    ]
    return {
        "project": "BCIPitch", "model": "A440", "developer_seal": SEAL,
        "milestone": "M4.2", "source_kind": "synthetic",
        "checkpoint_sha256": model_hash,
        "scale": {"local": local_math, "comparison": comparison_math},
        "arpeggio": {"L09": findings[1], "L10": findings[2],
                     "L11": findings[3], "L12": findings[4]},
        "chord": {"findings": findings,
                  "contradictions": [f["claim"] for f in findings
                                     if f["status"] == "contradicted"],
                  "summary": "contradiction_detected" if contradicted else "calculated_facts_with_unverified_learned_claims",
                  "external_market_verified": False,
                  "causality_established": False,
                  "deployment_approved": False},
    }


def evaluate_later_forecast(chord_result, observed_next):
    """Supply an independently held-out ninth point after inference."""
    if isinstance(observed_next, bool) or not isinstance(observed_next, (int, float)) or not math.isfinite(observed_next):
        raise ValueError("Outcome must be finite and numeric")
    forecast = chord_result["arpeggio"]["L11"]["value"]
    return {"status": "observed_synthetic_outcome",
            "forecast": forecast, "actual": observed_next,
            "absolute_error": abs(forecast - observed_next),
            "note": "Outcome supplied after the inference operation; no training performed"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="A440 M4.2 Chorded Truth research demo")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=940)
    args = parser.parse_args(argv)
    try:
        outdir = args.outdir.resolve()
        if outdir.exists() and any(outdir.iterdir()):
            raise FileExistsError(f"Refusing nonempty output directory: {outdir}")
        model, checkpoint_hash = load_verified_model(args.checkpoint)
        rng = random.Random(args.seed)
        cases = []
        for i in range(8):
            rule = i % 4
            local = sequence(rule, 10 + i, rng)
            peer = sequence((rule + (i % 2)) % 4, 20 + i, rng)
            case = chord(make_evidence(local[:8], f"synthetic-local-{i}"),
                         make_evidence(peer[:8], f"synthetic-peer-{i}"),
                         model, checkpoint_hash)
            # Ninth observation only enters after all inference is complete.
            case["later_outcome_evaluation"] = evaluate_later_forecast(case, local[8])
            cases.append(case)
        mae = sum(c["later_outcome_evaluation"]["absolute_error"] for c in cases) / len(cases)
        report = {"project": "BCIPitch", "model": "A440", "milestone": "M4.2",
                  "developer_seal": SEAL, "scenario": "unseen_synthetic_domains",
                  "checkpoint_sha256": checkpoint_hash,
                  "cases": cases,
                  "summary": {"case_count": len(cases),
                              "mean_absolute_forecast_error_original_units": mae,
                              "contradiction_count": sum(len(c["chord"]["contradictions"]) for c in cases),
                              "research_integrity_passed": True,
                              "deployment_approved": False,
                              "limitations": ["Only synthetic self-hashed data",
                                              "Known generating-rule families",
                                              "Uncalibrated model scores",
                                              "No causal identification", "No external market evidence"]}}
        outdir.mkdir(parents=True, exist_ok=True)
        result = outdir / "chorded_truth_results.json"
        result.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (outdir / "SHA256SUMS").write_text(f"{sha256_file(result)}  {result.name}\n", encoding="utf-8")
        print(json.dumps(report["summary"], indent=2))
        print(f"[BCI][PASS] Chorded Truth synthetic demo: {result}")
        print(f"[BCI][PASS] SHA-256: {outdir / 'SHA256SUMS'}")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"[BCI][FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
