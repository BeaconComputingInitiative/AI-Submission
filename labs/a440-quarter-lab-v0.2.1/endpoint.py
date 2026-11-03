#!/usr/bin/env python3
# BEACON COMPUTING INITIATIVE
# Developer Seal: CJB-DEV-2026
# Component: A440 Synthetic Independent Business Endpoint
import json, os, hashlib, math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ID=int(os.environ.get('ENDPOINT_ID','1'))
SEAL='CJB-DEV-2026'

def record(q):
    # q=0..7: two years of baseline. q>=8: live quarters.
    # no random sequences/shared state; each endpoint generates its own contribution.
    base=10000+ID*750
    seasonal=(0.92, 1.00, 1.08, 1.18)[q%4]
    trend=1+0.019*q
    shock=1+0.016*math.sin((q+ID)*0.61)
    sales=round(base*seasonal*trend*shock,2)
    units=round(sales/(42+ID%7),0)
    returns=round(sales*(0.018+(ID%4)*0.003),2)
    costs=round(sales*(0.55+ID%5*0.018),2)
    payload={'agent':f'endpoint-{ID:02d}','quarter':q,'sales':sales,'units':int(units),'returns':returns,'costs':costs,'currency':'USD','kind':'synthetic'}
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    payload['sha256']=hashlib.sha256(canonical).hexdigest()
    return payload

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/health': result={'ok':True,'agent':ID}
        elif self.path=='/baseline': result={'agent':ID,'records':[record(q) for q in range(8)]}
        elif self.path.startswith('/quarter/'):
            try:
                q=int(self.path.split('/')[-1]); assert q>=8
                result=record(q)
            except Exception:
                self.send_error(400);return
        else: self.send_error(404);return
        out=json.dumps(result).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(out)));self.end_headers();self.wfile.write(out)
    def log_message(self,*args): pass

if __name__=='__main__':
    print(f'[BCI] endpoint-{ID:02d} ready',flush=True)
    ThreadingHTTPServer(('0.0.0.0',8000),Handler).serve_forever()
