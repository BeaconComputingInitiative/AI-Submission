#!/usr/bin/env python3
# BEACON COMPUTING INITIATIVE
# Developer Seal: CJB-DEV-2026
# Component: A440 Chorded Truth, Online Neural Learning, Quarter Simulation
import hashlib,json,math,os,random,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

COUNT=20
SECONDS=int(os.getenv('QUARTER_SECONDS','300'))
SEED=440
DB=Path(os.environ.get('A440_STATE_DIR', '/state')); DB.mkdir(parents=True, exist_ok=True)
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

if __name__=='__main__':
    if SECONDS<1:raise RuntimeError('Invalid interval')
    threading.Thread(target=loop,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
