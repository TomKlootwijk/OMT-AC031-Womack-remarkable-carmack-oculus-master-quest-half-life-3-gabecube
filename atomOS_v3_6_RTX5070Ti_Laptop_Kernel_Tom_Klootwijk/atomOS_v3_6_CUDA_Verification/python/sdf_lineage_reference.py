"""Independent exported lineage replay; no native or CUDA helper is invoked.

Geometry uses Python signed divmod, occupancy uses sets of cells, whole-word
filtering uses the existing independent bit-set oracle. This establishes export
conformance; a runner separately retains actual process/GPU provenance.
"""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path
from reference import TAU, TOL, bit_core, observe, bank
from sdf_atlas import verify_atlas
from sdf_nor_reference import equal, integer, sha256

U32, U64 = (1 << 32) - 1, (1 << 64) - 1
LEAF = 'id row angle'.split()
BRANCH = 'id parent branch row angle parity delta_phi live diagnostic_status admitted'.split()
WORDS = 'row word before q_before emitted asa na hits output q_after reemitted committed committed_q'.split()
DIAGNOSTIC = 'id delta_rho delta_phi alpha interval status beta_status beta raw principal line'.split()
DIAGNOSTIC += [f'check{i}_{key}' for i in range(6) for key in ('state', 'reason', 'error')]


def rows(path, header, floats=(), optional=()):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        equal(reader.fieldnames, header, f'{path} header')
        result = []
        for row in reader:
            if None in row or None in row.values():
                raise ValueError('malformed row: ' + str(path))
            parsed = {}
            for key, text in row.items():
                if not text and key in optional:
                    value = None
                elif key in floats:
                    value = float(text)
                    if not math.isfinite(value):
                        raise ValueError('nonfinite CSV number')
                else:
                    value = int(text)
                parsed[key] = value
            result.append(parsed)
        return result


def near(a, b, label):
    if b is None:
        equal(a, None, label)
    elif type(a) not in (int, float) or not math.isfinite(a) or abs(a - b) > TOL:
        raise ValueError(f'{label}: {a!r} differs from {b!r}')


def canonical(row, angle, height, width):
    winding, angle = divmod(angle, width)
    row %= height
    return (height - 1 - row if winding % 2 else row), angle, winding % 2


def frontier_file(path, height, width):
    found = rows(path, LEAF)
    previous = 0
    for leaf in found:
        integer(leaf['id'], 'lineage ID', previous + 1, U64)
        integer(leaf['row'], 'radial cell', high=height - 1)
        integer(leaf['angle'], 'angular cell', high=width - 1)
        previous = leaf['id']
    return found


