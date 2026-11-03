#!/usr/bin/env bash
# ============================================================
# BEACON COMPUTING INITIATIVE
# Component: A440-U2.1 Unified Model In-Place Verified Upgrade
# Developer Seal: CJB-DEV-2026
# Policy: isolate -> verify -> 50 tests -> preserve backup -> atomic upgrade
# ============================================================
set -euo pipefail

LAB="${A440_LAB_DIR:-$HOME/Documents/A440-Docker-Lab/bci_quarter_lab}"
OLD_SHA="5fe7d953b2c863deb4d5e1e05ddc684306089bffec79fdebc56d5d6102725f7d"
NEW_SHA="b79c6c73ff85a5ed3c71cc094930827cb260fb82f7b59e4a85730a2d8124976e"

[[ -f "$LAB/model.py" && -f "$LAB/test_lab.py" && -f "$LAB/endpoint.py" ]] || {
  echo "[BCI][BLOCKED] Quarter lab not found at $LAB"; exit 1;
}
# Repeated installation is safe if and only if every installed artifact
# matches the previously verified U2.1 content.
CURRENT="$(sha256sum "$LAB/model.py" | cut -d ' ' -f 1)"
if [[ "$CURRENT" == "$NEW_SHA" ]]; then
  [[ -f "$LAB/test_extended_u21.py" && -f "$LAB/test_u21.py" ]] || {
    echo '[BCI][BLOCKED] U2.1 source present but its audit tests are missing'; exit 1;
  }
  printf '%s  %s\n' 'e841c1b8dd9da97e10647bd73432785734e8675044229d5df3c3947edc860b22' "$LAB/test_extended_u21.py" | sha256sum -c -
  printf '%s  %s\n' '8c04359004981cb2af9fd817f2de5e0aa555092b271dc62ce2c6636627619899' "$LAB/test_u21.py" | sha256sum -c -
  echo '[BCI][PASS] U2.1 already installed with verified tests; no mutation'
  exit 0
fi
for f in test_extended_u21.py test_u21.py; do
  if [[ -e "$LAB/$f" ]]; then
    echo "[BCI][BLOCKED] Existing conflicting test file: $f"; exit 1;
  fi
done

mkdir -p "$HOME/Documents"
STAGE="$(mktemp -d "$HOME/Documents/.a440-u21-stage-XXXXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
cat <<'BCI_U21_MODEL_SOURCE' > "$STAGE/model.py"
#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Component: A440 Unified Model U2.0 (legacy + universal foundation)
# Developer Seal: CJB-DEV-2026
# Design: business-independent schemas, learned temporal relationships,
#         query/forecast heads, reconciled evidence, governed checkpoints
# ============================================================
"""A440 integrated model architecture. Existing no-argument runtime remains
backward-compatible; generic business foundation activates via explicit CLI.

Model architecture ≠ pretrained universal competency. Task performance must be
measured on chronological and untouched external business holdouts.
"""
from __future__ import annotations

import hashlib,json,math,os,random,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

COUNT=20
SECONDS=int(os.getenv('QUARTER_SECONDS','300'))
SEED=440
DB=Path(os.environ.get('A440_STATE_DIR', str(Path.home() / 'Documents' / 'A440-Legacy-State')))
LOCK=threading.RLock()
DATA={}           # id -> list of records, known quarters only
FORECAST={}       # issued forecasts are stored before outcomes arrive
HISTORY=[]        # quarter reconciliations
MODEL_VERSION=0
START=time.monotonic()
READY=False
ERROR='Initializing'

def verify(r,agent,quarter):
    d=dict(r); claimed=d.pop('sha256',None)
    raw=json.dumps(d,sort_keys=True,separators=(',',':')).encode()
    expected=hashlib.sha256(raw).hexdigest()
    if not (claimed==expected and d.get('agent')==agent and d.get('quarter')==quarter and d.get('kind')=='synthetic' and d.get('currency')=='USD'):
        raise ValueError('Evidence contract/hash/identity mismatch')
    if not all(isinstance(d.get(k),(int,float)) and math.isfinite(d[k]) and d[k]>=0 for k in ('sales','units','returns','costs')):
        raise ValueError('Invalid business metrics')
    return r

def get(i,route):
    url=f'http://endpoint-{i:02d}:8000{route}'
    with urllib.request.urlopen(url,timeout=3) as resp:
        return json.load(resp)

def snapshot(records):
    if len(records)!=COUNT: raise ValueError('Quarter incomplete')
    result={k:round(sum(r[k] for r in records),2) for k in ('sales','returns','costs','units')}
    result['net_sales']=round(result['sales']-result['returns'],2)
    result['contribution_margin']=round(result['net_sales']-result['costs'],2)
    result['sources']=COUNT
    return result

# Shared 6->10->1 neural model, trained across all independent source histories.
# Input: four prior sales / source scale + season sine & cosine.
class Net:
    def __init__(self):
        rng=random.Random(SEED)
        self.w=[[rng.uniform(-.14,.14) for _ in range(6)] for _ in range(10)]
        self.b=[0.0]*10
        self.v=[rng.uniform(-.14,.14) for _ in range(10)]
        self.c=0.0
    def forward(self,x):
        h=[math.tanh(sum(w*t for w,t in zip(row,x))+b) for row,b in zip(self.w,self.b)]
        return sum(v*t for v,t in zip(self.v,h))+self.c,h
    def train(self,samples,epochs=140,lr=.01):
        rng=random.Random(SEED+len(samples)); indices=list(range(len(samples)))
        for _ in range(epochs):
            rng.shuffle(indices)
            for k in indices:
                x,target=samples[k];y,h=self.forward(x);err=max(-2,min(2,y-target))
                oldv=self.v[:]
                for j in range(10):
                    delta=err*oldv[j]*(1-h[j]*h[j])
                    for z in range(6):self.w[j][z]-=lr*delta*x[z]
                    self.b[j]-=lr*delta
                    self.v[j]-=lr*err*h[j]
                self.c-=lr*err
    def parameters(self):return {'w':self.w,'b':self.b,'v':self.v,'c':self.c}

NET=Net()

def feature(sales,q,scale):
    return [float(v/scale) for v in sales[-4:]]+[math.sin(q*math.pi/2), math.cos(q*math.pi/2)]

def examples():
    ex=[]
    for i in range(1,COUNT+1):
        records=DATA[i];sales=[r['sales'] for r in records];scale=max(1,sum(sales[:4])/4)
        for k in range(4,len(sales)):
            ex.append((feature(sales[:k],k,scale),sales[k]/scale))
    return ex

def predict_source(i,q,known=None):
    records=DATA[i];sales=[r['sales'] for r in records] if known is None else known
    scale=max(1,sum(r['sales'] for r in records[:4])/4)
    val,_=NET.forward(feature(sales,q,scale))
    # Bound forecast range to avoid nonsensical raw outputs early in training.
    return round(max(0,min(3*scale,val*scale)),2)

def forecast_quarters(start,n=4):
    local={i:[r['sales'] for r in DATA[i]] for i in range(1,COUNT+1)}
    projections=[]
    for q in range(start,start+n):
        total=0
        for i in local:
            value=predict_source(i,q,local[i]);local[i].append(value);total+=value
        projections.append({'quarter':q,'sales':round(total,2)})
    return projections

def atomic(path,payload):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(payload,indent=2)+'\n');tmp.replace(path)

def save():
    DB.mkdir(parents=True, exist_ok=True)
    doc={'initiative':'BEACON COMPUTING INITIATIVE','developer_seal':'CJB-DEV-2026','simulated_quarter_seconds':SECONDS,'baseline_quarters':8,'metrics':['sales','units','returns','costs','net_sales','contribution_margin'],'trained_model_version':MODEL_VERSION,'history':HISTORY,'issued_forecasts':FORECAST,'model_parameters':NET.parameters()}
    atomic(DB/'a440_state.json',doc)
    raw=(DB/'a440_state.json').read_bytes();atomic(DB/'SHA256.json',{'developer_seal':'CJB-DEV-2026','file':'a440_state.json','sha256':hashlib.sha256(raw).hexdigest()})

def load_baseline():
    for i in range(1,COUNT+1):
        agent=f'endpoint-{i:02d}'
        for trial in range(40):
            try:
                response=get(i,'/baseline')
                rs=response['records']
                if len(rs)!=8:raise ValueError('Bad baseline length')
                DATA[i]=[verify(r,agent,q) for q,r in enumerate(rs)]
                break
            except Exception:
                if trial==39:raise
                time.sleep(.5)

def loop():
    global READY,ERROR,MODEL_VERSION
    try:
        load_baseline()
        with LOCK:
            NET.train(examples()); MODEL_VERSION+=1
            for q in range(8):
                HISTORY.append({'quarter':q,'metrics':snapshot([DATA[i][q] for i in DATA]),'period':'baseline'})
            FORECAST['8']={'issued_before_outcome':True,'model_version':MODEL_VERSION,'sales':forecast_quarters(8,1)[0]['sales']}
            save();READY=True;ERROR=''
        print('[BCI] Hi, I am your BCIPitch. Baseline: 8 quarters, 20 endpoints; metrics: sales, units, returns, costs, net sales, contribution margin.',flush=True)
        q=8
        while True:
            deadline=START+(q-7)*SECONDS
            wait=deadline-time.monotonic()
            if wait>0:time.sleep(wait)
            # Fetch quarter only after its simulated time has ended.
            collected={}
            for i in range(1,COUNT+1):
                try: collected[i]=verify(get(i,f'/quarter/{q}'),f'endpoint-{i:02d}',q)
                except Exception as exc:print(f'[BCI][BLOCKED] {i} quarter {q}: {exc}',flush=True)
            if len(collected)!=COUNT:
                print(f'[BCI][BLOCKED] quarter {q}: {len(collected)}/20 sources; retry next second',flush=True)
                time.sleep(1);continue
            with LOCK:
                for i,r in collected.items(): DATA[i].append(r)
                metric=snapshot(list(collected.values()))
                prev=HISTORY[-1]['metrics']['sales']
                f=FORECAST.get(str(q),{})
                HISTORY.append({'quarter':q,'period':'live','metrics':metric,'quarter_on_quarter_sales_pct':round((metric['sales']/prev-1)*100,2),'prior_prediction_sales':f.get('sales'),'prior_prediction_error':round(metric['sales']-f['sales'],2) if 'sales' in f else None})
                # Completed quarter is now eligible for training; live predictions are separate.
                NET.train(examples(),epochs=50,lr=.006);MODEL_VERSION+=1
                FORECAST[str(q+1)]={'issued_before_outcome':True,'model_version':MODEL_VERSION,'sales':forecast_quarters(q+1,1)[0]['sales']}
                save()
                print(f'[BCI][Q{q-7}] This is how we are doing this quarter: sales ${metric["sales"]:,.2f}, net sales ${metric["net_sales"]:,.2f}, 20/20 verified sources; next forecast ${FORECAST[str(q+1)]["sales"]:,.2f}',flush=True)
            q+=1
    except Exception as exc:
        ERROR=str(exc);print('[BCI][FAIL]',ERROR,flush=True)

def report():
    if not READY:return {'status':'initializing' if ERROR=='Initializing' else 'blocked','details':ERROR}
    current=HISTORY[-1]; q=current['quarter']
    nextq=q+1
    forecasts=forecast_quarters(nextq,4)
    fiscal_start=(nextq//4)*4
    completed=[h['metrics']['sales'] for h in HISTORY if fiscal_start<=h['quarter']<nextq]
    needed=4-len(completed)
    year_forecast=round(sum(completed)+sum(x['sales'] for x in forecasts[:needed]),2)
    message=(f'Hi, I am your BCIPitch. I was loaded with 20 independently collected sources, eight historical financial quarters, and the following metrics: sales, units, returns, costs, net sales, and contribution margin. The baseline is ready.' if q==7 else f'This is how we are doing this quarter: sales ${current["metrics"]["sales"]:,.2f}, net sales ${current["metrics"]["net_sales"]:,.2f}. My next quarter sales forecast is ${forecasts[0]["sales"]:,.2f}; the current fiscal-year sales projection is ${year_forecast:,.2f}. These figures are synthetic simulations.')
    return {'message':message,'greeting':'Hi, I am your BCIPitch.','status':'running','loaded_metrics':['sales','units','returns','costs','net_sales','contribution_margin'],'baseline':'8 historical quarters (2 simulated fiscal years)','required_source_contributions':20,'latest_complete_quarter':q,'latest_period':current['period'],'latest_sales':current['metrics']['sales'],'latest_net_sales':current['metrics']['net_sales'],'latest_costs':current['metrics']['costs'],'next_quarter_forecast_sales':forecasts[0]['sales'],'current_fiscal_year_projected_sales':year_forecast,'model_version':MODEL_VERSION,'quarter_duration_seconds':SECONDS,'seconds_to_next_close':max(0,int(START+(q-6)*SECONDS-time.monotonic())),'reconciliation':'20 of 20 endpoint records verified per completed quarter','data_type':'SYNTHETIC / NOT FINANCIAL ADVICE','deployment_approved':False}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/','/ask','/health'):self.send_error(404);return
        with LOCK: r=report()
        body=json.dumps(r,indent=2).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*a):pass



# --- Upgraded business-independent A440 foundation (integrated) ---

