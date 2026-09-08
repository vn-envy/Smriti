"""Root's read-only check of completed matched public-QA artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

parser = argparse.ArgumentParser()
parser.add_argument('left', type=Path)
parser.add_argument('right', type=Path)
parser.add_argument('--out', type=Path)
args = parser.parse_args()
artifacts = [json.loads(p.read_text()) for p in (args.left, args.right)]

for data in artifacts:
    assert data['status'] == 'complete', 'A benchmark is still pending or failed'
    rows = data['results']
    summary = data['summary']
    assert len(rows) == summary['requested'] == summary['completed']
    assert len({r['question_id'] for r in rows}) == len(rows)
    assert [r['question_id'] for r in rows] == data['selection']['question_ids']
    assert not any(r['errors'] for r in rows), 'Operational errors need manual review'
    assert summary['failures'] == summary['cleanup_failures'] == 0
    assert len(data['cleanup']) == len(rows)
    assert all(r['attempted'] and r['ok'] for r in data['cleanup'])
    assert summary['failure_inclusive_denominator'] == len(rows)
    assert all(type(r['correct']) is bool and type(r['unanswerable']) is bool for r in rows)
    correct = sum(r['correct'] for r in rows)
    assert correct == summary['correct']
    assert abs(summary['accuracy'] - correct / len(rows)) < 0.0001
    for name, unanswerable in [('answerable', False), ('abstention', True)]:
        group = [r for r in rows if r['unanswerable'] == unanswerable]
        hits = sum(r['correct'] for r in group)
        assert len(group) == summary[name + '_requested'] == summary[name + '_completed']
        assert hits == summary[name + '_correct']
        assert abs(summary[name + '_accuracy'] - hits / len(group)) < 0.0001

left, right = artifacts
assert left['dataset_sha256'] == right['dataset_sha256']
for key in ['question_ids', 'sample_ids', 'answerable_question_ids', 'abstention_question_ids']:
    assert left['selection'][key] == right['selection'][key], key
for key in ['models', 'budgets', 'embedding']:
    assert left['provenance'][key] == right['provenance'][key], key
assert left['summary']['benchmark'] == right['summary']['benchmark']

pair_counts = {'both_correct': 0, 'both_wrong': 0, 'left_only_correct': 0, 'right_only_correct': 0}
disagreements = []
for lrow, rrow in zip(left['results'], right['results']):
    for key in ['question_id', 'sample_id', 'question_type', 'question', 'gold', 'unanswerable']:
        assert lrow[key] == rrow[key], (lrow['question_id'], key)
    key = ('both_correct' if lrow['correct'] and rrow['correct'] else
           'both_wrong' if not lrow['correct'] and not rrow['correct'] else
           'left_only_correct' if lrow['correct'] else 'right_only_correct')
    pair_counts[key] += 1
    if lrow['correct'] != rrow['correct']:
        disagreements.append({
            'question_id': lrow['question_id'], 'question_type': lrow['question_type'],
            'unanswerable': lrow['unanswerable'], 'gold': lrow['gold'],
            'left_hypothesis': lrow['hypothesis'], 'right_hypothesis': rrow['hypothesis'],
            'left_recorded_correct': lrow['correct'], 'right_recorded_correct': rrow['correct'],
        })

report = {
    'status': 'root_completed_pair_integrity_verified',
    'captured_at_utc': datetime.now(timezone.utc).isoformat(),
    'benchmark': left['summary']['benchmark'],
    'artifacts': {label: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                  for label, path in [('left', args.left), ('right', args.right)]},
    'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'verified': ['Terminal complete artifacts', 'Unique selected IDs in identical order',
                 'Identical gold/question/type/abstention labels', 'Identical dataset hash',
                 'Identical reader/judge, embedding, and context budgets',
                 'Recomputed score and answerable/abstention partitions',
                 'Zero operational errors and all cleanup records successful'],
    'left_summary': left['summary'], 'right_summary': right['summary'],
    'pair_counts': pair_counts, 'disagreements': disagreements,
    'model_calls': 0, 'scores_changed': False,
    'limits': ['This verifies the recorded labels and counts, not the correctness of every judge decision.',
               'Scores describe the selected sample and pinned modes; they are not dataset-wide or universal rankings.',
               'Elapsed time is preserved but is not accepted as a controlled speed comparison.'],
}
if args.out:
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
print(json.dumps({'status': report['status'], 'benchmark': report['benchmark'],
                  'left_correct': left['summary']['correct'], 'right_correct': right['summary']['correct'],
                  'pair_counts': pair_counts}, indent=2))
