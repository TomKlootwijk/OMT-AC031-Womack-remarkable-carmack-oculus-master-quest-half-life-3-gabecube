#!/usr/bin/env python3
"""Bind R18 narrow/wide CUDA resources and static SASS; executes no GPU work."""
from pathlib import Path
import argparse
import collections
import datetime
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / 'review'
KINDS = ('journal_fused_words', 'journal_batch', 'journal_receipt',
         'batch_kernel', 'step_kernel', 'fused_words', 'commit_words',
         'inject_words', 'read_cells', 'read_header', 'expand')
# Explicit mnemonic groups, not a claim that all other instructions are floating.
INTEGER = set('IADD IADD3 IADD32I IMAD IMADSP IMAD32I IMUL IMUL32I ISETP ISET '
              'VIMNMX IMNMX ISCADD SHF SHL SHR LOP LOP3 LOP32I BFE BFI BMSK '
              'BREV FLO POPC LEA UIADD3 UIMAD UISETP ULOP ULOP3 USHF ULEA '
              'UFLO UPOPC I2I I2IP UIMNMX'.split())
FLOAT = set('FADD FADD32I FFMA FFMA32I FMUL FMUL32I FSET FSETP FMNMX FSWZ '
            'DADD DMUL DFMA DSETP HADD2 HMUL2 HFMA2 HSET2 HSETP2 '
            'HADD2_32I HMUL2_32I HFMA2_32I MUFU F2F F2I I2F FRND'.split())


