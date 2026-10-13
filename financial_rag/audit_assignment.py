"""Read-only assignment checks; optional official downloads, no model calls."""
import argparse
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import fitz
import numpy as np
import requests

from .paths import ROOT, MANIFEST, INDEX, OUTPUT, COMPANIES


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--online', action='store_true', help='Re-download 24 official PDFs for byte comparison')
    args = parser.parse_args()
    directory = OUTPUT / 'assignment_audit'
    directory.mkdir(parents=True, exist_ok=True)
    reports = json.loads(MANIFEST.read_text(encoding='utf-8'))
    chunks = json.loads((INDEX / 'chunks.json').read_text(encoding='utf-8'))
    questions = json.loads((ROOT / 'financial_rag/example_questions.json').read_text(encoding='utf-8'))
    assert len(reports) == 24 and len(COMPANIES) == 12
    source_checks = []
    identities = []
    for report in reports:
        data = (ROOT / report['local_file']).read_bytes()
        with fitz.open(stream=data, filetype='pdf') as doc:
            pages = [p.get_text(sort=True) for p in list(doc)[:12]]
            cover = ''.join(''.join(pages[:3]).split())
            assert len(doc) == report['pages'] and len(doc) >= 40
            assert str(report['year']) + '年' in cover
            assert '年度报告摘要' not in cover[:1800]
            record = {'report_id': report['report_id'], 'company': report['company'],
                      'year': report['year'], 'pages': len(doc), 'url': report['url'],
                      'manifest_hash_matches': sha(data) == report['sha256']}
            assert record['manifest_hash_matches']
            assert urlparse(report['url']).hostname == 'static.cninfo.com.cn'
            source_checks.append(record)
            if report['year'] == 2025:
                expected = '上海证券交易所' if report['code'].startswith('6') else '深圳证券交易所'
                found = None
                for i, text in enumerate(pages):
                    if '股票上市' not in text and '上市交易所' not in text:
                        continue
                    joined = ''.join(''.join(pages[i:i+2]).split())
                    if expected in joined and report['code'] in joined and report['company'] in joined:
                        found = {'company': report['company'], 'code': report['code'], 'exchange': expected,
                                 'source_url': report['url'], 'profile_pages': [i+1, min(i+2, len(doc))],
                                 'listing_disclosed': True}
                        break
                assert found, report['company']
                identities.append(found)
    assert len(identities) == 12
    assert all({r['year'] for r in reports if r['company'] == name} == {2024, 2025} for _, name in COMPANIES)
    report_map = {r['report_id']: r for r in reports}
    chunk_map = {c['id']: c for c in chunks}
    assert len(chunk_map) == len(chunks)
    for c in chunks:
        report = report_map[c['report_id']]
        assert c['company'] == report['company'] and c['year'] == report['year']
        assert c['chapter'] and 1 <= c['page'] <= report['pages'] and c['url'] == report['url']
        if c['kind'] == 'table_row':
            assert c['columns'] and c['rows']
            assert all(len(row['values']) == len(c['columns']) for row in c['rows']), c['id']
    vectors = np.load(INDEX / 'vectors.npy', mmap_mode='r')
    assert vectors.shape == (len(chunks), 512) and np.isfinite(vectors).all()
    assert (INDEX / 'bm25.pkl').is_file()
    assert len(questions) == 10 and sum(q['type'] == 'panoramic' for q in questions) >= 2
    evaluations = []
    for q in questions:
        record = json.loads((OUTPUT / 'evaluation_v4' / (q['id'] + '_hybrid_expanded.json')).read_text(encoding='utf-8'))
        review = record['manual_review']
        assert record['question'] == q['question'] and record['chunks'] and record['answer']
        assert isinstance(review['correct'], bool) and review['reason']
        assert all(c == chunk_map[c['id']] for c in record['chunks']), q['id']
        fingerprint = sha(json.dumps({k: record[k] for k in ['question', 'answer', 'chunks']},
                                     ensure_ascii=False, sort_keys=True).encode())
        assert fingerprint == review['evidence_sha256'], q['id']
        evaluations.append({'id': q['id'], 'question': q['question'], 'panoramic': q['type'] == 'panoramic',
                            'recalled_blocks': [c['id'] for c in record['chunks']],
                            'correct': review['correct'], 'reason': review['reason'],
                            'covered_companies': sorted({c['company'] for c in record['chunks']})})
    if args.online:
        response = requests.get('https://www.cninfo.com.cn/new/data/szse_stock.json', timeout=60)
        response.raise_for_status()
        catalog = {item['code']: item for item in response.json()['stockList']}
        for identity in identities:
            item = catalog.get(identity['code'])
            identity['current_catalog_match'] = bool(item and item.get('zwjc') == identity['company'])
            assert identity['current_catalog_match'], identity['company']

        def remote_check(record):
            response = requests.get(record['url'], timeout=(20, 100))
            response.raise_for_status()
            original = report_map[record['report_id']]
            record['remote_hash_matches'] = sha(response.content) == original['sha256']
            assert record['remote_hash_matches'], record['report_id']
            print(record['report_id'], 'official bytes match', flush=True)
            return record

        with ThreadPoolExecutor(max_workers=3) as pool:
            source_checks = list(pool.map(remote_check, source_checks))
    result = {'status': 'passed', 'online_verified': args.online, 'listed_companies': identities,
              'reports': source_checks, 'chunks': len(chunks), 'table_chunks': sum(c['kind'] == 'table_row' for c in chunks),
              'table_header_sources': dict(Counter(c.get('header_source') for c in chunks if c['kind'] == 'table_row')),
              'evaluations': evaluations, 'model_calls': 0,
              'limits': 'Source/structure and recorded-review integrity checks, not all-cell or general answer-accuracy certification. Historical evaluations do not score current automatic routing.'}
    (directory / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Assignment audit passed: 12 listed-company disclosures, 24 full reports, 10 intact reviewed records; no model calls.')


if __name__ == '__main__':
    main()
