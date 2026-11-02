#!/usr/bin/env python3
# BEACON COMPUTING INITIATIVE
# BCIPitch A440 M2.2 Learned Harmonic Octet Tournament
# Developer Seal: CJB-DEV-2026

import hashlib
import json
import random
import statistics
import time
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments" / "A440-M2.2"

SEEDS = (440, 441, 442)
STEPS = 240
BATCH = 8


class Baseline(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(4, 32),
            nn.GELU(),
            nn.Linear(32, 32),
            nn.GELU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x)


class HarmonicOctet(nn.Module):
    """Learned 8 -> 4 -> 2 -> 1 hierarchy."""

    def __init__(self):
        super().__init__()

        self.encoder = nn.Sequential(
            nn.Linear(4, 32), nn.GELU()
        )

        self.pair = nn.Sequential(
            nn.Linear(64, 32), nn.GELU()
        )

        self.quartet = nn.Sequential(
            nn.Linear(64, 32), nn.GELU()
        )

        self.root = nn.Sequential(
            nn.Linear(64, 32), nn.GELU()
        )

        self.head = nn.Sequential(
            nn.Linear(64, 32),
            nn.GELU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        if x.ndim != 2 or x.shape != (8, 4):
            raise ValueError(
                "Expected exactly eight four-feature examples"
            )

        # Eight initial embeddings.
        e = self.encoder(x)

        # Eight embeddings become four learned pair nodes.
        p = self.pair(e.reshape(4, 64))

        # Four pair nodes become two harmonic nodes.
        q = self.quartet(p.reshape(2, 64))

        # Two nodes become one contextual synthesis.
        root = self.root(q.reshape(1, 64))

        # Each example receives the synthesized context.
        context = root.expand(8, -1)

        return self.head(
            torch.cat((e, context), dim=-1)
        )


def dataset():
    g = torch.Generator().manual_seed(440)

    x = torch.randn(640, 4, generator=g)
    noise = torch.randn(640, 1, generator=g) * 0.025

    y = (
        0.5 * x[:, :1]
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


def groups(count, seed, shuffle):
    if count % BATCH:
        raise ValueError("Split must be divisible by eight")

    if shuffle:
        generator = torch.Generator().manual_seed(seed)
        order = torch.randperm(
            count, generator=generator
        )
    else:
        order = torch.arange(count)

    return order.reshape(-1, BATCH)


@torch.no_grad()
def evaluate(model, split):
    model.eval()

    x, y = split
    total = 0.0

    for indices in groups(len(x), 0, False):
        prediction = model(x[indices])

        total += F.mse_loss(
            prediction,
            y[indices],
            reduction="sum",
        ).item()

    return total / len(x)


def train(label, seed, splits):
    training, validation, testing = splits

    torch.manual_seed(seed)
    random.seed(seed)

    model = (
        HarmonicOctet()
        if label == "harmonic_octet"
        else Baseline()
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=0.003,
        weight_decay=0.0001,
    )

    parameter_count = sum(
        p.numel() for p in model.parameters()
    )

    best_loss = float("inf")
    best_state = None
    step = 0
    epoch = 0

    started = time.perf_counter()

    while step < STEPS:
        epoch += 1

        for indices in groups(
            len(training[0]), seed + epoch, True
        ):
            if step >= STEPS:
                break

            x = training[0][indices]
            y = training[1][indices]

            model.train()
            optimizer.zero_grad(set_to_none=True)

            loss = F.mse_loss(model(x), y)
            loss.backward()
            optimizer.step()

            step += 1

            if step % 20 == 0:
                validation_loss = evaluate(
                    model, validation
                )

                if validation_loss < best_loss:
                    best_loss = validation_loss
                    best_state = {
                        key: value.detach().clone()
                        for key, value
                        in model.state_dict().items()
                    }

    duration = time.perf_counter() - started

    if best_state is None:
        raise RuntimeError("No checkpoint selected")

    model.load_state_dict(best_state)

    result = {
        "model": label,
        "seed": seed,
        "parameters": parameter_count,
        "optimizer_updates": step,
        "samples_processed": step * BATCH,
        "best_validation_mse": best_loss,
        "test_mse": evaluate(model, testing),
        "seconds": duration,
    }

    return result, best_state


def sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def main():
    torch.set_num_threads(
        min(4, torch.get_num_threads())
    )

    splits = dataset()
    OUT.mkdir(parents=True, exist_ok=True)

    runs = []
    artifacts = []

    for seed in SEEDS:
        for label in ("baseline8", "harmonic_octet"):
            result, state = train(
                label, seed, splits
            )

            runs.append(result)

            checkpoint = OUT / (
                f"{label}-seed{seed}.pt"
            )

            torch.save({
                "project": "BCIPitch",
                "developer_seal": "CJB-DEV-2026",
                "version": "0.2.2",
                "architecture": label,
                "seed": seed,
                "state_dict": state,
            }, checkpoint)

            artifacts.append(checkpoint)

            print(
                f"[BCI][TRAIN] {label} "
                f"seed={seed} "
                f"test_mse={result['test_mse']:.7f} "
                f"time={result['seconds']:.3f}s"
            )

    summary = {}

    for label in ("baseline8", "harmonic_octet"):
        selected = [
            r for r in runs
            if r["model"] == label
        ]

        errors = [
            r["test_mse"] for r in selected
        ]

        summary[label] = {
            "mean_test_mse": statistics.mean(errors),
            "std_test_mse": statistics.stdev(errors),
            "mean_seconds": statistics.mean(
                r["seconds"] for r in selected
            ),
            "parameters": selected[0]["parameters"],
        }

    report = {
        "project": "BCIPitch",
        "developer_seal": "CJB-DEV-2026",
        "version": "0.2.2",
        "experiment": "Harmonic Octet Tournament",
        "dataset": "synthetic_regression",
        "seeds": list(SEEDS),
        "steps_per_run": STEPS,
        "batch_size": BATCH,
        "limitations": [
            "Tournament has more parameters than baseline",
            "Hierarchy is sensitive to input order",
            "Synthetic labels do not require group context",
            "Results do not establish tournament superiority",
        ],
        "summary": summary,
        "runs": runs,
    }

    report_path = OUT / "results.json"

    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    artifacts.append(report_path)
    artifacts.append(Path(__file__).resolve())

    manifest = OUT / "SHA256SUMS"

    manifest.write_text(
        "".join(
            f"{sha256(path)}  "
            f"{path.relative_to(ROOT)}\n"
            for path in artifacts
        ),
        encoding="utf-8",
    )

    print("\n=== BCI M2.2 HARMONIC TOURNAMENT ===")

    for label, metrics in summary.items():
        print(
            f"{label}: "
            f"MSE={metrics['mean_test_mse']:.7f} "
            f"+/-{metrics['std_test_mse']:.7f} "
            f"TIME={metrics['mean_seconds']:.3f}s "
            f"PARAMS={metrics['parameters']}"
        )

    print(f"[BCI][PASS] {report_path}")
    print(f"[BCI][SHA256] {manifest}")


if __name__ == "__main__":
    main()