import argparse
import copy
import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import random
import sqlite3
import statistics
import tempfile
import threading
import time
import urllib.parse
import unittest
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SEAL = "CJB-DEV-2026"
BRAND = "BEACON COMPUTING INITIATIVE"
VERSION = "A440-U2.1.0"
START_YEAR = 2024
INPUTS = 128
HIDDEN = 12
SEED = 440


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def bounded(x, a, b):
    return max(a, min(b, x))


def money(n):
    return f"${n:,.2f}"


def date_label(month):
    year, offset = divmod(month, 12)
    return f"{START_YEAR + year:04d}-{offset+1:02d}"


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(tmp, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclasses.dataclass(frozen=True)
class Metric:
    name: str
    source: str
    unit: str
    role: str
    department: str = "business"
    entity: str = "business"
    forecast: bool = False


class Contract:
    """Configuration, not business-dependent neural architecture."""

    def __init__(self, tenant, metrics, formulas=None):
        self.tenant = tenant
        self.metrics = {m.name: m for m in metrics}
        self.formulas = formulas or {}
        if not tenant or not metrics or len(self.metrics) != len(metrics):
            raise ValueError("Unique tenant and metric names are required")
        for m in metrics:
            if not m.name or not m.source or not m.unit or not m.role:
                raise ValueError("Incomplete data-acquisition contract")
        for name in self.formulas:
            self.evaluate_formula(name, {k: 0.0 for k in self.metrics})
            self.formula_unit(name)
            self.formula_leaves(name)

    def formula_unit(self, name, seen=None):
        if name in self.metrics:
            return self.metrics[name].unit
        seen = set() if seen is None else seen
        if name not in self.formulas or name in seen:
            raise ValueError("Unknown or cyclic formula unit")
        units = [self.formula_unit(arg, seen | {name}) for arg in self.formulas[name]["args"]]
        if len(set(units)) != 1:
            raise ValueError("Incompatible units in financial formula: "+name)
        return units[0]

    def formula_leaves(self, name, seen=None):
        if name in self.metrics:
            return [name]
        seen = set() if seen is None else seen
        if name not in self.formulas or name in seen:
            raise ValueError("Unknown or cyclic formula leaves")
        leaves = []
        for arg in self.formulas[name]["args"]:
            leaves.extend(self.formula_leaves(arg, seen | {name}))
        if len(leaves) != len(set(leaves)):
            raise ValueError("Double-counted metric in formula: "+name)
        return leaves

    def config(self):
        return {"initiative": BRAND, "developer_seal": SEAL, "tenant": self.tenant,
                "metrics": [dataclasses.asdict(x) for x in self.metrics.values()],
                "formulas": self.formulas}

    @classmethod
    def parse(cls, document):
        return cls(document["tenant"], [Metric(**m) for m in document["metrics"]],
                   document.get("formulas", {}))

    def evaluate_formula(self, name, values, active=None):
        active = set() if active is None else active
        if name in values:
            return values[name]
        if name not in self.formulas or name in active:
            raise ValueError("Unknown or cyclic financial formula: " + name)
        item = self.formulas[name]
        args = item.get("args", [])
        if not args or item.get("op") not in ("sum", "subtract"):
            raise ValueError("Invalid financial formula")
        active.add(name)
        values_list = [self.evaluate_formula(a, values, active) for a in args]
        active.remove(name)
        if item["op"] == "sum":
            return sum(values_list)
        return values_list[0] - sum(values_list[1:])

    def totals(self, values):
        result = dict(values)
        for name in self.formulas:
            result[name] = round(self.evaluate_formula(name, values), 2)
        return result


@dataclasses.dataclass(frozen=True)
class Evidence:
    tenant: str
    month: int
    source: str
    entity: str
    metric: str
    value: float
    unit: str
    department: str
    sha256: str

    def body(self):
        return {k: getattr(self, k) for k in
                ("tenant", "month", "source", "entity", "metric", "value", "unit", "department")}

    @classmethod
    def make(cls, tenant, month, spec, value):
        body = {"tenant": tenant, "month": month, "source": spec.source,
                "entity": spec.entity, "metric": spec.name, "value": float(value),
                "unit": spec.unit, "department": spec.department}
        return cls(**body, sha256=digest(body))

    @classmethod
    def parse(cls, data):
        return cls(**data)


def validate_evidence(record, contract):
    if record.tenant != contract.tenant or record.metric not in contract.metrics:
        raise ValueError("Unknown tenant or metric")
    m = contract.metrics[record.metric]
    if (record.source, record.entity, record.unit, record.department) != (
            m.source, m.entity, m.unit, m.department):
        raise ValueError("Evidence contract mismatch")
    if (type(record.month) is not int or record.month < 0 or
            type(record.value) not in (int, float) or not math.isfinite(record.value)):
        raise ValueError("Invalid month or numeric value")
    if record.sha256 != digest(record.body()):
        raise ValueError("SHA-256 evidence integrity mismatch")
    return True


class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)  # shared under A440Lab.lock
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS evidence (
            tenant TEXT NOT NULL, month INTEGER NOT NULL, source TEXT NOT NULL,
            entity TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL,
            unit TEXT NOT NULL, department TEXT NOT NULL, sha256 TEXT NOT NULL,
            PRIMARY KEY(tenant, month, source, entity, metric))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events (
            tenant TEXT NOT NULL, month INTEGER NOT NULL, event_id TEXT NOT NULL,
            data_json TEXT NOT NULL, sha256 TEXT NOT NULL,
            PRIMARY KEY(tenant, event_id))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS employee_shifts (
            tenant TEXT NOT NULL, month INTEGER NOT NULL, shift_id TEXT NOT NULL,
            employee_id TEXT NOT NULL, department TEXT NOT NULL, role TEXT NOT NULL,
            scheduled_hours REAL NOT NULL, actual_hours REAL NOT NULL,
            overtime_hours REAL NOT NULL, sha256 TEXT NOT NULL,
            PRIMARY KEY(tenant,month,shift_id,employee_id))""")
        self.db.commit()

    def insert_month(self, contract, records):
        if len(records) != len(contract.metrics):
            raise ValueError("Incomplete monthly Chorded Truth")
        months = {r.month for r in records}
        names = [r.metric for r in records]
        if len(months) != 1 or set(names) != set(contract.metrics) or len(set(names)) != len(names):
            raise ValueError("Missing, duplicate or mixed-period metrics")
        for r in records:
            validate_evidence(r, contract)
        with self.db:
            for r in records:
                key = (r.tenant, r.month, r.source, r.entity, r.metric)
                prior = self.db.execute(
                    "SELECT sha256 FROM evidence WHERE tenant=? AND month=? AND source=? AND entity=? AND metric=?",
                    key).fetchone()
                if prior and prior[0] != r.sha256:
                    raise ValueError("Append-only evidence conflict")
                self.db.execute("""INSERT OR IGNORE INTO evidence
                    (tenant,month,source,entity,metric,value,unit,department,sha256)
                    VALUES (?,?,?,?,?,?,?,?,?)""", key + (r.value, r.unit, r.department, r.sha256))

    def insert_event(self, tenant, month, event_id, details):
        doc = {"tenant": tenant, "month": month, "event_id": event_id, "details": details}
        h = digest(doc)
        with self.db:
            prior = self.db.execute("SELECT sha256 FROM events WHERE tenant=? AND event_id=?",
                                    (tenant, event_id)).fetchone()
            if prior and prior[0] != h:
                raise ValueError("Append-only event conflict")
            self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",
                            (tenant, month, event_id, canonical(doc), h))

    def insert_shifts(self, contract, shifts):
        """Append-only employee-level shift evidence; never treat hours as payroll cost."""
        if not shifts:
            return 0
        validated = []
        seen = set()
        for sh in shifts:
            if not isinstance(sh, dict):
                raise ValueError("Invalid shift record")
            body = {k: sh[k] for k in ("tenant", "month", "shift_id", "employee_id",
                         "department", "role", "scheduled_hours", "actual_hours", "overtime_hours")}
            if body["tenant"] != contract.tenant or type(body["month"]) is not int or body["month"] < 0:
                raise ValueError("Shift tenant or month mismatch")
            if not all(isinstance(body[k], str) and body[k] and len(body[k]) <= 128
                       for k in ("shift_id", "employee_id", "department", "role")):
                raise ValueError("Invalid shift identity")
            for key in ("scheduled_hours", "actual_hours", "overtime_hours"):
                val = body[key]
                if type(val) not in (int, float) or not math.isfinite(val) or val < 0:
                    raise ValueError("Invalid shift hours")
            if (body["actual_hours"] > 24 or body["scheduled_hours"] > 24 or
                    body["overtime_hours"] > body["actual_hours"]):
                raise ValueError("Impossible shift hours")
            if sh.get("sha256") != digest(body):
                raise ValueError("Shift SHA-256 integrity mismatch")
            key = (body["tenant"], body["month"], body["shift_id"], body["employee_id"])
            if key in seen:
                raise ValueError("Duplicate shift in batch")
            seen.add(key)
            validated.append((key, body, sh["sha256"]))
        with self.db:
            for key, body, checksum in validated:
                existing = self.db.execute(
                    "SELECT sha256 FROM employee_shifts WHERE tenant=? AND month=? AND shift_id=? AND employee_id=?",
                    key).fetchone()
                if existing and existing[0] != checksum:
                    raise ValueError("Append-only employee shift conflict")
                self.db.execute("""INSERT OR IGNORE INTO employee_shifts VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (body["tenant"], body["month"], body["shift_id"], body["employee_id"],
                     body["department"], body["role"], body["scheduled_hours"],
                     body["actual_hours"], body["overtime_hours"], checksum))
        return len(validated)

    def shift_summary(self, tenant, start_month=None, end_month=None):
        """Distinct employees, hours and overtime by period; None if no shift-level evidence."""
        clauses = ["tenant=?"]
        args = [tenant]
        if start_month is not None:
            clauses.append("month>=?")
            args.append(start_month)
        if end_month is not None:
            clauses.append("month<=?")
            args.append(end_month)
        rows = self.db.execute(
            "SELECT tenant,month,shift_id,employee_id,department,role,scheduled_hours,actual_hours,overtime_hours,sha256 "
            "FROM employee_shifts WHERE "+" AND ".join(clauses)+" ORDER BY month,shift_id,employee_id",
            args).fetchall()
        if not rows:
            return {"available": False, "employee_count": None, "overtime_employee_count": None,
                    "reason": "No individual shift records for this period"}
        employees = set()
        overtime = defaultdict(float)
        by_department = defaultdict(lambda: {"scheduled_hours":0., "actual_hours":0., "overtime_hours":0.})
        for row in rows:
            body = dict(zip(("tenant", "month", "shift_id", "employee_id", "department", "role",
                             "scheduled_hours", "actual_hours", "overtime_hours"), row[:-1]))
            if digest(body) != row[-1]:
                raise ValueError("Employee shift ledger integrity mismatch")
            employees.add(body["employee_id"])
            overtime[body["employee_id"]] += body["overtime_hours"]
            for k in ("scheduled_hours", "actual_hours", "overtime_hours"):
                by_department[body["department"]][k] += body[k]
        affected = {key: round(value, 3) for key, value in overtime.items() if value > 1e-7}
        return {"available": True, "employee_count":len(employees),
                "overtime_employee_count":len(affected), "overtime_by_employee":affected,
                "total_overtime_hours":round(sum(affected.values()),3),
                "departments": {dep:{k:round(v,3) for k,v in vals.items()} for dep,vals in by_department.items()},
                "shift_records":len(rows), "synthetic":tenant=="restaurant-001"}

    def history(self, contract):
        rows = self.db.execute("""SELECT tenant,month,source,entity,metric,value,unit,department,sha256
            FROM evidence WHERE tenant=? ORDER BY month,metric""",
            (contract.tenant,)).fetchall()
        grouped = defaultdict(dict)
        for row in rows:
            evidence = Evidence(*row)
            validate_evidence(evidence, contract)
            grouped[evidence.month][evidence.metric] = evidence.value
        if grouped and sorted(grouped) != list(range(max(grouped)+1)):
            raise ValueError("Incomplete chronological history")
        for vals in grouped.values():
            if set(vals) != set(contract.metrics):
                raise ValueError("Incomplete monthly evidence")
        return [grouped[m] for m in sorted(grouped)]

    def integrity_digest(self, tenant):
        rows = self.db.execute("SELECT month,source,entity,metric,sha256 FROM evidence WHERE tenant=? ORDER BY month,source,entity,metric", (tenant,)).fetchall()
        events = self.db.execute("SELECT month,event_id,sha256 FROM events WHERE tenant=? ORDER BY month,event_id", (tenant,)).fetchall()
        shifts = self.db.execute("SELECT month,shift_id,employee_id,sha256 FROM employee_shifts WHERE tenant=? ORDER BY month,shift_id,employee_id", (tenant,)).fetchall()
        return digest({"tenant":tenant,"evidence":rows,"events":events,"employee_shifts":shifts})

    def verified_snapshot(self, destination):
        destination = Path(destination)
        temp = destination.with_name(destination.name + ".tmp")
        with sqlite3.connect(str(temp)) as output:
            self.db.backup(output)
        os.replace(temp, destination)
        return hashlib.sha256(destination.read_bytes()).hexdigest()

    def events(self, tenant):
        rows = self.db.execute("SELECT data_json,sha256 FROM events WHERE tenant=? ORDER BY month",
                               (tenant,)).fetchall()
        events = []
        for payload, h in rows:
            doc = json.loads(payload)
            if digest(doc) != h:
                raise ValueError("Event integrity mismatch")
            events.append(doc)
        return events


