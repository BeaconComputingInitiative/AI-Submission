# BEACON COMPUTING INITIATIVE
# Project: BCIPitch A440 M4.1 Tests
# Developer Seal: CJB-DEV-2026
import sys
from pathlib import Path
import torch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'bcipitch'))
from learned_truth import build_split, encode, experiment, sequence, LearnedTruth, SPLITS
import random

def test_no_target_leakage():
    sample = sequence(0, 1, random.Random(1))
    first, c, s = encode(sample)
    sample[-1] += 99999
    second, c2, s2 = encode(sample)
    assert first == second and c == c2 and s == s2

def test_independent_split_domains():
    assert not (set(SPLITS['train']) & set(SPLITS['validation']))
    assert not (set(SPLITS['train']) & set(SPLITS['test']))
    assert not (set(SPLITS['validation']) & set(SPLITS['test']))
    a = build_split('train', 8, 440)
    b = build_split('train', 8, 440)
    assert torch.equal(a['x'], b['x'])
    assert set(a['match'].tolist()) == {0, 1}
    assert a['x'].shape == (32, 8)

def test_head_dimensions():
    model = LearnedTruth()
    x = torch.randn(5, 8)
    out = model(x, x)
    assert [out[k].shape for k in ('pattern','comparison','forecast','rule')] == [(5,3),(5,2),(5,1),(5,4)]

def test_integration_checkpoint_and_manifest(tmp_path):
    r = experiment(tmp_path / 'first', steps=20, train_count=8, eval_count=8)
    assert r['dataset']['train'] == 32
    assert set(r['research_gates']) == {'L09_pattern_better_than_majority','L10_comparison_better_than_random','L11_better_than_persistence','L12_rule_better_than_random'}
    assert (tmp_path / 'first' / 'SHA256SUMS').is_file()
    assert r['deployment_approved'] is False
    with pytest.raises(FileExistsError):
        experiment(tmp_path / 'first', steps=1, train_count=8, eval_count=8)
