#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Project: BCIPitch / A440
# Component: M4.1 Learned Truth Numerical Prototype
# Developer Seal: CJB-DEV-2026
# ============================================================
"""Four-head synthetic research prototype. No real business data or self-training."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
SEAL = 'CJB-DEV-2026'
FAMILIES = ('linear', 'quadratic', 'compound', 'periodic')
SPLITS = {'train': (0, 1, 2, 3), 'validation': (4, 5), 'test': (6, 7)}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def sequence(family: int, domain: int, rng: random.Random) -> list[float]:
    """Nine values; only first 8 become model inputs."""
    base = 30 + domain * 125 + rng.uniform(-15, 15)
    magnitude = (1 + domain * 0.35) * rng.uniform(1.5, 4.0)
    sign = rng.choice((-1, 1))
    phase = rng.uniform(0, 4)
    curvature = rng.uniform(0.07, 0.15)
    rate = rng.uniform(1.14, 1.32)
    period = rng.uniform(3.6, 5.0)
    values = []
    for t in range(9):
        if family == 0:  # affine
            change = sign * magnitude * t
        elif family == 1:  # accelerating
            change = sign * magnitude * (0.17 * t + curvature * t * t)
        elif family == 2:  # compounding
            change = sign * magnitude * (rate ** t - 1) * 3.0
        elif family == 3:  # periodic
            change = magnitude * math.sin((t + phase) * 2 * math.pi / period)
        else:
            raise ValueError('unknown family')
        values.append(base + change)
    return values


def encode(values: list[float]) -> tuple[list[float], float, float]:
    """Normalize from observed 8 samples only; target t=8 is never inspected."""
    observed = values[:8]
    center = sum(observed) / 8
    variance = sum((v - center) ** 2 for v in observed) / 8
    spread = max(math.sqrt(variance), 1e-6)
    return [(v - center) / spread for v in observed], center, spread


def build_split(name: str, per_family: int, seed: int) -> dict[str, torch.Tensor | str | list[int]]:
    if name not in SPLITS or per_family <= 0:
        raise ValueError('invalid split configuration')
    rng = random.Random(seed)
    domains = SPLITS[name]
    records = []
    for rule in range(4):
        for j in range(per_family):
            domain = domains[j % len(domains)]
            first = sequence(rule, domain, rng)
            features, center, spread = encode(first)
            label = 2 if rule == 3 else (0 if first[7] > first[0] else 1)
            partner_rule = rule if j % 2 == 0 else (rule + 1 + rng.randrange(3)) % 4
            partner_domain = domains[(j + 1) % len(domains)]
            partner = sequence(partner_rule, partner_domain, rng)
            partner_features, _, _ = encode(partner)
            records.append((features, partner_features, label, rule,
                            int(partner_rule == rule), (first[8] - center) / spread))
    rng.shuffle(records)
    x, other, patterns, rules, matches, targets = zip(*records)
    return {
        'x': torch.tensor(x, dtype=torch.float32),
        'other': torch.tensor(other, dtype=torch.float32),
        'pattern': torch.tensor(patterns, dtype=torch.long),
        'rule': torch.tensor(rules, dtype=torch.long),
        'match': torch.tensor(matches, dtype=torch.long),
        'target': torch.tensor(targets, dtype=torch.float32).unsqueeze(1),
        'domains': list(domains), 'split': name,
    }


def fingerprint(data: dict) -> str:
    """Hash numeric inputs, withheld targets and rule labels in a fixed order."""
    h = hashlib.sha256()
    for key in ('x', 'other', 'pattern', 'rule', 'match', 'target'):
        t = data[key].contiguous()
        h.update(key.encode('ascii') + b'\0')
        h.update(str(tuple(t.shape)).encode('ascii') + b'\0')
        h.update(t.numpy().tobytes())
    return h.hexdigest()


class LearnedTruth(nn.Module):
    """Shared numerical encoder + four separately scored learned heads."""
    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(8, 64), nn.GELU(),
                                     nn.Linear(64, 32), nn.GELU())
        self.pattern = nn.Linear(32, 3)  # L09: up/down/cyclic
        self.comparison = nn.Sequential(nn.Linear(64, 32), nn.GELU(),
                                        nn.Linear(32, 2))  # L10: same family?
        self.forecast = nn.Linear(32, 1)  # L11: normalized next value
        self.rule = nn.Linear(32, 4)  # L12: rule family

    def forward(self, x: torch.Tensor, other: torch.Tensor) -> dict[str, torch.Tensor]:
        a, b = self.encoder(x), self.encoder(other)
        comparison_features = torch.cat((torch.abs(a - b), a * b), dim=1)
        return {
            'pattern': self.pattern(a),
            'comparison': self.comparison(comparison_features),
            'forecast': self.forecast(a),
            'rule': self.rule(a),
        }


def loss_for(outputs: dict[str, torch.Tensor], batch: dict) -> torch.Tensor:
    return (F.cross_entropy(outputs['pattern'], batch['pattern']) +
            F.cross_entropy(outputs['comparison'], batch['match']) +
            F.cross_entropy(outputs['rule'], batch['rule']) +
            0.3 * F.smooth_l1_loss(outputs['forecast'], batch['target']))


@torch.no_grad()
def evaluate(model: LearnedTruth, data: dict) -> dict:
    model.eval()
    out = model(data['x'], data['other'])
    true = data['target']
    mae = float((out['forecast'] - true).abs().mean().item())
    persistence = float((data['x'][:, -1:] - true).abs().mean().item())
    linear = float((2 * data['x'][:, -1:] - data['x'][:, -2:-1] - true).abs().mean().item())
    return {
        'total_validation_objective': float(loss_for(out, data).item()),
        'L09_pattern_accuracy': float((out['pattern'].argmax(1) == data['pattern']).float().mean().item()),
        'L10_cross_context_accuracy': float((out['comparison'].argmax(1) == data['match']).float().mean().item()),
        'L11_forecast_mae_normalized': mae,
        'forecast_persistence_mae': persistence,
        'forecast_linear_extrapolation_mae': linear,
        'L12_rule_accuracy': float((out['rule'].argmax(1) == data['rule']).float().mean().item()),
    }


def experiment(workdir: Path, steps: int = 240, seed: int = 440, train_count: int = 192,
               eval_count: int = 64) -> dict:
    if steps < 1 or train_count < 4 or eval_count < 4:
        raise ValueError('invalid training settings')
    if workdir.exists() and any(workdir.iterdir()):
        raise FileExistsError(f'Output directory must be empty: {workdir}')
    workdir.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(min(4, torch.get_num_threads()))
    torch.manual_seed(seed)
    training = build_split('train', train_count, seed)
    validation = build_split('validation', eval_count, seed + 1)
    testing = build_split('test', eval_count, seed + 2)
    if set(training['domains']) & set(validation['domains']) or set(training['domains']) & set(testing['domains']) or set(validation['domains']) & set(testing['domains']):
        raise RuntimeError('environment split overlap')
    model = LearnedTruth()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.002, weight_decay=1e-4)
    generator = torch.Generator().manual_seed(seed + 3)
    best_obj = float('inf')
    best_state = None
    started = time.perf_counter()
    for step in range(1, steps + 1):
        model.train()
        idx = torch.randint(len(training['x']), (64,), generator=generator)
        batch = {key: val[idx] for key, val in training.items() if isinstance(val, torch.Tensor)}
        optimizer.zero_grad(set_to_none=True)
        objective = loss_for(model(batch['x'], batch['other']), batch)
        if not torch.isfinite(objective):
            raise RuntimeError('nonfinite objective')
        objective.backward()
        optimizer.step()
        if step % 20 == 0 or step == steps:
            validation_stats = evaluate(model, validation)
            obj = validation_stats['total_validation_objective']
            if math.isfinite(obj) and obj < best_obj:
                best_obj = obj
                best_state = {name: t.detach().clone() for name, t in model.state_dict().items()}
    if best_state is None:
        raise RuntimeError('no valid candidate')
    elapsed = time.perf_counter() - started
    model.load_state_dict(best_state)
    val = evaluate(model, validation)
    test = evaluate(model, testing)  # invoked only after checkpoint selection
    gates = {
        'L09_pattern_better_than_majority': test['L09_pattern_accuracy'] > 0.34,
        'L10_comparison_better_than_random': test['L10_cross_context_accuracy'] > 0.5,
        'L11_better_than_persistence': test['L11_forecast_mae_normalized'] < test['forecast_persistence_mae'],
        'L12_rule_better_than_random': test['L12_rule_accuracy'] > 0.25,
    }
    checkpoint = workdir / 'learned_truth_candidate.pt'
    torch.save({'state_dict': best_state, 'seed': seed, 'developer_seal': SEAL,
                'architecture': 'A440-M4.1-FourHead-v0.1'}, checkpoint)
    report = {
        'project': 'BCIPitch', 'model': 'A440', 'developer_seal': SEAL,
        'milestone': 'M4.1', 'version': '0.1.0',
        'status': 'synthetic_numerical_research_only',
        'algorithms': {'L09': 'pattern', 'L10': 'cross_context',
                       'L11': 'forecast', 'L12': 'rule_induction_proxy'},
        'dataset': {'train': len(training['x']), 'validation': len(validation['x']),
                    'test': len(testing['x']), 'split_domains': SPLITS,
                    'generator_seed': seed,
                    'sha256': {name: fingerprint(data) for name, data in
                               (('train', training), ('validation', validation), ('test', testing))}},
        'parameters': sum(p.numel() for p in model.parameters()),
        'training_steps': steps, 'training_seconds': elapsed,
        'validation': val, 'test': test,
        'research_gates': gates, 'research_gate_passed': all(gates.values()),
        'deployment_approved': False,
        'limitations': ['Synthetic generator families known in advance',
                        'Rule classification is not general program synthesis',
                        'No market data or cross-business integration',
                        'No evidence-aware Chord integration',
                        'Test metrics do not independently certify business readiness'],
    }
    report_path = workdir / 'results.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    manifest = workdir / 'SHA256SUMS'
    manifest.write_text(f'{sha256(checkpoint)}  {checkpoint.name}\n{sha256(report_path)}  {report_path.name}\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description='BCIPitch M4.1 synthetic Learned Truth experiment')
    parser.add_argument('--workdir', type=Path, default=ROOT / 'experiments' / 'A440-M4.1')
    parser.add_argument('--steps', type=int, default=240)
    args = parser.parse_args()
    try:
        result = experiment(args.workdir, steps=args.steps)
        print(json.dumps({'model': result['model'], 'milestone': result['milestone'],
                          'validation': result['validation'], 'test': result['test'],
                          'research_gates': result['research_gates'],
                          'deployment_approved': result['deployment_approved']}, indent=2))
        print('[BCI][PASS] Experiment completed (not approved for deployment)')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'[BCI][FAIL] {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