class TemporalEncoder:
    """Fixed input width; stable hashing for new metrics, sources, entities.

    Relations are hashed learned interaction features, not causal claims or
    a transformer attention mechanism.
    """

    def __init__(self, contract, scales):
        self.contract = contract
        self.scales = scales

    @staticmethod
    def bucket(key):
        raw = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
        n = int.from_bytes(raw, "big")
        return 4 + n % (INPUTS - 4), (1 if (n >> 63) & 1 else -1)

    def encode(self, past, target_month):
        if not past or target_month != len(past):
            raise ValueError("Temporal features require past observations only")
        x = {0: 1.0, 1: math.sin(2*math.pi*(target_month%12)/12),
             2: math.cos(2*math.pi*(target_month%12)/12),
             3: bounded(len(past)/60, 0, 1)}

        def add(label, value):
            idx, sign = self.bucket(label)
            x[idx] = bounded(x.get(idx, 0) + sign*bounded(value, -3, 3)*.20, -3, 3)

        latest = past[-1]
        change = {}
        for name, m in self.contract.metrics.items():
            scale = self.scales[name]
            now = latest[name]
            prev = past[-2][name] if len(past) > 1 else now
            delta = bounded((now-prev)/scale, -2, 2)
            change[name] = delta
            add("value:"+name, now/scale)
            add("change:"+name, delta)
            add("role:"+m.role, delta)
            add("source:"+m.source, delta)
            add("department:"+m.department, delta)
            add("unit:"+m.unit, delta)
            add("entity:"+m.entity, delta)
        # Multi-resolution lag and rolling context uses strictly past periods.
        for name, m in self.contract.metrics.items():
            scale = self.scales[name]
            now = latest[name]
            for lag in (3, 6, 12):
                if len(past) > lag:
                    old = past[-1-lag][name]
                    add(f"lag:{lag}:{name}", (now-old)/scale)
            if len(past) >= 3:
                trailing = sum(row[name] for row in past[-3:])/3.0
                add("rolling3:"+name, (now-trailing)/scale)
        # Cross-source interactions; only contemporaneous *known* changes.
        by_department = defaultdict(list)
        for name, spec in self.contract.metrics.items():
            by_department[spec.department].append(name)
        for department, names in by_department.items():
            for i, left in enumerate(names):
                for right in names[i+1:]:
                    if self.contract.metrics[left].source == self.contract.metrics[right].source:
                        continue
                    add("relation:"+department+":"+left+":"+right,
                        change[left]*change[right])
        return x


def baseline_scales(history, contract):
    if len(history) < 4:
        raise ValueError("At least four baseline periods required")
    return {name: max(1., abs(statistics.median([r[name] for r in history[:24]])))
            for name in contract.metrics}


class UniversalNet:
    """Shared temporal encoder, semantic-role heads and isolated metric residuals.

    A string task preserves U2.0 role-head compatibility. A tuple
    (role, tenant, metric) trains a shared role head and an independent
    metric residual. Role heads allow learning transfer; residuals prevent
    two unrelated metrics from using precisely the same prediction head.
    """

    def __init__(self):
        rng = random.Random(SEED)
        self.w = [[rng.uniform(-.045, .045) for _ in range(INPUTS)] for _ in range(HIDDEN)]
        self.bias = [0.] * HIDDEN
        self.heads = {}

    @staticmethod
    def task_parts(task):
        if isinstance(task, str):
            return task, None
        if (not isinstance(task, tuple) or len(task) != 3 or
                not all(isinstance(part, str) and part for part in task)):
            raise ValueError("Invalid task-conditioned head")
        role, tenant, metric = task
        key = "metric::" + canonical([tenant, metric, role])
        return role, key

    def head(self, role):
        if role not in self.heads:
            rng = random.Random(SEED + int(hashlib.sha256(role.encode()).hexdigest()[:8], 16))
            self.heads[role] = {"w": [rng.uniform(-.03, .03) for _ in range(HIDDEN)], "b": 0.}
        return self.heads[role]

    def forward(self, x, task):
        role, specific = self.task_parts(task)
        h = [math.tanh(self.bias[j] + sum(self.w[j][i]*v for i,v in x.items()))
             for j in range(HIDDEN)]
        head = self.head(role)
        y = sum(a*b for a,b in zip(h,head["w"])) + head["b"]
        if specific is not None:
            residual = self.head(specific)
            y += sum(a*b for a,b in zip(h,residual["w"])) + residual["b"]
        return y, h

    def train_one(self, x, task, target, rate):
        pred, h = self.forward(x, task)
        err = bounded(pred-target, -1., 1.)
        role, specific = self.task_parts(task)
        heads = [self.head(role)] + ([self.head(specific)] if specific is not None else [])
        old = [sum(head["w"][j] for head in heads) for j in range(HIDDEN)]
        for j in range(HIDDEN):
            back = err*old[j]*(1-h[j]*h[j])
            for idx, value in x.items():
                self.w[j][idx] -= rate*back*value
            self.bias[j] -= rate*back
            for head in heads:
                head["w"][j] -= rate*err*h[j]/len(heads)
        for head in heads:
            head["b"] -= rate*err/len(heads)

    def export(self):
        return {"architecture": VERSION, "width": INPUTS, "hidden": HIDDEN,
                "w": self.w, "bias": self.bias, "heads": self.heads,
                "task_conditioning": "semantic-role-plus-tenant-metric-residual"}

    @classmethod
    def restore(cls, obj):
        if (obj.get("architecture") != VERSION or obj.get("width") != INPUTS or
                obj.get("hidden") != HIDDEN):
            raise ValueError("Incompatible model checkpoint: explicit migration required")
        m = cls()
        if (len(obj["w"]) != HIDDEN or any(len(row) != INPUTS for row in obj["w"]) or
                len(obj["bias"]) != HIDDEN or not isinstance(obj["heads"], dict)):
            raise ValueError("Invalid checkpoint dimensions")
        m.w, m.bias, m.heads = obj["w"], obj["bias"], obj["heads"]
        allvalues = [v for row in m.w for v in row] + m.bias
        for item in m.heads.values():
            if len(item["w"]) != HIDDEN:
                raise ValueError("Invalid task head")
            allvalues.extend(item["w"] + [item["b"]])
        if not all(type(v) in (float, int) and math.isfinite(v) for v in allvalues):
            raise ValueError("Nonfinite checkpoint")
        return m


class Learning:
    def __init__(self, contract, initial_history):
        self.contract = contract
        self.scales = baseline_scales(initial_history[:24], contract)
        self.encoder = TemporalEncoder(contract, self.scales)
        self.net = UniversalNet()
        self.version = 0
        self.decisions = []
        self.targets = [name for name,m in contract.metrics.items() if m.forecast]
        if not self.targets:
            raise ValueError("At least one forecast target required")

    def predict(self, history, name, net=None):
        net = net or self.net
        task = (self.contract.metrics[name].role, self.contract.tenant, name)
        x = self.encoder.encode(history, len(history))
        delta, _ = net.forward(x, task)
        base = history[-1][name]
        return round(max(0., base + bounded(delta, -.30, .30)*self.scales[name]), 2)

    def fit(self, net, history, max_target, epochs=8, rate=.002):
        # To train target period t, features may use periods [0, t).
        # Never train on targets >= max_target.
        samples = []
        for t in range(2, max_target):
            features = self.encoder.encode(history[:t], t)
            for name in self.targets:
                delta = bounded((history[t][name]-history[t-1][name])/self.scales[name], -.8, .8)
                task = (self.contract.metrics[name].role, self.contract.tenant, name)
                samples.append((features, task, delta))
        rng = random.Random(SEED + len(samples) + self.version)
        for _ in range(epochs):
            rng.shuffle(samples)
            for x, role, y in samples:
                net.train_one(x, role, y, rate)

    def score(self, net, history, months):
        errors = []
        for t in months:
            if t < 2 or t >= len(history):
                raise ValueError("Evaluation month out of range")
            for name in self.targets:
                forecast = self.predict(history[:t], name, net)
                errors.append(abs(forecast - history[t][name]) / self.scales[name])
        return round(sum(errors) / max(1, len(errors)), 8)

    def baseline(self, history):
        if len(history) != 24:
            raise ValueError("Baseline must be exactly 24 months")
        self.fit(self.net, history, max_target=20, epochs=13)
        self.version = 1
        return self.score(self.net, history, range(20, 24))

    def metric_scores(self, net, history, months):
        results = {}
        for name in self.targets:
            errors = []
            for t in months:
                if t < 2 or t >= len(history):
                    raise ValueError("Evaluation month out of range")
                errors.append(abs(self.predict(history[:t], name, net) - history[t][name]) / self.scales[name])
            results[name] = round(sum(errors) / len(errors), 8) if errors else 0.0
        return results

    def candidate_gate(self, history, previous_end):
        # Evaluate a locked six-month historical panel (two fiscal quarters)
        # with no examples from the panel used for gradient updates.
        last = len(history)
        if last < 27 or previous_end > last-1 or previous_end < 24:
            raise ValueError("Candidate gate needs a completed quarter and valid chronology")
        if (last - previous_end) != 3:
            raise ValueError("Candidate evaluation requires one newly closed quarter")
        validation_start = last - 6
        if validation_start < 20:
            raise ValueError("Not enough chronological validation history")
        candidate = copy.deepcopy(self.net)
        self.fit(candidate, history, max_target=validation_start, epochs=5, rate=.0015)
        window = range(validation_start, last)
        old_by = self.metric_scores(self.net, history, window)
        new_by = self.metric_scores(candidate, history, window)
        old_score = round(sum(old_by.values())/len(old_by), 8)
        new_score = round(sum(new_by.values())/len(new_by), 8)
        regressions = [name for name in self.targets if new_by[name] > old_by[name]*1.05 + 1e-8]
        improved = new_score <= old_score * .995
        promoted = improved and not regressions
        if promoted:
            self.net = candidate
            self.version += 1
        decision = {"validated_month":date_label(last-1), "validation_start":date_label(validation_start),
                    "validation_end":date_label(last-1), "validation_months":6,
                    "training_excludes_validation_window":True,
                    "old_normalized_MAE":old_score,"candidate_normalized_MAE":new_score,
                    "old_by_metric":old_by,"candidate_by_metric":new_by,
                    "metric_regressions_gt_5pct":regressions,
                    "promoted":promoted,"version":self.version,
                    "validation_scope":"two adjacent quarters; research selection exposure, not untouched holdout"}
        self.decisions.append(decision)
        return decision

    def next_quarter(self, history):
        projected = [dict(r) for r in history]
        rows = []
        for _ in range(3):
            new = dict(projected[-1])
            for name in self.targets:
                new[name] = self.predict(projected, name)
            projected.append(new)
            rows.append(self.contract.totals(new))
        amount = lambda key: round(sum(r.get(key, 0.) for r in rows), 2)
        return {"months": [date_label(len(history)+i) for i in range(3)],
                "forecast_metrics": {k: amount(k) for k in self.targets},
                "derived_quarter_totals": {k: amount(k) for k in self.contract.formulas},
                "assumption": "Unforecasted inputs carried forward; no future staffing event assumed",
                "calibrated_uncertainty": False, "model_version": self.version}


# The following *contracts and data generators* are replaceable; the above
# evidence schema, encoder, network, training, and reporting are unchanged.
def restaurant_contract():
    specs = [
        ("food_sales", "pos-food", "USD", "revenue", "kitchen", True),
        ("bar_sales", "pos-bar", "USD", "revenue", "bar", True),
        ("delivery_sales", "pos-delivery", "USD", "revenue", "kitchen", True),
        ("reservations", "reservations", "count", "demand", "front", False),
        ("covers", "guest-count", "count", "demand", "front", False),
        ("active_employees", "roster", "persons", "staffing", "business", False),
        ("kitchen_employees_per_shift", "shift-kitchen", "persons", "staffing", "kitchen", False),
        ("front_employees_per_shift", "shift-front", "persons", "staffing", "front", False),
        ("regular_hours", "timeclock", "hours", "labor", "business", False),
        ("overtime_hours", "overtime", "hours", "labor", "kitchen", True),
        ("kitchen_regular_wages", "payroll", "USD", "labor_cost", "kitchen", False),
        ("front_regular_wages", "payroll", "USD", "labor_cost", "front", False),
        ("kitchen_overtime_wages", "payroll", "USD", "labor_cost", "kitchen", False),
        ("front_overtime_wages", "payroll", "USD", "labor_cost", "front", False),
        ("inventory_units", "inventory", "units", "inventory", "kitchen", False),
        ("food_cogs", "inventory", "USD", "food_cost", "kitchen", True),
        ("purchases_cost", "purchasing", "USD", "cash_outflow", "kitchen", False),
        ("food_waste_cost", "waste", "USD", "food_cost", "kitchen", True),
        ("ingredient_price_index", "suppliers", "index", "prices", "kitchen", False),
        ("ticket_minutes", "kitchen-ops", "minutes", "service", "kitchen", True),
        ("complaints", "feedback", "count", "service", "front", False),
        ("kitchen_budget", "kitchen-budget", "USD", "budget", "kitchen", True),
        ("kitchen_utilities", "facilities", "USD", "overhead", "kitchen", False),
        ("other_utilities", "facilities", "USD", "overhead", "business", False),
        ("fixed_overhead", "facilities", "USD", "overhead", "business", False),
        ("marketing_cost", "marketing", "USD", "marketing", "business", False),
    ]
    formulas = {
        "kitchen_sales": {"op": "sum", "args": ["food_sales", "delivery_sales"]},
        "total_sales": {"op": "sum", "args": ["kitchen_sales", "bar_sales"]},
        "total_labor_cost": {"op": "sum", "args": ["kitchen_regular_wages", "front_regular_wages", "kitchen_overtime_wages", "front_overtime_wages"]},
        "kitchen_expenses": {"op": "sum", "args": ["food_cogs", "food_waste_cost", "kitchen_regular_wages", "kitchen_overtime_wages", "kitchen_utilities"]},
        "kitchen_budget_variance": {"op": "subtract", "args": ["kitchen_expenses", "kitchen_budget"]},
        "kitchen_contribution": {"op": "subtract", "args": ["kitchen_sales", "kitchen_expenses"]},
        "total_expenses": {"op": "sum", "args": ["food_cogs", "food_waste_cost", "total_labor_cost", "kitchen_utilities", "other_utilities", "fixed_overhead", "marketing_cost"]},
        "operating_profit": {"op": "subtract", "args": ["total_sales", "total_expenses"]}
    }
    return Contract("restaurant-001", [Metric(a,b,c,d,e,forecast=f) for a,b,c,d,e,f in specs], formulas)


