"""Verify canonical cache replay, force/frame arithmetic and actual CUDA execution."""
from pathlib import Path
import argparse,copy,hashlib,json,random,shutil,subprocess,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from orbit_native import NativeOrbit,numeric_model
from orbit_dynamics import acceleration,frame_matrix

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cpu-binary',type=Path,required=True)
    p.add_argument('--cuda-binary',type=Path);p.add_argument('--sanitizer',action='store_true')
    p.add_argument('--models-dir',type=Path,default=ROOT/'examples/orbit/models')
    p.add_argument('--objects',nargs='+',default=['G05','C03','C06','CHANDRA'])
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    report={'profile':'ORBIT-WORKER-1','status':'running','cpu_binary_sha256':digest(a.cpu_binary),'models':{},
      'scope':'numerical implementation, random-access cache and memory execution; not physical forecast truth'}
    rng=random.Random(3619);models={}
    for name in a.objects:
        path=a.models_dir/f'{name}.json';document=json.loads(path.read_text());model=document.get('model',document);models[name]=model
        model=copy.deepcopy(model);model['integration']['max_checkpoints']=4;model['integration']['checkpoint_stride_steps']=20
        times=[-86400.,-12345.678,0.,.125,300.,43212.34,150003.25,259259.3,604800.]
        order=times*2;rng.shuffle(order);baseline={};force_error=frame_error=0.
        with NativeOrbit(a.cpu_binary,model) as worker:
            for t in times:
                worker.reset();row=worker.query(t);assert row['status']=='ok',row;baseline[t]=row['state_gcrs']
            worker.reset()
            for t in order:
                row=worker.query(t);assert row['status']=='ok' and row['state_gcrs']==baseline[t],(name,t,'query-order mismatch')
                assert worker.stats()['cache_count']<=4
            stats=worker.stats();assert stats['evictions']>0
            for t in [-12345.678,0.,259259.3]:
                state=baseline[t];reply=worker.command('EVALUATE '+' '.join(format(x,'.17g') for x in [t,*state]))
                assert reply['status']=='ok' and reply['frame_available']
                force_error=max(force_error,float(np.linalg.norm(np.array(reply['acceleration_gcrs'])-acceleration(model,t,state))))
                frame_error=max(frame_error,float(np.max(np.abs(np.array(reply['gcrs_to_ecef']).reshape(3,3)-frame_matrix(model,t)))))
            assert force_error<1e-12 and frame_error<2e-14,(name,force_error,frame_error)
        item={'model_sha256':digest(path),'dynamics_profile':model['profile'],'query_count':len(times)+len(order),'cache_order_bit_exact':True,
          'cache_stats':stats,'force_vs_python_max_m_s2':force_error,'frame_vs_python_max_abs':frame_error}
        if a.cuda_binary:
            query_times=np.linspace(-86400.,604800.,257).tolist()+[.125,12345.678,259259.3]
            with NativeOrbit(a.cpu_binary,model) as cpu,NativeOrbit(a.cuda_binary,model,'cuda') as gpu:
                expected=cpu.batch(query_times);actual=gpu.batch(query_times)
                assert all(row['status']=='ok' for row in expected+actual)
                e=np.array([row['state_gcrs'] for row in expected]);g=np.array([row['state_gcrs'] for row in actual])
                position=float(np.linalg.norm(g[:,:3]-e[:,:3],axis=1).max());velocity=float(np.linalg.norm(g[:,3:]-e[:,3:],axis=1).max())
                assert position<.01 and velocity<1e-5,(name,position,velocity)
                for _ in range(64):
                    present=rng.getrandbits(32);q=rng.getrandbits(32)&present;drive=rng.getrandbits(32)
                    values=[q,drive,present,*[rng.getrandbits(32) for _ in range(6)],rng.randrange(16),rng.randrange(256),rng.randrange(256)]
                    command='TRANSITION '+' '.join(map(str,values));assert cpu.command(command)==gpu.command(command)
                device=gpu.command('QUERY 300')['device']
            item['cuda']={'queries':len(query_times),'cpu_position_max_m':position,'cpu_velocity_max_m_s':velocity,
                         'word_transitions_exact':64,'device':device}
        report['models'][name]=item
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(name,json.dumps(item),flush=True)
    if a.cuda_binary:report['cuda_binary_sha256']=digest(a.cuda_binary)
    if a.sanitizer:
        if not a.cuda_binary:raise ValueError('--sanitizer requires --cuda-binary')
        sanitizer=shutil.which('compute-sanitizer')
        if not sanitizer:raise RuntimeError('compute-sanitizer unavailable; not_run')
        modelpath=a.out/'sanitizer_model.txt';modelpath.write_text(numeric_model(models['G05']),encoding='ascii')
        times=np.linspace(-21600.,86400.,129)
        requests='BATCH 129 '+' '.join(format(t,'.17g') for t in times)+'\nTRANSITION 0 15 15 15 15 0 15 15 8 14 204 0\nQUIT\n'
        (a.out/'sanitizer_requests.txt').write_text(requests)
        command=[sanitizer,'--tool','memcheck','--error-exitcode','99','--log-file',str((a.out/'memcheck.log').resolve()),
                 str(a.cuda_binary.resolve()),'--model',str(modelpath.resolve()),'--backend','cuda']
        run=subprocess.run(command,input=requests,text=True,capture_output=True,timeout=180)
        (a.out/'sanitizer_stdout.jsonl').write_text(run.stdout);(a.out/'sanitizer_stderr.txt').write_text(run.stderr)
        assert run.returncode==0,(run.returncode,run.stderr)
        rows=[json.loads(line) for line in run.stdout.splitlines()];batch=next(r for r in rows if r['type']=='batch')
        assert len(batch['queries'])==129 and all(q['status']=='ok' for q in batch['queries'])
        assert next(r for r in rows if r['type']=='transition')['stage_b']['hits']==1
        assert 'ERROR SUMMARY: 0 errors' in (a.out/'memcheck.log').read_text()
        report['compute_sanitizer']={'status':'passed','queries':129,'word_transitions':1,'command':command,'error_count':0}
    report['status']='passed';(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print('passed',a.out/'summary.json')

if __name__=='__main__':main()