def record(path):
    data = path.read_bytes()
    try:
        label = path.relative_to(ROOT).as_posix()
    except ValueError:
        label = path.as_posix()
    return dict(path=label, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def identity(symbol):
    kind = next((k for k in KINDS if k in symbol), None)
    if kind is None:
        raise ValueError('Unknown kernel ' + symbol)
    flags = re.search(r'ILb([01])E(?:Lb([01])E)?', symbol)
    texture = bool(int(flags[1])) if flags else None
    inject = bool(int(flags[2])) if flags and flags[2] else None
    return kind, texture, inject


def inspect(executable, label, dumper):
    before = record(executable)
    paths = {}
    for mode, option in [('resources', '--dump-resource-usage'), ('sass', '--dump-sass')]:
        target = REVIEW / ('r18_' + label + '_' + mode + '.txt')
        result = subprocess.run([str(dumper), option, str(executable)],
                                capture_output=True, check=True)
        target.write_bytes(result.stdout)
        paths[mode] = target
    if record(executable) != before:
        raise ValueError('Executable changed during static inspection')
    resources = paths['resources'].read_text(encoding='utf-8-sig')
    sass = paths['sass'].read_text(encoding='utf-8-sig')
    if set(re.findall(r'arch = (\S+)', resources)) != {'sm_120'}:
        raise ValueError('Expected only pinned sm_120 architecture')
    resource_map = {}
    for symbol, line in re.findall(r' Function ([^:\n]+):\s*\n([^\n]+)', resources):
        resource_map[symbol] = {k: int(v) for k, v in
                                re.findall(r'([A-Z]+(?:\[\d+\])?):(\d+)', line)}
    kernels = []
    starts = list(re.finditer(r'^\s*Function : ([^\r\n]+)', sass, re.M))
    for index, start in enumerate(starts):
        symbol = start[1]
        body = sass[start.end():starts[index+1].start() if index+1 < len(starts) else len(sass)]
        counts = collections.Counter()
        instructions = []
        for line in body.splitlines():
            if not re.match(r'^\s*/\*[0-9a-fA-F]+\*/', line):
                continue
            match = re.match(r'^\s*/\*[0-9a-fA-F]+\*/\s+(?:@!?[UPT0-9]+\s+)?([A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+)*)\b', line)
            if not match:
                raise ValueError('Unparsed instruction: ' + line)
            op = match[1].split('.')[0]
            counts[op] += 1
            instructions.append((op, line.strip()))
        kind, texture, inject = identity(symbol)
        hfma = [line for op, line in instructions if op == 'HFMA2']
        integer_sites = sum(counts[k] for k in INTEGER)
        floating_sites = sum(counts[k] for k in FLOAT)
        kernels.append(dict(kind=kind, texture=texture, injection=inject, symbol=symbol,
                            resources=resource_map.pop(symbol),
                            instruction_sites=sum(counts.values()),
                            integer_logic_group_sites=integer_sites,
                            floating_conversion_group_sites=floating_sites,
                            other_group_sites=sum(counts.values())-integer_sites-floating_sites,
                            opcode_counts=dict(sorted(counts.items())),
                            hfma2_sites_all_zero_register_constant_forms=all(
                                re.search(r'HFMA2 R\d+, -?RZ, RZ,', line) for line in hfma)))
    if resource_map or not kernels:
        raise ValueError('Resource/SASS kernel coverage mismatch')
    return dict(executable=before, dumps=[record(p) for p in paths.values()],
                kernel_count=len(kernels), kernels=kernels)


def key(kernel):
    return kernel['kind'], kernel['texture'], kernel['injection']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cuobjdump', type=Path, default=Path('C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.8/bin/cuobjdump.exe'))
    parser.add_argument('--narrow', type=Path, default=Path('C:/aTOMosBuild/r18vm/Release'))
    parser.add_argument('--wide', type=Path, default=Path('C:/aTOMosBuild/r18wide/Release'))
    args = parser.parse_args()
    binaries = {}
    for label, directory, name in [('narrow', args.narrow, 'wqk_run.exe'),
                                    ('wide', args.wide, 'wqk_run.exe'),
                                    ('materialize', args.narrow, 'wqk_materialize.exe'),
                                    ('materialize_wide', args.wide, 'wqk_materialize.exe')]:
        binaries[label] = inspect(directory / name, label, args.cuobjdump)
    wide = {key(k): k for k in binaries['wide']['kernels']}
    matched = []
    for n in binaries['narrow']['kernels']:
        w = wide.pop(key(n))
        matched.append(dict(kind=n['kind'], texture=n['texture'], injection=n['injection'],
                            narrow_registers=n['resources']['REG'], wide_registers=w['resources']['REG'],
                            narrow_sites=n['instruction_sites'], wide_sites=w['instruction_sites'],
                            narrow_integer_logic_sites=n['integer_logic_group_sites'],
                            wide_integer_logic_sites=w['integer_logic_group_sites'],
                            narrow_float_conversion_sites=n['floating_conversion_group_sites'],
                            wide_float_conversion_sites=w['floating_conversion_group_sites']))
    if wide:
        raise ValueError('Unmatched wide kernels')
    # Check separately linked CLI kernels against corresponding run bodies.
    for cli, run in [('materialize', 'narrow'), ('materialize_wide', 'wide')]:
        by_key = {key(k): k for k in binaries[run]['kernels']}
        for kernel in binaries[cli]['kernels']:
            other = by_key[key(kernel)]
            if kernel['opcode_counts'] != other['opcode_counts'] or kernel['resources'] != other['resources']:
                raise ValueError('CLI kernel differs from corresponding runner resources/opcode counts')
    all_kernels = [k for b in binaries.values() for k in b['kernels']]
    report = dict(profile='ATOMOS-R18-COMPILED-NATIVE-AUDIT-R1',
                  captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  architecture='sm_120', scope='Static compiled resource/SASS inspection; no GPU workload, timing, cache-hit or achieved occupancy measurement.',
                  dumper=record(args.cuobjdump), audit_tool=record(Path(__file__).resolve()),
                  native_sources=[record(ROOT / p) for p in ['CMakeLists.txt',
                      'include/atomos/tomagi_vm.hpp', 'include/atomos/tomagi_feedback.hpp',
                      'include/atomos/tomagi_journal.hpp', 'cuda/tomagi_vm.cu',
                      'cuda/tomagi_feedback.cu', 'cuda/tomagi_transition.cuh',
                      'cuda/tomagi_journal.cuh', 'cuda/tomagi_journal.cu',
                      'tools/wqk_run.cpp', 'tools/wqk_materialize.cpp']],
                  instruction_group_definitions=dict(integer_logic=sorted(INTEGER),
                      floating_conversion=sorted(FLOAT), other='Every remaining mnemonic; includes memory, movement, control and predicate operations. Groups describe static mnemonics, not runtime precision or hardware utilization.'),
                  binaries=binaries, matched_runner_kernels=matched,
                  all_stack_local_zero=all(k['resources']['STACK']==0 and k['resources']['LOCAL']==0 for k in all_kernels),
                  all_ldl_stl_absent=all(not k['opcode_counts'].get('LDL') and not k['opcode_counts'].get('STL') for k in all_kernels),
                  all_i2f_mufu_f2i_absent=all(not any(k['opcode_counts'].get(op) for op in ('I2F','MUFU','F2I')) for k in all_kernels),
                  cli_common_resources_and_opcode_counts_match_runner=True,
                  documentation='https://docs.nvidia.com/cuda/archive/12.8.1/cuda-binary-utilities/index.html')
    (REVIEW / 'r18_native_code.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k.startswith('all_') or k == 'matched_runner_kernels'}, indent=2))


if __name__ == '__main__':
    main()
