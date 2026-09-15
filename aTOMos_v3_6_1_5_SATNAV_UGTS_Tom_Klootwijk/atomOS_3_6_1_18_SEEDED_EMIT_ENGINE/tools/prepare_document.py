#!/usr/bin/env python3
"""Verify R18 sources and authored TeX dependencies without rewriting any file."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
NAME = 'aTOMos_v3_6_1_18_Seeded_Emit_Engine_Tom_Klootwijk'
REQUIRED_CHAPTERS = (
    'seeded_emit.tex', 'phase32.tex', 'r18_evidence.tex', 'orbit_comparison.tex', 'spice_comparison.tex',
    'fused_execution.tex', 'fused_evidence.tex', 'wqk_integration.tex', 'wqk_events.tex', 'wqk_evidence.tex', 'hinge_core.tex',
    'spatial_calculus.tex', 'runtime_evidence.tex', 'resident_gpu.tex',
    'word_optimization.tex', 'word_profile.tex', 'exact_core.tex',
    'kernel_bridge.tex', 'physics_core.tex', 'physics_energy.tex',
    'physics_em.tex', 'unified_coupling.tex', 'field_step.tex',
    'gravity_time.tex', 'clock_binding.tex', 'physics_measurement.tex',
    'completion.tex', 'exact_registry.tex',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(base, relative):
    """Admit only an explicit relative path staying inside its declared root."""
    relative = Path(relative)
    if relative.is_absolute() or relative.drive or '..' in relative.parts:
        raise ValueError('Nonlocal bound path: ' + str(relative))
    result = (base / relative).resolve()
    if not result.is_relative_to(base.resolve()):
        raise ValueError('Bound path escapes its root: ' + str(relative))
    return result


def verify_item(base, item):
    path = contained(base, item['path'])
    if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
        raise ValueError('Bound source bytes differ: ' + str(path))
    return path


def verify_release_sources():
    binding = json.loads((ROOT / 'source/SOURCE_BINDING.json').read_text(encoding='utf-8'))
    if binding['version'] != '3.6.1.18':
        raise ValueError('Source binding does not identify R18')
    seen = set()
    for item in binding['inspected_or_adapted_sources']:
        if item['path'] in seen:
            raise ValueError('Duplicate inherited source binding: ' + item['path'])
        seen.add(item['path'])
        verify_item(ROOT.parent, item)
    parent_pdfs = 0
    for parent in binding['parents']:
        base = contained(ROOT.parent, parent['directory'])
        for item in parent['pdfs']:
            verify_item(base, item)
            parent_pdfs += 1
    imported = binding['external_imports']
    manifest_path = verify_item(ROOT, imported['manifest'])
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    entries = manifest['files']
    if len(entries) != 42 or len(entries) != imported['expected_files']:
        raise ValueError('The pinned WQK import must contain all 42 source files')
    vendor = contained(ROOT, imported['vendor_directory'])
    imported_paths = set()
    for item in entries:
        path = verify_item(vendor, item)
        if path in imported_paths:
            raise ValueError('Duplicate WQK import path: ' + item['path'])
        imported_paths.add(path)
    actual = {p.resolve() for p in vendor.rglob('*') if p.is_file()
              and '__pycache__' not in p.relative_to(vendor).parts and p.suffix != '.pyc'}
    if actual != imported_paths:
        raise ValueError('Vendor directory and pinned WQK file inventory differ')
    orbital = verify_orbit_evidence()
    return {'preserved_parent_pdfs': parent_pdfs,
            'preserved_source_files': len(seen), 'verified_wqk_imports': len(entries),
            'wqk_import_manifest_sha256': digest(manifest_path), **orbital}


def verify_orbit_evidence():
    """Bind the measured orbital chapters to their frozen sources and outputs."""
    folder = ROOT / 'review'
    protocol_path = folder / 'r18_orbit_protocol.json'
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    for item in protocol['frozen_inputs']:
        verify_item(ROOT.parent, {'path': item['file'], 'bytes': item['bytes'], 'sha256': item['sha256']})
    audit = json.loads((folder / 'r18_orekit_numerical_audit.json').read_text(encoding='utf-8'))
    expected = {period + '_' + satellite for period in ('jan', 'feb')
                for satellite in ('G05', 'C03', 'C06', 'CHANDRA')}
    if audit.get('complete') is not True or {c['case'] for c in audit['cases']} != expected:
        raise ValueError('Eight-case Orekit numerical audit is incomplete')
    for name, key in [('OrekitFrozenOrbit.java', 'adapter_sha256'), ('run_orekit_comparison.py', 'runner_sha256')]:
        if digest(ROOT / 'tools' / name) != audit[key]:
            raise ValueError('Audited orbital implementation differs: ' + name)
    for case in audit['cases']:
        for prefix, key in [('orekit_', 'standard_report_sha256'), ('orekit_tight_', 'tight_report_sha256')]:
            if digest(folder / 'orbit_comparison' / (prefix + case['case'] + '.json')) != case[key]:
                raise ValueError('Audited orbital state report differs')
    for name in ('matched_forecast_summary.json', 'matched_forecast_tight_summary.json'):
        scored = json.loads((folder / 'orbit_comparison' / name).read_text(encoding='utf-8'))
        if scored.get('complete_eight_case_scope') is not True or scored['protocol_sha256'] != digest(protocol_path):
            raise ValueError('Matched forecast scores have a different or partial protocol')
    spk_count = 0
    for report_name, validation_name in [('r18_spice_comparison.json', 'r18_spice_validation.json'),
                                         ('r18_spice_chandra_refinement.json', 'r18_spice_chandra_refinement_validation.json')]:
        path = folder / report_name
        report = json.loads(path.read_text(encoding='utf-8'))
        validation = json.loads((folder / validation_name).read_text(encoding='utf-8'))
        if (report.get('complete') is not True or validation['comparison_sha256'] != digest(path)
                or validation.get('all_reported_max_position_errors_reproduced_exactly') is not True):
            raise ValueError('SPICE comparison does not have matching replay evidence')
        for case in report['cases']:
            record = case['spk']
            verify_item(folder / 'r18_spice_data', {**record, 'path': Path(record['path']).name})
            spk_count += 1
    return {'orbital_frozen_inputs_verified': len(protocol['frozen_inputs']),
            'audited_orekit_state_reports': 2 * len(audit['cases']), 'verified_spice_spks': spk_count}


def tex_body(path):
    return re.sub(r'(?<!\\)%[^\n]*', '', path.read_text(encoding='utf-8'))


def document_dependencies():
    """Resolve literal input/include edges in the authored master, read-only."""
    docs = ROOT / 'docs'
    found, visiting = set(), set()

    def visit(path):
        if path in visiting:
            raise ValueError('Cyclic TeX input: ' + str(path))
        if path in found:
            return
        if not path.is_file():
            raise ValueError('Missing authored TeX input: ' + str(path))
        visiting.add(path)
        for value in re.findall(r'\\(?:input|include)\s*\{([^{}]+)\}', tex_body(path)):
            if any(token in value for token in ('\\', '#', '$')):
                raise ValueError('TeX dependency must have a literal path: ' + value)
            relative = Path(value)
            if not relative.suffix:
                relative = relative.with_suffix('.tex')
            # TeX is built with docs as cwd; relative inputs use that root.
            visit(contained(docs, relative))
        visiting.remove(path)
        found.add(path)

    visit((docs / 'unified.tex').resolve())
    missing = [name for name in REQUIRED_CHAPTERS if (docs / name).resolve() not in found]
    if missing:
        raise ValueError('Master omits required R18/inherited chapters: ' + ', '.join(missing))
    if '3.6.1.18' not in tex_body(docs / 'unified.tex'):
        raise ValueError('Authored master does not identify R18')
    return sorted(found)


def required_headings():
    headings = []
    for path in document_dependencies():
        name = path.relative_to(ROOT / 'docs').as_posix()
        body = tex_body(path)
        values = re.findall(r'\\section\*?\s*\{([^{}]+)\}', body)
        if name in REQUIRED_CHAPTERS and not values:
            raise ValueError('Required chapter has no literal section heading: ' + name)
        headings.extend({'chapter': name, 'heading': value} for value in values)
    return headings


def document_records():
    inputs = set(document_dependencies())
    for path in list(inputs):
        for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\s*\{([^{}]+)\}', tex_body(path)):
            if any(token in name for token in ('\\', '#', '$')):
                raise ValueError('Graphic dependency must have a literal path')
            image = contained(ROOT / 'docs', name)
            if not image.is_file():
                raise ValueError('Missing authored graphic input: ' + str(image))
            inputs.add(image)
    return [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
             'sha256': digest(p)} for p in sorted(inputs)]


def main():
    result = verify_release_sources()
    dependencies = document_dependencies()
    result.update({'purpose': 'Read-only source and authored-document verification',
                   'rewritten_files': 0,
                   'tex_inputs': [p.relative_to(ROOT).as_posix() for p in dependencies],
                   'required_section_headings': required_headings()})
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
