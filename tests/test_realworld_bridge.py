# ============================================================
# BEACON COMPUTING INITIATIVE
# Project: BCIPitch / A440
# Component: M4.4 Real-world Comparative Bridge Tests
# Developer Seal: CJB-DEV-2026
# ============================================================
from __future__ import annotations

from datetime import date
from pathlib import Path
import hashlib
import json
import math
import random
import sys

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "bcipitch"))
from realworld_bridge import (
    build_windows, chronological_splits, conformal_radius, encode_window,
    load_paired_data, next_month, parse_csv, parse_month, run_realworld,
    checkpoint_seed, sha256_file,
)
from learned_truth import LearnedTruth


def csv_blob(series_id, dates, numbers):
    text = f"observation_date,{series_id}\n"
    text += "".join(f"{day.isoformat()},{v}\n" for day, v in zip(dates,numbers))
    return text.encode("utf-8")


def monthly_dates(count, start=date(2010,1,1)):
    out=[]
    for _ in range(count):
        out.append(start)
        start=next_month(start)
    return out


def fixture_data(tmp_path, count=180, *, mismatch=False):
    out=tmp_path / "source"
    out.mkdir()
    dates=monthly_dates(count)
    rng=random.Random(432)
    broad=[]
    local=[]
    x=5.0
    for i in range(count):
        x=0.90*x + 0.5 + rng.gauss(0,0.15)
        broad.append(round(x,3))
        local.append(round(0.9*x+0.15*math.sin(i/3) + rng.gauss(0,0.12),3))
    meta={"model":"A440","developer_seal":"CJB-DEV-2026", "local_series":"CAUR","reference_series":"NVUR","sources":{}}
    for series_id,values in (("CAUR",local),("NVUR",broad)):
        content=csv_blob(series_id,dates,values)
        (out/f"{series_id}.csv").write_bytes(content)
        meta["sources"][series_id]={"sha256":hashlib.sha256(content).hexdigest(),"filename":f"{series_id}.csv","unit":"percent" if not (mismatch and series_id=="NVUR") else "dollars","frequency":"monthly","seasonal_adjustment":"seasonally_adjusted"}
    (out/"sources.json").write_text(json.dumps(meta))
    return out


def fixture_checkpoint(tmp_path):
    folder=tmp_path / "m41"
    folder.mkdir()
    torch.manual_seed(440)
    network=LearnedTruth()
    target=folder/"learned_truth_candidate.pt"
    torch.save({"state_dict":network.state_dict(),"developer_seal":"CJB-DEV-2026","architecture":"A440-M4.1-FourHead-v0.1"},target)
    (folder/"SHA256SUMS").write_text(f"{sha256_file(target)}  learned_truth_candidate.pt\n")
    return target


def test_monthly_date_rules():
    assert next_month(date(2024,12,1)) == date(2025,1,1)
    assert parse_month("2025-01-01") == date(2025,1,1)
    with pytest.raises(ValueError): parse_month("2025-01-02")
    with pytest.raises(ValueError): parse_month("2025-99-01")


def test_numeric_csv_and_missing_cells():
    dates=monthly_dates(4)
    data=csv_blob("CAUR",dates,["4.1",".","4.4", "4.2"])
    observations=parse_csv(data,"CAUR")
    assert len(observations)==3
    assert dates[1] not in observations


def test_duplicate_dates_fail():
    dates=monthly_dates(3)
    with pytest.raises(ValueError,match="ordered and unique"):
        parse_csv(csv_blob("CAUR",[dates[0],dates[1],dates[1]],[1,2,3]),"CAUR")


def test_nonfinite_values_fail():
    with pytest.raises(ValueError,match="Nonfinite"):
        parse_csv(csv_blob("CAUR",monthly_dates(2),[1,"nan"]),"CAUR")


def test_tampered_source_rejected(tmp_path):
    folder=fixture_data(tmp_path)
    assert len(load_paired_data(folder)[0]) == 180
    with (folder/"CAUR.csv").open("ab") as fp:
        fp.write(b"2027-01-01,1000\n")
    with pytest.raises(ValueError,match="integrity"):
        load_paired_data(folder)


def test_incompatible_units_rejected(tmp_path):
    folder=fixture_data(tmp_path,mismatch=True)
    with pytest.raises(ValueError,match="inconsistent unit"):
        load_paired_data(folder)


def test_gaps_cannot_form_fake_octets():
    dates=monthly_dates(30)
    aligned=[(d,float(i),float(i+2)) for i,d in enumerate(dates) if i!=10]
    windows=build_windows(aligned)
    assert len(windows)==30-8-9
    assert "2010-11-01" not in [w["date"] for w in windows]


def test_future_outcome_is_not_in_features():
    dates=monthly_dates(10)
    aligned=[(d,5.0+i,6.0+i) for i,d in enumerate(dates)]
    first=build_windows(aligned)[0]
    aligned[8]=(dates[8],99999,88888)
    second=build_windows(aligned)[0]
    assert first["local"]==second["local"]
    assert first["market"]==second["market"]
    assert first["target_original"]!=second["target_original"]


def test_normalization_uses_exact_octet():
    with pytest.raises(ValueError): encode_window([1,2,3])
    z,mu,s=encode_window([1.0]*8)
    assert z == [0.0]*8 and s >= 0.25


def test_splits_are_strictly_chronological(tmp_path):
    folder=fixture_data(tmp_path)
    records=build_windows(load_paired_data(folder)[0])
    splits=chronological_splits(records)
    ordered=[x["date"] for v in splits.values() for x in v]
    assert len(ordered)==len(set(ordered))
    assert ordered==sorted(ordered)
    for part in splits.values():
        assert all(row["last_input_date"] < row["date"] for row in part)


def test_checkpoint_sha_enforced(tmp_path):
    checkpoint=fixture_checkpoint(tmp_path)
    assert checkpoint_seed(checkpoint)[1] == sha256_file(checkpoint)
    with checkpoint.open("ab") as f: f.write(b"altered")
    with pytest.raises(ValueError,match="integrity"):
        checkpoint_seed(checkpoint)


def test_conformal_diagnostic():
    assert conformal_radius([0.0]*20,[0.0]*18+[1.0]*2,alpha=0.1)==1.0


def test_training_and_manifest_and_overwrite(tmp_path):
    data=fixture_data(tmp_path)
    checkpoint=fixture_checkpoint(tmp_path)
    out=tmp_path/"run"
    report=run_realworld(data,checkpoint,out,steps=12)
    assert report["deployment_approved"] is False
    assert report["model_comparison"]["market_context_model"]["test_mae_original_units"]>=0
    assert len(report["splits"])==4
    for line in (out/"SHA256SUMS").read_text().splitlines():
        digest,path=line.split(maxsplit=1)
        assert sha256_file(out/path)==digest
    with pytest.raises(FileExistsError): run_realworld(data,checkpoint,out,steps=12)
