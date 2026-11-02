#!/usr/bin/env python3
# BEACON COMPUTING INITIATIVE
# BCIPitch | A440 Harmonic Validation v0.2.3
# Developer Seal: CJB-DEV-2026

import copy
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
OUT = ROOT / "experiments" / "A440-M2.3"

SEEDS = (440, 441, 442)
STEPS = 180
OCTET = 8
THREADS = 4


def parameters(model):
    return sum(p.numel() for p in model.parameters())


class Baseline(nn.Module):
    """Independent predictions; no cross-example communication."""

    def __init__(self, width=48):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(4, width),
            nn.GELU(),
            nn.Linear(width, width),
            nn.GELU(),
            nn.Linear(width, 1),
        )

    def forward(self, x):
        return self.net(x)


class Harmonic(nn.Module):
    """Learnable 8 -> 4 -> 2 -> 1 composition."""

    def __init__(self, width):
        super().__init__()

        self.encoder = nn.Sequential(
            nn.Linear(4, width),
            nn.GELU(),
        )

        def merge():
            return nn.Sequential(
                nn.Linear(width * 2, width),
                nn.GELU(),
            )

        self.pair = merge()
        self.quartet = merge()
        self.root = merge()

        self.head = nn.Sequential(
            nn.Linear(width * 2, width),
            nn.GELU(),
            nn.Linear(width, 1),
        )

    def forward(self, x):
        if x.shape != (OCTET, 4):
            raise ValueError("Expected an 8 x 4 Octet")

        e = self.encoder(x)

        p = self.pair(
            e.reshape(4, -1)
        )

        q = self.quartet(
            p.reshape(2, -1)
        )

        root = self.root(
            q.reshape(1, -1)
        )

        context = root.expand(OCTET, -1)

        return self.head(
            torch.cat((e, context), dim=-1)
        )


def matching_width(target):
    """Choose closest harmonic parameter count."""
    candidates = []

    for width in range(4, 97):
        count = parameters(Harmonic(width))
        candidates.append(
            (abs(count - target), width, count)
        )

    _, width, count = min(candidates)
    return width, count


def dataset(task):
    """Independent Octets, split by group, not by row."""
    generator = torch.Generator().manual_seed(440)

    x = torch.randn(
        80, OCTET, 4,
        generator=generator,
    )

    noise = 0.025 * torch.randn(
        80, OCTET, 1,
        generator=generator,
    )

    individual = (
        0.5 * x[..., 0:1]
        + 0.3 * x[..., 1:2].square()
        - 0.2 * x[..., 2:3]
        + 0.15 * torch.sin(x[..., 3:4])
    )

    if task == "relational":
        # Each target depends on the group's mean feature.
        context = x[..., 1:2].mean(
            dim=1, keepdim=True
        )

        y = (
            individual
            + 1.5 * context * x[..., 2:3]
            + noise
        )

    elif task == "independent":
        y = individual + noise

    else:
        raise ValueError("Unknown task")

    # 56 training groups, 12 validation, 12 test.
    return (
        (x[:56], y[:56]),
        (x[56:68], y[56:68]),
        (x[68:], y[68:]),
    )


@torch.no_grad()
def evaluate(model, split):
    model.eval()
    x, y = split

    total = 0.0

    for group_x, group_y in zip(x, y):
        total += F.mse_loss(
            model(group_x),
            group_y,
            reduction="sum",
        ).item()

    return total / y.numel()


@torch.no_grad()
def permutation_error(model, split, seed):
    """Measure changed predictions after shuffling input order."""
    model.eval()
    x, _ = split

    generator = torch.Generator().manual_seed(seed)
    differences = []

    for group in x:
        original = model(group)

        permutation = torch.randperm(
            OCTET, generator=generator
        )

        shuffled = model(group[permutation])

        inverse = torch.argsort(permutation)
        restored = shuffled[inverse]

        differences.append(
            (original - restored)
            .abs()
            .mean()
            .item()
        )

    return statistics.mean(differences)


def train(model_type, width, seed, task, splits):
    training, validation, testing = splits

    torch.manual_seed(seed)
    random.seed(seed)

    if model_type == "baseline":
        model = Baseline(width=48)
    else:
        model = Harmonic(width=width)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=0.003,
        weight_decay=0.0001,
    )

    best_validation = float("inf")
    best_weights = None

    step = 0
    epoch = 0

    start = time.perf_counter()

    while step < STEPS:
        epoch += 1

        generator = torch.Generator().manual_seed(
            seed + epoch
        )

        ordering = torch.randperm(
            len(training[0]), generator=generator
        )

        for index in ordering:
            if step >= STEPS:
                break

            x = training[0][index]
            y = training[1][index]

            model.train()
            optimizer.zero_grad(set_to_none=True)

            prediction = model(x)
            loss = F.mse_loss(prediction, y)

            loss.backward()
            optimizer.step()

            step += 1

            # Select checkpoints using validation only.
            if step % 20 == 0:
                score = evaluate(model, validation)

                if score < best_validation:
                    best_validation = score
                    best_weights = copy.deepcopy(
                        model.state_dict()
                    )

    elapsed = time.perf_counter() - start

    if best_weights is None:
        raise RuntimeError("No validated checkpoint")

    model.load_state_dict(best_weights)

    result = {
        "task": task,
        "model": model_type,
        "seed": seed,
        "parameters": parameters(model),
        "steps": step,
        "samples_processed": step * OCTET,
        "validation_mse": best_validation,
        "test_mse": evaluate(model, testing),
        "permutation_delta": permutation_error(
            model, testing, seed + 900
        ),
        "seconds": elapsed,
    }

    return result, best_weights


