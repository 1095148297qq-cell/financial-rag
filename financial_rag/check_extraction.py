"""Audit the repaired corpus against source rows and previously verified metrics."""
import json
from collections import Counter
import fitz
from .extract import numeric_data
from .paths import ROOT,PROCESSED,MANIFEST,OUTPUT

def normalize(s): return ''.join(str(s or '').split()).replace('−','-').replace('－','-')

def main():
    reports=json.loads(MANIFEST.read_text(encoding='utf-8'))
    files=sorted(PROCESSED.glob('*_v4.jsonl'))
    if len(files)!=len(reports): raise RuntimeError('v4 提取数量尚未齐全')
    chunks=[json.loads(line) for f in files for line in f.open(encoding='utf-8')]
    tables=[c for c in chunks if c['kind']=='table_row']
    wrong=[c['id'] for c in tables if any(numeric_data(v) for v in c['columns'][1:])]
    source=json.loads((OUTPUT/'report_accuracy_audit.json').read_text(encoding='utf-8'))
    metrics=[]
    for report in source['reports']:
        for m in report['key_metrics']:
            matches=[c for c in chunks if c['report_id']==report['report_id'] and c['page']==m['primary_page'] and normalize(m['value']) in normalize(c['text'])]
            metrics.append({'report_id':report['report_id'],'metric':m['metric'],'page':m['primary_page'],'preserved':bool(matches)})
    # Verify the first data row of actual continuation tables has not vanished.
    continuations=[]
    for c in tables:
        if c['header_source']!='previous_page' or c['rows'][0]['row']!=1: continue
        r=next(r for r in reports if r['report_id']==c['report_id'])
        with fitz.open(ROOT/r['local_file']) as doc:
            row=doc[c['page']-1].find_tables(strategy='lines_strict').tables[c['table']-1].extract()[0]
        ok=len(row)==len(c['rows'][0]['values']) and all(normalize(a)==normalize(b) for a,b in zip(row,c['rows'][0]['values']))
        continuations.append({'report_id':c['report_id'],'page':c['page'],'table':c['table'],'first_row_preserved':ok})
    result={'extraction_version':'v4','reports':len(files),'chunks':len(chunks),'table_chunks':len(tables),
        'header_sources':dict(Counter(c['header_source'] for c in tables)),
        'monetary_data_used_as_headers':wrong,'verified_primary_metrics':metrics,'continuation_first_rows':continuations,
        'limits':'规则检查及已核对指标回归，并非全库逐单元格校验。未识别表头保留原始行，需核对 PDF。历史 v3 实验不代表 v4 质量。'}
    (OUTPUT/'extraction_v4_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not wrong and all(m['preserved'] for m in metrics) and all(c['first_row_preserved'] for c in continuations)
    print(f"v4: {len(files)} reports, {len(chunks)} chunks; {len(metrics)} primary metrics preserved; {len(continuations)} continuation first rows checked; no monetary headers.")

if __name__=='__main__':main()
