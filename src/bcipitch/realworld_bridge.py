#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Project: BCIPitch / A440
# Component: M4.4 Real-World Comparative Learning Bridge v0.1
# Developer Seal: CJB-DEV-2026
# ============================================================
"""Audited paired real-time-series ingestion and held-out comparative forecasting.

Research only. The built-in CAUR/NVUR pair consists of BLS state unemployment
rates via FRED: percent, monthly, seasonally adjusted. It is NOT business data.
FRED observations can be revised after original publication; this is an
ex-post historical backtest, NOT a real-time vintage backtest.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import torch
from torch import nn
from torch.nn import functional as F

from learned_truth import LearnedTruth

SEAL = "CJB-DEV-2026"
VERSION = "0.1.0"
PUBLIC_SERIES = {
    "CAUR": "Unemployment Rate in California",
    "NVUR": "Unemployment Rate in Nevada",
}
SOURCE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
MONTH_UNIT = "percent"
MONTH_FREQ = "monthly"
SEASONALITY = "seasonally_adjusted"
MAX_DOWNLOAD_BYTES = 3_000_000


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def next_month(month: date) -> date:
    if month.month == 12:
        return date(month.year + 1, 1, 1)
    return date(month.year, month.month + 1, 1)


def parse_month(raw: str) -> date:
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date: {raw!r}") from exc
    if parsed.day != 1:
        raise ValueError("A monthly observation must use the first day of the month")
    return parsed


def parse_csv(content: bytes, series_id: str) -> dict[date, float]:
    """Require sorted, unique, numeric monthly values; skip explicit missing cells."""
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    except UnicodeError as exc:
        raise ValueError("Non-UTF8 time series") from exc
    if not reader.fieldnames:
        raise ValueError("Missing CSV column headers")
    date_col = next((c for c in ("observation_date", "DATE") if c in reader.fieldnames), None)
    if date_col is None or series_id not in reader.fieldnames:
        raise ValueError(f"Missing observation_date and {series_id} columns")
    observations: dict[date, float] = {}
    last: date | None = None
    for row in reader:
        if None in row:
            raise ValueError("Malformed CSV row")
        stamp = parse_month(row[date_col])
        if last is not None and stamp <= last:
            raise ValueError("Dates must be strictly ordered and unique")
        last = stamp
        raw = row[series_id].strip()
        if raw in ("", "."):
            continue
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"Non-numeric {series_id} at {stamp}") from exc
        if not math.isfinite(value):
            raise ValueError("Nonfinite numerical value")
        observations[stamp] = value
    if not observations:
        raise ValueError("Empty numerical series")
    return observations


def fetch_public_pair(outdir: Path, start: str = "1990-01-01", end: str = "2025-12-01") -> dict:
    """Download bytes from the official FRED graph exporter, with SHA provenance."""
    from_date, to_date = parse_month(start), parse_month(end)
    if not (from_date < to_date):
        raise ValueError("Start date must be earlier than end date")
    if outdir.exists():
        raise FileExistsError(f"Refusing to overwrite existing directory: {outdir}")
    blobs = {}
    sources = {}
    for series_id, description in PUBLIC_SERIES.items():
        params = urlencode({"id": series_id, "cosd": start, "coed": end})
        url = f"{SOURCE_URL}?{params}"
        req = Request(url, headers={"User-Agent": "BCIPitch-A440-Research/0.1"})
        with urlopen(req, timeout=25) as response:
            if response.status != 200:
                raise RuntimeError(f"FRED returned HTTP {response.status} for {series_id}")
            blob = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(blob) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Source CSV exceeds size limit")
        values = parse_csv(blob, series_id)
        if len(values) < 64:
            raise ValueError(f"Insufficient source observations: {series_id}")
        blobs[series_id] = blob
        sources[series_id] = {
            "filename": f"{series_id}.csv",
            "series_id": series_id,
            "name": description,
            "original_provider": "U.S. Bureau of Labor Statistics",
            "download_provider": "Federal Reserve Bank of St. Louis FRED",
            "source_url": url,
            "reference_url": f"https://fred.stlouisfed.org/series/{series_id}",
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "sha256": sha256_bytes(blob),
            "frequency": MONTH_FREQ,
            "unit": MONTH_UNIT,
            "seasonal_adjustment": SEASONALITY,
            "rows_with_values": len(values),
        }
    outdir.mkdir(parents=True, exist_ok=False)
    for series_id, blob in blobs.items():
        (outdir / f"{series_id}.csv").write_bytes(blob)
    metadata = {
        "project": "BCIPitch", "model": "A440", "developer_seal": SEAL,
        "format_version": VERSION, "local_series": "CAUR", "reference_series": "NVUR",
        "data_notice": "Series may have undergone revision; not vintage-correct real-time data.",
        "sources": sources,
    }
    (outdir / "sources.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {"outdir": str(outdir), "sources": sources}


def load_paired_data(datadir: Path) -> tuple[list[tuple[date, float, float]], dict]:
    meta = json.loads((datadir / "sources.json").read_text(encoding="utf-8"))
    if meta.get("developer_seal") != SEAL or meta.get("model") != "A440":
        raise ValueError("Unknown or invalid source manifest identity")
    a_id = meta.get("local_series")
    b_id = meta.get("reference_series")
    if a_id == b_id or not all(isinstance(i, str) and re.fullmatch(r"[A-Z0-9]{2,24}", i or "") for i in [a_id, b_id]):
        raise ValueError("Invalid or identical series identifiers")
    sources = meta["sources"]
    values = {}
    for sid in (a_id, b_id):
        details = sources[sid]
        filename = details.get("filename")
        if filename != f"{sid}.csv":
            raise ValueError("Series filenames must match their identifiers")
        content = (datadir / filename).read_bytes()
        if sha256_bytes(content) != details.get("sha256"):
            raise ValueError(f"Source integrity check failed for {sid}")
        values[sid] = parse_csv(content, sid)

    for field in ("frequency", "unit", "seasonal_adjustment"):
        vals = [sources[sid].get(field) for sid in (a_id, b_id)]
        if vals[0] != vals[1]:
            raise ValueError(f"Cannot compare inconsistent {field}")
    if sources[a_id]["frequency"] != MONTH_FREQ:
        raise ValueError("Only monthly input supported by M4.4")
    dates = sorted(set(values[a_id]) & set(values[b_id]))
    aligned = [(d, values[a_id][d], values[b_id][d]) for d in dates]
    if len(aligned) < 100:
        raise ValueError("Need at least 100 aligned observations before splitting")
    return aligned, meta


def encode_window(values: list[float]) -> tuple[list[float], float, float]:
    if len(values) != 8 or not all(math.isfinite(x) for x in values):
        raise ValueError("Expected eight finite observations")
    center = sum(values) / 8
    spread = max(math.sqrt(sum((x - center) ** 2 for x in values) / 8), 0.25)
    return [(x - center) / spread for x in values], center, spread


def build_windows(aligned: list[tuple[date, float, float]]) -> list[dict]:
    records = []
    for idx in range(8, len(aligned)):
        window = aligned[idx-8:idx]
        target = aligned[idx]
        chain = [row[0] for row in window] + [target[0]]
        if any(next_month(chain[k]) != chain[k+1] for k in range(8)):
            continue
        local_past = [row[1] for row in window]
        market_past = [row[2] for row in window]
        local_x, center, scale = encode_window(local_past)
        market_x, _, _ = encode_window(market_past)
        records.append({
            "date": target[0].isoformat(),
            "local": local_x,
            "market": market_x,
            "target_normalized": (target[1] - center) / scale,
            "target_original": target[1],
            "center": center, "scale": scale,
            "persistence": local_past[-1],
            "linear": local_past[-1] + (local_past[-1] - local_past[-2]),
            "last_input_date": window[-1][0].isoformat(),
        })
    return records


def chronological_splits(records: list[dict]) -> dict[str, list[dict]]:
    n = len(records)
    n_train = int(n * 0.60)
    n_val = int(n * 0.15)
    n_cal = int(n * 0.10)
    segments = {
        "train": records[:n_train],
        "validation": records[n_train:n_train+n_val],
        "calibration": records[n_train+n_val:n_train+n_val+n_cal],
        "test": records[n_train+n_val+n_cal:],
    }
    if any(len(v) < 12 for v in segments.values()):
        raise ValueError("Insufficient windows for chronological research splits")
    dates = [r["date"] for segment in segments.values() for r in segment]
    if dates != sorted(set(dates)):
        raise ValueError("Target date split leakage or chronology violation")
    return segments


def matrix(records: list[dict]):
    def tensor(key):
        return torch.tensor([r[key] for r in records], dtype=torch.float32)
    return tensor("local"), tensor("market"), tensor("target_normalized").unsqueeze(1)


class ForecastModel(nn.Module):
    def __init__(self, pretrained: LearnedTruth, contextual: bool):
        super().__init__()
        self.encoder = copy.deepcopy(pretrained.encoder)
        self.forecast = copy.deepcopy(pretrained.forecast)
        self.contextual = contextual
        if contextual:
            self.gate_logits = nn.Parameter(torch.full((32,), -2.0))

    def forward(self, local: torch.Tensor, market: torch.Tensor):
        embedding = self.encoder(local)
        if self.contextual:
            counterpart = self.encoder(market)
            gate = torch.sigmoid(self.gate_logits)
            embedding = embedding + gate * (counterpart - embedding)
        return self.forecast(embedding)


def checkpoint_seed(path: Path) -> tuple[LearnedTruth, str]:
    if not path.is_file():
        raise FileNotFoundError(f"M4.1 checkpoint not found: {path}")
    manifest = path.parent / "SHA256SUMS"
    if not manifest.is_file():
        raise ValueError("Checkpoint integrity manifest missing")
    expected = None
    for line in manifest.read_text(encoding="utf-8").splitlines():
        entry = line.split(maxsplit=1)
        if len(entry) == 2 and entry[1].lstrip("* ") == path.name:
            expected = entry[0]
    digest = sha256_file(path)
    if not expected or digest != expected:
        raise ValueError("M4.1 checkpoint integrity check failed")
    bundle = torch.load(path, map_location="cpu", weights_only=True)
    if bundle.get("developer_seal") != SEAL or bundle.get("architecture") != "A440-M4.1-FourHead-v0.1":
        raise ValueError("Wrong checkpoint family")
    seed = LearnedTruth()
    seed.load_state_dict(bundle["state_dict"], strict=True)
    return seed, digest


def fit(pretrained: LearnedTruth, segments: dict, *, contextual: bool, seed: int, steps: int) -> tuple[ForecastModel, dict]:
    torch.manual_seed(seed)
    model = ForecastModel(pretrained, contextual)
    opt = torch.optim.AdamW(model.parameters(), lr=0.0008, weight_decay=0.0001)
    x, m, y = matrix(segments["train"])
    vx, vm, vy = matrix(segments["validation"])
    vcenter = torch.tensor([r["center"] for r in segments["validation"]]).unsqueeze(1)
    vscale = torch.tensor([r["scale"] for r in segments["validation"]]).unsqueeze(1)
    rng = torch.Generator().manual_seed(seed + 1)
    best_mae = float("inf")
    best = None
    for step in range(1, steps+1):
        model.train()
        idx = torch.randint(len(x), (min(64, len(x)),), generator=rng)
        pred = model(x[idx], m[idx])
        loss = F.smooth_l1_loss(pred, y[idx])
        if not torch.isfinite(loss):
            raise RuntimeError("Nonfinite training loss")
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step % 10 == 0 or step == steps:
            model.eval()
            with torch.no_grad():
                val = ((model(vx, vm) * vscale + vcenter) - (vy * vscale + vcenter)).abs().mean().item()
            if math.isfinite(val) and val < best_mae:
                best_mae = val
                best = {name: t.detach().clone() for name, t in model.state_dict().items()}
    if best is None:
        raise RuntimeError("No validated candidate")
    model.load_state_dict(best)
    return model, {"best_validation_mae_original_units": best_mae, "parameters": sum(p.numel() for p in model.parameters()), "training_steps": steps}


@torch.no_grad()
def predictions(model: ForecastModel, records: list[dict]) -> list[float]:
    model.eval()
    x, market, _ = matrix(records)
    output = model(x, market).flatten().tolist()
    return [float(r["center"] + r["scale"] * estimate) for r, estimate in zip(records, output)]


def mean_abs(a: list[float], b: list[float]) -> float:
    return sum(abs(x-y) for x, y in zip(a,b)) / len(a)


def conformal_radius(pred: list[float], target: list[float], alpha: float = 0.1) -> float:
    diffs = sorted(abs(a-b) for a,b in zip(pred,target))
    k = math.ceil((len(diffs)+1)*(1-alpha))
    return diffs[min(k-1,len(diffs)-1)] if k <= len(diffs) else float("inf")


def run_realworld(datadir: Path, checkpoint: Path, outdir: Path, steps: int = 250, seed: int = 440) -> dict:
    if steps < 5 or steps > 10000:
        raise ValueError("steps must be 5..10000")
    if outdir.exists():
        raise FileExistsError(f"Refusing to overwrite: {outdir}")
    aligned, meta = load_paired_data(datadir)
    records = build_windows(aligned)
    splits = chronological_splits(records)
    torch.set_num_threads(min(4,torch.get_num_threads()))
    pretrained, checkpoint_hash = checkpoint_seed(checkpoint)
    local, local_fit = fit(pretrained, splits, contextual=False, seed=seed, steps=steps)
    broader, broad_fit = fit(pretrained, splits, contextual=True, seed=seed, steps=steps)
    cal_truth = [r["target_original"] for r in splits["calibration"]]
    test_truth = [r["target_original"] for r in splits["test"]]
    local_predictions = predictions(local, splits["test"])
    contextual_predictions = predictions(broader, splits["test"])
    calibration_predictions = predictions(broader, splits["calibration"])
    radius = conformal_radius(calibration_predictions, cal_truth)
    coverage = sum(abs(y-p) <= radius for y,p in zip(test_truth,contextual_predictions)) / len(test_truth)
    baseline_p = [r["persistence"] for r in splits["test"]]
    baseline_l = [r["linear"] for r in splits["test"]]
    local_mae = mean_abs(local_predictions,test_truth)
    broad_mae = mean_abs(contextual_predictions,test_truth)
    report = {
        "project":"BCIPitch", "model":"A440", "developer_seal":SEAL, "milestone":"M4.4",
        "status":"research_backtest_not_deployment", "source_evidence": {
            "local": meta["local_series"], "broader": meta["reference_series"],
            "frequency": meta["sources"][meta["local_series"]]["frequency"],
            "units": meta["sources"][meta["local_series"]]["unit"],
            "seasonal_adjustment": meta["sources"][meta["local_series"]]["seasonal_adjustment"],
            "source_shas": {sid:meta["sources"][sid]["sha256"] for sid in (meta["local_series"],meta["reference_series"])},
            "source_urls": {sid:meta["sources"][sid].get("reference_url") for sid in (meta["local_series"],meta["reference_series"])},
            "aligned_observations":len(aligned), "eligible_complete_octet_windows":len(records),
        },
        "initial_m41_checkpoint_sha256":checkpoint_hash,
        "splits": {name:{"count":len(rs),"first_target":rs[0]["date"],"last_target":rs[-1]["date"]} for name,rs in splits.items()},
        "model_comparison": {
            "local_only_model": {**local_fit,"test_mae_original_units":local_mae},
            "market_context_model": {**broad_fit,"test_mae_original_units":broad_mae},
            "persistence_mae_original_units":mean_abs(baseline_p,test_truth),
            "linear_extrapolation_mae_original_units":mean_abs(baseline_l,test_truth),
            "broader_context_improves_mae": broad_mae < local_mae,
        },
        "interval_diagnostic": {"method":"chronological_split_conformal_absolute_error",
            "nominal_coverage":0.90, "calibration_count":len(cal_truth),
            "empirical_test_coverage":coverage,
            "mean_interval_width_original_units":2*radius if math.isfinite(radius) else None,
            "coverage_guarantee":False},
        "limitations":[
            "Public state unemployment data are a nonbusiness feasibility test",
            "Ex-post FRED observations may incorporate later revisions: not vintage-correct",
            "Adjacent time windows share history; chronological splits mitigate but do not eliminate dependence",
            "Comparative model has additional gating parameters; results are not causal evidence of context value",
            "No guaranteed conformal coverage under time-series distribution shift",
            "No real-time model serving, confidentiality enforcement, or automatic promotion",
        ],
        "deployment_approved":False,
    }
    if not all(math.isfinite(x) for x in (local_mae,broad_mae,radius)):
        raise RuntimeError("Nonfinite evaluation result")
    outdir.mkdir(parents=True,exist_ok=False)
    for name, model in (("local",local),("contextual",broader)):
        torch.save({"state_dict":model.state_dict(),"name":name,"developer_seal":SEAL,"initial_checkpoint_sha256":checkpoint_hash}, outdir / f"{name}_candidate.pt")
    (outdir / "results.json").write_text(json.dumps(report, indent=2)+"\n",encoding="utf-8")
    (outdir / "SHA256SUMS").write_text("".join(f"{sha256_file(outdir/name)}  {name}\n" for name in ("local_candidate.pt","contextual_candidate.pt","results.json")),encoding="utf-8")
    return report


def main(argv=None):
    ap=argparse.ArgumentParser(description="A440 M4.4 real-world comparative research bridge")
    sub=ap.add_subparsers(dest="command",required=True)
    fetch=sub.add_parser("fetch",help="Retrieve BLS monthly state unemployment via FRED")
    fetch.add_argument("--outdir",required=True,type=Path)
    fetch.add_argument("--start",default="1990-01-01")
    fetch.add_argument("--end",default="2025-12-01")
    run=sub.add_parser("run",help="Leakage-limited chronological model comparison")
    run.add_argument("--data-dir",required=True,type=Path)
    run.add_argument("--checkpoint",required=True,type=Path)
    run.add_argument("--outdir",required=True,type=Path)
    run.add_argument("--steps",type=int,default=250)
    args=ap.parse_args(argv)
    try:
        if args.command=="fetch": result=fetch_public_pair(args.outdir,args.start,args.end)
        else: result=run_realworld(args.data_dir,args.checkpoint,args.outdir,args.steps)
        print(json.dumps(result,indent=2))
        print("[BCI][PASS] M4.4 research action complete; deployment remains disabled")
        return 0
    except (OSError,RuntimeError,ValueError,KeyError,IndexError,ImportError) as exc:
        print(f"[BCI][FAIL] {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
