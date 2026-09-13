"""Execute source-SDF/Klein conformance and cold full-epoch cache measurements.

Every exported result is independently replayed. Counter profiles retain raw logs
and use cold replay; ordinary timings are collected outside the profiler.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from sdf_atlas import default_config, write_atlas, verify_atlas
from sdf_reference import verify_source_run
from profile_cache import METRICS, parse_metrics, read_log, resolve_ncu
from validate import find_compute_sanitizer

COUNTERS=METRICS+('l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum',
 'l1tex__t_sectors_pipe_lsu_mem_global_op_ld_lookup_miss.sum','launch__shared_mem_config_size')
SOURCES=('include/atomos/core.hpp','include/atomos/host.hpp','include/atomos/klein.hpp',
 'include/atomos/packed_atlas.hpp','cuda/kernel.cu','experiments/cache_bulk.cu',
 'python/sdf_atlas.py','python/sdf_reference.py','python/reference.py')

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--phase',choices=('conformance','edges','profiles','capacity'),required=True)
    p.add_argument('--profile-trials',type=int,default=2)
    p.add_argument('--capacity-rows',type=int,nargs='+',help='Optional no-padding row counts for a capacity refinement')
    args=p.parse_args()
    exe=args.exe.resolve();out=args.out.resolve()
    if out.exists():raise FileExistsError('study output must be new')
    out.mkdir(parents=True)
    if args.profile_trials<1:raise ValueError('positive trial count required')
    if args.capacity_rows and (args.phase!='capacity' or any(r<8 or r%8 or r>2048 for r in args.capacity_rows)):
        raise ValueError('capacity row refinement requires multiples of eight from 8 through 2048')
    source_hashes={name:digest(ROOT/name) for name in SOURCES}
    report=dict(schema='atomos-sdf-klein-study-v1',status='running',phase=args.phase,
                created_at_utc=datetime.now(timezone.utc).isoformat(),executable=str(exe),
                executable_sha256=digest(exe),source_hashes=source_hashes,atlases=[],runs=[],commands=[])
    def save():(out/'study.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def run(cmd,label):
        print(label,flush=True)
        started=time.perf_counter()
        with (out/(label+'.stdout.log')).open('w',encoding='utf-8') as stdout, (out/(label+'.stderr.log')).open('w',encoding='utf-8') as stderr:
            done=subprocess.run([str(v) for v in cmd],cwd=ROOT,stdout=stdout,stderr=stderr)
        report['commands'].append(dict(command=[str(v) for v in cmd],exit_code=done.returncode,
            wall_seconds=time.perf_counter()-started,stdout=label+'.stdout.log',stderr=label+'.stderr.log'))
        save()
        if done.returncode:raise RuntimeError(label+' failed; see retained command logs')
        receipts=[]
        for line in (out/(label+'.stdout.log')).read_text(encoding='utf-8').splitlines():
            if line.startswith('{'):
                value=json.loads(line)
                if value.get('scope')=='experimental_bulk_io_warm_work_retention_probe':receipts.append(value)
        if not receipts or any(r.get('status')!='passed' for r in receipts):raise ValueError('verified GPU receipt missing')
        return receipts
    atlas_cache={}
    def atlas(rows,angles,profile='geometry'):
        key=(rows,angles,profile)
        if key not in atlas_cache:
            config=default_config(profile,rows,angles)
            if profile=='geometry':
                # Asymmetric placement crosses the angular seam; a torus gives
                # different predicates. Exact parameters are retained in JSON.
                for primitives in config['planes'].values():
                    for primitive in primitives:primitive['center']=[.23,.02]
            path=out/'atlases'/f'{profile}_{rows}_{angles}.atlas'
            info=write_atlas(config,path)
            report['atlases'].append(info);atlas_cache[key]=path;save()
        return atlas_cache[key]
    def application(rows,angles,layout,carrier,epochs,profile='geometry',mode='recurrent',fringe=True):
        return [exe,'--rows',rows,'--angles',angles,'--layout',layout,'--carrier',carrier,
                '--atlas',atlas(rows,angles,profile),'--atlas-cap-texels',1<<20,
                '--epochs',epochs,'--mode',mode,'--fringe','on' if fringe else 'off']
    try:
        if args.phase in ('conformance','edges'):
            cases=[]
            for dims,layout,carrier,mode,fringe in itertools.product(
                ((1,1),(3,65),(17,257)),('linear','morton8'),('direct','klein-plus','klein-minus'),
                ('provided','recurrent','shift-xor','shift-or'),(False,True)):
                cases.append((*dims,layout,carrier,mode,fringe,3))
            for carrier in ('klein-plus','klein-minus'):
                cases.append((3,65,'morton8',carrier,'recurrent',True,130))
            if args.phase=='edges':
                cases=[(*dims,layout,carrier,'recurrent',True,3) for dims,layout,carrier in itertools.product(
                    ((1,33),(9,33),(17,700)),('linear','morton8'),('klein-plus','klein-minus'))]
            for index,(rows,angles,layout,carrier,mode,fringe,epochs) in enumerate(cases):
                label=f'run_{index:03d}_{rows}_{angles}_{layout}_{carrier}_{mode}_{int(fringe)}'
                directory=out/label
                cmd=application(rows,angles,layout,carrier,epochs,mode=mode,fringe=fringe)+['--out',directory]
                receipt=run(cmd,label)[0]
                checked=verify_source_run(directory,atlas(rows,angles))
                report['runs'].append(dict(kind='conformance',label=label,verification=checked,
                    mask_bytes=receipt['mask_bytes'],median_kernel_ms=statistics.median(receipt['compute_ms']),
                    occupied_seam_crossings=sum(x['occupied_seam_crossings'] for x in receipt['epoch_occupancy'])))
                save()
            sanitizer=find_compute_sanitizer()
            if sanitizer is None:raise RuntimeError('required native Compute Sanitizer unavailable')
            sanitizer_shape=(17,700) if args.phase=='edges' else (17,257)
            for tool,layout,carrier in itertools.product(('memcheck','racecheck','synccheck'),('linear','morton8'),('klein-plus','klein-minus')):
                label=f'{tool}_{layout}_{carrier}';directory=out/label
                cmd=[sanitizer,'--tool',tool,'--error-exitcode','2',*application(*sanitizer_shape,layout,carrier,3),'--out',directory]
                run(cmd,label)
                report['runs'].append(dict(kind='sanitizer',label=label,verification=verify_source_run(directory,atlas(*sanitizer_shape))))
                save()
        else:
            ncu=resolve_ncu(None)
            if ncu is None:raise RuntimeError('required Nsight Compute unavailable')
            report['profiler_executable']=str(ncu)
            sizes=(tuple(args.capacity_rows) if args.capacity_rows else (512,576,608,624,640,672)) if args.phase=='capacity' else (128,512)
            for rows,layout in itertools.product(sizes,('linear','morton8')):
                angles=1024 if rows==128 else 16384
                label=f'timing_{rows}_{angles}_{layout}'
                receipt=run(application(rows,angles,layout,'klein-plus',3),label)[0]
                report['runs'].append(dict(kind='timing',label=label,receipt=receipt,
                    median_kernel_ms=statistics.median(receipt['compute_ms'])))
                save()
                for trial in range(args.profile_trials):
                    label=f'cold_{rows}_{angles}_{layout}_{trial}'
                    csv_path=out/(label+'.csv.log')
                    cmd=[ncu,'--replay-mode','kernel','--cache-control','all','--clock-control','none',
                         '--launch-skip','1','--launch-count','1','--check-exit-code','1',
                         '--metrics',','.join(COUNTERS),'--csv','--page','raw','--print-units','base',
                         '--log-file',csv_path,*application(rows,angles,layout,'klein-plus',1)]
                    receipts=run(cmd,label)
                    metrics=parse_metrics(read_log(csv_path),COUNTERS)
                    if any(x.get('status')!='collected' for x in metrics.values()):raise ValueError('requested cache counter unavailable')
                    receipt=receipts[0];texels=receipt['stored_texels']
                    if texels!=receipt['logical_texels']:raise ValueError('capacity profile must have no padded texels')
                    floor=texels//2
                    sectors=metrics[METRICS[1]]['value'];hits=metrics[METRICS[2]]['value'];misses=metrics[METRICS[3]]['value']
                    # Divergent scheduling can split a coalesced request into
                    # extra transactions. This changes traffic, not the unique
                    # cold-data floor. Retention still requires misses==floor.
                    if hits+misses!=sectors or sectors<3*floor or misses<floor:
                        raise ValueError('cold full-atlas traffic conservation or compulsory floor mismatch')
                    report['runs'].append(dict(kind='cold_profile',label=label,mask_bytes=receipt['mask_bytes'],
                        layout=layout,rows=rows,angles=angles,metrics=metrics,compulsory_miss_floor=floor,
                        measured_misses=misses,extra_misses=misses-floor,at_compulsory_floor=misses==floor,
                        minimum_tex_sectors=3*floor,extra_tex_sectors=sectors-3*floor,
                        maximum_assigned_mask_bytes=receipt['maximum_assigned_mask_bytes'],receipt=receipt))
                    save()
        if source_hashes!={name:digest(ROOT/name) for name in SOURCES}:raise ValueError('audited source changed during study')
        if report['executable_sha256']!=digest(exe):raise ValueError('executable changed during study')
        report['status']='passed'
    except Exception as exc:
        report.update(status='failed',reason=str(exc));save();raise
    save()
    print(json.dumps(dict(status=report['status'],runs=len(report['runs']),study=str(out/'study.json'))))

if __name__=='__main__':main()
