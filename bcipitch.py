#!/usr/bin/env python3
# BEACON COMPUTING INITIATIVE | BCIPitch Foundation v0.1.0
# Developer Seal: CJB-DEV-2026
"""BCIPitch M1: A440 manifest, scoped Signatures, Measures and Octets.
Research prototype; DOES NOT implement model weights or self-training.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VERSION = '0.1.0'
SEAL = 'CJB-DEV-2026'
METRIC = 'checkout_latency_ms'

def utcnow(): return datetime.now(timezone.utc).isoformat()
def canon(obj): return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(obj): return hashlib.sha256(canon(obj).encode()).hexdigest()
def db_open(path):
    con = sqlite3.connect(str(path))
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, signature_id TEXT NOT NULL, observed_at TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL, source_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS measures(measure_id TEXT PRIMARY KEY,event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id),baseline REAL NOT NULL,delta REAL NOT NULL,quality TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS octet_entries(octet_id TEXT NOT NULL,position INTEGER NOT NULL,measure_id TEXT NOT NULL UNIQUE REFERENCES measures(measure_id),PRIMARY KEY(octet_id,position));''')
    return con

def install(root):
    root.mkdir(parents=True, exist_ok=True)
    (root/'state').mkdir(exist_ok=True)
    a = root/'A440'; a.mkdir(exist_ok=True)
    manifest = {'artifact_type':'A440-prototype-manifest','version':VERSION,'developer_seal':SEAL,
                'architecture':'future foundational model (not yet pretrained)',
                'policy':{'allowed_signatures':['SIG-06'],'allowed_metrics':[METRIC], 'collect_only_simulated':True},
                'baseline':{METRIC:150.0}}
    p = a/'manifest.json'
    if p.exists():
        existing = json.loads(p.read_text())
        if existing != manifest:
            raise RuntimeError('Existing A440 manifest differs: refusing overwrite')
    else: p.write_text(json.dumps(manifest, indent=2)+'\n')
    db_open(root/'state'/'evidence.sqlite3').close()
    return manifest

def load(root):
    p=root/'A440'/'manifest.json'
    m=json.loads(p.read_text())
    if m.get('developer_seal') != SEAL or m.get('version') != VERSION: raise ValueError('A440 manifest identity mismatch')
    if m.get('policy',{}).get('collect_only_simulated') is not True: raise ValueError('Prototype requires simulation-only policy')
    return m

def process(root, count):
    m=load(root)
    con=db_open(root/'state'/'evidence.sqlite3')
    baseline=m['baseline'][METRIC]
    allowed=m['policy']['allowed_metrics']; sigs=m['policy']['allowed_signatures']
    added=0
    try:
        with con:
            for index in range(count):
                # Deterministic sample observations, not actual business telemetry.
                value=float(145 + (index * 11) % 53)
                ev={'event_id':f'sim-{index:06d}','signature_id':'SIG-06', 'observed_at':f'sim-tick-{index:06d}', 'metric':METRIC, 'value':value, 'unit':'ms'}
                # Accept if and only if policy, schema, finite value and provenance criteria hold.
                valid=(ev['signature_id'] in sigs and ev['metric'] in allowed and math.isfinite(value) and value>=0)
                if not valid: continue
                h=digest(ev)
                row=con.execute('SELECT source_hash FROM events WHERE event_id=?',(ev['event_id'],)).fetchone()
                if row:
                    if row[0]!=h: raise ValueError('Same event ID with conflicting content')
                    continue
                con.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',(ev['event_id'],ev['signature_id'],ev['observed_at'],ev['metric'],value,ev['unit'],h))
                measure_id=f'msr-{index:06d}'
                quality='qualified' if 0 <= value <= 5000 else 'rejected'
                con.execute('INSERT INTO measures VALUES(?,?,?,?,?)',(measure_id,ev['event_id'],baseline,value-baseline,quality))
                added+=1
            # Builds octets of 8; preserve partial final octet, and never overwrite assigned records.
            ids=[row[0] for row in con.execute("SELECT measure_id FROM measures WHERE quality='qualified' AND measure_id NOT IN (SELECT measure_id FROM octet_entries) ORDER BY measure_id")]
            full, rem=divmod(len(ids),8)
            ordinal=con.execute('SELECT COUNT(DISTINCT octet_id) FROM octet_entries').fetchone()[0]
            for j in range(full+(1 if rem else 0)):
                chunk=ids[j*8:(j+1)*8]
                octet_id=f'oct-{ordinal+j:06d}'
                con.executemany('INSERT INTO octet_entries VALUES(?,?,?)',[(octet_id,k,x) for k,x in enumerate(chunk)])
        counts={k:con.execute(f'SELECT COUNT(*) FROM {k}').fetchone()[0] for k in ('events','measures','octet_entries')}
        counts['octets']=con.execute('SELECT COUNT(DISTINCT octet_id) FROM octet_entries').fetchone()[0]
        counts['new_events']=added
        return counts
    finally:con.close()

def validate(root):
    m=load(root)
    con=db_open(root/'state'/'evidence.sqlite3')
    try:
        errors=[]
        rows=con.execute('SELECT octet_id,COUNT(*),MIN(position),MAX(position) FROM octet_entries GROUP BY octet_id ORDER BY octet_id').fetchall()
        for i,n,lo,hi in rows:
            if not (1<=n<=8 and lo==0 and hi==n-1):errors.append(f'{i}: bad positions')
        issues=con.execute('PRAGMA foreign_key_check').fetchall()
        if issues:errors.append('foreign key violations')
        missing=con.execute("SELECT COUNT(*) FROM measures WHERE quality='qualified' AND measure_id NOT IN (SELECT measure_id FROM octet_entries)").fetchone()[0]
        if missing:errors.append(f'unassigned qualified measures: {missing}')
        counts={'events':con.execute('SELECT COUNT(*) FROM events').fetchone()[0], 'measures':con.execute('SELECT COUNT(*) FROM measures').fetchone()[0], 'octets':len(rows),'octet_sizes':[n for _,n,_,_ in rows], 'errors':errors}
        return counts
    finally:con.close()

def main(argv=None):
    ap=argparse.ArgumentParser(description='BCIPitch research prototype (simulation only)')
    ap.add_argument('command',choices=['init','simulate','validate'])
    ap.add_argument('--root',type=Path,default=Path.home()/'Documents'/'BCIPitch')
    ap.add_argument('--count',type=int,default=100)
    args=ap.parse_args(argv)
    if args.count<0 or args.count>100000:ap.error('count must be 0..100000')
    try:
        if args.command=='init':result=install(args.root)
        elif args.command=='simulate':result=process(args.root,args.count)
        else:result=validate(args.root)
    except (ValueError,RuntimeError,OSError,sqlite3.Error,FileNotFoundError,KeyError) as e:
        print(f'[BCI][FAIL] {e}',file=sys.stderr);return 1
    print(json.dumps({'project':'BCIPitch','version':VERSION,'developer_seal':SEAL,'result':result},indent=2))
    return 0 if not result.get('errors') else 1
if __name__=='__main__':sys.exit(main())
