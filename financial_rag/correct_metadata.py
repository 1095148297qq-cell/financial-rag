"""Correct page-level chapter labels without changing frozen retrieval rankings."""
import json
import re
import fitz
from .paths import ROOT, MANIFEST, PROCESSED, INDEX, OUTPUT

# This migration only repairs the frozen historical v3 experiment.
# Current v4 metadata is produced correctly during extraction and re-embedded.
INDEX = ROOT/'data/index'

def main():
    mapping={}; changed=0
    reports=json.loads(MANIFEST.read_text(encoding='utf-8'))
    for report in reports:
        chapter='封面及目录'
        with fitz.open(ROOT/report['local_file']) as doc:
            for page_no,page in enumerate(doc,1):
                headings=re.findall(r'(?:^|\n)\s*(第[一二三四五六七八九十\d]+节[^\n]{2,45})',page.get_text(sort=True))
                headings=[h.strip() for h in headings if '...' not in h and '……' not in h]
                if headings: chapter=headings[-1]
                mapping[(report['report_id'],page_no)]=' / '.join(headings) if headings else chapter
    def update(chunk):
        nonlocal changed
        label=mapping[(chunk['report_id'],chunk['page'])]
        if chunk['chapter']!=label:
            chunk['chapter']=label; changed+=1
        # embedding_text remains the input snapshot used by the frozen indexes.
        return chunk
    for file in PROCESSED.glob('*_v3.jsonl'):
        chunks=[update(json.loads(line)) for line in file.open(encoding='utf-8')]
        file.write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks),encoding='utf-8')
    path=INDEX/'chunks.json'
    chunks=[update(c) for c in json.loads(path.read_text(encoding='utf-8'))]
    path.write_text(json.dumps(chunks,ensure_ascii=False),encoding='utf-8')
    for path in (OUTPUT/'evaluation').glob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        data['chunks']=[update(c) for c in data['chunks']]
        data['metadata_revision']='Chapter labels corrected; evidence text and frozen retrieval ranking unchanged.'
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Corrected chapter labels: {changed} stored records; rankings unchanged.')

if __name__=='__main__': main()
