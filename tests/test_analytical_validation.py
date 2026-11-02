# BEACON COMPUTING INITIATIVE
# Component: A440 M4.3 Analytical Validation Tests
# Developer Seal: CJB-DEV-2026
import copy
import json
from pathlib import Path
import sys

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "bcipitch"))
from analytical_validation import (
    audit_net_change_claim, compare_contexts, collect_cases,
    demonstrate_controls, quantile_radius, run, summarize,
)
from chorded_truth import make_evidence, sha256_file
from learned_truth import LearnedTruth


def context(**changes):
    d = {"metric": "units", "period": "Q1", "basis": "net",
         "sector": "retail", "geography": "test"}
    return dict(d, **changes)


def samples():
    a = make_evidence([10, 11, 12, 13, 14, 15, 16, 17], "a")
    b = make_evidence([20, 21, 22, 23, 24, 25, 26, 27], "b")
    return a, b


def test_exact_claim_and_contradiction():
    a, _ = samples()
    assert audit_net_change_claim(a, "7")["status"] == "verified_calculation"
    assert audit_net_change_claim(a, 70)["status"] == "contradicted"
    for value in (True, float("nan"), "Infinity", None):
        with pytest.raises(ValueError):
            audit_net_change_claim(a, value)


def test_bad_source_digest_rejected():
    a, _ = samples()
    a = copy.deepcopy(a)
    a["points"][3]["value"] = 50
    with pytest.raises(ValueError, match="digest mismatch"):
        audit_net_change_claim(a, 7)


def test_aligned_context_and_gap():
    a, b = samples()
    answer = compare_contexts(a, b, context(), context())
    assert answer["status"] == "qualified_comparison"
    assert abs(float(answer["growth_gap"]) - (0.35)) < 1e-10
    assert answer["causality_established"] is False


def test_context_blockers_and_warnings():
    a, b = samples()
    assert compare_contexts(a, b, context(), context(period="Q2"))["status"] == "incomparable"
    assert compare_contexts(a, b, context(), context(metric="profit"))["status"] == "incomparable"
    assert compare_contexts(a, b, context(), context(sector="transport"))["status"] == "conditional_comparison"
    with pytest.raises(ValueError):
        compare_contexts(a, b, context(), {})
    c = make_evidence([1,2,3,4,5,6,7,8], "c", unit="seconds")
    assert compare_contexts(a, c, context(), context())["status"] == "incomparable"


def test_finite_sample_quantile():
    assert quantile_radius([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], .9) == 10
    assert quantile_radius([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], .5) == 6
    with pytest.raises(ValueError):
        quantile_radius([1, 2], .9)
    with pytest.raises(ValueError):
        quantile_radius([1, -3, 4], .5)


def test_injected_wrong_model_and_unresolved_causality():
    controls = demonstrate_controls(LearnedTruth(), "mock-hash")
    assert controls["all_passed"]
    assert controls["injected_pattern_fixture"]["uses_trained_model"] is False
    assert controls["checks"]["injected_model_contradiction_detected"]


def test_outcome_is_not_in_the_eight_input_observations():
    rows = collect_cases(LearnedTruth(), "mock-hash", (10, 11), 3, seed=14)
    assert len(rows) == 12
    assert all(r["outcome_was_withheld"] for r in rows)
    assert all(r["cause_unresolved"] for r in rows)
    assert all(r["context_status"] == "conditional_comparison" for r in rows)


def test_run_writes_report_and_refuses_overwrite(tmp_path):
    checkpoint_dir = tmp_path / "trained"
    checkpoint_dir.mkdir()
    checkpoint = checkpoint_dir / "learned_truth_candidate.pt"
    torch.save({"developer_seal": "CJB-DEV-2026",
                "architecture": "A440-M4.1-FourHead-v0.1",
                "state_dict": LearnedTruth().state_dict()}, checkpoint)
    (checkpoint_dir / "SHA256SUMS").write_text(
        f"{sha256_file(checkpoint)}  {checkpoint.name}\n")
    out = tmp_path / "reports"
    report = run(checkpoint, out, 3, 3, seed=24)
    assert report["research_integrity_passed"] is True
    assert report["deployment_approved"] is False
    assert report["summary"]["cases"] == 12
    digest, filename = (out / "SHA256SUMS").read_text().split()
    assert digest == sha256_file(out / filename)
    with pytest.raises(FileExistsError):
        run(checkpoint, out, 3, 3, seed=24)


def test_preserves_original_m41_checkpoint(tmp_path):
    checkpoint_dir = tmp_path / "trained"
    checkpoint_dir.mkdir()
    checkpoint = checkpoint_dir / "learned_truth_candidate.pt"
    torch.save({"developer_seal": "CJB-DEV-2026",
                "architecture": "A440-M4.1-FourHead-v0.1",
                "state_dict": LearnedTruth().state_dict()}, checkpoint)
    before = sha256_file(checkpoint)
    (checkpoint_dir / "SHA256SUMS").write_text(f"{before}  {checkpoint.name}\n")
    run(checkpoint, tmp_path / "reports", 3, 3, seed=25)
    assert sha256_file(checkpoint) == before


def test_real_model_proof_is_not_inferred_from_no_contradictions():
    result = summarize(LearnedTruth(), "mock-hash", 3, 3, seed=26)
    assert "real_model_pattern_contradictions" in result["summary"]
    assert result["summary"]["injected_contradictions_detected"] == 1
    assert result["summary"]["deployment_approved"] is False
