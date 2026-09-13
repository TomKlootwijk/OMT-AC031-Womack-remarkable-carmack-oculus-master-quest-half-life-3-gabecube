"""Typed queries over six independently specified finite knowledge capabilities.

This module parses a deliberately small command grammar. It never invokes an
LLM or executes a candidate. A CPU oracle verifies eligibility and supplies the
expected value for a separate native run, not a pretend GPU answer.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re

from knowledge_admission import semantic_signature
from program_bank_reference import decode_bank, evaluate
from teacher_knowledge import profiles, scalar_oracle

MAX_BANK_BYTES = 64 << 20
MAX_MANIFEST_BYTES = 16 << 20
MAX_QUERY_CHARACTERS = 256
ROOT = Path(__file__).resolve().parents[1]

COMMANDS = {
    'full_adder_1bit_v1': 'add one-bit A B carry C (A, B, C: 0..1)',
    'unsigned_compare_2bit_v1': 'compare A B (A, B: 0..3)',
    'unsigned_add_2bit_v1': 'add A B (A, B: 0..3)',
    'binary_to_gray_4bit_v1': 'gray N (N: 0..15, decimal)',
    'absolute_difference_2bit_v1': 'difference A B (A, B: 0..3)',
    'mux_2bit_v1': 'select A B if S (A, B: 0..3; S: 0..1)',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def require_unchanged(bindings):
    for path, expected in bindings.items():
        if not Path(path).is_file() or sha(path) != expected:
            raise ValueError('query dependency changed: ' + path)


def _read(path, maximum):
    if path.stat().st_size > maximum:
        raise ValueError('query artifact byte bound')
    raw = path.read_bytes()
    if len(raw) > maximum:
        raise ValueError('query artifact byte bound')
    return raw


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _verified_capability(capsule, descriptor, profile):
    identity = profile['profile_id']
    admission = descriptor['knowledge_admission']
    source = admission['source']
    if (source.get('kind') != 'independent-integer-specification' or
            source.get('reference') != identity + ': ' + profile['specification'] or
            source.get('input_labels') != profile['input_labels'] or
            source.get('output_labels') != profile['output_labels'] or
            (capsule['input_bits'], capsule['output_bits']) != (profile['input_bits'], profile['output_bits'])):
        raise ValueError('source specification, labels or interface do not match the declared profile')
    for field in ('frozen_oracle_sha256', 'specification_adapter_sha256'):
        if not _digest(source.get(field)):
            raise ValueError('missing source specification digest: ' + field)
    teacher = source.get('teacher_proposal')
    if not isinstance(teacher, dict):
        raise ValueError('missing retained teacher proposal provenance')
    for field in ('model_artifact_sha256', 'prompt_sha256', 'response_sha256', 'run_sha256'):
        if not _digest(teacher.get(field)):
            raise ValueError('missing teacher provenance digest: ' + field)
    if (not isinstance(teacher.get('model_repo'), str) or
            re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', teacher['model_repo']) is None or
            teacher.get('model_revision_status') != 'pinned_huggingface_commit' or
            not isinstance(teacher.get('model_revision'), str) or
            re.fullmatch(r'[0-9a-f]{40}', teacher['model_revision']) is None):
        raise ValueError('teacher repository revision is not pinned')
    for field in ('response_path', 'run_path'):
        if not isinstance(teacher.get(field), str) or not 1 <= len(teacher[field]) <= 4096:
            raise ValueError('missing bounded retained evidence path: ' + field)
    oracle_id = admission.get('oracle_id')
    if (not isinstance(oracle_id, str) or
            re.fullmatch(re.escape(identity) + r':(?:response|expression-response):[0-9]{1,6}', oracle_id) is None):
        raise ValueError('oracle identity is not bound to the declared profile')
    cases = []
    for value in range(1 << profile['input_bits']):
        expected = scalar_oracle(identity, value)
        actual = evaluate(capsule, value)
        if actual != expected:
            raise ValueError(f'full-domain mismatch at {value}: expected {expected}, got {actual}')
        cases.append({'input': value, 'output': expected})
    oracle = dict(id=oracle_id, kind='fixed-domain-oracle', independent_of_candidate=True,
                  input_bits=profile['input_bits'], output_bits=profile['output_bits'], source=source, cases=cases)
    if hashlib.sha256(canonical(oracle)).hexdigest() != admission.get('oracle_record_sha256'):
        raise ValueError('admission oracle digest differs from reconstructed independent specification')
    circuit = dict(input_bits=capsule['input_bits'], output_bits=capsule['output_bits'],
                   constant_zero_wire=capsule['input_bits'], gates=[list(gate) for gate in capsule['gates']],
                   outputs=capsule['outputs'])
    if semantic_signature(circuit) != admission.get('semantic_sha256'):
        raise ValueError('admission semantic digest differs from verified function')
    return dict(profile_id=identity, command=COMMANDS[identity], specification=profile['specification'],
                input_bits=profile['input_bits'], output_bits=profile['output_bits'],
                input_labels=profile['input_labels'], output_labels=profile['output_labels'],
                program_id=capsule['id'], version=capsule['version'], seed_hex=capsule['seed_hex'],
                content_sha256=capsule['content_sha256'], gate_count=capsule['gate_count'],
                verified_domain_cases=len(cases), oracle_record_sha256=admission['oracle_record_sha256'],
                semantic_sha256=admission['semantic_sha256'], source=copy.deepcopy(source),
                evidence_status='manifest references retained teacher evidence; source origin not authenticated by query execution')


def load_registry(bank_path):
    bank_path = Path(bank_path).resolve()
    manifest_path = bank_path.parent / 'manifest.json'
    bank_raw, manifest_raw = _read(bank_path, MAX_BANK_BYTES), _read(manifest_path, MAX_MANIFEST_BYTES)
    manifest = json.loads(manifest_raw)
    bindings = {str(bank_path): hashlib.sha256(bank_raw).hexdigest(),
                str(manifest_path): hashlib.sha256(manifest_raw).hexdigest()}
    sources = ['python/knowledge_queries.py', 'python/teacher_knowledge.py', 'python/knowledge_admission.py',
               'python/program_bank.py', 'python/program_bank_reference.py']
    bindings.update({str(ROOT / name): sha(ROOT / name) for name in sources})
    bank = decode_bank(bank_path, manifest_path)
    known = {p['profile_id']: p for p in profiles()}
    capabilities, rejected = [], []
    for capsule, descriptor in zip(bank['capsules'], manifest['capsules']):
        admission = descriptor.get('knowledge_admission')
        source = admission.get('source') if isinstance(admission, dict) else None
        reference = source.get('reference') if isinstance(source, dict) else None
        identity = reference.split(': ', 1)[0] if isinstance(reference, str) else None
        if identity not in known:
            continue  # Names alone never establish a typed knowledge capability.
        try:
            capabilities.append(_verified_capability(capsule, descriptor, known[identity]))
        except (KeyError, TypeError, ValueError) as error:
            rejected.append(dict(program_id=capsule['id'], profile_id=identity, reason=str(error)))
    require_unchanged(bindings)
    return dict(schema='atomos-typed-knowledge-registry-v1', status='verified_finite_registry',
                bank_path=str(bank_path), bank=bank, bindings=bindings, capabilities=capabilities,
                rejected_capabilities=rejected,
                scope='six finite integer profiles only; capability enumeration performs CPU verification, no GPU execution')


def public_registry(registry):
    return {key: copy.deepcopy(value) for key, value in registry.items() if key != 'bank'}


def unknown(query, reason):
    return dict(schema='atomos-typed-knowledge-query-v1', status='unknown', reason=reason,
                query=query if isinstance(query, str) and len(query) <= MAX_QUERY_CHARACTERS else None,
                gpu_execution='not_run', answer=None)


def parse_query(query):
    if not isinstance(query, str) or not 1 <= len(query) <= MAX_QUERY_CHARACTERS:
        return unknown(query, 'query_length_or_type')
    normalized = ' '.join(query.lower().split())
    number = r'(-?[0-9]{1,3})'
    forms = [(rf'add one-bit {number} {number} carry {number}', 'full_adder_1bit_v1', [1, 1, 1]),
             (rf'gray {number}', 'binary_to_gray_4bit_v1', [15]),
             (rf'compare {number} {number}', 'unsigned_compare_2bit_v1', [3, 3]),
             (rf'add {number} {number}', 'unsigned_add_2bit_v1', [3, 3]),
             (rf'difference {number} {number}', 'absolute_difference_2bit_v1', [3, 3]),
             (rf'select {number} {number} if {number}', 'mux_2bit_v1', [3, 3, 1])]
    for pattern, identity, maxima in forms:
        match = re.fullmatch(pattern, normalized)
        if match is None:
            continue
        args = [int(text) for text in match.groups()]
        if any(not 0 <= value <= maximum for value, maximum in zip(args, maxima)):
            return unknown(query, 'out_of_domain')
        if identity == 'full_adder_1bit_v1':
            packed = args[0] | (args[1] << 1) | (args[2] << 2)
            inputs = dict(a=args[0], b=args[1], carry_in=args[2])
        elif identity == 'binary_to_gray_4bit_v1':
            packed, inputs = args[0], dict(binary=args[0])
        else:
            packed, inputs = args[0] | (args[1] << 2), dict(a=args[0], b=args[1])
            if identity == 'mux_2bit_v1':
                packed |= args[2] << 4
                inputs['select_b'] = args[2]
        return dict(schema='atomos-typed-knowledge-query-v1', status='parsed', query=query,
                    profile_id=identity, packed_input=packed, typed_input=inputs)
    return unknown(query, 'unsupported_command')


def plan_query(registry, query):
    plan = parse_query(query)
    if plan['status'] == 'unknown':
        return plan
    available = [cap for cap in registry['capabilities'] if cap['profile_id'] == plan['profile_id']]
    if not available:
        return unknown(query, 'capability_unavailable_in_verified_bank')
    capability = min(available, key=lambda cap: cap['program_id'])
    plan.update(status='ready_for_native_verification', capability=copy.deepcopy(capability),
                expected_output=scalar_oracle(plan['profile_id'], plan['packed_input']), gpu_execution='not_run')
    return plan


def decode_answer(plan, output):
    if type(output) is not int or output != plan['expected_output']:
        raise ValueError('native output disagrees with independently checked typed query')
    identity, inputs = plan['profile_id'], plan['typed_input']
    if identity == 'full_adder_1bit_v1':
        result = dict(sum=output & 1, carry_out=(output >> 1) & 1, total=output)
        answer = f"{inputs['a']} + {inputs['b']} + carry {inputs['carry_in']} = {output}; sum bit {output & 1}, carry {(output >> 1) & 1}."
    elif identity == 'binary_to_gray_4bit_v1':
        result = dict(gray_decimal=output, gray_bits=f'{output:04b}')
        answer = f"Binary integer {inputs['binary']} maps to Gray code {output:04b} ({output})."
    elif identity == 'unsigned_compare_2bit_v1':
        result = dict(less=bool(output & 1), equal=bool(output & 2), greater=bool(output & 4))
        relation = '<' if result['less'] else '=' if result['equal'] else '>'
        answer = f"{inputs['a']} {relation} {inputs['b']}."
    elif identity == 'unsigned_add_2bit_v1':
        result, answer = dict(sum=output), f"{inputs['a']} + {inputs['b']} = {output}."
    elif identity == 'absolute_difference_2bit_v1':
        result, answer = dict(absolute_difference=output), f"The absolute difference is {output}."
    elif identity == 'mux_2bit_v1':
        result, answer = dict(selected=output), f"Selected {'B' if inputs['select_b'] else 'A'}: {output}."
    else:
        raise ValueError('unsupported typed result')
    return dict(typed_output=result, answer=answer)