def restaurant_values(month):
    season = 1. + .09*math.sin(2*math.pi*(month%12)/12) + .025*math.cos(2*math.pi*(month%12)/12)
    trend = 1. + .003*month
    departures = int(month >= 24) + int(month >= 26)
    staff = 6-departures
    kitchen_demand = season*trend*(1.-.008*departures)
    food = 132000*kitchen_demand
    delivery = 38000*season*trend
    bar = 41000*season*trend
    overtime = 50. + 37*departures + 12*max(0.,season-1.)
    kitchen_wages = 31200. + 200*month/12 - 500*departures
    kitchen_ot = overtime*28.
    front_wages = 42200. + 250*month/12
    front_ot = 300. + 100*max(0., season-1.)
    ordinary_cogs = (food+delivery)*(.28 + .0006*month)
    ordinary_waste = 2100. + .004*food
    crisis = (month == 28)  # May 2026, once during catch-up year.
    cogs = ordinary_cogs + (16000. if crisis else 0.)
    waste = ordinary_waste + (12500. if crisis else 0.)
    utilities = 4100. + 120*season
    planned_cost = ordinary_cogs + ordinary_waste + kitchen_wages + kitchen_ot + utilities
    data = {
        "food_sales": food, "bar_sales": bar, "delivery_sales": delivery,
        "reservations": 2400*season, "covers": 3800*season,
        "active_employees": 28-departures,
        "kitchen_employees_per_shift": staff, "front_employees_per_shift": 7,
        "regular_hours": (28-departures)*145., "overtime_hours": overtime,
        "kitchen_regular_wages": kitchen_wages, "front_regular_wages": front_wages,
        "kitchen_overtime_wages": kitchen_ot, "front_overtime_wages": front_ot,
        "inventory_units": 6500.-20*departures, "food_cogs": cogs,
        "purchases_cost": ordinary_cogs*.99 + (16000. if crisis else 0.),
        "food_waste_cost": waste, "ingredient_price_index": 1.+.002*month,
        "ticket_minutes": 17.+2.6*departures+(3. if crisis else 0.),
        "complaints": 9.+3*departures+(8 if crisis else 0),
        "kitchen_budget": planned_cost*1.055,
        "kitchen_utilities": utilities, "other_utilities": 7100.+100*season,
        "fixed_overhead": 34000.+30*month, "marketing_cost": 5100.+250*season,
    }
    return {name: round(float(value),2) for name,value in data.items()}


def retail_contract():
    specs = [
        Metric("in_store_sales", "store-pos", "USD", "revenue", forecast=True),
        Metric("online_sales", "web-pos", "USD", "revenue", forecast=True),
        Metric("returns_cost", "refunds", "USD", "cost", forecast=True),
        Metric("product_cogs", "stock-ledger", "USD", "cost", forecast=True),
        Metric("inventory_units", "warehouse", "units", "inventory"),
        Metric("labor_cost", "payroll", "USD", "labor_cost"),
        Metric("operating_cost", "facilities", "USD", "overhead"),
    ]
    formulas = {"total_sales": {"op":"sum", "args":["in_store_sales", "online_sales"]},
                "operating_profit": {"op":"subtract", "args":["total_sales", "returns_cost", "product_cogs", "labor_cost", "operating_cost"]}}
    return Contract("retail-001", specs, formulas)


def retail_values(month):
    seasonal = 1+.13*math.cos(2*math.pi*(month%12)/12)
    return {"in_store_sales":round(115000*seasonal*(1+.002*month),2),
            "online_sales":round(39000*seasonal*(1+.009*month),2),
            "returns_cost":round(4800*seasonal,2),
            "product_cogs":round(65000*seasonal*(1+.003*month),2),
            "inventory_units":round(8000-6*month,2),
            "labor_cost":round(38500+80*month,2),
            "operating_cost":round(19500+35*month,2)}


def logistics_contract():
    specs = [
        Metric("delivery_revenue", "billing", "USD", "revenue", forecast=True),
        Metric("jobs", "dispatch", "count", "demand", forecast=True),
        Metric("fuel_cost", "fleet-fuel", "USD", "cost", forecast=True),
        Metric("driver_labor", "driver-payroll", "USD", "labor_cost"),
        Metric("vehicle_maintenance", "maintenance", "USD", "cost"),
        Metric("late_deliveries", "sla", "count", "service", forecast=True),
        Metric("warehouse_capacity", "warehousing", "units", "capacity"),
    ]
    formulas = {"operating_profit": {"op":"subtract", "args":["delivery_revenue", "fuel_cost", "driver_labor", "vehicle_maintenance"]}}
    return Contract("logistics-001", specs, formulas)


def logistics_values(month):
    k = (1+.08*math.sin(2*math.pi*month/12))*(1+.004*month)
    return {"delivery_revenue":round(195000*k,2), "jobs":round(3800*k,2),
            "fuel_cost":round(51000*k,2), "driver_labor":round(60000*(1+.003*month),2),
            "vehicle_maintenance":round(18000+130*month,2),
            "late_deliveries":round(110+10*max(0., k-1.),2),
            "warehouse_capacity": 12500.}


PROFILES = {"restaurant":(restaurant_contract,restaurant_values),
            "retail":(retail_contract,retail_values),
            "logistics":(logistics_contract,logistics_values)}


def synthetic_records(contract, values, month):
    if set(values) != set(contract.metrics):
        raise ValueError("Synthetic generator does not satisfy business contract")
    return [Evidence.make(contract.tenant, month, spec, values[name])
            for name, spec in contract.metrics.items()]


def synthetic_employee_shifts(contract, month, monthly_values):
    """Reproducible shift evidence for the *catch-up* restaurant period only.

    Synthetic IDs are not names. Six original kitchen employees, seven front,
    and fifteen support employees; kitchen exits at months 24 and 26. The
    records reconcile the restaurant's aggregate monthly overtime hours.
    """
    if contract.tenant != "restaurant-001" or month < 24:
        return []
    kitchen = [f"EMP-K{i:03d}" for i in range(1, 7)
               if not (i == 5 and month >= 24) and not (i == 6 and month >= 26)]
    front = [f"EMP-F{i:03d}" for i in range(1, 8)]
    support = [f"EMP-S{i:03d}" for i in range(1, 16)]
    all_people = [(eid, dep, role) for dep, role, staff in
                  (("kitchen", "cook", kitchen), ("front", "server", front),
                   ("support", "support", support)) for eid in staff]
    if len(all_people) != int(monthly_values["active_employees"]):
        raise ValueError("Synthetic roster cannot reconcile active employees")
    overtime_cents = int(round(float(monthly_values["overtime_hours"])*100))
    n_over_shifts = len(kitchen)*16
    base, extra = divmod(overtime_cents, n_over_shifts)
    hours_regular = float(monthly_values["regular_hours"])/len(all_people)/16
    rows = []
    position = 0
    for employee_id, department, role in all_people:
        for shift in range(16):
            ot = (base + (1 if position < extra else 0))/100 if department == "kitchen" else 0.
            if department == "kitchen":
                position += 1
            body = {"tenant":contract.tenant, "month":month,
                    "shift_id":f"{month:03d}-D{shift+1:02d}-{department}",
                    "employee_id":employee_id,"department":department,"role":role,
                    "scheduled_hours":round(hours_regular,6),
                    "actual_hours":round(hours_regular+ot,6),"overtime_hours":ot}
            rows.append({**body, "sha256":digest(body)})
    return rows


def synthetic_events(contract, month):
    if contract.tenant != "restaurant-001":
        return []
    events = {24:("EMP-K005", "kitchen", "voluntary_departure"),
              26:("EMP-K006", "kitchen", "voluntary_departure"),
              28:("KITCHEN-BUDGET", "kitchen", "one_month_overrun")}
    return [(f"event-{month}", {"subject":events[month][0],
            "department":events[month][1], "type":events[month][2],
            "date":date_label(month)})] if month in events else []


def anomaly_questions(contract, history):
    if len(history) < 2:
        return []
    current, prev = history[-1], history[-2]
    results = []
    for name, spec in contract.metrics.items():
        old = prev[name]
        if old and abs(current[name]-old)/abs(old) >= .16:
            results.append({"metric":name, "change_pct":round((current[name]/old-1)*100,2),
                            "question":f"What changed in {spec.department} that explains {name}?",
                            "status":"hypothesis_to_investigate_not_causal_conclusion"})
    return sorted(results, key=lambda a:abs(a["change_pct"]), reverse=True)[:6]