def emission(frontier, height, width):
    cells = {(leaf['row'], leaf['angle']) for leaf in frontier}
    word_count = (width + 31) // 32
    words = [0] * (height * word_count)
    for row, angle in cells:
        words[row * word_count + angle // 32] += 1 << (angle % 32)
    return words


def proposals(frontier, height, width, phi_steps, profile):
    children = []
    for parent in frontier:
        if parent['id'] > U64 // 2:
            raise OverflowError('lineage_overflow')
        for branch, direction in enumerate((1, -1)):
            row, angle, parity = canonical(parent['row'], parent['angle'] + direction * phi_steps, height, width)
            delta = direction * TAU * phi_steps / width
            status = 1 if phi_steps == 0 else 2 if profile == 'source' else 0
            children.append(dict(id=parent['id'] * 2 + branch, parent=parent['id'],
                branch=branch, row=row, angle=angle, parity=parity, delta_phi=delta,
                live=1, diagnostic_status=status))
    return children


def filter_words(emitted, atlas, j, k, q):
    height, width, count = atlas['rows'], atlas['angles'], atlas['words_per_row']
    output = []
    for row in range(height):
        for word in range(count):
            operands = [int(atlas['planes'][key][row, word]) for key in ('asa', 'na', 'boundary', 'fringe')]
            valid = (1 << min(32, width - word * 32)) - 1
            aa, nn, hits, y = bit_core(emitted[row * count + word], *operands[:3], valid, operands[3])
            old_q = q[row * count + word]
            next_q = (1 - old_q if k else 1) if j else (0 if k else old_q)
            output.append(dict(asa=aa, na=nn, hits=hits, output=y, q_after=next_q))
    return output


def verify_diagnostics(path, children, profile):
    optional = ['beta', 'raw', 'principal', 'line'] + [f'check{i}_error' for i in range(6)]
    floats = optional + ['delta_rho', 'delta_phi', 'alpha', 'interval']
    actual = rows(path, DIAGNOSTIC, floats, optional)
    equal(len(actual), len(children), 'diagnostic count')
    for record, child in zip(actual, children):
        equal(record['id'], child['id'], 'diagnostic lineage association')
        for key, value in dict(delta_rho=0.0, delta_phi=child['delta_phi'], alpha=0.0, interval=1.0).items():
            near(record[key], value, 'lifted diagnostic ' + key)
        sample = dict(dr=0.0, dp=child['delta_phi'], alpha=0.0, interval=1.0,
                      profile=int(profile == 'directed'), axis_known=1, frame_known=1, increment_known=1)
        expected = observe(sample)
        for key in ('status', 'beta_status'):
            equal(record[key], expected[key], 'OTAN2 ' + key)
        for key in ('beta', 'raw', 'principal', 'line'):
            near(record[key], expected[key], 'OTAN2 ' + key)
        for i, probe in enumerate(bank(sample, expected)):
            for key in ('state', 'reason'):
                equal(record[f'check{i}_{key}'], probe[key], 'diagnostic invariant ' + key)
            near(record[f'check{i}_error'], probe['error'], 'invariant error')
    return len(actual)


def verify_tree(path, frontier, root):
    nodes = rows(path / 'tree.csv', 'node key left right leaf'.split())
    equal(len(nodes), len(frontier), 'one search node per live ID')
    visited = set()
    def walk(index, low, high):
        if index == U32:
            return 0
        integer(index, 'search node index', high=len(nodes) - 1)
        if index in visited:
            raise ValueError('BST cycle/duplicate child')
        visited.add(index)
        node = nodes[index]
        equal(node['node'], index, 'BST node order')
        integer(node['key'], 'BST strict search order', low + 1, high - 1)
        integer(node['leaf'], 'BST leaf index', high=len(frontier) - 1)
        equal(frontier[node['leaf']]['id'], node['key'], 'BST key/leaf binding')
        left = walk(node['left'], low, node['key'])
        right = walk(node['right'], node['key'], high)
        if abs(left - right) > 1:
            raise ValueError('search tree is not height-balanced')
        return max(left, right) + 1
    walk(root, 0, U64 + 1)
    equal(len(visited), len(nodes), 'BST all nodes reachable')
    searches = rows(path / 'searches.csv', 'key found_leaf'.split())
    keys = [leaf['id'] for leaf in frontier]
    absent = 1
    while absent in set(keys):
        absent += 1
    equal([record['key'] for record in searches], keys + [0, absent], 'all existing and absent queries')
    expected_indices = {leaf['id']: i for i, leaf in enumerate(frontier)}
    for record in searches:
        expected = expected_indices.get(record['key'], U32)
        equal(record['found_leaf'], expected, 'GPU BST search result')
        current = root
        while current != U32:
            node = nodes[current]
            if node['key'] == record['key']:
                break
            current = node['left' if record['key'] < node['key'] else 'right']
        equal(U32 if current == U32 else nodes[current]['leaf'], expected, 'independent BST traversal')
    return len(searches)


def verify_export(directory, *, expected=None):
    path = Path(directory)
    summary = json.loads((path / 'summary.json').read_text(encoding='utf-8'))
    atlas = verify_atlas(path / 'operators.atlas')
    equal(summary.get('schema'), 'atomOS-sdf-lineage-v1', 'schema')
    equal(summary.get('topology'), 'klein_m1_angular_twist', 'mandatory topology')
    equal(summary.get('profile'), 'quantized-two-child-hinge-v1', 'hinge profile')
    if summary.get('layout') not in ('linear', 'morton8'):
        raise ValueError('unknown physical layout')
    height, width, count = atlas['rows'], atlas['angles'], atlas['words_per_row']
    pr, pw = (height + 7) // 8 * 8, (count + 7) // 8 * 8
    for key, value in dict(rows=height, angles=width, words=count, padded_rows=pr, padded_words=pw,
        atlas_file_bytes=16 + 16 * height * count, atlas_texture_bytes=16 * pr * pw).items():
        equal(summary[key], value, key)
    cap = integer(summary['max_frontier'], 'frontier capacity', 1, U32 - 256)
    budget = integer(summary['generations_requested'], 'generation budget', high=U32)
    phi = integer(summary['phi_hinge_angle']['steps'], 'lower-case phi steps', high=65536)
    near(summary['phi_hinge_angle']['radians'], TAU * phi / width, 'hinge radians')
    equal(summary['phi_hinge_angle']['parameterization'], 'exact angular-cell count; no continuous-angle quantization', 'hinge parameterization')
    profile = summary['diagnostic_profile']
    if profile not in ('source', 'directed'):
        raise ValueError('diagnostic profile')
    j, k, initial_q = [integer(summary[key], key, high=1) for key in ('j', 'k', 'q_initial')]
    seed = summary['seed']
    seed_id = integer(seed['id'], 'seed ID', 1)
    integer(seed['live'], 'seed live symbol', high=1)
    for key in ('lifted_row', 'lifted_angle'):
        integer(seed[key], key, -(1 << 63), (1 << 63) - 1)
    sr, sa, parity = canonical(seed['lifted_row'], seed['lifted_angle'], height, width)
    for key, value in dict(row=sr, angle=sa, parity=parity).items():
        equal(seed[key], value, 'canonical seed ' + key)
    if expected:
        for key in ('layout', 'max_frontier', 'generations_requested', 'diagnostic_profile', 'j', 'k', 'q_initial'):
            equal(summary[key], expected[key], 'invocation ' + key)
        equal(phi, expected['phi_steps'], 'invocation phi')
        equal(seed, dict(id=expected['seed_id'], live=expected['seed_live'], lifted_row=expected['seed_row'],
            lifted_angle=expected['seed_angle'], row=sr, angle=sa, parity=parity), 'invocation seed')
        equal(sha256(path / 'operators.atlas'), expected['atlas_sha256'], 'invocation atlas')
    payload = 16 * pr * pw + 264 * height * count + 240 * cap + 28
    equal(summary['device_payload_bytes'], payload, 'exact allocated payload')
    equal(summary['host_geometry_bytes'], 32 * pr * pw + 88 * height * count, 'host geometry payload')
    memory = integer(summary['memory_budget_bytes'], 'memory ceiling', 1)
    reserve = integer(summary['reserve_bytes'], 'device reserve')
    free = integer(summary['device']['free_bytes_at_start'], 'observed available device bytes')
    if payload > memory or summary['host_geometry_bytes'] > memory or memory + reserve > free:
        raise ValueError('resource admission metadata mismatch')
    if expected:
        equal(memory, min(expected['memory_mib'] << 20, free - reserve), 'selected memory ceiling')
        equal(reserve, expected['reserve_mib'] << 20, 'selected reserve')
    equal(summary['abi'], dict(leaf=16, branch=48, diagnostic=136, bst_node=24, lane=80, state=8, result=168), 'pinned ABI')
    frontier = [dict(id=seed_id, row=sr, angle=sa)] if seed['live'] else []
    equal(frontier_file(path / 'initial_frontier.csv', height, width), frontier, 'initial frontier')
    previous_words = emission(frontier, height, width)
    q = [initial_q] * (height * count)
    epochs = summary['epochs']
    equal(len(epochs), summary['generations_attempted'], 'attempt count')
    if len(epochs) > budget:
        raise ValueError('generation budget exceeded')
    committed = children_checked = admitted_total = odd_total = searches_total = diagnostics_checked = 0
    total_ms = 0.0
    final_status, stop = 'passed', 'generation_budget'
    for generation, record in enumerate(epochs):
        directory = path / f'generation_{generation}'
        equal(json.loads((directory / 'generation.json').read_text(encoding='utf-8')), record, 'generation receipt')
        equal(record['generation'], generation, 'chronological generation')
        equal(frontier_file(directory / 'before_frontier.csv', height, width), frontier, 'committed-prefix input')
        equal(record['before_count'], len(frontier), 'before ID count')
        if not frontier:
            raise ValueError('an extinct frontier executed another generation')
        refusal = 'lineage_overflow' if any(leaf['id'] > U64 // 2 for leaf in frontier) else 'frontier_cap' if 2 * len(frontier) > cap else None
        if refusal:
            for key, value in dict(accepted=False, status='resource_refused', resource_status=refusal,
                proposed_count=0, committed_count=len(frontier), gpu_executed=False, kernel_ms=0).items():
                equal(record[key], value, 'resource attempt ' + key)
            equal(frontier_file(directory / 'committed_frontier.csv', height, width), frontier, 'resource frontier rollback')
            for name in ('branches.csv', 'candidate_frontier.csv', 'words.csv', 'diagnostics.csv', 'tree.csv', 'searches.csv'):
                if (directory / name).exists():
                    raise ValueError('resource-refused generation fabricates GPU candidate records')
            equal(generation, len(epochs) - 1, 'stop after refused generation')
            final_status, stop = 'resource_refused', refusal
            break
        expected_children = proposals(frontier, height, width, phi, profile)
        emitted = emission(expected_children, height, width)
        filtered = filter_words(emitted, atlas, j, k, q)
        y = [word['output'] for word in filtered]
        candidate = []
        for child in expected_children:
            child['admitted'] = (y[child['row'] * count + child['angle'] // 32] >> (child['angle'] % 32)) & 1
            if child['admitted']:
                candidate.append({key: child[key] for key in LEAF})
        actual_children = rows(directory / 'branches.csv', BRANCH, ('delta_phi',))
        equal(len(actual_children), len(expected_children), 'every proposed child recorded')
        for actual, child in zip(actual_children, expected_children):
            near(actual.pop('delta_phi'), child['delta_phi'], 'child lifted hinge')
            equal(actual, {key: value for key, value in child.items() if key != 'delta_phi'}, 'child geometry/ID/admission')
        diagnostics_checked += verify_diagnostics(directory / 'diagnostics.csv', expected_children, profile)
        equal(frontier_file(directory / 'candidate_frontier.csv', height, width), candidate, 'all and only admitted IDs')
        equal(frontier_file(directory / 'committed_frontier.csv', height, width), candidate, 'verified frontier commit')
        equal(emission(candidate, height, width), y, 'admitted ID re-emission equals filtered words')
        expected_words = []
        for row in range(height):
            for word in range(count):
                i = row * count + word
                expected_words.append(dict(row=row, word=word, before=previous_words[i], q_before=q[i],
                    emitted=emitted[i], **filtered[i], reemitted=y[i], committed=y[i], committed_q=filtered[i]['q_after']))
        equal(rows(directory / 'words.csv', WORDS), expected_words, 'all texture-filtered words, JK bank and rollback fields')
        search_count = verify_tree(directory, candidate, record['tree_root'])
        odd = sum(child['parity'] for child in expected_children)
        for key, value in dict(accepted=True, status='passed', resource_status='ok', gpu_executed=True,
            proposed_count=len(expected_children), candidate_count=len(candidate), committed_count=len(candidate),
            odd_seam_children=odd, searches=search_count, texture_reads=height * count).items():
            equal(record[key], value, 'generation ' + key)
        equal(record['verification'], dict(geometry=True, diagnostics=True, words=True, admission=True, reemission=True, bst=True), 'native stage verification')
        times = [record[key + '_ms'] for key in ('geometry', 'prepare', 'filter', 'admission', 'search')]
        if any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times):
            raise ValueError('invalid recorded CUDA timing')
        near(record['kernel_ms'], sum(times), 'per-generation timing sum')
        total_ms += sum(times)
        committed += 1
        children_checked += len(expected_children)
        admitted_total += len(candidate)
        odd_total += odd
        searches_total += search_count
        frontier, previous_words, q = candidate, y, [word['q_after'] for word in filtered]
    if final_status == 'passed':
        if not frontier:
            stop = 'extinct'
        elif committed != budget:
            raise ValueError('live frontier stopped before its requested finite budget')
    equal(frontier_file(path / 'final_frontier.csv', height, width), frontier, 'final committed lineage state')
    equal(rows(path / 'final_words.csv', 'row word value q'.split()),
        [dict(row=r, word=w, value=previous_words[r * count + w], q=q[r * count + w]) for r in range(height) for w in range(count)], 'final occupancy and JK state')
    for key, value in dict(status=final_status, stop_reason=stop, all_executed_stages_verified=True,
        generations_committed=committed, final_frontier_count=len(frontier), children_proposed=children_checked,
        children_admitted=admitted_total, odd_seam_children=odd_total, bst_searches=searches_total,
        texture_reads=committed * height * count).items():
        equal(summary[key], value, 'final ' + key)
    near(summary['kernel_ms'], total_ms, 'whole-run kernel sum')
    marker = 'COMMITTED' if final_status == 'passed' else 'PREFIX_VERIFIED'
    if not (path / marker).is_file() or (path / ('PREFIX_VERIFIED' if marker == 'COMMITTED' else 'COMMITTED')).exists():
        raise ValueError('commit marker mismatch')
    return dict(status='passed', execution_status=final_status, stop_reason=stop,
        generations=committed, children=children_checked, diagnostics=diagnostics_checked,
        admitted_ids=admitted_total, searches=searches_total, words=committed * height * count,
        sdf_bits=atlas['verified_bits'])
