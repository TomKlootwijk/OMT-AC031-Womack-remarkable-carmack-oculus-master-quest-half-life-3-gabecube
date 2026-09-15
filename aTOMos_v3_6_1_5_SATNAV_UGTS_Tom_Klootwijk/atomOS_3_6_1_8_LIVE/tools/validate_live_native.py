"""Verify the persistent native worker against independent Householder solutions."""
from pathlib import Path
import argparse,collections,csv,json,math,statistics,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from live_native import NativeSolver
from reference import load,solve

def validate(binary,backend,out):
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    epochs=load(ROOT/'examples/demo');latencies=[];comparisons=0;maximum=0.;statuses=collections.Counter();traces=[]
    with NativeSolver(binary,backend=backend) as worker:
        for epoch in epochs:
            rows=[{'channel':i,'sx_rx_m':o['sat'][0],'sy_rx_m':o['sat'][1],'sz_rx_m':o['sat'][2],'code_m':o['corrected'],'add_correction_m':0.,'sigma_m':o['sigma'],'ready':o['ready']} for i,o in epoch['observations'].items()]
            start=time.perf_counter();actual=worker.solve(epoch['id'],epoch['time'],epoch['seed'],rows,epoch['asa'],epoch['na'],epoch['boundary']);latencies.append((time.perf_counter()-start)*1000)
            expected=solve(epoch);statuses[actual['status']]+=1
            for key in ('status','asa','na','hits','active','used'):
                assert actual[key]==expected[key],(epoch['id'],key);comparisons+=1
            if actual['status']=='CONVERGED':
                assert actual['fit']==expected['fit'];comparisons+=1
                for a,b in zip(actual['state'],expected['state']):
                    error=abs(a-b);maximum=max(maximum,error);assert error<1e-4;comparisons+=1
                for a,b in zip(actual['variance'],expected['variance']):assert abs(a-b)<1e-6+1e-7*abs(b);comparisons+=1
                for item,(channel,residual) in zip(actual['residuals'],expected['residuals']):
                    assert item['channel']==channel and abs(item['residual_m']-residual)<1e-5;comparisons+=1
            traces.append(actual)
        rejected=[]
        for name,line in [('malformed','invalid'),('negative_id','SOLVE -1 10 0 0 0 0 0 0 0 0'),('nonfinite_time','SOLVE 0 nan 0 0 0 0 0 0 0 0'),('count_mismatch','SOLVE 0 10 0 0 0 0 0 0 0 1'),('long_request','x'*65537)]:
            try:worker.request(line)
            except ValueError:rejected.append(name)
            else:raise AssertionError(name+' accepted')
            assert worker.request('PING')=={'type':'pong'}
        assert worker.solve(999,1.,[0,0,0,0],[])['status']=='TOO_FEW'
        report={'version':'3.6.1.8','status':'passed','backend':backend,'epochs':len(epochs),'comparisons':comparisons,'status_counts':dict(statuses),'max_absolute_state_difference_m':maximum,'rejected_requests_then_worker_recovered':rejected,'request_latency_ms':{'median':statistics.median(latencies),'p95':sorted(latencies)[int(.95*(len(latencies)-1))],'max':max(latencies),'scope':'local request serialization, native worker and response parsing; excludes raw transport and correction preparation'},'binary_sha256':worker.binary_sha256,'command':worker.command,'pid':worker.process.pid,'scope':'Synthetic interface regression only; real-observation and Internet validations have separate reports.'}
    (out/'native_trace.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in traces),encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--backend',choices=['cpu','cuda'],default='cpu');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(validate(a.binary,a.backend,a.out),indent=2))