class A440Lab:
    def __init__(self, contract, state_dir, generator=None):
        self.contract = contract
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db = Ledger(self.state_dir / "evidence.sqlite3")
        self.generator = generator
        self.learning = None
        self.baseline_score = None
        self.forecast_issued = {}
        self.quarter_results = []
        self.lock = threading.RLock()

    def add_synthetic_month(self, month):
        if not self.generator:
            raise ValueError("No synthetic generator configured")
        values = self.generator(month)
        self.db.insert_month(self.contract, synthetic_records(self.contract,values,month))
        shifts = synthetic_employee_shifts(self.contract, month, values)
        if shifts:
            self.db.insert_shifts(self.contract, shifts)
        for event_id,details in synthetic_events(self.contract,month):
            self.db.insert_event(self.contract.tenant, month, event_id, details)

    def bootstrap(self):
        history = self.db.history(self.contract)
        if len(history) >= 24:
            raise ValueError("Existing ledger detected: refusing automatic checkpoint reset")
        if history:
            raise ValueError("Partial ledger detected: operator reconciliation required")
        for month in range(24):
            self.add_synthetic_month(month)
        baseline = self.db.history(self.contract)
        self.learning = Learning(self.contract, baseline)
        self.baseline_score = self.learning.baseline(baseline)
        self.save()
        return self.baseline_score

    def save(self):
        if not self.learning:
            raise ValueError("Model not initialized")
        state = {"initiative":BRAND, "developer_seal":SEAL, "architecture":VERSION,
                 "contract_sha256":digest(self.contract.config()),
                 "evidence_ledger_sha256":self.db.integrity_digest(self.contract.tenant),
                 "last_month":len(self.db.history(self.contract))-1,
                 "baseline_normalized_MAE":self.baseline_score,
                 "model_version":self.learning.version,
                 "scales":self.learning.scales, "model":self.learning.net.export(),
                 "promotion_audit":self.learning.decisions,
                 "quarter_results":self.quarter_results,
                 "issued_forecasts":self.forecast_issued,
                 "synthetic_only":self.generator is not None}
        h = atomic_json(self.state_dir / "a440_model.json", state)
        db_sha = self.db.verified_snapshot(self.state_dir / "a440_evidence_snapshot.sqlite3")
        atomic_json(self.state_dir / "a440_model.SHA256.json",
                    {"initiative":BRAND,"developer_seal":SEAL,
                     "files":{"a440_model.json":h,
                              "a440_evidence_snapshot.sqlite3":db_sha}})

    def load(self):
        state_file = self.state_dir / "a440_model.json"
        hfile = self.state_dir / "a440_model.SHA256.json"
        if not (state_file.exists() and hfile.exists()):
            raise ValueError("Missing signed-off checkpoint/manifest; no automatic overwrite")
        manifest = json.loads(hfile.read_text())
        actual_model_sha = hashlib.sha256(state_file.read_bytes()).hexdigest()
        snap_file = self.state_dir / "a440_evidence_snapshot.sqlite3"
        if (manifest.get("files",{}).get("a440_model.json") != actual_model_sha or
                not snap_file.exists() or
                manifest["files"].get("a440_evidence_snapshot.sqlite3") != hashlib.sha256(snap_file.read_bytes()).hexdigest()):
            raise ValueError("Checkpoint SHA-256 integrity failure")
        state = json.loads(state_file.read_text())
        if state.get("evidence_ledger_sha256") != self.db.integrity_digest(self.contract.tenant):
            raise ValueError("Evidence ledger integrity mismatch")
        if state.get("contract_sha256") != digest(self.contract.config()):
            raise ValueError("Checkpoint contract mismatch")
        history = self.db.history(self.contract)
        if state["last_month"] != len(history)-1:
            raise ValueError("Ledger/checkpoint version mismatch: refusing unsafe resume")
        self.learning = Learning(self.contract, history[:24])
        self.learning.net = UniversalNet.restore(state["model"])
        if self.learning.scales != state["scales"]:
            raise ValueError("Baseline normalization mismatch")
        self.learning.version = state["model_version"]
        self.learning.decisions = state["promotion_audit"]
        self.baseline_score = state["baseline_normalized_MAE"]
        self.quarter_results = state["quarter_results"]
        self.forecast_issued = state["issued_forecasts"]

    def train_ingested(self):
        """Replay imported complete months chronologically; do not retrain live state."""
        if (self.state_dir / "a440_model.json").exists():
            raise ValueError("Existing checkpoint: refusing replacement")
        all_months = self.db.history(self.contract)
        if len(all_months) < 24 or len(all_months) % 3:
            raise ValueError("Imported history requires >=24 consecutive, complete months in quarters")
        self.learning = Learning(self.contract, all_months[:24])
        self.baseline_score = self.learning.baseline(all_months[:24])
        for start in range(24, len(all_months), 3):
            self.forecast_issued[str(start//3)] = self.learning.next_quarter(all_months[:start])
            decision = self.learning.candidate_gate(all_months[:start+3],previous_end=start)
            observed = [self.contract.totals(row) for row in all_months[start:start+3]]
            self.quarter_results.append({
                "quarter":start//3, "period":f"{date_label(start)}..{date_label(start+2)}",
                "issued_prior_to_outcome":True,
                "issued_forecast":self.forecast_issued[str(start//3)],
                "actuals":{k:round(sum(row[k] for row in observed),2)
                           for k in self.contract.formulas},
                "candidate_decision":decision})
        self.save()
        return {"processed_months":len(all_months),
                "replayed_quarters":len(self.quarter_results),
                "model_version":self.learning.version}

    def close_quarter(self):
        if not self.learning:
            raise ValueError("Bootstrap before collecting quarterly data")
        history = self.db.history(self.contract)
        start = len(history)
        if start % 3:
            raise ValueError("Quarter cannot start on an incomplete boundary")
        # Forecast is issued if and only if no future quarter is ingested.
        forecast = self.learning.next_quarter(history)
        self.forecast_issued[str(start//3)] = copy.deepcopy(forecast)
        for month in range(start,start+3):
            self.add_synthetic_month(month)
        updated = self.db.history(self.contract)
        candidate = self.learning.candidate_gate(updated, previous_end=start)
        months = [self.contract.totals(row) for row in updated[start:start+3]]
        metric_keys = set(months[0])
        quarter_totals = {k:round(sum(row[k] for row in months),2) for k in metric_keys
                          if k not in ("active_employees","kitchen_employees_per_shift","front_employees_per_shift","ingredient_price_index","ticket_minutes","inventory_units")}
        if "kitchen_employees_per_shift" in updated[-1]:
            quarter_totals["employees_per_kitchen_shift_at_close"] = updated[-1]["kitchen_employees_per_shift"]
            quarter_totals["employees_active_at_close"] = updated[-1]["active_employees"]
        outcome = {"quarter":start//3, "period":f"{date_label(start)}..{date_label(start+2)}",
                   "issued_prior_to_outcome":True,"issued_forecast":forecast,
                   "actuals":quarter_totals,"candidate_decision":candidate,
                   "events":[e for e in self.db.events(self.contract.tenant)
                             if start <= e["month"] < start+3]}
        self.quarter_results.append(outcome)
        self.save()
        return outcome

    def summary(self):
        history = self.db.history(self.contract)
        if not history:
            return {"status":"empty","tenant":self.contract.tenant}
        latest = self.contract.totals(history[-1])
        result = {"initiative":BRAND,"developer_seal":SEAL,"version":VERSION,
                  "status":"running","tenant":self.contract.tenant,
                  "complete_months":len(history), "complete_quarters":len(history)//3,
                  "last_period":date_label(len(history)-1),
                  "observed_sources":len({m.source for m in self.contract.metrics.values()}),
                  "current_actuals":{k:latest[k] for k in self.contract.formulas},
                  "events":self.db.events(self.contract.tenant),
                  "model_version":self.learning.version if self.learning else 0,
                  "last_training_gate":self.learning.decisions[-1] if self.learning and self.learning.decisions else None,
                  "open_investigations":anomaly_questions(self.contract, history),
                  "individual_shift_evidence":self.db.shift_summary(self.contract.tenant,
                    start_month=max(0,len(history)-3),end_month=len(history)-1),
                  "research_only":True}
        if self.learning:
            result["next_quarter"] = self.learning.next_quarter(history)
        return result

    def investigate(self, question):
        """Deterministic, evidence-grounded comparison; no language-model inference."""
        history = self.db.history(self.contract)
        if len(history) < 2:
            return {"status":"insufficient_history"}
        prompt = question.lower()
        names = sorted(list(self.contract.metrics)+list(self.contract.formulas),key=len,reverse=True)
        target = next((key for key in names if key.replace("_", " ") in prompt or key in prompt), None)
        if target is None:
            return {"status":"unsupported_intent", "available_metrics":names}
        prev = self.contract.totals(history[-2]); now = self.contract.totals(history[-1])
        unit = self.contract.formula_unit(target)
        difference = round(now[target]-prev[target], 4)
        return {"status":"evidence_grounded", "metric":target,"unit":unit,
                "previous_month":date_label(len(history)-2),
                "current_month":date_label(len(history)-1),
                "previous_value":prev[target],"current_value":now[target],
                "delta":difference,"delta_percent":round(difference/abs(prev[target])*100,2) if prev[target] else None,
                "provenance_sources":sorted({self.contract.metrics[name].source
                    for name in self.contract.formula_leaves(target)}),
                "causal_claim":False,
                "question":"What supporting operational factors could explain this change?"}

    def ask(self, question):
        with self.lock:
            history = self.db.history(self.contract)
            if not history:
                return {"status":"no_data"}
            text = question.lower()
            latest = self.contract.totals(history[-1])
            if ("kitchen" in text and ("budget" in text or "overrun" in text)) and "kitchen_budget_variance" in latest:
                over = [(date_label(i), self.contract.totals(row)["kitchen_budget_variance"])
                        for i,row in enumerate(history) if self.contract.totals(row)["kitchen_budget_variance"] > 0]
                return {"question":question,"status":"evidence_grounded",
                        "latest_month":""+date_label(len(history)-1),
                        "kitchen_sales_latest":latest["kitchen_sales"],
                        "kitchen_expenses_latest":latest["kitchen_expenses"],
                        "kitchen_budget_latest":latest["kitchen_budget"],
                        "months_over_budget":over,
                        "expense_breakdown_latest":{key:latest[key] for key in
                          ("food_cogs","food_waste_cost","kitchen_regular_wages",
                           "kitchen_overtime_wages","kitchen_utilities")},
                        "explanation":"Variance equals actual kitchen expenses less the kitchen budget. Expense categories are exact ledger calculations; causal attribution is not established."}
            if "overtime" in text or "employee" in text or "staff" in text:
                fields = ("active_employees","kitchen_employees_per_shift","overtime_hours",
                          "kitchen_overtime_wages","front_overtime_wages")
                return {"question":question,"status":"evidence_grounded",
                        "current":{k:latest[k] for k in fields if k in latest},
                        "historical_events":self.db.events(self.contract.tenant),
                        "employee_shift_evidence":self.db.shift_summary(self.contract.tenant,
                            start_month=max(0,len(history)-3), end_month=len(history)-1),
                        "note":"Synthetic employee IDs; individual counts only when shift evidence exists"}
            if "forecast" in text or "next quarter" in text or "project" in text:
                return {"question":question,"status":"model_estimate",
                        "forecast":self.learning.next_quarter(history)}
            if "sales" in text or "profit" in text or "revenue" in text:
                return {"question":question,"status":"evidence_grounded",
                        "actuals":{k:latest[k] for k in self.contract.formulas}}
            if any(k in text for k in ("why", "investigate", "explain", "changed", "drivers")):
                return self.investigate(question)
            # Metric-name lookup works for a new contract without rewriting code.
            for name in self.contract.metrics:
                if name.replace("_"," ") in text:
                    return {"question":question,"status":"evidence_grounded",
                            "metric":name,"value":latest[name],
                            "unit":self.contract.metrics[name].unit}
            return {"question":question,"status":"unsupported_intent",
                    "message":"This is a verified calculation/forecast router, not yet a general conversational LLM.",
                    "available_formulas":list(self.contract.formulas),
                    "available_metrics":list(self.contract.metrics)}


class BusinessHandler(BaseHTTPRequestHandler):
    lab = None
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/status", "/health"):
            with self.lab.lock:
                data = self.lab.summary()
        elif parsed.path == "/ask":
            q = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
            data = self.lab.ask(q)
        else:
            self.send_error(404)
            return
        data_bytes = json.dumps(data, indent=2, allow_nan=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data_bytes)))
        self.end_headers()
        self.wfile.write(data_bytes)
    def log_message(self, *_args):
        return


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.contract = restaurant_contract()

    def test_twenty_sources_and_completeness(self):
        self.assertEqual(len({m.source for m in self.contract.metrics.values()}), 20)
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder)/"ledger.db")
            records = synthetic_records(self.contract, restaurant_values(0), 0)
            with self.assertRaises(ValueError):
                ledger.insert_month(self.contract, records[:-1])
            ledger.insert_month(self.contract, records)
            self.assertEqual(len(ledger.history(self.contract)), 1)

    def test_tamper_proof(self):
        original = Evidence.make(self.contract.tenant, 0, self.contract.metrics["food_sales"], 200)
        bad = dataclasses.replace(original, value=300)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_evidence(bad, self.contract)

    def test_ledger_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder)/"ledger.db")
            ledger.insert_month(self.contract, synthetic_records(self.contract,restaurant_values(0),0))
            vals = restaurant_values(0)
            vals["food_sales"] += 1000
            with self.assertRaisesRegex(ValueError,"conflict"):
                ledger.insert_month(self.contract,synthetic_records(self.contract,vals,0))

    def test_departures_overtime(self):
        a,b,c = restaurant_values(23), restaurant_values(24), restaurant_values(26)
        self.assertEqual(a["active_employees"]-c["active_employees"], 2)
        self.assertEqual(a["kitchen_employees_per_shift"]-c["kitchen_employees_per_shift"],2)
        self.assertGreater(c["overtime_hours"], a["overtime_hours"])

    def test_may_2026_kitchen_overrun(self):
        vals = self.contract.totals(restaurant_values(28))
        self.assertGreater(vals["kitchen_budget_variance"],0)
        self.assertGreater(vals["kitchen_sales"],0)
        self.assertAlmostEqual(vals["kitchen_sales"],vals["food_sales"]+vals["delivery_sales"],places=2)
        self.assertAlmostEqual(vals["total_sales"],vals["kitchen_sales"]+vals["bar_sales"],places=2)
        self.assertEqual(date_label(28),"2026-05")

    def test_formula_units_and_duplicate_guards(self):
        specs = [Metric("usd", "a", "USD", "revenue"),
                 Metric("count", "b", "count", "volume")]
        with self.assertRaisesRegex(ValueError,"Incompatible units"):
            Contract("broken",specs,{"bad":{"op":"sum","args":["usd","count"]}})
        with self.assertRaisesRegex(ValueError,"Double-counted"):
            Contract("broken",specs,{"bad":{"op":"sum","args":["usd","usd"]}})

    def test_no_double_count_purchases(self):
        a = restaurant_values(28)
        first = self.contract.totals(a)["operating_profit"]
        a["purchases_cost"] += 100000
        self.assertEqual(first,self.contract.totals(a)["operating_profit"])

    def test_future_leakage(self):
        history = [restaurant_values(i) for i in range(24)]
        encoder = TemporalEncoder(self.contract,baseline_scales(history,self.contract))
        before = encoder.encode(history[:15],15)
        history[23]["food_sales"] = 1e99
        after = encoder.encode(history[:15],15)
        self.assertEqual(before,after)

    def test_two_industries_same_network(self):
        for make_contract, gen in ((retail_contract,retail_values),(logistics_contract,logistics_values)):
            contract = make_contract()
            history = [gen(m) for m in range(24)]
            learner = Learning(contract,history)
            learner.baseline(history)
            pred = learner.next_quarter(history)
            self.assertTrue(pred["forecast_metrics"])
            self.assertEqual(learner.net.export()["width"],INPUTS)

    def test_industry_agnostic_import_and_training(self):
        contract = logistics_contract()
        with tempfile.TemporaryDirectory() as folder:
            lab = A440Lab(contract,folder)
            for m in range(27):
                lab.db.insert_month(contract, synthetic_records(contract,logistics_values(m),m))
            result = lab.train_ingested()
            self.assertEqual(result["processed_months"],27)
            self.assertEqual(result["replayed_quarters"],1)
            second = A440Lab(contract,folder)
            second.load()
            self.assertEqual(second.summary()["complete_months"],27)

    def test_checkpoint_sha_and_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            lab=A440Lab(self.contract,folder,restaurant_values)
            lab.bootstrap()
            restored=A440Lab(self.contract,folder,restaurant_values)
            restored.load()
            self.assertEqual(lab.learning.version,restored.learning.version)
            target=Path(folder)/"a440_model.json"
            target.write_text(target.read_text()+" ")
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                restored.load()

    def test_catchup_four_quarters(self):
        with tempfile.TemporaryDirectory() as folder:
            lab=A440Lab(self.contract,folder,restaurant_values)
            lab.bootstrap()
            for _ in range(4):
                lab.close_quarter()
            self.assertEqual(len(lab.db.history(self.contract)),36)
            self.assertEqual(len(lab.quarter_results),4)
            self.assertEqual(len(lab.db.events(self.contract.tenant)),3)
            r=lab.ask("Why is the kitchen over budget?")
            self.assertTrue(any(month=="2026-05" for month,_ in r["months_over_budget"]))


