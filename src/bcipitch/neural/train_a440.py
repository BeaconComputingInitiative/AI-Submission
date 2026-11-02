#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Project: BCIPitch — A440 Tonal Network Model
# Component: A440 Neural Foundation / Benchmark v0.2.0
# Developer Seal: CJB-DEV-2026
# ============================================================

import hashlib
import json
import random
import time
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "A440-M2"
MODELS = ROOT / "models" / "A440"

SEED = 440
EPOCHS = 15
THREADS = 4


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class A440(nn.Module):
    """Small experimental numerical model, not a language model."""

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


def dataset():
    generator = torch.Generator().manual_seed(SEED)
    x = torch.randn(640, 4, generator=generator)
    noise = torch.randn(640, 1, generator=generator) * 0.025

    y = (
        0.50 * x[:, 0:1]
        + 0.30 * x[:, 1:2].square()
        - 0.20 * x[:, 2:3]
        + 0.15 * torch.sin(x[:, 3:4])
        + noise
    )

    # Independent deterministic partitions: 448 / 96 / 96.
    return (
        TensorDataset(x[:448], y[:448]),
        TensorDataset(x[448:544], y[448:544]),
        TensorDataset(x[544:], y[544:]),
    )


@torch.no_grad()
def evaluate(model, data):
    model.eval()
    loader = DataLoader(data, batch_size=32, shuffle=False)
    total = 0.0
    count = 0

    for x, y in loader:
        error = (model(x) - y).square()
        total += error.sum().item()
        count += error.numel()

    return total / count


def train(label, batch_size, splits, initial_state):
    training, validation, testing = splits

    model = A440()
    model.load_state_dict(initial_state)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=0.003, weight_decay=0.0001
    )

    generator = torch.Generator().manual_seed(SEED + 1)
    loader = DataLoader(
        training,
        batch_size=batch_size,
        shuffle=True,
        generator=generator,
        num_workers=0,
    )

    history = []
    best_loss = float("inf")
    best_state = None
    start = time.perf_counter()

    for epoch in range(1, EPOCHS + 1):
        model.train()
        for x, y in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.mse_loss(model(x), y)
            loss.backward()
            optimizer.step()

        validation_loss = evaluate(model, validation)
        history.append({
            "epoch": epoch,
            "validation_mse": validation_loss,
        })

        if validation_loss < best_loss:
            best_loss = validation_loss
            best_state = {
                key: value.detach().clone()
                for key, value in model.state_dict().items()
            }

    duration = time.perf_counter() - start
    model.load_state_dict(best_state)
    test_loss = evaluate(model, testing)

    OUT.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)

    checkpoint = MODELS / f"A440-{label}-v0.2.0.pt"

    torch.save({
        "architecture": "A440-MLP-4-32-32-1",
        "version": "0.2.0",
        "developer_seal": "CJB-DEV-2026",
        "seed": SEED,
        "state_dict": best_state,
    }, checkpoint)

    return {
        "configuration": label,
        "batch_size": batch_size,
        "epochs": EPOCHS,
        "best_validation_mse": best_loss,
        "held_out_test_mse": test_loss,
        "training_seconds": duration,
        "checkpoint": str(checkpoint.relative_to(ROOT)),
        "checkpoint_sha256": sha256(checkpoint),
        "history": history,
    }


def main():
    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(THREADS)

    splits = dataset()
    base = A440()

    initial_state = {
        key: value.detach().clone()
        for key, value in base.state_dict().items()
    }

    parameters = sum(p.numel() for p in base.parameters())

    results = [
        train("baseline", 32, splits, initial_state),
        train("octet", 8, splits, initial_state),
    ]

    report = {
        "project": "BCIPitch",
        "developer_seal": "CJB-DEV-2026",
        "milestone": "A440-M2",
        "version": "0.2.0",
        "device": "cpu",
        "pytorch": torch.__version__,
        "parameters": parameters,
        "dataset": "deterministic_synthetic_regression",
        "dataset_sizes": {
            "train": 448,
            "validation": 96,
            "test": 96,
        },
        "note": (
            "Octet is currently a batch-size comparison, "
            "not a harmonic tournament implementation."
        ),
        "results": results,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "comparison.json"

    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = OUT / "SHA256SUMS"
    files = [report_path] + [
        ROOT / result["checkpoint"] for result in results
    ]

    manifest.write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(ROOT)}\n"
            for path in files
        ),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))
    print(f"\n[BCI][PASS] Report: {report_path}")
    print(f"[BCI][PASS] SHA-256 manifest: {manifest}")


if __name__ == "__main__":
    main()
