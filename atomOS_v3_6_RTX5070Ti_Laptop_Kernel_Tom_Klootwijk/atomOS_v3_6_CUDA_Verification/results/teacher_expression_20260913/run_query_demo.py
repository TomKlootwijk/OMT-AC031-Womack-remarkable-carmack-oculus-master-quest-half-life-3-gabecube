"""Actual bounded query demonstration; no answer is accepted without native replay."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from query_knowledge import execute_query, load_registry, public_registry, save

def main():
    out = Path('C:/Users/Tom/.cache/ak1/expr_queries')
    out.mkdir(parents=True, exist_ok=False)
    bank = ROOT / 'results/teacher_expression_20260913/compilation/proposed/bank.bin'
    registry = public_registry(load_registry(bank))
    save(out / 'registry.json', registry)
    commands = ['add one-bit 1 0 carry 1', 'gray 11', 'select 2 1 if 0', 'select 2 1 if 1',
                'compare 2 3', 'add 2 3', 'difference 1 3', 'select 7 1 if 0',
                'Explain the causes of gravity']
    records = []
    for index, query in enumerate(commands):
        result = execute_query(bank=bank, query=query,
                               exe=ROOT / 'output/bin/program_bank_v1/atomos_program_bank.exe',
                               atlas=ROOT / 'results/sdf_klein_20260913/atlases/nor_8_256.atlas',
                               out=out / ('query_' + str(index)))
        if index < 4:
            assert result['status'] == 'answered' and result['gpu_execution'] == 'run_and_independently_verified'
        else:
            assert result['status'] == 'unknown' and result['answer'] is None
            assert result['gpu_execution'] == 'not_run' and not (out / ('query_' + str(index))).exists()
        save(out / ('result_' + str(index) + '.json'), result)
        records.append({key: result.get(key) for key in ('query', 'status', 'reason', 'answer', 'gpu_execution', 'typed_output')})
    report = dict(schema='atomos-actual-typed-query-demo-v1', status='passed', queries=records,
                  accepted_native_queries=4, explicit_unknown_queries=5,
                  scope='bounded command grammar over three actual admitted finite algorithms; no general language understanding')
    save(out / 'summary.json', report)
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
