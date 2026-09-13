#!/usr/bin/env python3
"""Small executable cases in automatically cleaned temporary directories."""
from pathlib import Path
import argparse,json,math,subprocess,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python.reference import verify_directory
from python.provenance import seal,verify

def expect_exit(result, success):
    expected = 0 if success else 1
    if result.returncode != expected:
        raise RuntimeError(f'{result.args}: expected exit {expected}, got {result.returncode}: {result.stdout}\n{result.stderr}')


def verify_execution_metadata(meta, args, gpu):
    options = dict(zip(args[::2], args[1::2]))
    executed = gpu and meta['samples'] > 0
    if meta['gpu_executed'] is not executed:
        raise RuntimeError('gpu_executed must describe whether a device kernel actually ran')
    if meta['sample_order'] != options.get('--sample-order', 'locality' if gpu else 'natural'):
        raise RuntimeError('sample order does not match the requested path')
    warmup = int(options.get('--warmup', 0)) if executed else 0
    repeats = int(options.get('--repeat', 1)) if executed else 0
    if (meta['warmup_runs_per_path'], meta['timed_runs_per_path']) != (warmup, repeats):
        raise RuntimeError('timing metadata claims the wrong number of kernel launches')
    block_size = int(options.get('--block-size',512)) if executed else 0
    if meta['block_size'] != block_size:
        raise RuntimeError('block size metadata does not match actual kernel execution')
    policy = options.get('--l2-policy','normal')
    active = executed and policy == 'persist-image'
    if meta['l2_policy'] != policy or meta['l2_policy_active'] is not active:
        raise RuntimeError('L2 policy metadata does not match requested device execution')
    for key in ('l2_requested_bytes','l2_accepted_bytes','l2_window_bytes',
                'l2_cache_bytes','persisting_l2_max_bytes','access_policy_max_window_bytes','l2_window_base_address'):
        if not isinstance(meta[key],int) or isinstance(meta[key],bool) or meta[key] < 0:
            raise RuntimeError('invalid L2 cache byte count: '+key)
    if not math.isfinite(meta['l2_hit_ratio']) or not 0 <= meta['l2_hit_ratio'] <= 1:
        raise RuntimeError('invalid L2 policy hit ratio')
    if not active:
        if any(meta[key] != 0 for key in ('l2_requested_bytes','l2_accepted_bytes','l2_window_bytes','l2_hit_ratio',
                                        'l2_window_base_address','l2_hit_property','l2_miss_property')):
            raise RuntimeError('inactive L2 policy must not claim a configured window or reservation')
    else:
        image_bytes = 4*meta['config']['rho_bins']*meta['config']['phi_bins']
        if not 0 < meta['l2_window_bytes'] <= min(image_bytes,meta['access_policy_max_window_bytes']):
            raise RuntimeError('L2 policy window exceeds its image allocation or supported limit')
        if not 0 < meta['l2_requested_bytes'] <= meta['persisting_l2_max_bytes'] or not 0 < meta['l2_accepted_bytes'] <= meta['persisting_l2_max_bytes']:
            raise RuntimeError('L2 policy reservation exceeds its supported limit')
        if meta['l2_window_base_address'] == 0 or (meta['l2_hit_property'],meta['l2_miss_property']) != (2,0):
            raise RuntimeError('L2 stream window readback does not show the requested persistence policy')
    for key in ('reorder_ms', 'restore_ms', 'texture_mean_ms', 'texture_min_ms', 'global_mean_ms', 'global_min_ms'):
        if not math.isfinite(meta[key]) or meta[key] < 0:
            raise RuntimeError('invalid timing measurement: '+key)
    if not meta['texture_min_ms'] <= meta['texture_mean_ms'] or not meta['global_min_ms'] <= meta['global_mean_ms']:
        raise RuntimeError('minimum kernel time exceeds its mean')
    if not executed and any(meta[key] != 0 for key in ('texture_mean_ms', 'texture_min_ms', 'global_mean_ms', 'global_min_ms')):
        raise RuntimeError('unexecuted device path must not report a measured kernel time')
    if gpu and meta['compute_ms'] != meta['texture_mean_ms']:
        raise RuntimeError('compute_ms must report mean texture kernel time')


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--executable',type=Path,required=True);p.add_argument('--gpu',action='store_true')
    a=p.parse_args(argv);exe=str(a.executable.resolve());results=[];matching_records={}
    cases=[(['--samples',str(n),'--layout',layout],True)
           for n in (0,1,257,4097,65536) for layout in ('linear','morton')]
    cases += [(['--samples','257','--rho-bins',str(h),'--phi-bins',str(w),'--layout',layout],True)
              for h,w in ((8,8),(16,24),(40,64)) for layout in ('linear','morton')]
    cases = [(args+['--sample-order',order],expected) for args,expected in cases for order in ('natural','locality')]
    if a.gpu:
        cases += [(['--samples',str(n),'--layout',layout,'--sample-order',order,'--warmup','2','--repeat','3'],True)
                  for n in (0,257) for layout in ('linear','morton') for order in ('natural','locality')]
        cases += [(['--samples','257','--layout','morton','--sample-order',order,'--block-size',str(block)],True)
                  for block in (128,256,512,1024) for order in ('natural','locality')]
        cases += [(['--samples','0','--layout','morton','--sample-order',order,'--block-size','1024'],True)
                  for order in ('natural','locality')]
        cases += [(['--samples','257','--layout',layout,'--sample-order',order,'--l2-policy','persist-image'],True)
                  for layout in ('linear','morton') for order in ('natural','locality')]
        cases.append((['--samples','0','--l2-policy','persist-image'],True))
    cases += [(['--samples',str(n),'--layout','morton'],True) for n in (0,257)]
    cases += [(['--rho-bins','9'],False),(['--samples','-1'],False),(['--budget-mib','1'],False),
           (['--layout','bad'],False),(['--samples','4194305'],False),(['--unknown','1'],False),
           (['--sample-order','bad'],False),(['--warmup','-1'],False),(['--warmup','101'],False),
           (['--repeat','-1'],False),(['--repeat','0'],False),(['--repeat','1001'],False),
           (['--l2-policy','bad'],False)]
    cases += [(['--block-size',str(block)],False) for block in (-1,0,1,255,2048)]
    if a.gpu:cases.append((['--device','4294967295'],False))
    else:cases += [(['--warmup','1'],False),(['--repeat','2'],False),(['--l2-policy','persist-image'],False),
                  *[(['--block-size',str(block)],False) for block in (128,512,1024)]]
    for args,expected in cases:
        with tempfile.TemporaryDirectory(prefix='asa_case_') as tmp:
            directory=Path(tmp)/'run'
            run=subprocess.run([exe,'--out',str(directory),*args],text=True,capture_output=True)
            expect_exit(run,expected)
            if expected:
                oracle=verify_directory(directory)
                meta=json.loads((directory/'run.json').read_text())
                verify_execution_metadata(meta,args,a.gpu)
                key = (json.dumps(meta['config'],sort_keys=True),meta['samples'])
                records = ((directory/'samples.f64x2').read_bytes(),(directory/'results.bin').read_bytes())
                if key in matching_records and matching_records[key] != records:
                    raise RuntimeError('sample reordering or repetitions changed original samples/results')
                matching_records[key] = records
                value=seal(directory)
                if not verify(directory,value['head']):raise RuntimeError('seal check failed')
                repeated=subprocess.run([exe,'--out',str(directory),*args],capture_output=True)
                expect_exit(repeated,False)
                if not verify(directory,value['head']):raise RuntimeError('existing result directory was changed')
            elif directory.exists():
                raise RuntimeError('rejected input must fail before creating its output directory')
            results.append({'arguments':args,'expected_success':expected,'status':'pass',
                            **({'oracle':oracle,'gpu_executed':meta['gpu_executed'],'sample_order':meta['sample_order'],
                                'block_size':meta['block_size']} if expected else {})})
    print(json.dumps({'backend':'GPU' if a.gpu else 'CPU','cases':results},indent=2))


if __name__ == '__main__':
    main()
