"""Bounded application rule amendment, with independent checks and version commit.

The host policy reads GPU-exported self-inspection (id/version/link/output), then
amends that application's encoded routing link. This is not autonomous learning
or native CUDA self-modification. Candidate textures stay immutable in flight.

active_bank.json is the commit authority. Evidence and a candidate-hash COMMITTED
marker are prepared before its final atomic replacement. The marker represents a
commit only when its hash matches the active pointer. This is not a filesystem
crash-consistency or durability claim.
"""
from __future__ import annotations
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from program_bank import load_bank, write_bank
from program_bank_reference import decode_bank, evaluate, verify_trace


def hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same_skills(before, after):
    checked = 0
    if len(before['capsules']) != len(after['capsules']):
        raise ValueError('amendment changed library extent')
    for a, b in zip(before['capsules'], after['capsules']):
        if (a['input_bits'], a['output_bits']) != (b['input_bits'], b['output_bits']):
            raise ValueError('amendment changed skill interface')
        if a['input_bits'] > 12:
            raise ValueError('amendment exhaustive audit limited to 12 input bits')
        for value in range(1 << a['input_bits']):
            if evaluate(a,value) != evaluate(b,value):
                raise ValueError(f'changed skill {a["id"]} at input {value}')
            checked += 1
    return checked


def validate_routing_amendment(before, after, identity, next_slot):
    """Allow exactly one routing/version/parent revision in an otherwise fixed bank."""
    for field in ('rows', 'angles', 'capsule_count', 'master_seed_hex'):
        if before[field] != after[field]:
            raise ValueError('amendment changed bank ' + field)
    count = before['capsule_count']
    if len(before['capsules']) != count or len(after['capsules']) != count:
        raise ValueError('amendment changed library extent')
    if type(identity) is not int or not 0 <= identity < count:
        raise ValueError('amendment identity outside bank')
    if type(next_slot) is not int or not 0 <= next_slot < count:
        raise ValueError('amendment route outside bank')
    old = before['capsules'][identity]
    revised = after['capsules'][identity]
    if next_slot == old['next_slot']:
        raise ValueError('amendment did not change routing')
    if (revised['next_slot'] != next_slot or
            revised['parent_sha256'] != old['content_sha256'] or
            revised['version'] != old['version'] + 1 or revised['version'] > 0xffffffff):
        raise ValueError('proposal violates declared routing/version policy')
    allowed = {'next_slot', 'version', 'parent_sha256', 'content_sha256'}
    for index, (a, b) in enumerate(zip(before['capsules'], after['capsules'])):
        if index != identity:
            if a != b:
                raise ValueError('amendment changed an unrelated page')
        elif ({key: value for key, value in a.items() if key not in allowed} !=
              {key: value for key, value in b.items() if key not in allowed}):
            raise ValueError('routing-only amendment changed another field of its page')
    return same_skills(before, after)


