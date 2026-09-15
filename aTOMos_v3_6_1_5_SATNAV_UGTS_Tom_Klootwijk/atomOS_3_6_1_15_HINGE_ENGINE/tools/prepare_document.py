"""Bind the preserved R14 foundation into the editable R15 manuscript."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent / 'atomOS_3_6_1_14_UNIFIED_FIELD'
NAME = 'aTOMos_v3_6_1_15_Native_Hinge_Engine_Tom_Klootwijk'


def main():
    inherited = []
    for folder, names in {
        'formal': ['CLOCK_BINDING.md', 'GRAVITY_TIME.md', 'KERNEL_INTEGRATION.md',
                   'OPERATOR_CATALOG.md', 'PHYSICS_PROFILE.md', 'UNIFIED_COUPLING.md'],
        'source': ['ELECTROMAGNETIC_LAWS.md', 'ENERGY_AND_MECHANICS.md', 'MEASUREMENT_AND_CONSTANTS.md'],
        'docs': ['exact_core.tex', 'kernel_bridge.tex', 'physics_core.tex', 'physics_energy.tex',
                 'physics_em.tex', 'unified_coupling.tex', 'field_step.tex', 'gravity_time.tex',
                 'clock_binding.tex', 'physics_measurement.tex', 'exact_registry.tex'],
    }.items():
        for name in names:
            old, new = PARENT / folder / name, ROOT / folder / name
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, new)
            inherited.append(old)
    exact_core = ROOT / 'docs/exact_core.tex'
    body = exact_core.read_text(encoding='utf-8')
    body = body.replace('obligations. No new runtime, machine-checked proof, test, simulation or measured\nimprovement is asserted.',
                        'obligations. By this retained specification alone, no new runtime, machine-checked\nproof, test, simulation or measured improvement is asserted. R15 executable\nsubsets and their evidence are specified separately in the preceding chapters.')
    body = body.replace('These are the available reasoning-based improvements in this\nsubversion; execution and machine proof remain future obligations.',
                        'These are reasoning-based improvements in the retained XOP-R1 strategy\ncontract. Full XOP execution and machine proof remain future obligations;\nR15 implements and checks the explicitly named subsets.')
    exact_core.write_text(body, encoding='utf-8')
    for old in sorted((PARENT / 'source/clock_capture').rglob('*')):
        if old.is_file():
            new = ROOT / old.relative_to(PARENT)
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, new)
            inherited.append(old)
    preamble = (PARENT / 'docs/preamble.tex').read_text(encoding='utf-8')
    preamble = preamble.replace('3.6.1.14', '3.6.1.15').replace('Unified Field Formalization', 'Native Hinge Engine')
    preamble = preamble.replace('UNIFIED FIELD / R14', 'NATIVE HINGE ENGINE / R15')
    (ROOT / 'docs/preamble.tex').write_text(preamble, encoding='utf-8')
    for name in ['build_pdf.py', 'review_pdf.py', 'package_release.py']:
        source = (PARENT / 'tools' / name).read_text(encoding='utf-8')
        source = source.replace('aTOMos_v3_6_1_14_Unified_Field_Formalization_Tom_Klootwijk', NAME)
        source = source.replace('3.6.1.14', '3.6.1.15')
        source = source.replace('Compile the R14 formal document; this does not run the proposed algorithms.',
                                'Compile the R15 formal document; runtime evidence is collected separately.')
        source = source.replace('Publish the reviewed PDF and package source artifacts; no kernel is executed.',
                                'Publish the reviewed R15 PDF, source and separately collected runtime evidence.')
        source = source.replace('Document/source distribution integrity; no proposed kernel execution',
                                'Document/source and recorded runtime evidence distribution integrity')
        source = source.replace("'distribution'}", "'distribution', 'build'}")
        (ROOT / 'tools' / name).write_text(source, encoding='utf-8')
    def record(p):
        return {'path': p.relative_to(ROOT.parent).as_posix(), 'bytes': p.stat().st_size,
                'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    inherited.append(PARENT / 'source/SOURCE_BINDING.json')
    inherited += [ROOT.parent / 'atomOS_3_6_1_12_PHOTONIC_INTERFACE' / p for p in
                  ['source/embedded/Pasted markdown.md', 'docs/phi_source_audit.tex']]
    parent_pdfs = []
    for pdf in sorted((PARENT / 'output/pdf').glob('*.pdf')):
        item = record(pdf)
        item['path'] = pdf.relative_to(PARENT).as_posix()
        parent_pdfs.append(item)
    binding = {
        'version': '3.6.1.15',
        'parent_commit': '01a7f7d5af43ae32cf6df9adcb0d4acd8f0f38ec',
        'parents': [{'directory': PARENT.name, 'pdfs': parent_pdfs}],
        'inspected_or_adapted_sources': [record(p) for p in inherited],
        'source_clock': 'Immutable inherited NIST observation; no new live synchronization claim.',
        'execution': 'R15 correctness checks and S2 benchmarks authorized explicitly by the user.',
        'runtime_profiles': ['ATOMOS-HINGE-R1', 'R15 native spatial/word profiles'],
        'catalog_scope': 'Inherited XOP catalog remains a specification; the new executors implement explicitly bounded subsets.',
    }
    (ROOT / 'source/SOURCE_BINDING.json').write_text(json.dumps(binding, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
