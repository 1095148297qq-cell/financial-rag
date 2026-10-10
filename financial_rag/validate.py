"""Audit corpus completeness and source-to-chunk fidelity without model calls."""
import json
import numpy as np
from .paths import MANIFEST, PROCESSED, INDEX, OUTPUT

def main():
    reports=json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert len(reports)==24 and len({r['company'] for r in reports})==12
    assert all({r['year'] for r in reports if r['company']==name}=={2024,2025} for name in {r['company'] for r in reports})
    chunks=json.loads((INDEX/'chunks.json').read_text(encoding='utf-8'))
    assert len({c['id'] for c in chunks})==len(chunks)
    assert all(all(k in c for k in ['company','year','chapter','page','url','id','text']) for c in chunks)
    facts=json.loads((OUTPUT/'financial_facts.json').read_text(encoding='utf-8'))
    for fact in facts:
        page=[c for c in chunks if c['company']==fact['company'] and c['year']==fact['year'] and c['page']==fact['page']]
        source='\n'.join(c['text'] for c in page)
        assert fact['metrics']['revenue']['current'] in source, (fact['company'],fact['year'],'revenue missing')
        assert fact['metrics']['net_profit']['current'] in source, (fact['company'],fact['year'],'net profit missing')
    vectors=np.load(INDEX/'vectors.npy',mmap_mode='r')
    assert vectors.shape==(len(chunks),512)
    assert np.all(np.isfinite(vectors))
    assert np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-4)
    summary={'reports':len(reports),'companies':12,'pages':sum(r['pages'] for r in reports),
        'chunks':len(chunks),'table_chunks':sum(c['kind']=='table_row' for c in chunks),
        'vector_dimensions':vectors.shape[1],'primary_financial_page_audits':len(facts),'status':'passed'}
    summary['index_version']=json.loads((INDEX/'version.json').read_text(encoding='utf-8'))['extraction_version']
    (OUTPUT/f"validation_{summary['index_version']}.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()