def checked_chain_summary(path):
    receipt = json.loads(Path(path).read_text(encoding='utf-8'))
    if (receipt.get('schema') != 'atomOS-program-bank-runtime-v1' or
            receipt.get('status') != 'passed' or receipt.get('accepted') is not True or
            receipt.get('committed') is not True or receipt.get('execution_mode') != 'chain'):
        raise ValueError('execution receipt is not a committed native chain')
    for field in ('input_initial', 'initial_slot', 'hops', 'hops_executed', 'kernel_error'):
        if type(receipt.get(field)) is not int or receipt[field] < 0:
            raise ValueError('execution receipt has invalid ' + field)
    if not receipt['hops'] or receipt['hops_executed'] != receipt['hops'] or receipt['kernel_error']:
        raise ValueError('execution receipt has an incomplete or failed chain')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('bank','source-run','exe','atlas','out'):
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args(); out=a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    source=a.bank.resolve(); source_run=a.source_run.resolve(); exe=a.exe.resolve(); atlas=a.atlas.resolve()
    before=decode_bank(source, source.parent/'manifest.json')
    source_receipt=checked_chain_summary(source_run/'summary.json')
    if not (source_run/'COMMITTED').is_file() or hash_file(source_run/'bank.bin')!=hash_file(source):
        raise ValueError('source execution not committed or not bound to source bank')
    verify_trace(source_run/'trace.csv', before, source_receipt['input_initial'],
                 source_receipt['hops'], source_receipt.get('initial_slot',0))
    active=dict(bank=str(source),sha256=hash_file(source),publication_sequence=0)
    def publish_active(value):
        temporary=out/'active_bank.json.partial'
        temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        temporary.replace(out/'active_bank.json')
    publish_active(active)
    active_before=(out/'active_bank.json').read_bytes()
    with (source_run/'trace.csv').open(encoding='utf-8',newline='') as stream:
        trace=list(csv.DictReader(stream))
    count=before['capsule_count']
    evidence=next((r for r in trace if int(r['output'])%count != 0),None)
    if evidence is None:
        raise ValueError('this trace proposes no changed route under the declared policy')
    identity=int(evidence['program_id']); old=before['capsules'][identity]
    # Read the old rule from the actual executed texture export, not a chosen goal.
    if int(evidence['next_slot'])!=old['next_slot'] or int(evidence['version'])!=old['version']:
        raise ValueError('self-inspection differs from source rule')
    next_slot=(int(evidence['next_slot'])+int(evidence['output']))%count
    compiled=load_bank(source)['capsules']
    capsules=copy.deepcopy(compiled)
    for capsule, descriptor in zip(capsules,json.loads((source.parent/'manifest.json').read_text(encoding='utf-8'))['capsules']):
        capsule['name']=descriptor['name']
    # A structurally legal but behaviour-changing candidate must be rejected.
    bad=copy.deepcopy(capsules)
    bad[identity]['circuit']['outputs']=[bad[identity]['circuit']['constant_zero_wire']]*old['output_bits']
    bad[identity].update(version=old['version']+1,parent_sha256=old['content_sha256'])
    write_bank(out/'rejected_proposal'/'bank.bin',bad,master_seed_hex=before['master_seed_hex'],rows=before['rows'],angles=before['angles'])
    rejected=decode_bank(out/'rejected_proposal'/'bank.bin',out/'rejected_proposal'/'manifest.json')
    try:
        same_skills(before,rejected)
    except ValueError as error:
        rejection=str(error)
    else:
        raise ValueError('negative amendment did not change behaviour; invalid rejection fixture')
    if (out/'active_bank.json').read_bytes()!=active_before:
        raise ValueError('rejected proposal changed committed identity')
    (out/'rejected_proposal'/'REJECTED').write_text(rejection+'\n')
    # The application proposes a new routing rule; its finite skills must persist.
    capsules[identity].update(next_slot=next_slot,version=old['version']+1,parent_sha256=old['content_sha256'])
    proposal=out/'routing_proposal'/'bank.bin'
    write_bank(proposal,capsules,master_seed_hex=before['master_seed_hex'],rows=before['rows'],angles=before['angles'])
    after=decode_bank(proposal,proposal.parent/'manifest.json')
    cases=validate_routing_amendment(before,after,identity,next_slot)
    revised=after['capsules'][identity]
    proposal_hash=after['bank_file_sha256']
    executable_hash=hash_file(exe)
    atlas_hash=hash_file(atlas)
    command=[str(exe),'--bank',str(proposal),'--atlas',str(atlas),'--layout','morton8','--mode','chain',
             '--input',str(source_receipt['input_initial']),'--initial-slot',str(source_receipt.get('initial_slot',0)),
             '--hops','24','--out',str(out/'native_candidate')]
    with (out/'native_candidate.log').open('w',encoding='utf-8') as log:
        completed=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if completed.returncode:
        raise RuntimeError('amended candidate native execution failed')
    native=out/'native_candidate'
    native_receipt=checked_chain_summary(native/'summary.json')
    if (native_receipt['input_initial'] != source_receipt['input_initial'] or
            native_receipt['initial_slot'] != source_receipt['initial_slot'] or native_receipt['hops'] != 24):
        raise ValueError('native amendment execution parameters differ from proposal')
    if (not (native/'COMMITTED').is_file() or hash_file(proposal)!=proposal_hash or
            hash_file(native/'bank.bin')!=proposal_hash):
        raise ValueError('native amendment commit/input binding')
    if hash_file(native/'operators.atlas') != atlas_hash:
        raise ValueError('native amendment operator atlas binding')
    checked=verify_trace(native/'trace.csv',after,source_receipt['input_initial'],24,source_receipt.get('initial_slot',0))
    accepted_hash=proposal_hash
    receipt=dict(schema='atomos-bounded-routing-amendment-v1',status='passed',
                 scope='host-mediated application self-inspection and routing-rule revision; no autonomous learned improvement',
                 policy='new_next_slot = (observed_own_next_slot + observed_output) mod capsule_count',
                 source_bank_sha256=hash_file(source),source_trace_sha256=hash_file(source_run/'trace.csv'),
                 original_version=old['version'],new_version=revised['version'],program_id=identity,
                 original_next_slot=old['next_slot'],new_next_slot=next_slot,source_evidence=evidence,
                 rejected_candidate_reason=rejection,rejected_preserved_active_bank=True,
                 exhaustive_preserved_skill_cases=cases,native_command=command,
                 executable_sha256=executable_hash,operator_atlas_sha256=atlas_hash,
                 independent_native_verification=checked,
                 accepted_bank_sha256=accepted_hash,
                 publication_protocol='Evidence, VERIFIED and candidate-hash marker prepared before atomic active_bank.json replacement; active pointer is commit authority',
                 marker_valid_only_when_active_hash_matches=True,
                 filesystem_crash_consistency='not_claimed')
    (out/'amendment.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    (out/'VERIFIED').write_text(accepted_hash+'\n',encoding='utf-8')
    (out/'COMMITTED').write_text(accepted_hash+'\n',encoding='utf-8')
    publish_active(dict(bank=str(proposal),sha256=accepted_hash,publication_sequence=1))
    print(json.dumps(receipt,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
