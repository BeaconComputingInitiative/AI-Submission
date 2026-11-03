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
VERSION = "A440-U1.0.0"
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
        return digest({"tenant":tenant,"evidence":rows,"events":events})

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
    """Shared tanh encoder + learnable semantic-role prediction heads."""

    def __init__(self):
        rng = random.Random(SEED)
        self.w = [[rng.uniform(-.045, .045) for _ in range(INPUTS)] for _ in range(HIDDEN)]
        self.bias = [0.] * HIDDEN
        self.heads = {}  # role -> (weights, bias)

    def head(self, role):
        if role not in self.heads:
            rng = random.Random(SEED + int(hashlib.sha256(role.encode()).hexdigest()[:8], 16))
            self.heads[role] = {"w": [rng.uniform(-.03, .03) for _ in range(HIDDEN)], "b": 0.}
        return self.heads[role]

    def forward(self, x, role):
        h = [math.tanh(self.bias[j] + sum(self.w[j][i]*v for i,v in x.items()))
             for j in range(HIDDEN)]
        head = self.head(role)
        return sum(a*b for a,b in zip(h,head["w"])) + head["b"], h

    def train_one(self, x, role, target, rate):
        pred, h = self.forward(x, role)
        err = bounded(pred-target, -1., 1.)
        head = self.head(role)
        old = head["w"][:]
        for j in range(HIDDEN):
            back = err*old[j]*(1-h[j]*h[j])
            for idx, value in x.items():
                self.w[j][idx] -= rate*back*value
            self.bias[j] -= rate*back
            head["w"][j] -= rate*err*h[j]
        head["b"] -= rate*err

    def export(self):
        return {"architecture": VERSION, "width": INPUTS, "hidden": HIDDEN,
                "w": self.w, "bias": self.bias, "heads": self.heads}

    @classmethod
    def restore(cls, obj):
        if obj.get("architecture") != VERSION or obj.get("width") != INPUTS or obj.get("hidden") != HIDDEN:
            raise ValueError("Incompatible model checkpoint")
        m = cls()
        if (len(obj["w"]) != HIDDEN or any(len(row) != INPUTS for row in obj["w"]) or
                len(obj["bias"]) != HIDDEN):
            raise ValueError("Invalid checkpoint dimensions")
        m.w, m.bias, m.heads = obj["w"], obj["bias"], obj["heads"]
        allvalues = [v for row in m.w for v in row] + m.bias
        for h in m.heads.values():
            if len(h["w"]) != HIDDEN:
                raise ValueError("Invalid task head")
            allvalues.extend(h["w"] + [h["b"]])
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in allvalues):
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
        role = self.contract.metrics[name].role
        x = self.encoder.encode(history, len(history))
        delta, _ = net.forward(x, role)
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
                samples.append((features, self.contract.metrics[name].role, delta))
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

    def candidate_gate(self, history, previous_end):
        # Last month is strictly validation: the candidate cannot fit to it.
        # The last-quarter forecast was issued BEFORE the quarter was observed.
        final_month = len(history) - 1
        if final_month < 25 or previous_end > final_month:
            raise ValueError("Cannot evaluate candidate with future data")
        candidate = copy.deepcopy(self.net)
        self.fit(candidate, history, max_target=final_month, epochs=5, rate=.0015)
        old_score = self.score(self.net, history, [final_month])
        new_score = self.score(candidate, history, [final_month])
        promoted = new_score <= old_score * .995
        if promoted:
            self.net = candidate
            self.version += 1
        result = {"validated_month": date_label(final_month),
                  "old_normalized_MAE": old_score,
                  "candidate_normalized_MAE": new_score,
                  "promoted": promoted, "version": self.version,
                  "validation_scope": "one newly closed month; research-only"}
        self.decisions.append(result)
        return result

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
        self.db.insert_month(self.contract, synthetic_records(self.contract,self.generator(month),month))
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
                  "research_only":True}
        if self.learning:
            result["next_quarter"] = self.learning.next_quarter(history)
        return result

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
                        "explanation":"Variance is actual kitchen expenses minus its budget; investigate waste, food COGS, and overtime separately. Associations do not prove causation."}
            if "overtime" in text or "employee" in text or "staff" in text:
                fields = ("active_employees","kitchen_employees_per_shift","overtime_hours",
                          "kitchen_overtime_wages","front_overtime_wages")
                return {"question":question,"status":"evidence_grounded",
                        "current":{k:latest[k] for k in fields if k in latest},
                        "historical_events":self.db.events(self.contract.tenant),
                        "note":"Synthetic employee IDs and departures; no individual personnel inference"}
            if "forecast" in text or "next quarter" in text or "project" in text:
                return {"question":question,"status":"model_estimate",
                        "forecast":self.learning.next_quarter(history)}
            if "sales" in text or "profit" in text or "revenue" in text:
                return {"question":question,"status":"evidence_grounded",
                        "actuals":{k:latest[k] for k in self.contract.formulas}}
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
    p.add_argument("--state-dir",default=str(Path.home()/"Documents"/"A440-Universal-State"))
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
