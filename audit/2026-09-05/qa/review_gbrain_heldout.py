"""Independently recompute the bounded retrieval comparison from source labels."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('gbrain', type=Path)
parser.add_argument('smriti', type=Path)
parser.add_argument('dataset', type=Path)
parser.add_argument('--out', type=Path)
args = parser.parse_args()
gbrain, smriti = [json.loads(p.read_text()) for p in (args.gbrain, args.smriti)]
source = {r['question_id']: r for r in json.loads(args.dataset.read_text())}
digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
assert gbrain['status'] == smriti['status'] == 'complete'
assert digest == gbrain['dataset']['sha256'] == smriti['dataset']['sha256']
ids = gbrain['dataset']['selected_question_ids']
assert ids == smriti['dataset']['selected_question_ids'] and len(ids) == len(set(ids)) == 20
assert gbrain['configuration']['budgets'] == smriti['configuration']['budgets']
assert gbrain['configuration']['budgets']['k'] == 5
assert gbrain['configuration']['embedding']['provider'] == 'ollama:nomic-embed-text:v1.5'
assert smriti['configuration']['embedding']['model'] == 'nomic-embed-text:v1.5'
assert gbrain['configuration']['embedding']['measured_dimensions'] == 768
assert smriti['run']['embedding_dimension_probe']['measured_dimensions'] == 768
for data in (gbrain, smriti):
    assert not data['failure_records'] and not data['cleanup_failure_records']
    assert [r['question_id'] for r in data['results']] == ids
    for key in ['requested', 'completed', 'failure_inclusive_denominator']:
        assert data['summary'][key] == len(ids)
    assert data['summary']['failures'] == data['summary']['cleanup_failures'] == 0

rows = []
for grow, srow in zip(gbrain['results'], smriti['results']):
    original = source[grow['question_id']]
    assert grow['question'] == srow['question'] == original['question']
    assert grow['session_count'] == srow['session_count'] == len(original['haystack_sessions'])
    assert grow['chunk_count'] == srow['chunk_count']
    assert not grow['unanswerable'] and not srow['unanswerable']
    document_sessions = []
    budgets = gbrain['configuration']['budgets']
    for sid, messages in zip(original['haystack_session_ids'], original['haystack_sessions']):
        rendered = '\n'.join(f"{m.get('role', 'user')}: {m['content']}"
                             for m in messages if m.get('content'))
        length = min(len(rendered), budgets['session_char_budget'])
        document_sessions.extend([sid] * len(range(0, length, budgets['chunk_char_budget'])))
    assert len(document_sessions) == grow['chunk_count']
    for hit in grow['hits']:
        index = int(hit['document_slug'].removeprefix('bench/public-'))
        assert hit['document_slug'] == f'bench/public-{index:08d}'
        assert document_sessions[index] == hit['session_id']
    stats, meta = grow['vector_stats'], grow['search_meta']
    assert stats['embedded_count'] == stats['chunk_count'] > 0
    assert stats['page_count'] == grow['chunk_count']
    assert meta['vector_enabled'] and not meta['degraded']
    assert not meta['expansion_applied']
    scores = {}
    variants = {'gbrain': (grow['hits'], grow['relevance'])}
    variants.update({k: (v['hits'], v) for k, v in srow['variants'].items()})
    for name, (hits, recorded) in variants.items():
        assert len(hits) <= 5
        assert all(h['session_id'] in original['haystack_session_ids'] for h in hits)
        returned = list(dict.fromkeys(h['session_id'] for h in hits))
        relevant = list(dict.fromkeys(original['answer_session_ids']))
        assert relevant
        coverage = set(returned).intersection(relevant)
        recall = len(coverage) / len(relevant)
        reciprocal = next((1 / (i + 1) for i, sid in enumerate(returned) if sid in relevant), 0)
        assert abs(recorded['recall_at_k'] - recall) < 0.0001
        assert abs(recorded['reciprocal_rank'] - reciprocal) < 0.0001
        scores[name] = {'recall_at_5_chunks': recall, 'deduplicated_session_reciprocal_rank': reciprocal}
    rows.append({'question_id': grow['question_id'], 'scores': scores})

means = {name: {metric: sum(r['scores'][name][metric] for r in rows) / len(ids)
                for metric in rows[0]['scores'][name]} for name in rows[0]['scores']}
for name, values in means.items():
    recorded = gbrain['summary']['gbrain'] if name == 'gbrain' else smriti['summary'][name]
    assert abs(recorded['mean_recall_at_k'] - values['recall_at_5_chunks']) < 0.0001
    assert abs(recorded['mean_reciprocal_rank'] - values['deduplicated_session_reciprocal_rank']) < 0.0001
report = {
    'status': 'root_source_labels_vectors_and_pair_counts_verified',
    'artifacts': {k: {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                  for k, p in [('gbrain', args.gbrain), ('smriti', args.smriti), ('dataset', args.dataset)]},
    'questions': len(ids), 'means': means, 'rows': rows,
    'limits': [
        'Raw-session retrieval coverage, not reader/judge answer accuracy.',
        'Reciprocal rank uses deduplicated session order within five returned chunks, not chunk rank.',
        'Smriti session diversity is opt-in; its default comparison is reported separately.',
        'Pinned local configurations and a selected twenty-question sample are not full-product rankings.',
        'GBrain graph enrichment, expansion and reranking are outside this raw-session track.',
        'Elapsed times were not controlled for a speed comparison.',
    ],
}
if args.out:
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
print(json.dumps({'status': report['status'], 'questions': len(ids), 'means': means}, indent=2))