def run_tests():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FoundationTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def cli():
    p=argparse.ArgumentParser(description=f"{BRAND} - {VERSION} - {SEAL}")
    p.add_argument("--profile",choices=tuple(PROFILES),default="restaurant")
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--demo",action="store_true",help="24-month baseline + 12-month chronological catch-up")
    p.add_argument("--run",action="store_true",help="continue simulated quarters; local read-only API")
    p.add_argument("--quarter-seconds",type=int,default=300)
    p.add_argument("--port",type=int,default=18081)
    p.add_argument("--state-dir",default=str(Path.home()/"Documents"/"A440-Universal-State-U2.1"))
    p.add_argument("--show-contract",action="store_true")
    p.add_argument("--contract-json",help="External business's reviewed data contract")
    p.add_argument("--ingest-jsonl",help="Import monthly evidence rows with SHA256, one JSON object per line")
    p.add_argument("--train-ingested",action="store_true",help="Train on imported baseline then replay complete quarters chronologically")
    p.add_argument("--ask",help="Ask a supported evidence or forecast question")
    args=p.parse_args()
    if args.self_test:
        raise SystemExit(0 if run_tests() else 1)
    if args.quarter_seconds < 1 or not (1024 <= args.port <= 65535):
        p.error("Invalid quarter length or port")
    if args.contract_json:
        contract=Contract.parse(json.loads(Path(args.contract_json).read_text()))
        generator=None
    else:
        factory,generator=PROFILES[args.profile]
        contract=factory()
    if args.show_contract:
        print(json.dumps(contract.config(),indent=2))
        return
    if args.demo and (args.ingest_jsonl or args.contract_json):
        p.error("Synthetic demo and external ingestion must remain separate")
    if args.demo:
        with tempfile.TemporaryDirectory(prefix="a440-universal-demo-") as folder:
            lab=A440Lab(contract,folder,generator)
            base=lab.bootstrap()
            print(f"[BCI][PASS] {contract.tenant} 24-month baseline; normalized MAE={base:.6f}",flush=True)
            for _ in range(4):
                result=lab.close_quarter()
                print(f"[BCI][QUARTER] {result['period']} candidate={result['candidate_decision']['promoted']} ",
                      f"version={result['candidate_decision']['version']}",flush=True)
            print(json.dumps(lab.summary(),indent=2))
            print(json.dumps(lab.ask("why did the kitchen go over budget?"),indent=2))
        return
    state_path=Path(args.state_dir)/contract.tenant
    lab=A440Lab(contract,state_path,generator)
    if args.ingest_jsonl:
        # External evidence must already carry SHA256 computed by data producer.
        # Import only complete months; unsigned/malformed rows are rejected.
        by_month=defaultdict(list)
        for line in Path(args.ingest_jsonl).read_text().splitlines():
            if line.strip():
                record=Evidence.parse(json.loads(line))
                validate_evidence(record,contract)
                by_month[record.month].append(record)
        for month, rows in sorted(by_month.items()):
            lab.db.insert_month(contract,rows)
        print(f"[BCI][PASS] Imported {len(by_month)} complete months for {contract.tenant}")
        if not args.train_ingested:
            return
    if args.train_ingested:
        print(json.dumps(lab.train_ingested(),indent=2))
        return
    if args.ask:
        lab.load()
        print(json.dumps(lab.ask(args.ask),indent=2))
        return
    if not args.run:
        p.print_help()
        return
    if generator is None:
        p.error("Live simulation requires a built-in synthetic profile; external contracts support ingestion")
    if (state_path/"a440_model.json").exists():
        lab.load()
        print("[BCI][PASS] Verified previous checkpoint restored",flush=True)
    else:
        lab.bootstrap()
        for _ in range(4):
            output=lab.close_quarter()
            print(f"[BCI][CATCH-UP] {output['period']}: "
                  f"{'PROMOTE' if output['candidate_decision']['promoted'] else 'REJECT'}",flush=True)
    BusinessHandler.lab=lab
    server=ThreadingHTTPServer(("127.0.0.1",args.port),BusinessHandler)
    print(f"[BCI][READY] {contract.tenant}: http://127.0.0.1:{args.port}/status",flush=True)
    print(f"[BCI][READY] One fiscal quarter every {args.quarter_seconds} real seconds",flush=True)

    def quarterly_worker():
        while True:
            time.sleep(args.quarter_seconds)
            with lab.lock:
                try:
                    outcome=lab.close_quarter()
                    print(f"[BCI][OBSERVED] {outcome['period']} "
                          f"candidate={outcome['candidate_decision']['promoted']}",flush=True)
                except Exception as exc:
                    print(f"[BCI][BLOCKED] Quarterly processing: {exc}",flush=True)
                    break

    threading.Thread(target=quarterly_worker,daemon=True).start()
    try:
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        print("\n[BCI] Stopping server, checkpoint retained",flush=True)
    finally:
        server.server_close()




# ---------------------- Unified model dispatch -----------------------------
def architecture_manifest():
    """Describe architecture only; neither load data nor start a server."""
    return {
        "initiative": "BEACON COMPUTING INITIATIVE",
        "developer_seal": "CJB-DEV-2026",
        "model": "A440-U2.0 integrated",
        "current_model": "A440-U2.1.0 integrated",
        "foundation_version": VERSION,
        "architecture_ready": True,
        "trained_across_businesses": False,
        "legacy": {
            "model": "Net 6->10->1",
            "interfaces": ["verify", "snapshot", "Net", "examples", "forecast_quarters"],
            "launch": "python model.py  (legacy compatibility)"
        },
        "universal": {
            "inputs": INPUTS, "hidden": HIDDEN,
            "dynamic_metric_contracts": True,
            "temporal_and_hashed_relational_features": True,
            "multi_target_forecasting": True,
            "role_and_metric_specific_heads": True,
            "multi_resolution_temporal_features": [3,6,12],
            "individual_employee_shift_ledger": True,
            "six_month_candidate_gate": True,
            "deterministic_accounting": True,
            "chronological_candidate_gate": True,
            "evidence_ledger": "SQLite WAL / SHA-256",
            "question_handling": "limited evidence-based intent routing",
            "training": "requires explicit external data contracts and baseline",
        },
        "state_isolation": "universal foundation uses a separate state directory",
    }


def launch_legacy_runtime():
    """The original Docker entry point is preserved without code changes."""
    if SECONDS < 1:
        raise RuntimeError('Invalid interval')
    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()


def main():
    import sys
    if len(sys.argv) == 1:
        launch_legacy_runtime()
        return
    if sys.argv[1] == '--legacy':
        if len(sys.argv) > 2:
            raise SystemExit('--legacy accepts no additional parameters')
        launch_legacy_runtime()
        return
    if sys.argv[1] == '--architecture':
        if len(sys.argv) > 2:
            raise SystemExit('--architecture accepts no additional parameters')
        print(json.dumps(architecture_manifest(), indent=2, sort_keys=True))
        return
    if sys.argv[1] == '--foundation':
        sys.argv.pop(1)
    cli()  # Existing U1 foundation CLI, now part of model.py itself.


if __name__ == '__main__':
    main()
BCI_U21_MODEL_SOURCE
cat <<'BCI_U21_EXTENDED_TESTS' > "$STAGE/test_extended.py"
#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Component: A440 U2.0 Extended Function and Failure-Path Audit
# Developer Seal: CJB-DEV-2026
# Execution: isolated temporary state; no external containers
# ============================================================
import contextlib
import copy
import io
import json
import math
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from http.server import ThreadingHTTPServer

import model
import endpoint


class ExtendedAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bci-a440-exhaustive-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.contract = model.restaurant_contract()

    def _value(self, month=0):
        return model.restaurant_values(month)

    def _lab(self):
        return model.A440Lab(self.contract, self.folder / "lab", model.restaurant_values)

    def test_01_legacy_net_features_and_verification(self):
        endpoint.ID = 1
        payload = endpoint.record(0)
        self.assertIs(model.verify(payload, "endpoint-01", 0), payload)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            model.verify(payload, "endpoint-99", 0)
        with self.assertRaisesRegex(ValueError, "Quarter incomplete"):
            model.snapshot([payload])
        samples = []
        for i in range(1, 21):
            endpoint.ID = i
            samples.append(endpoint.record(7))
        self.assertEqual(model.snapshot(samples)["sources"], 20)
        n = model.Net()
        x = model.feature([1, 2, 3, 4], 8, 2)
        self.assertEqual(len(x), 6)
        prior = n.forward(x)[0]
        n.train([(x, 1.)], epochs=1)
        self.assertNotEqual(prior, n.forward(x)[0])
        self.assertEqual(len(n.parameters()["w"]), 10)

    def test_02_legacy_network_fetch_and_baseline(self):
        endpoint.ID = 5
        value = endpoint.record(8)
        class DummyResponse:
            def __enter__(self):
                return io.BytesIO(json.dumps(value).encode())
            def __exit__(self, *_):
                return False
        with mock.patch.object(model.urllib.request, "urlopen", return_value=DummyResponse()) as wrapped:
            self.assertEqual(model.get(5, "/quarter/8")["agent"], "endpoint-05")
            self.assertIn("endpoint-05:8000/quarter/8", wrapped.call_args.args[0])
        def fake_get(i, route):
            endpoint.ID = i
            return {"records": [endpoint.record(k) for k in range(8)]}
        old_data = model.DATA
        with mock.patch.object(model, "DATA", {}), mock.patch.object(model, "get", side_effect=fake_get):
            model.load_baseline()
            self.assertEqual(len(model.DATA), 20)
            self.assertEqual(len(model.examples()), 80)
            self.assertEqual(len(model.forecast_quarters(8, 4)), 4)
            self.assertGreaterEqual(model.predict_source(1, 8), 0)
        self.assertIs(model.DATA, old_data)

    def test_03_legacy_checkpoint_and_report(self):
        old_db = model.DB
        with mock.patch.object(model, "DB", self.folder / "legacy-state"):
            with mock.patch.object(model, "HISTORY", [{"quarter": 7, "metrics": {"sales": 1000, "costs": 400, "net_sales": 950}, "period": "baseline"}]):
                with mock.patch.object(model, "FORECAST", {"8": {"sales": 1200}}):
                    with mock.patch.object(model, "MODEL_VERSION", 1), mock.patch.object(model, "READY", True):
                        with mock.patch.object(model, "forecast_quarters", return_value=[{"sales": 1200}]*4):
                            r = model.report()
                            self.assertEqual(r["status"], "running")
                        model.save()
                        self.assertTrue((model.DB / "SHA256.json").exists())
        self.assertIs(model.DB, old_db)
        with mock.patch.object(model, "READY", False), mock.patch.object(model, "ERROR", "Initializing"):
            self.assertEqual(model.report()["status"], "initializing")
        with mock.patch.object(model, "READY", False), mock.patch.object(model, "ERROR", "startup error"):
            self.assertEqual(model.report()["status"], "blocked")
        model.atomic(self.folder / "simple.json", {"ok": True})
        self.assertEqual(json.loads((self.folder / "simple.json").read_text())["ok"], True)

    def test_04_legacy_complete_quarter_loop_bounded(self):
        def fake_get(i, route):
            endpoint.ID = i
            if route == "/baseline":
                return {"records": [endpoint.record(k) for k in range(8)]}
            if route == "/quarter/8":
                return endpoint.record(8)
            raise ValueError("audit controlled termination")
        def stop_sleep(*_):
            raise RuntimeError("end bounded live audit")
        with contextlib.redirect_stdout(io.StringIO()), \
             mock.patch.object(model, "get", side_effect=fake_get), \
             mock.patch.object(model, "DATA", {}), \
             mock.patch.object(model, "HISTORY", []), \
             mock.patch.object(model, "FORECAST", {}), \
             mock.patch.object(model, "NET", model.Net()), \
             mock.patch.object(model, "MODEL_VERSION", 0), \
             mock.patch.object(model, "READY", False), \
             mock.patch.object(model, "ERROR", "Initializing"), \
             mock.patch.object(model, "START", -9999999999.), \
             mock.patch.object(model, "SECONDS", 1), \
             mock.patch.object(model, "DB", self.folder / "legacy-loop"), \
             mock.patch.object(model.time, "sleep", side_effect=stop_sleep):
            model.loop()
            self.assertEqual(len(model.HISTORY), 9)
            self.assertEqual(model.MODEL_VERSION, 2)
            self.assertTrue(model.READY)
            self.assertIn("end bounded", model.ERROR)
            self.assertTrue((model.DB / "a440_state.json").exists())

    def test_05_helpers_and_calendar(self):
        self.assertEqual(model.canonical({"b": 1, "a": 2}), '{"a":2,"b":1}')
        self.assertEqual(len(model.digest({"a": 1})), 64)
        self.assertEqual(model.bounded(99, 0, 1), 1)
        self.assertEqual(model.money(1234.56), "$1,234.56")
        self.assertEqual(model.date_label(28), "2026-05")
        target = self.folder / "nested" / "state.json"
        h = model.atomic_json(target, {"value": 3})
        self.assertEqual(len(h), 64)
        self.assertEqual(json.loads(target.read_text())["value"], 3)
        with self.assertRaises(ValueError):
            model.canonical({"nan": float("nan")})

    def test_06_contract_formula_validation_and_cycle_guards(self):
        obj = self.contract.config()
        self.assertEqual(model.Contract.parse(obj).config(), obj)
        self.assertEqual(self.contract.formula_unit("kitchen_sales"), "USD")
        self.assertEqual(set(self.contract.formula_leaves("kitchen_sales")), {"food_sales", "delivery_sales"})
        self.assertAlmostEqual(self.contract.totals(self._value())["total_sales"], sum(self._value()[k] for k in ("food_sales", "bar_sales", "delivery_sales")))
        self.assertEqual(self.contract.evaluate_formula("food_sales", self._value()), self._value()["food_sales"])
        with self.assertRaises(ValueError):
            model.Contract("", [model.Metric("a", "b", "USD", "revenue")])
        with self.assertRaises(ValueError):
            model.Contract("x", [model.Metric("a", "b", "USD", "revenue"),model.Metric("a", "b", "USD", "revenue")])
        with self.assertRaises(ValueError):
            model.Contract("x", [model.Metric("a", "b", "USD", "revenue")], {"bad":{"op":"sum","args":["a","bad"]}})
        with self.assertRaises(ValueError):
            model.Contract("x", [model.Metric("a", "b", "USD", "revenue")], {"double":{"op":"sum","args":["a","a"]}})
        with self.assertRaises(ValueError):
            model.Contract("x", [model.Metric("a", "b", "USD", "revenue"),model.Metric("c", "b", "hours", "labor")], {"mix":{"op":"sum","args":["a","c"]}})
        with self.assertRaises(ValueError):
            self.contract.evaluate_formula("nonexistent", self._value())

    def test_07_evidence_validation_all_constraints(self):
        metric = self.contract.metrics["food_sales"]
        rec = model.Evidence.make(self.contract.tenant, 0, metric, 15)
        self.assertTrue(model.validate_evidence(rec, self.contract))
        self.assertEqual(model.Evidence.parse(rec.__dict__), rec)
        self.assertEqual(rec.body()["source"], "pos-food")
        for changes in ({"sha256": "0"*64}, {"tenant": "other"}, {"unit": "hours"}, {"month": -1}, {"month": 1.5}, {"value": float("inf")}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    model.validate_evidence(model.dataclasses.replace(rec, **changes), self.contract)

    def test_08_ledger_idempotent_conflict_and_event_integrity(self):
        ledger = model.Ledger(self.folder / "ledger.db")
        rows = model.synthetic_records(self.contract,self._value(),0)
        ledger.insert_month(self.contract,rows)
        ledger.insert_month(self.contract,rows)
        self.assertEqual(len(ledger.history(self.contract)),1)
        self.assertEqual(len(ledger.integrity_digest(self.contract.tenant)),64)
        with self.assertRaises(ValueError):
            ledger.insert_month(self.contract,rows[:-1])
        changed = list(rows)
        changed[0] = model.Evidence.make(self.contract.tenant,0,self.contract.metrics["food_sales"],999.)
        with self.assertRaises(ValueError):
            ledger.insert_month(self.contract,changed)
        ledger.insert_event(self.contract.tenant,0,"event-a",{"note":"test"})
        ledger.insert_event(self.contract.tenant,0,"event-a",{"note":"test"})
        with self.assertRaises(ValueError):
            ledger.insert_event(self.contract.tenant,0,"event-a",{"note":"different"})
        self.assertEqual(len(ledger.events(self.contract.tenant)),1)
        checksum = ledger.verified_snapshot(self.folder / "snapshot.db")
        self.assertEqual(len(checksum),64)
        with ledger.db:
            ledger.db.execute("UPDATE events SET data_json='{}' WHERE event_id='event-a'")
        with self.assertRaisesRegex(ValueError,"Event integrity"):
            ledger.events(self.contract.tenant)
        ledger.db.close()

    def test_09_ledger_missing_month_and_corrupted_database(self):
        ledger = model.Ledger(self.folder / "gapped.db")
        ledger.insert_month(self.contract,model.synthetic_records(self.contract,self._value(1),1))
        with self.assertRaisesRegex(ValueError,"Incomplete chronological"):
            ledger.history(self.contract)
        ledger.db.close()

    def test_10_temporal_feature_hash_and_leakage(self):
        history = [self._value(i) for i in range(24)]
        scales = model.baseline_scales(history,self.contract)
        encoder = model.TemporalEncoder(self.contract,scales)
        b1 = encoder.bucket("source:pos-food")
        self.assertEqual(b1, encoder.bucket("source:pos-food"))
        self.assertTrue(4 <= b1[0] < model.INPUTS)
        with self.assertRaises(ValueError):
            model.baseline_scales(history[:2],self.contract)
        with self.assertRaises(ValueError):
            encoder.encode([],0)
        with self.assertRaises(ValueError):
            encoder.encode(history[:5],6)
        x = encoder.encode(history[:15],15)
        history[23]["food_sales"] = 10**15
        self.assertEqual(x,encoder.encode(history[:15],15))
        self.assertTrue(all(0 <= key < model.INPUTS for key in x))
        self.assertTrue(all(math.isfinite(val) for val in x.values()))

    def test_11_network_heads_train_export_restore_rejection(self):
        net = model.UniversalNet()
        feat = {0:1.,1:.2,4:.9}
        p0,_ = net.forward(feat,"revenue")
        net.train_one(feat,"revenue",1.2,.01)
        p1,_ = net.forward(feat,"revenue")
        self.assertNotEqual(p0,p1)
        self.assertIn("revenue",net.heads)
        checkpoint = net.export()
        restored = model.UniversalNet.restore(copy.deepcopy(checkpoint))
        self.assertEqual(restored.forward(feat,"revenue")[0],p1)
        for bad in (dict(checkpoint,architecture="wrong"),dict(checkpoint,width=42),dict(checkpoint,hidden=2)):
            with self.assertRaises(ValueError):
                model.UniversalNet.restore(bad)
        bad=copy.deepcopy(checkpoint);bad["w"][0]=[1.]
        with self.assertRaises(ValueError):model.UniversalNet.restore(bad)
        bad=copy.deepcopy(checkpoint);bad["bias"][0]=float("nan")
        with self.assertRaises(ValueError):model.UniversalNet.restore(bad)
        bad=copy.deepcopy(checkpoint);bad["heads"]["revenue"]["w"]=[.5]
        with self.assertRaises(ValueError):model.UniversalNet.restore(bad)

    def test_12_learning_baseline_candidate_and_bounds(self):
        hist=[self._value(m) for m in range(27)]
        learner=model.Learning(self.contract,hist[:24])
        self.assertGreaterEqual(learner.baseline(hist[:24]),0)
        self.assertTrue(learner.targets)
        self.assertGreaterEqual(learner.predict(hist[:24],"food_sales"),0)
        self.assertIn("forecast_metrics",learner.next_quarter(hist[:24]))
        with self.assertRaises(ValueError):learner.baseline(hist[:23])
        with self.assertRaises(ValueError):learner.score(learner.net,hist,[27])
        with self.assertRaises(ValueError):learner.candidate_gate(hist[:25], previous_end=26)
        decision=learner.candidate_gate(hist,previous_end=24)
        self.assertIn("promoted",decision)
        self.assertIn("old_normalized_MAE",decision)
        self.assertEqual(len(learner.decisions),1)

    def test_13_contract_profiles_and_synthetic_generator(self):
        for kind,(factory,generator) in model.PROFILES.items():
            with self.subTest(kind=kind):
                contract=factory()
                vals=generator(12)
                self.assertEqual(set(vals),set(contract.metrics))
                rec=model.synthetic_records(contract,vals,12)
                self.assertEqual(len(rec),len(vals))
                self.assertTrue(all(model.validate_evidence(x,contract) for x in rec))
                if kind!="restaurant":self.assertEqual(model.synthetic_events(contract,28),[])
        self.assertEqual(len(model.synthetic_events(self.contract,24)),1)
        self.assertEqual(len(model.synthetic_events(self.contract,26)),1)
        self.assertEqual(len(model.synthetic_events(self.contract,28)),1)
        self.assertEqual(model.synthetic_events(self.contract,29),[])
        with self.assertRaises(ValueError):
            model.synthetic_records(self.contract,{"a":1},0)
        self.assertEqual(model.anomaly_questions(self.contract,[self._value()]),[])
        results=model.anomaly_questions(self.contract,[self._value(27),self._value(28)])
        self.assertTrue(results)
        self.assertEqual(results[0]["status"],"hypothesis_to_investigate_not_causal_conclusion")

    def test_14_business_empty_bootstrap_query_routes(self):
        lab=self._lab()
        self.assertEqual(lab.summary()["status"],"empty")
        self.assertEqual(lab.ask("sales")["status"],"no_data")
        with self.assertRaises(ValueError):lab.add_synthetic_month(0) if lab.generator is None else lab.close_quarter()
        lab.bootstrap()
        self.assertEqual(lab.summary()["complete_months"],24)
        self.assertEqual(lab.ask("What were sales and profit?")["status"],"evidence_grounded")
        self.assertEqual(lab.ask("How many employees are working overtime?")["status"],"evidence_grounded")
        self.assertEqual(lab.ask("What is next quarter forecast?")["status"],"model_estimate")
        self.assertEqual(lab.ask("How are food costs?")["status"],"unsupported_intent")
        self.assertEqual(lab.ask("food cogs")["metric"],"food_cogs")
        with self.assertRaises(ValueError):lab.bootstrap()
        no_gen=model.A440Lab(self.contract,self.folder/"external-only")
        with self.assertRaises(ValueError):no_gen.add_synthetic_month(0)
        lab.db.db.close();no_gen.db.db.close()

    def test_15_business_quarter_replay_budget_and_recovery(self):
        lab=self._lab();lab.bootstrap()
        outputs=[lab.close_quarter() for _ in range(4)]
        self.assertEqual(len(outputs),4)
        self.assertEqual(outputs[-1]["period"],"2026-10..2026-12")
        over=lab.ask("Why did kitchen go over budget?")
        self.assertIn("2026-05",[m for m,v in over["months_over_budget"]])
        staffing=lab.ask("Tell me about employee departures and overtime")
        self.assertEqual(len(staffing["historical_events"]),3)
        self.assertIn("employees_active_at_close",outputs[-1]["actuals"])
        self.assertEqual(lab.summary()["complete_months"],36)
        self.assertIn("2027",model.date_label(36))
        restored=model.A440Lab(self.contract,lab.state_dir,model.restaurant_values)
        restored.load()
        self.assertEqual(restored.summary()["model_version"],lab.summary()["model_version"])
        with self.assertRaises(ValueError):restored.bootstrap()
        restored.db.db.close();lab.db.db.close()

    def test_16_business_ingestion_path(self):
        contract=model.retail_contract()
        path=self.folder/"retail"
        lab=model.A440Lab(contract,path)
        for m in range(27):
            lab.db.insert_month(contract,model.synthetic_records(contract,model.retail_values(m),m))
        self.assertEqual(lab.train_ingested()["replayed_quarters"],1)
        with self.assertRaises(ValueError):lab.train_ingested()
        loaded=model.A440Lab(contract,path)
        loaded.load()
        self.assertEqual(loaded.summary()["complete_months"],27)
        loaded.db.db.close();lab.db.db.close()

    def test_17_http_business_and_legacy(self):
        lab=self._lab();lab.bootstrap()
        model.BusinessHandler.lab=lab
        server=ThreadingHTTPServer(("127.0.0.1",0),model.BusinessHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(url+"/status") as r:
                self.assertEqual(json.load(r)["status"],"running")
            with urllib.request.urlopen(url+"/ask?q=next%20quarter%20forecast") as r:
                self.assertEqual(json.load(r)["status"],"model_estimate")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(url+"/invalid")
            self.assertEqual(ctx.exception.code,404)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)
        with mock.patch.object(model,"READY",False),mock.patch.object(model,"ERROR","Initializing"):
            server=ThreadingHTTPServer(("127.0.0.1",0),model.Handler)
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                url=f"http://127.0.0.1:{server.server_port}"
                with urllib.request.urlopen(url+"/health") as r:
                    self.assertEqual(json.load(r)["status"],"initializing")
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url+"/unknown")
            finally:
                server.shutdown();server.server_close();t.join(timeout=2)
        lab.db.db.close()

    def test_18_architecture_and_dispatch(self):
        manifest=model.architecture_manifest()
        self.assertEqual(manifest["model"],"A440-U2.0 integrated")
        with mock.patch.object(sys,"argv",["model.py","--architecture"]),contextlib.redirect_stdout(io.StringIO()) as out:
            model.main()
            self.assertIn("architecture_ready",out.getvalue())
        with mock.patch.object(sys,"argv",["model.py","--show-contract"]),contextlib.redirect_stdout(io.StringIO()) as out:
            model.main()
            self.assertIn("restaurant-001",out.getvalue())
        with mock.patch.object(sys,"argv",["model.py"]),mock.patch.object(model,"launch_legacy_runtime") as launched:
            model.main();launched.assert_called_once()
        with mock.patch.object(sys,"argv",["model.py","--legacy"]),mock.patch.object(model,"launch_legacy_runtime") as launched:
            model.main();launched.assert_called_once()
        with mock.patch.object(sys,"argv",["model.py","--legacy","bad"]):
            with self.assertRaises(SystemExit):model.main()
        with mock.patch.object(sys,"argv",["model.py","--architecture","bad"]):
            with self.assertRaises(SystemExit):model.main()
        with mock.patch.object(sys,"argv",["model.py","--quarter-seconds","0"]),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):model.cli()

    def test_20_foundation_test_runner_dispatch(self):
        # The real twelve foundation tests are run separately by audit_runner.
        # Here we verify the runner's success handling without duplicating training.
        with mock.patch.object(unittest.defaultTestLoader,"loadTestsFromTestCase",return_value=unittest.TestSuite()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertTrue(model.run_tests())

    def test_19_legacy_runtime_gate(self):
        with mock.patch.object(model,"SECONDS",0):
            with self.assertRaises(RuntimeError):model.launch_legacy_runtime()


if __name__ == "__main__":
    unittest.main(verbosity=2)
BCI_U21_EXTENDED_TESTS
cat <<'BCI_U21_NEW_TESTS' > "$STAGE/test_u21.py"
#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Developer Seal: CJB-DEV-2026
# Component: A440 U2.1 Architectural Regression Tests
# ============================================================
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import model


class U21Tests(unittest.TestCase):
    def setUp(self):
        self.contract = model.restaurant_contract()

    def test_01_role_and_metric_heads_are_distinct(self):
        net = model.UniversalNet()
        x = {0: 1., 1: .2, 7: .13}
        a = ("revenue", "restaurant-001", "food_sales")
        b = ("revenue", "restaurant-001", "bar_sales")
        _, _ = net.forward(x, a)
        _, _ = net.forward(x, b)
        role, key_a = net.task_parts(a)
        _, key_b = net.task_parts(b)
        self.assertNotEqual(key_a, key_b)
        self.assertIn(role, net.heads)
        old_a = copy.deepcopy(net.heads[key_a])
        old_b = copy.deepcopy(net.heads[key_b])
        net.train_one(x, a, 1., .02)
        self.assertNotEqual(old_a, net.heads[key_a])
        self.assertEqual(old_b, net.heads[key_b])
        r = model.UniversalNet.restore(net.export())
        self.assertEqual(net.forward(x,a)[0],r.forward(x,a)[0])
        self.assertEqual(net.forward(x,b)[0],r.forward(x,b)[0])

    def test_02_head_validation_rejects_bad_tasks(self):
        for task in ((), ("revenue", "tenant"), ("", "tenant", "metric"), 4):
            with self.assertRaises(ValueError): model.UniversalNet.task_parts(task)

    def test_03_temporal_features_use_past_only(self):
        rows = [model.restaurant_values(i) for i in range(27)]
        encoder = model.TemporalEncoder(self.contract,model.baseline_scales(rows[:24],self.contract))
        first = encoder.encode(rows[:24],24)
        rows[26]["food_sales"] = 1e16
        second = encoder.encode(rows[:24],24)
        self.assertEqual(first,second)
        self.assertEqual(encoder.bucket("lag:3:food_sales"),encoder.bucket("lag:3:food_sales"))

    def test_04_shift_evidence_rejects_tamper_and_impossible_hours(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = model.Ledger(Path(td)/"shift.db")
            body={"tenant":self.contract.tenant,"month":24,"shift_id":"a","employee_id":"EMP-K001",
                  "department":"kitchen","role":"cook","scheduled_hours":8.,"actual_hours":10.,"overtime_hours":2.}
            good={**body,"sha256":model.digest(body)}
            ledger.insert_shifts(self.contract,[good])
            ledger.insert_shifts(self.contract,[good])
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                ledger.insert_shifts(self.contract,[{**good,"overtime_hours":3.}])
            too={**body,"actual_hours":25.}
            with self.assertRaisesRegex(ValueError,"Impossible"):
                ledger.insert_shifts(self.contract,[{**too,"sha256":model.digest(too)}])
            conflicting={**body,"actual_hours":9.,"overtime_hours":1.}
            with self.assertRaisesRegex(ValueError,"conflict"):
                ledger.insert_shifts(self.contract,[{**conflicting,"sha256":model.digest(conflicting)}])
            s=ledger.shift_summary(self.contract.tenant)
            self.assertEqual(s["overtime_employee_count"],1)
            self.assertAlmostEqual(s["total_overtime_hours"],2.)
            self.assertEqual(s["shift_records"],1)
            ledger.db.close()

    def test_05_no_shift_evidence_does_not_invent_headcount(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = model.Ledger(Path(td)/"shift.db")
            self.assertIsNone(ledger.shift_summary(self.contract.tenant)["overtime_employee_count"])
            ledger.db.close()

    def test_06_two_departures_appear_in_shift_data(self):
        old=model.synthetic_employee_shifts(self.contract,24,model.restaurant_values(24))
        now=model.synthetic_employee_shifts(self.contract,26,model.restaurant_values(26))
        self.assertEqual(len({x["employee_id"] for x in old}),27)
        self.assertEqual(len({x["employee_id"] for x in now}),26)
        self.assertNotIn("EMP-K005",{x["employee_id"] for x in old})
        self.assertNotIn("EMP-K006",{x["employee_id"] for x in now})
        self.assertAlmostEqual(sum(x["overtime_hours"] for x in now),model.restaurant_values(26)["overtime_hours"])
        self.assertEqual(len(model.synthetic_employee_shifts(self.contract,23,model.restaurant_values(23))),0)

    def test_07_shift_integrity_part_of_ledger_digest(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=model.Ledger(Path(td)/"x.db")
            earlier=ledger.integrity_digest(self.contract.tenant)
            records=model.synthetic_employee_shifts(self.contract,24,model.restaurant_values(24))
            ledger.insert_shifts(self.contract,records)
            self.assertNotEqual(earlier,ledger.integrity_digest(self.contract.tenant))
            ledger.db.execute("UPDATE employee_shifts SET overtime_hours=99 WHERE employee_id='EMP-K001'")
            ledger.db.commit()
            with self.assertRaisesRegex(ValueError,"integrity mismatch"):
                ledger.shift_summary(self.contract.tenant)
            ledger.db.close()

    def test_08_six_month_gate_rejects_no_improvement(self):
        hist=[model.restaurant_values(i) for i in range(27)]
        learning=model.Learning(self.contract,hist[:24]);learning.baseline(hist[:24])
        before=model.digest(learning.net.export())
        with mock.patch.object(learning,"fit",return_value=None):
            decision=learning.candidate_gate(hist,24)
        self.assertFalse(decision["promoted"])
        self.assertEqual(decision["validation_months"],6)
        self.assertEqual(decision["validation_start"],"2025-10")
        self.assertTrue(decision["training_excludes_validation_window"])
        self.assertEqual(before,model.digest(learning.net.export()))
        with self.assertRaisesRegex(ValueError,"one newly closed quarter"):
            learning.candidate_gate(hist,25)

    def test_09_checkpoint_wrong_version_fails(self):
        net=model.UniversalNet(); data=net.export()
        self.assertEqual(data["architecture"],"A440-U2.1.0")
        with self.assertRaisesRegex(ValueError,"migration"):
            model.UniversalNet.restore({**data,"architecture":"A440-U1.0.0"})

    def test_10_generic_metric_investigation_has_sources(self):
        with tempfile.TemporaryDirectory() as td:
            lab=model.A440Lab(self.contract,td,model.restaurant_values)
            for month in range(24):
                lab.add_synthetic_month(month)
            info=lab.investigate("Why did food cogs change?")
            self.assertEqual(info["metric"],"food_cogs")
            self.assertFalse(info["causal_claim"])
            self.assertIn("inventory",info["provenance_sources"])
            lab.db.db.close()

    def test_11_cross_industry_metric_heads_same_width(self):
        for factory, generator in ((model.retail_contract,model.retail_values),
                                   (model.logistics_contract,model.logistics_values)):
            contract=factory(); history=[generator(i) for i in range(24)]
            learner=model.Learning(contract,history);learner.baseline(history)
            self.assertEqual(learner.net.export()["width"],model.INPUTS)
            self.assertTrue(any(n.startswith("metric::") for n in learner.net.heads))

    def test_12_catchup_shift_reconciliation_and_question(self):
        with tempfile.TemporaryDirectory() as td:
            lab=model.A440Lab(self.contract,td,model.restaurant_values)
            lab.bootstrap()
            self.assertFalse(lab.db.shift_summary(self.contract.tenant)["available"])
            for _ in range(4): lab.close_quarter()
            summary=lab.db.shift_summary(self.contract.tenant,33,35)
            self.assertTrue(summary["available"])
            self.assertEqual(summary["employee_count"],26)
            self.assertEqual(summary["overtime_employee_count"],4)
            self.assertEqual(lab.ask("How many employees are working overtime?")["employee_shift_evidence"]["overtime_employee_count"],4)
            self.assertEqual(len(lab.db.events(self.contract.tenant)),3)
            self.assertIn("2026-05",[p for p,_ in lab.ask("Why is the kitchen over budget?")["months_over_budget"]])
            restored=model.A440Lab(self.contract,td,model.restaurant_values)
            restored.load()
            self.assertEqual(restored.db.shift_summary(self.contract.tenant,33,35)["employee_count"],26)
            lab.db.db.close();restored.db.db.close()

if __name__=="__main__":
    unittest.main(verbosity=2)
BCI_U21_NEW_TESTS

printf '%s  %s\n' "$NEW_SHA" "$STAGE/model.py" | sha256sum -c -
printf '%s  %s\n' 'e841c1b8dd9da97e10647bd73432785734e8675044229d5df3c3947edc860b22' "$STAGE/test_extended.py" | sha256sum -c -
printf '%s  %s\n' '8c04359004981cb2af9fd817f2de5e0aa555092b271dc62ce2c6636627619899' "$STAGE/test_u21.py" | sha256sum -c -

# Preserve the exact user-owned source and execute all tests in isolation.
cp "$LAB/test_lab.py" "$STAGE/test_lab.py"
cp "$LAB/endpoint.py" "$STAGE/endpoint.py"
echo "=== VERIFY ORIGINAL LAB CONTRACT TESTS ==="
(
  cd "$STAGE"
  PYTHONWARNINGS=ignore::ResourceWarning python3 -m unittest -v test_lab test_extended test_u21
)
echo "=== VERIFY UNIVERSAL FOUNDATION TESTS ==="
(
  cd "$STAGE"
  PYTHONWARNINGS=ignore::ResourceWarning python3 model.py --self-test
  python3 model.py --architecture
)

# Install if and only if the pre-existing model is the U2.0 verified source.
ACTUAL="$(sha256sum "$LAB/model.py" | cut -d ' ' -f 1)"
if [[ "$ACTUAL" == "$NEW_SHA" ]]; then
  echo '[BCI][PASS] U2.1 already installed. No files replaced.'
  exit 0
fi
[[ "$ACTUAL" == "$OLD_SHA" ]] || {
  echo "[BCI][BLOCKED] U2.0 source was modified: $ACTUAL"; exit 1;
}
BACKUPS="$HOME/Documents/A440-U2.1-Backups"
mkdir -p "$BACKUPS"
BACKUP="$(mktemp "$BACKUPS/model.py.pre-U2.1.XXXXXXXX")"
cp -- "$LAB/model.py" "$BACKUP"
printf '%s  %s\n' "$OLD_SHA" "$BACKUP" | sha256sum -c -
{
  echo '# BEACON COMPUTING INITIATIVE'
  echo '# Developer Seal: CJB-DEV-2026'
  printf '%s  %s\n' "$OLD_SHA" "$(basename "$BACKUP")"
} > "$BACKUP.sha256"
# Mutate only after every integrity and test gate passes.
TMP="$(mktemp "$LAB/.model.py.u21.XXXXXXXX")"
trap 'rm -f "$TMP"; rm -rf "$STAGE"' EXIT
cp "$STAGE/model.py" "$TMP"
chmod --reference="$LAB/model.py" "$TMP"
mv -f -- "$TMP" "$LAB/model.py"
cp "$STAGE/test_extended.py" "$LAB/test_extended_u21.py"
cp "$STAGE/test_u21.py" "$LAB/test_u21.py"
{
 echo '# BEACON COMPUTING INITIATIVE'
 echo '# Developer Seal: CJB-DEV-2026'
 echo 'b79c6c73ff85a5ed3c71cc094930827cb260fb82f7b59e4a85730a2d8124976e  model.py'
 echo 'e841c1b8dd9da97e10647bd73432785734e8675044229d5df3c3947edc860b22  test_extended_u21.py'
 echo '8c04359004981cb2af9fd817f2de5e0aa555092b271dc62ce2c6636627619899  test_u21.py'
} > "$LAB/A440-U2.1-SHA256SUMS"
(
 cd "$LAB"
 sha256sum -c A440-U2.1-SHA256SUMS
)
echo '[BCI][PASS] A440 U2.1 installed; 50 offline tests passed before replacement'
echo "[BCI] Original U2.0 source backup: $BACKUP"
echo '[BCI] No simulation, training service, or Docker container was started'
echo '[BCI] Developer Seal: CJB-DEV-2026'
