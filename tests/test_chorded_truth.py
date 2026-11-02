# BEACON COMPUTING INITIATIVE
# Project: BCIPitch / A440
# Component: M4.2 Chorded Truth Tests
# Developer Seal: CJB-DEV-2026
import json
import math
import sys
from pathlib import Path
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "bcipitch"))
from chorded_truth import (chord, evaluate_later_forecast, load_verified_model,
                           make_evidence, scale, sha256_file, validate_evidence)
from learned_truth import LearnedTruth


def test_scale_calculations_and_integrity():
    e = make_evidence([2, 4, 6, 8, 10, 12, 14, 16], 'synthetic-test')
    result = scale(e)
    assert result['net_change'] == '14'
    assert result['median'] == '9'
    assert result['fractional_change_from_abs_baseline'] == '7'
    assert result['invariants']['telescoping_differences']
    assert validate_evidence(e)


def test_tampered_and_reordered_records_blocked():
    e = make_evidence([2, 4, 6, 8, 10, 12, 14, 16], 'synthetic-test')
    e['points'][7]['value'] = 200
    with pytest.raises(ValueError, match='digest mismatch'):
        scale(e)
    e = make_evidence([2, 4, 6, 8, 10, 12, 14, 16], 'synthetic-test')
    e['points'][4]['tick'] = e['points'][3]['tick']
    with pytest.raises(ValueError, match='ordering'):
        scale(e)


def test_invalid_inputs_blocked():
    with pytest.raises(ValueError):
        make_evidence([1, 2, 3], 'short')
    with pytest.raises(ValueError):
        make_evidence([1, 2, 3, 4, 5, 6, 7, float('nan')], 'nan')
    with pytest.raises(ValueError):
        make_evidence([1, 2, 3, 4, 5, 6, 7, True], 'bool')


class ContradictingModel(torch.nn.Module):
    def forward(self, x, other):
        size=x.shape[0]
        return {
            'pattern': torch.tensor([[-15.0, 15.0, -15.0]]).repeat(size,1),
            'comparison': torch.zeros(size, 2),
            'forecast': torch.ones(size, 1),
            'rule': torch.zeros(size, 4),
        }


def test_contradictions_are_not_overruled():
    rec = make_evidence([1, 2, 3, 4, 5, 6, 7, 8], 'synthetic-1')
    peer = make_evidence([3, 4, 5, 6, 7, 8, 9, 10], 'synthetic-2')
    result = chord(rec, peer, ContradictingModel(), 'test-model-sha')
    assert result['chord']['summary'] == 'contradiction_detected'
    assert result['arpeggio']['L09']['status'] == 'contradicted'
    assert result['scale']['local']['net_change'] == '7'
    assert result['chord']['causality_established'] is False
    assert result['chord']['deployment_approved'] is False


def test_unseen_future_target_only_used_after_inference():
    rec = make_evidence([1, 2, 3, 4, 5, 6, 7, 8], 'synthetic-1')
    peer = make_evidence([3, 4, 5, 6, 7, 8, 9, 10], 'synthetic-2')
    r = chord(rec, peer, LearnedTruth(), 'test-model-sha')
    assert r['arpeggio']['L11']['status'] == 'learned_hypothesis'
    assert 'later_outcome_evaluation' not in r
    score = evaluate_later_forecast(r, 9)
    assert score['actual'] == 9
    assert score['absolute_error'] >= 0
    assert r['chord']['external_market_verified'] is False


def test_checkpoint_requires_valid_sha_manifest(tmp_path):
    path = tmp_path / 'learned_truth_candidate.pt'
    torch.save({'developer_seal': 'CJB-DEV-2026',
                'architecture': 'A440-M4.1-FourHead-v0.1',
                'state_dict': LearnedTruth().state_dict()},path)
    (tmp_path/'SHA256SUMS').write_text(f'{sha256_file(path)}  {path.name}\n')
    _, checksum = load_verified_model(path)
    assert checksum == sha256_file(path)
    path.write_bytes(path.read_bytes() + b'tamper')
    with pytest.raises(ValueError, match='SHA-256'):
        load_verified_model(path)


def test_mismatched_units_block_comparison():
    a = make_evidence(list(range(1,9)), 'a', unit='units')
    b = make_evidence(list(range(1,9)), 'b', unit='ms')
    with pytest.raises(ValueError, match='units'):
        chord(a,b,LearnedTruth(), 'hash')