def digest(path):
    h = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1024 * 1024), b""
        ):
            h.update(block)

    return h.hexdigest()


def main():
    torch.set_num_threads(THREADS)
    OUT.mkdir(parents=True, exist_ok=True)

    baseline_count = parameters(Baseline())
    width, harmonic_count = matching_width(
        baseline_count
    )

    print("=== BCI M2.3 ARCHITECTURE ===")
    print("Developer Seal: CJB-DEV-2026")
    print("Baseline parameters:", baseline_count)
    print("Harmonic parameters:", harmonic_count)
    print("Harmonic width:", width)

    results = []
    artifacts = []

    for task in ("independent", "relational"):
        splits = dataset(task)

        for seed in SEEDS:
            for model_type in (
                "baseline",
                "harmonic",
            ):
                row, weights = train(
                    model_type,
                    width,
                    seed,
                    task,
                    splits,
                )

                results.append(row)

                checkpoint = OUT / (
                    f"{task}-{model_type}-"
                    f"seed{seed}.pt"
                )

                torch.save({
                    "project": "BCIPitch",
                    "developer_seal": "CJB-DEV-2026",
                    "version": "0.2.3",
                    "task": task,
                    "model": model_type,
                    "seed": seed,
                    "harmonic_width": (
                        width if model_type == "harmonic"
                        else None
                    ),
                    "state_dict": weights,
                }, checkpoint)

                artifacts.append(checkpoint)

                print(
                    "[BCI][TRAIN]",
                    task,
                    model_type,
                    f"seed={seed}",
                    f"test={row['test_mse']:.7f}",
                )

    summary = {}

    for task in ("independent", "relational"):
        summary[task] = {}

        for model_type in ("baseline", "harmonic"):
            rows = [
                r for r in results
                if r["task"] == task
                and r["model"] == model_type
            ]

            summary[task][model_type] = {
                "mean_test_mse": statistics.mean(
                    r["test_mse"] for r in rows
                ),
                "std_test_mse": statistics.stdev(
                    r["test_mse"] for r in rows
                ),
                "mean_permutation_delta":
                    statistics.mean(
                        r["permutation_delta"]
                        for r in rows
                    ),
                "mean_seconds": statistics.mean(
                    r["seconds"] for r in rows
                ),
                "parameters": rows[0]["parameters"],
            }

    report = {
        "project": "BCIPitch",
        "developer_seal": "CJB-DEV-2026",
        "version": "0.2.3",
        "experiment": "Parameter-matched harmonic study",
        "optimizer_steps": STEPS,
        "octet_size": OCTET,
        "seeds": list(SEEDS),
        "baseline_parameters": baseline_count,
        "harmonic_parameters": harmonic_count,
        "harmonic_width": width,
        "dataset_groups": {
            "train": 56,
            "validation": 12,
            "test": 12,
        },
        "limitations": [
            "Synthetic tasks only",
            "One fixed dataset per task",
            "Three seeds are exploratory",
            "Model counts are approximately matched",
            "Octet membership is fixed during evaluation",
            "No claims about real-world causal inference",
        ],
        "summary": summary,
        "runs": results,
    }

    report_path = OUT / "results.json"

    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    artifacts.extend([
        report_path,
        Path(__file__).resolve(),
    ])

    manifest = OUT / "SHA256SUMS"

    manifest.write_text(
        "# BEACON COMPUTING INITIATIVE\n"
        "# Developer Seal: CJB-DEV-2026\n"
        + "".join(
            f"{digest(path)}  "
            f"{path.relative_to(ROOT)}\n"
            for path in artifacts
        ),
        encoding="utf-8",
    )

    print("\n=== BCI M2.3 RESULTS ===")

    for task, models in summary.items():
        print(f"\nTASK: {task}")

        for name, row in models.items():
            print(
                f"  {name}: "
                f"MSE={row['mean_test_mse']:.7f} "
                f"STD={row['std_test_mse']:.7f} "
                f"PERM={row['mean_permutation_delta']:.7f} "
                f"TIME={row['mean_seconds']:.3f}s"
            )

    print("\n[BCI][PASS] Results:", report_path)
    print("[BCI][SHA256] Manifest:", manifest)


if __name__ == "__main__":
    main()
