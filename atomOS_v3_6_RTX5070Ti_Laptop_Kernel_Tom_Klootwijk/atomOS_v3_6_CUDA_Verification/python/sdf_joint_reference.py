"""Independent causal reference for the declared joint SDF/NOR/lineage profile.

This is a finite-prefix model. Program logic uses an independent sparse tape;
geometric children use signed integer deck coordinates and set-based occupancy.
It does not assert that all named source operators have scalar SDF definitions.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from universal_reference import (I64_MIN, I64_MAX, initial_state, pack_state,
    read_packed, read_program, parse_program)
from sdf_nor_reference import (table_output, equal, integer, sha256, csv_rows,
    verify_compiler, boolean_wires, decode, gate_site, GATE_HEADER, DECODED)
from sdf_lineage_reference import (canonical, emission, proposals, filter_words,
    frontier_file, rows as read_rows, near, LEAF, BRANCH, DIAGNOSTIC, U32, U64)
from sdf_atlas import verify_atlas, PLANES
from reference import TAU, observe, bank, address


def initial_joint(program, atlas, *, seed_id=1, seed_live=1, seed_row=0,
                  seed_angle=0, q_initial=0):
    row, angle, _ = canonical(seed_row, seed_angle, atlas['rows'], atlas['angles'])
    frontier = [dict(id=seed_id, row=row, angle=angle)] if seed_live else []
    return dict(machine=initial_state(program), frontier=frontier,
                words=emission(frontier, atlas['rows'], atlas['angles']),
                q=[q_initial] * (atlas['rows'] * atlas['words_per_row']))


def causal_step(program, atlas, state, decoded, *, origin, cells, phi_base,
                max_frontier, j, k, diagnostic_profile='source', word_fault=False):
    """Propose one joint step without modifying any input state.

    The caller supplies the already evaluated controller outputs, so both a
    correct table output and an explicitly injected circuit result can be replayed.
    A refused step returns no candidate; all three state domains stay unchanged.
    """
    machine = state['machine']
    if decoded['halt_current']:
        return dict(stop='halted', candidate=None)
    if not decoded['defined']:
        return dict(stop='missing_rule', candidate=None)
    if (not 0 <= decoded['next'] < program.states or
        not 0 <= decoded['write'] < program.alphabet or abs(decoded['move']) > 1):
        return dict(stop='invalid', candidate=None)
    destination = machine['head'] + decoded['move']
    if not I64_MIN <= destination <= I64_MAX or not origin <= destination < origin + cells:
        return dict(stop='tape_range', candidate=None)
    phi_steps = phi_base * (1 + decoded['write'])
    if phi_steps > (1 << 32) - 1:
        return dict(stop='hinge_overflow', candidate=None)
    if any(leaf['id'] > U64 // 2 for leaf in state['frontier']):
        return dict(stop='lineage_overflow', candidate=None)
    if 2 * len(state['frontier']) > max_frontier:
        return dict(stop='frontier_cap', candidate=None)
    children = proposals(state['frontier'], atlas['rows'], atlas['angles'],
                         phi_steps, diagnostic_profile)
    emitted = emission(children, atlas['rows'], atlas['angles'])
    filtered = filter_words(emitted, atlas, j, k, state['q'])
    if word_fault:
        filtered[0]['output'] ^= 1
    words = [record['output'] for record in filtered]
    frontier = []
    for child in children:
        word = words[child['row'] * atlas['words_per_row'] + child['angle'] // 32]
        child['admitted'] = (word >> (child['angle'] % 32)) & 1
        if child['admitted']:
            frontier.append({key: child[key] for key in LEAF})
    tape = dict(machine['tape'])
    if decoded['write']:
        tape[machine['head']] = decoded['write']
    else:
        tape.pop(machine['head'], None)
    candidate = dict(machine=dict(control=decoded['next'], head=destination, tape=tape),
                     frontier=frontier, words=words,
                     q=[record['q_after'] for record in filtered])
    transition = dict(control_before=machine['control'], head_before=machine['head'],
        read=machine['tape'].get(machine['head'], 0), write=decoded['write'], move=decoded['move'],
        control_after=decoded['next'], head_after=destination)
    return dict(stop='halted' if decoded['halt_after'] else 'running', candidate=candidate,
                phi_steps=phi_steps, children=children, emitted=emitted,
                filtered=filtered, transition=transition)


def simulate_joint(program, atlas, *, budget, origin, cells, phi_base,
                   max_frontier, j=0, k=0, diagnostic_profile='source', **seed):
    state = initial_joint(program, atlas, **seed)
    steps, evaluations = [], []
    stop = 'running'
    if not origin <= state['machine']['head'] < origin + cells:
        return dict(state=state, steps=steps, evaluations=evaluations, stop='tape_range')
    while True:
        machine = state['machine']
        symbol = machine['tape'].get(machine['head'], 0)
        decoded = table_output(program, machine['control'], symbol)
        evaluations.append(dict(control=machine['control'], head=machine['head'], read=symbol, **decoded))
        if decoded['halt_current']:
            stop = 'halted'
            break
        if len(steps) >= budget:
            break
        result = causal_step(program, atlas, state, decoded, origin=origin, cells=cells,
            phi_base=phi_base, max_frontier=max_frontier, j=j, k=k,
            diagnostic_profile=diagnostic_profile)
        stop = result['stop']
        if result['candidate'] is None:
            break
        steps.append(dict(before=state, **result))
        state = result['candidate']
        if stop == 'halted' or len(steps) >= budget:
            break
    return dict(state=state, steps=steps, evaluations=evaluations, stop=stop)


def search_path(frontier, key):
    """Independently traverse an implicit balanced BST of sorted lineage IDs."""
    low, high, visited, found = 0, len(frontier), [], U32
    while low < high:
        middle = (low + high) // 2
        visited.append(middle)
        value = frontier[middle]['id']
        if value == key:
            found = middle
            break
        if value < key:
            low = middle + 1
        else:
            high = middle
    if len(visited) > 32:
        raise ValueError('search exceeds declared finite capacity')
    return dict(found=found, visits=len(visited), overflow=0,
                **{f'path{i}': visited[i] if i < len(visited) else U32 for i in range(33)})


def verify_diagnostics(path, children, profile, interval):
    """Recompute lifted OTAN2 values and all six probes, preserving missingness."""
    optional = ['beta', 'raw', 'principal', 'line'] + [f'check{i}_error' for i in range(6)]
    records = read_rows(path, DIAGNOSTIC,
        optional + ['delta_rho', 'delta_phi', 'alpha', 'interval'], optional)
    equal(len(records), len(children), 'one diagnostic per proposed child')
    for record, child in zip(records, children):
        equal(record['id'], child['id'], 'diagnostic lineage association')
        for key, value in dict(delta_rho=0.0, delta_phi=child['delta_phi'], alpha=0.0, interval=interval).items():
            near(record[key], value, 'lifted diagnostic ' + key)
        sample = dict(dr=0.0, dp=child['delta_phi'], alpha=0.0, interval=interval,
                      profile=int(profile == 'directed'), axis_known=1, frame_known=1, increment_known=1)
        result = observe(sample)
        for key in ('status', 'beta_status'):
            equal(record[key], result[key], 'OTAN2 ' + key)
        for key in ('beta', 'raw', 'principal', 'line'):
            near(record[key], result[key], 'OTAN2 ' + key)
        for index, probe in enumerate(bank(sample, result)):
            for key in ('state', 'reason'):
                equal(record[f'check{index}_{key}'], probe[key], 'invariant ' + key)
            near(record[f'check{index}_error'], probe['error'], 'invariant error')
    return len(records)


def joint_payload_bytes(*, stored_words, logical_words, gates, outputs, wires,
                        budget, capacity, cells, bits):
    """Actual CUDA arrays including full immutable history and terminal records."""
    evaluations = max(1, budget)
    snapshots = budget + 1
    return dict(operator_texture=16 * stored_words, gates=8 * gates,
        outputs=4 * outputs, wires=4 * wires,
        tape_snapshots=4 * snapshots * ((cells * bits + 31) // 32),
        bank_snapshots=8 * snapshots * logical_words,
        frontier_snapshots=16 * snapshots * capacity,
        gate_trace=36 * evaluations * gates, step_trace=120 * evaluations,
        branch_trace=48 * budget * capacity,
        diagnostic_trace=136 * budget * capacity,
        admission_trace=4 * budget * capacity,
        word_trace=60 * budget * logical_words,
        search_trace=152 * budget * (capacity + 2), result=80)


WORD_HEADER = ('lane emitted q_before texel asa_mask na_mask boundary_mask fringe_mask '
               'produced asa na hits output q_after blend blend_known').split()
SEARCH_HEADER = 'index key found visits overflow'.split() + [f'path{i}' for i in range(33)]


def verify_export(directory, *, expected=None):
    """Replay every actual proposal and independently decide atomic publication.

    A declared fault has a separate actual-state replay. It must diverge from the
    correct computation and roll back tape, lineage, word bank and time together.
    Process execution and CUDA provenance are bound separately by the study runner.
    """
    directory = Path(directory)
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    metadata = dict(schema='atomOS-sdf-joint-v1',
        profile='new-finite-NOR-controlled-Klein-lineage-v1', topology='klein_m1_angular_twist',
        operator_source='loaded-SDF-predicate-atlas', runtime_rule_table=False,
        controller_coupling='phi_steps = base_phi_steps * (1 + decoded.write)',
        empty_frontier_policy='continue controller and every word JK update',
        search_organization='sorted-array binary search / implicit balanced BST',
        child_ids='2*positive_parent_id+branch',
        collision_policy='admit every child ID whose packed cell survives',
        commit_scope='all verified earlier joint steps as one candidate prefix; verification failure restores initial state',
        kernel_launches=1, active_threads=1, block_threads=32,
        tape_addressing='nonaliasing signed logical addresses separate from immutable operator texture')
    for key, value in metadata.items():
        equal(summary.get(key), value, 'joint metadata ' + key)
    atlas = verify_atlas(directory / 'operators.atlas')
    equal(atlas['manifest']['profile'], 'nor_sites', 'declared new SDF profile')
    program = read_program(directory / 'program.atomos')
    circuit = json.loads((directory / 'circuit.json').read_text(encoding='utf-8'))
    truth_rows = verify_compiler(circuit, program)
    height, angles, words = atlas['rows'], atlas['angles'], atlas['words_per_row']
    if height < 2 or angles < 32 or angles % 32:
        raise ValueError('joint profile needs at least two rows and full words')
    pr, pw = (height + 7) // 8 * 8, (words + 7) // 8 * 8
    logical, stored = height * words, pr * pw
    gates, inputs = len(circuit['gates']), circuit['input_count']
    for key, value in dict(rows=height, angles=angles, words=words, padded_rows=pr,
        padded_words=pw, atlas_file_bytes=16 + 16 * logical,
        atlas_texture_bytes=16 * stored, control_bits=circuit['control_bits'],
        symbol_bits=program.bits, circuit_gates=gates, circuit_wires=inputs + gates).items():
        equal(summary.get(key), value, key)
    origin = integer(summary.get('origin'), 'tape origin', I64_MIN, I64_MAX)
    cells = integer(summary.get('cells'), 'tape cells', 1)
    if origin + cells - 1 > I64_MAX or any(not origin <= a < origin + cells for a in program.cells):
        raise ValueError('invalid signed tape extent/initial cell')
    budget = integer(summary.get('steps_budget'), 'step budget', high=U32)
    capacity = integer(summary.get('max_frontier'), 'frontier capacity', 1, U32 - 2)
    phi = integer(summary.get('base_phi_steps'), 'base hinge', high=U32)
    fill = integer(summary.get('tail_fill'), 'unused tape bit fill', high=U32)
    j, k, q_initial = [integer(summary.get(key), key, high=1) for key in ('j', 'k', 'q_initial')]
    layout, injection, profile = [summary.get(key) for key in ('layout', 'injection', 'diagnostic_profile')]
    if layout not in ('linear', 'morton8') or injection not in ('none', 'gate', 'word') or profile not in ('source', 'directed'):
        raise ValueError('unknown joint profile option')
    interval = summary.get('interval')
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
        raise ValueError('invalid positive observation interval')
    seed = summary.get('seed', {})
    seed_id = integer(seed.get('id'), 'seed ID', 1)
    seed_live = integer(seed.get('live'), 'seed presence', high=1)
    seed_row = integer(seed.get('lifted_row'), 'lifted seed row', I64_MIN, I64_MAX)
    seed_angle = integer(seed.get('lifted_angle'), 'lifted seed angle', I64_MIN, I64_MAX)
    sr, sa, parity = canonical(seed_row, seed_angle, height, angles)
    equal(seed, dict(id=seed_id, live=seed_live, lifted_row=seed_row, lifted_angle=seed_angle,
                    row=sr, angle=sa, parity=parity), 'exact canonical seed')
    if expected:
        mapping = dict(budget='steps_budget', phi_base='base_phi_steps')
        for key in ('layout', 'budget', 'origin', 'cells', 'phi_base', 'max_frontier',
                    'q_initial', 'j', 'k', 'diagnostic_profile', 'injection'):
            if key in expected:
                equal(summary.get(mapping.get(key, key)), expected[key], 'requested ' + key)
        near(interval, expected.get('interval', interval), 'requested interval')
        for key, value in dict(seed_id=seed_id, seed_live=seed_live, seed_row=seed_row, seed_angle=seed_angle).items():
            if key in expected:
                equal(value, expected[key], 'requested ' + key)
        if 'program' in expected:
            equal(program, parse_program(expected['program']), 'requested editable program')
        if 'atlas_sha256' in expected:
            equal(sha256(directory / 'operators.atlas'), expected['atlas_sha256'], 'requested atlas bytes')
        if 'atlas_manifest_sha256' in expected:
            equal(sha256(directory / 'operators.json'), expected['atlas_manifest_sha256'], 'requested scalar geometry manifest')
    options = dict(origin=origin, cells=cells, phi_base=phi, max_frontier=capacity,
                   j=j, k=k, diagnostic_profile=profile)
    seed_options = dict(seed_id=seed_id, seed_live=seed_live, seed_row=seed_row,
                        seed_angle=seed_angle, q_initial=q_initial)
    initial = initial_joint(program, atlas, **seed_options)
    correct_run = simulate_joint(program, atlas, budget=budget, **options, **seed_options)
    tape_count = (cells * program.bits + 31) // 32
    initial_packed = pack_state(initial['machine']['tape'], origin=origin, cells=cells,
        alphabet=program.alphabet, original_words=[fill] * tape_count)
    verified_snapshot_words = 0

    def snapshot(path, prefix, state):
        nonlocal verified_snapshot_words
        packed = pack_state(state['machine']['tape'], origin=origin, cells=cells,
                            alphabet=program.alphabet, original_words=initial_packed)
        equal(read_packed(path / (prefix + '_tape.u32le')), packed, 'complete packed tape including untouched/tail bits')
        equal(frontier_file(path / (prefix + '_frontier.csv'), height, angles),
              state['frontier'], 'every lineage ID and canonical cell')
        equal(list(csv_rows(path / (prefix + '_words.csv'), ['lane', 'word', 'q'])),
              [dict(lane=i, word=word, q=state['q'][i]) for i, word in enumerate(state['words'])],
              'complete canonical occupancy and JK bank')
        verified_snapshot_words += tape_count + logical

    snapshot(directory, 'before', initial)
    sites = [gate_site(g, height, angles, pw, layout) for g in range(gates)]
    masks = [[int(atlas['planes'][plane][row, word]) for plane in PLANES] for row, word, _, _ in sites]
    if any(value != [7, 7, 6, 7] for value in masks):
        raise ValueError('sampled atlas does not realize the declared NOR primitive')
    state, applied, evaluations, stop = initial, 0, 0, 'running'
    gate_faults = word_faults = children_checked = search_checked = word_checked = diagnostic_checked = odd_children = 0
    if not origin <= state['machine']['head'] < origin + cells:
        stop = 'tape_range'
    else:
        while True:
            step_dir = directory / f'step_{evaluations}'
            record = json.loads((step_dir / 'step.json').read_text(encoding='utf-8'))
            snapshot(step_dir, 'before', state)
            machine = state['machine']
            symbol = machine['tape'].get(machine['head'], 0)
            wires = [(machine['control'] >> bit) & 1 for bit in range(circuit['control_bits'])]
            wires += [(symbol >> bit) & 1 for bit in range(program.bits)] + [0]
            equal(decode(circuit, boolean_wires(circuit, machine['control'], symbol)),
                  table_output(program, machine['control'], symbol), 'actual-input compiler truth')
            trace = list(csv_rows(step_dir / 'gate_trace.csv', GATE_HEADER))
            equal(len(trace), gates, 'all actual gates exported')
            for gate, (left, right) in enumerate(circuit['gates']):
                a, b = wires[left], wires[right]
                output = int(not (a or b))
                if injection == 'gate' and evaluations == 0 and gate == 0:
                    output ^= 1
                    gate_faults += 1
                wires.append(output)
                _, _, texel, gate_parity = sites[gate]
                equal(trace[gate], dict(evaluation=evaluations, gate=gate, a=a, b=b, output=output,
                    texel=texel, parity=gate_parity, **dict(zip(PLANES, masks[gate]))),
                    'actual Boolean NOR / lifted Klein gate / scalar SDF operands')
            decoded = decode(circuit, wires)
            if decoded['halt_current']:
                result = dict(candidate=None, stop='halted')
            elif applied >= budget:
                result = dict(candidate=None, stop='running')
            else:
                result = causal_step(program, atlas, state, decoded, **options,
                    word_fault=injection == 'word' and applied == 0)
            did_apply = result['candidate'] is not None
            child = result.get('children', [])
            after = result['candidate'] if did_apply else state
            stop = result['stop']
            integer_fields = dict(evaluation=evaluations, step=applied, applied=did_apply, status=stop,
                machine={key: machine[key] for key in ('control', 'head')}, read=symbol,
                decoded=decoded, transition=result.get('transition'), before_count=len(state['frontier']),
                after_count=len(after['frontier']), children=len(child), phi_steps=result.get('phi_steps', 0),
                searches=len(child) + 2 if did_apply else 0)
            equal({key: value for key, value in record.items() if key not in ('time_before', 'time_candidate')},
                  integer_fields, 'exact chronological joint proposal')
            near(record.get('time_before'), applied * interval, 'proposal input time')
            near(record.get('time_candidate'), (applied + int(did_apply)) * interval, 'proposal time advancement')
            branches = read_rows(step_dir / 'branches.csv', BRANCH, ['delta_phi'])
            equal(len(branches), len(child), 'all proposed child IDs exported')
            for actual, intended in zip(branches, child):
                for key in BRANCH:
                    if key == 'delta_phi':
                        near(actual[key], intended[key], 'lifted child displacement')
                    else:
                        equal(actual[key], intended[key], 'Klein child / all-ID admission ' + key)
            diagnostic_checked += verify_diagnostics(step_dir / 'diagnostics.csv', child, profile, interval)
            word_records = list(csv_rows(step_dir / 'words.csv', WORD_HEADER))
            equal(len(word_records), logical if did_apply else 0, 'all word lanes including empty frontier')
            if did_apply:
                for lane, value in enumerate(result['filtered']):
                    row, word = divmod(lane, words)
                    plane_values = {key + '_mask': int(atlas['planes'][key][row, word]) for key in PLANES}
                    intended = dict(lane=lane, emitted=result['emitted'][lane], q_before=state['q'][lane],
                        texel=address(row, word, pw, layout), **plane_values,
                        produced=result['emitted'][lane], **value, blend=0, blend_known=0)
                    equal(word_records[lane], intended, 'whole-word absorption / explicit JK / loaded masks')
                if injection == 'word' and applied == 0:
                    word_faults += 1
            searches = list(csv_rows(step_dir / 'search.csv', SEARCH_HEADER))
            keys = [c['id'] for c in child] + [0, U64] if did_apply else []
            equal(len(searches), len(keys), 'search query extent')
            for index, key in enumerate(keys):
                equal(searches[index], dict(index=index, key=key, **search_path(after['frontier'], key)),
                      'all actual implicit BST midpoint visits and found/absent results')
            snapshot(step_dir, 'candidate', after)
            children_checked += len(child)
            odd_children += sum(c['parity'] for c in child)
            search_checked += len(keys)
            word_checked += len(word_records)
            state = after
            evaluations += 1
            if not did_apply:
                break
            applied += 1
            if stop == 'halted' or applied >= budget:
                break
    equal(sorted(p.name for p in directory.glob('step_*') if p.is_dir()),
          sorted(f'step_{i}' for i in range(evaluations)), 'no missing or extra evaluations')
    snapshot(directory, 'candidate', state)
    verified = gate_faults == 0 and word_faults == 0
    if verified:
        equal(state, correct_run['state'], 'independent complete correct candidate prefix')
        equal(stop, correct_run['stop'], 'independent terminal reason')
        equal(applied, len(correct_run['steps']), 'independent successful transition count')
        equal(evaluations, len(correct_run['evaluations']), 'independent evaluation count')
    completed = stop in ('running', 'halted')
    resource = stop in ('frontier_cap', 'lineage_overflow', 'hinge_overflow')
    status = 'rejected_verification' if not verified else 'passed' if completed else 'resource_refused' if resource else 'program_refused'
    committed = state if verified else initial
    committed_steps = applied if verified else 0
    snapshot(directory, 'committed', committed)
    for key, value in dict(candidate_verified=verified, run_completed=verified and completed,
        status=status, program_stop=stop, executed_steps=applied, evaluations=evaluations,
        committed_steps=committed_steps, before_frontier_count=len(initial['frontier']),
        candidate_frontier_count=len(state['frontier']), committed_frontier_count=len(committed['frontier'])).items():
        equal(summary.get(key), value, 'publication ' + key)
    for name, value in (('before', initial), ('candidate', state), ('committed', committed)):
        equal(summary.get(name), {key: value['machine'][key] for key in ('control', 'head')}, 'publication machine ' + name)
    for key, value in dict(time_before=0, time_candidate=applied * interval,
                           time_committed=committed_steps * interval).items():
        near(summary.get(key), value, 'joint transaction ' + key)
    marker = 'REJECTED' if not verified else 'COMMITTED' if completed else 'PREFIX_VERIFIED'
    equal([name for name in ('COMMITTED', 'PREFIX_VERIFIED', 'REJECTED') if (directory / name).is_file()],
          [marker], 'unambiguous joint transaction marker')
    # The native audit stops once an expected controller record is absent. Its
    # reference-stop field therefore describes this auditable prefix, not a claim
    # that an injected candidate executed the entire independent correct run.
    native_evals = min(evaluations, len(correct_run['evaluations']))
    native_steps = correct_run['steps'][:native_evals]
    native_stop = correct_run['stop'] if native_evals == len(correct_run['evaluations']) else native_steps[-1]['stop'] if native_steps else 'running'
    equal(summary.get('reference_stop'), native_stop, 'native auditable correct-prefix stop')
    native = summary.get('verification', {})
    for key, value in dict(passed=verified, gates_checked=native_evals * gates,
        words_checked=len(native_steps) * logical,
        children_checked=sum(len(s['children']) for s in native_steps),
        searches_checked=sum(len(s['children']) + 2 for s in native_steps)).items():
        equal(native.get(key), value, 'native verification coverage ' + key)
    integer(native.get('checks'), 'native assertions counted', 1)
    checksum = [0] * 4
    for index, plane in enumerate(PLANES):
        for value in atlas['planes'][plane].reshape(-1):
            checksum[index] ^= int(value)
    equal(summary.get('warm_checksum'), checksum, 'every uploaded texel warm XOR')
    equal(summary.get('reread_checksum'), checksum, 'every uploaded texel reread XOR')
    integer(summary.get('sm_before'), 'launch SM')
    equal(summary.get('sm_after'), summary['sm_before'], 'same physical SM for warm/work/reread')
    reads = dict(warm=stored, gates=evaluations * gates, filter=applied * logical,
                 reread=stored, total=2 * stored + evaluations * gates + applied * logical)
    equal(summary.get('texture_reads'), reads, 'actual TEX request accounting')
    payload = joint_payload_bytes(stored_words=stored, logical_words=logical, gates=gates,
        outputs=len(circuit['outputs']), wires=inputs + gates, budget=budget, capacity=capacity,
        cells=cells, bits=program.bits)
    equal(summary.get('abi'), dict(gate=8, gate_trace=36, step_trace=120, result_trace=80,
        word_trace=60, search_trace=152, leaf=16, branch=48, diagnostic=136, state=8), 'pinned allocation ABI')
    equal(summary.get('device_payload_bytes'), sum(payload.values()), 'exact device array bytes')
    host_geometry = 48 * stored + 88 * logical
    equal(summary.get('host_geometry_bytes'), host_geometry, 'host geometry accounting')
    memory = integer(summary.get('memory_budget_bytes'), 'selected memory budget', 1)
    reserve = integer(summary.get('reserve_bytes'), 'device reserve')
    device = summary.get('device', {})
    free = integer(device.get('free_bytes_at_start'), 'available driver bytes', 1)
    integer(device.get('total_bytes'), 'total device bytes', free)
    if sum(payload.values()) + host_geometry > memory or memory + reserve > free:
        raise ValueError('payload/resource admission differs from declared memory contract')
    if expected and 'memory_mib' in expected:
        equal(memory, min(expected['memory_mib'] << 20, free - reserve), 'requested memory ceiling')
        equal(reserve, expected['reserve_mib'] << 20, 'requested device reserve')
    if stored > integer(device.get('max_texture_1d_linear'), 'device texture limit', 1):
        raise ValueError('texture exceeds declared hardware capacity')
    for key in ('runtime', 'driver', 'cc_major', 'cc_minor'):
        integer(device.get(key), 'device ' + key)
    if not isinstance(device.get('name'), str) or not device['name']:
        raise ValueError('missing actual device identity')
    for key in ('registers_per_thread', 'local_bytes_per_thread', 'static_shared_bytes'):
        integer(summary.get(key), key)
    duration = summary.get('kernel_ms')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
        raise ValueError('invalid actual event duration')
    return dict(status='passed', candidate_verified=verified, run_completed=verified and completed,
        rollback_verified=not verified, prefix_retained=verified and not completed,
        program_stop=stop, committed_steps=committed_steps, actual_transitions=applied,
        controller_evaluations=evaluations, gate_evaluations=evaluations * gates,
        compiler_truth_rows=truth_rows, injected_gate_faults_detected=gate_faults,
        injected_word_faults_detected=word_faults,
        odd_seam_gate_evaluations=sum(site[3] for site in sites) * evaluations,
        proposed_children=children_checked, odd_seam_children=odd_children,
        diagnostic_records=diagnostic_checked, word_records=word_checked, bst_searches=search_checked,
        packed_snapshot_words_verified=verified_snapshot_words,
        scalar_atlas_bits_verified=atlas['verified_bits'], device_payload_components=payload,
        device_payload_bytes=sum(payload.values()), texture_reads=reads,
        export_hashes={str(p.relative_to(directory)).replace('\\', '/'): sha256(p)
                       for p in sorted(directory.rglob('*')) if p.is_file()})
