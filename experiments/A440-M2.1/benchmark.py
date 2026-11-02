#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# BCIPitch: Controlled Octet Benchmark v0.2.1
# Developer Seal: CJB-DEV-2026
# ============================================================

import copy
import hashlib
import json
import random
import statistics
import time
from pathlib import Path

import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments" / "A440-M2.1"

SEEDS = [440, 441, 442, 443, 444]
STEPS = 240
THREADS = 4

CONFIGS = {
    "baseline32": {"batch": 32, "structured": False},
    "random8": {"batch": 8, "structured": False},
    "octet8": {"batch": 8, "structured": True},
}


class A440(nn.Module):
    def __init__(self):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(4, 32),
            nn.GELU(),
            nn.Linear(32, 32),
            nn.GELU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.network(x)


def make_data():
    g = torch.Generator().manual_seed(440)
    x = torch.randn(640, 4, generator=g)
    noise = torch.randn(640, 1, generator=g) * 0.025

    y = (
        0.5 * x[:, 0:1]
        + 0.3 * x[:, 1:2].square()
        - 0.2 * x[:, 2:3]
        + 0.15 * torch.sin(x[:, 3:4])
        + noise
    )

    return (
        (x[:448], y[:448]),
        (x[448:544], y[448:544]),
        (x[544:], y[544:]),
    )


def batches(x, batch_size, structured, seed):
    """Create one epoch of indices without duplicate sampling."""
    g = torch.Generator().manual_seed(seed)
    n = len(x)

    if not structured:
        order = torch.randperm(n, generator=g).tolist()
        return [
            order[i:i + batch_size]
            for i in range(0, n, batch_size)
        ]

    # Structured grouping if and only if batch size is eight.
    if batch_size != 8:
        raise ValueError("Structured Octet requires batch_size=8")

    negative = torch.where(x[:, 0] < 0)[0].tolist()
    positive = torch.where(x[:, 0] >= 0)[0].tolist()

    rng = random.Random(seed)
    rng.shuffle(negative)
    rng.shuffle(positive)

    groups = []

    # Use four from each partition whenever possible.
    while len(negative) >= 4 and len(positive) >= 4:
        group = [negative.pop() for _ in range(4)]
        group += [positive.pop() for _ in range(4)]
        rng.shuffle(group)
        groups.append(group)

    # No samples are dropped: fill remaining eight-entry groups.
    leftovers = negative + positive
    rng.shuffle(leftovers)

    groups += [
        leftovers[i:i + 8]
        for i in range(0, len(leftovers), 8)
    ]

    rng.shuffle(groups)

    flat = [index for group in groups for index in group]

    assert len(flat) == n
    assert len(set(flat)) == n

    return groups


@torch.no_grad()
def mse(model, split):
    model.eval()
    x, y = split
    return nn.functional.mse_loss(model(x), y).item()


def run_one(config_name, config, seed, data):
    train, validation, testing = data
    x, y = train

    random.seed(seed)
    torch.manual_seed(seed)

    model = A440()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=0.003,
        weight_decay=0.0001,
    )

    initial_parameters = sum(
        p.numel() for p in model.parameters()
    )

    best_val = float("inf")
    best_state = None
    total_seen = 0
    step = 0
    epoch = 0

    start = time.perf_counter()

    while step < STEPS:
        epoch += 1

        groups = batches(
            x,
            config["batch"],
            config["structured"],
            seed + epoch,
        )

        for indices in groups:
            if step >= STEPS:
                break

            xb = x[indices]
            yb = y[indices]

            model.train()
            optimizer.zero_grad(set_to_none=True)

            loss = nn.functional.mse_loss(model(xb), yb)
            loss.backward()
            optimizer.step()

            step += 1
            total_seen += len(indices)

            if step % 20 == 0 or step == STEPS:
                val = mse(model, validation)

                if val < best_val:
                    best_val = val
                    best_state = copy.deepcopy(
                        model.state_dict()
                    )

    duration = time.perf_counter() - start

    if best_state is None:
        raise RuntimeError("No valid checkpoint selected")

    model.load_state_dict(best_state)

    return {
        "configuration": config_name,
        "seed": seed,
        "parameters": initial_parameters,
        "optimizer_steps": step,
        "samples_processed": total_seen,
        "best_validation_mse": best_val,
        "held_out_test_mse": mse(model, testing),
        "training_seconds": duration,
        "samples_per_second": total_seen / duration,
    }


def summarize(results):
    summary = {}

    for name in CONFIGS:
        rows = [
            row for row in results
            if row["configuration"] == name
        ]

        errors = [
            row["held_out_test_mse"]
            for row in rows
        ]

        durations = [
            row["training_seconds"]
            for row in rows
        ]

        summary[name] = {
            "runs": len(rows),
            "mean_test_mse": statistics.mean(errors),
            "std_test_mse": statistics.stdev(errors),
            "mean_training_seconds": statistics.mean(durations),
            "mean_samples_processed": statistics.mean(
                row["samples_processed"] for row in rows
            ),
        }

    return summary


def main():
    torch.set_num_threads(THREADS)

    data = make_data()
    results = []

    for seed in SEEDS:
        for name, config in CONFIGS.items():
            result = run_one(name, config, seed, data)
            results.append(result)

            print(
                f"[BCI][RUN] {name} seed={seed} "
                f"test_mse={result['held_out_test_mse']:.7f} "
                f"time={result['training_seconds']:.3f}s"
            )

    summary = summarize(results)

    report = {
        "project": "BCIPitch",
        "developer_seal": "CJB-DEV-2026",
        "version": "0.2.1",
        "experiment": "Controlled Octet Benchmark",
        "dataset": "synthetic regression",
        "device": "cpu",
        "optimizer_steps_per_run": STEPS,
        "seeds": SEEDS,
        "limitations": [
            "Only one fixed synthetic dataset is evaluated.",
            "Equal updates do not imply equal samples processed.",
            "Structured grouping is feature balancing, not "
            "a learned harmonic tournament.",
            "No generalization claim beyond this experiment."
        ],
        "summary": summary,
        "runs": results,
    }

    OUT.mkdir(parents=True, exist_ok=True)

    path = OUT / "results.json"
    path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    (OUT / "SHA256SUMS").write_text(
        f"{digest}  results.json\n",
        encoding="utf-8",
    )

    print("\n=== BCI CONTROLLED BENCHMARK ===")

    for name, metrics in summary.items():
        print(
            f"{name:12s} "
            f"MSE={metrics['mean_test_mse']:.7f} "
            f"±{metrics['std_test_mse']:.7f} "
            f"TIME={metrics['mean_training_seconds']:.3f}s"
        )

    print(f"\n[BCI][PASS] {path}")
    print(f"[BCI][SHA256] {digest}")


if __name__ == "__main__":
    main()
