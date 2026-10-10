"""Freeze retrieval first; run at most eight paired answers without retries.

Question/reference JSON is a local evaluation attachment, never an index input.
Preparation makes no generation call. Model/auth pins fail before sending a request.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

from .paths import ROOT, OUTPUT, INDEX, COMPANIES, RAW

DIRECTORY = OUTPUT / 'challenge'
MODES = ('hybrid', 'hybrid_expanded')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def filters(question):
    # No answer-key company list: use all company names actually mentioned.
    companies = [name for _, name in COMPANIES if name in question]
    years = sorted({int(y) for y in re.findall(r'20\d{2}', question)})
    if not companies or not years:
        raise ValueError('Challenge questions must explicitly name companies and years')
    return companies, years


def verify(protocol):
    for item in protocol['inputs']:
        if digest(ROOT / item['path']) != item['sha256']:
            raise RuntimeError('Frozen input changed: '+item['path'])
    for item in protocol['records']:
        if digest(DIRECTORY / item['evidence_file']) != item['sha256']:
            raise RuntimeError('Frozen retrieval changed: '+item['evidence_file'])


def prepare(model):
    from .retrieval import Retriever
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    if (DIRECTORY/'protocol.json').exists():
        raise RuntimeError('Protocol already frozen; preserve it instead of overwriting')
    questions = json.loads((DIRECTORY/'questions.json').read_text(encoding='utf-8'))
    if len(questions)!=4 or len({q['id'] for q in questions})!=4:
        raise ValueError('Exactly four unique questions required')
    source_files = sorted({RAW / ref['file'] for q in questions for ref in q['sources']})
    inputs = [DIRECTORY/'questions.json', INDEX/'version.json', INDEX/'chunks.json',
              INDEX/'vectors.npy', INDEX/'bm25.pkl', ROOT/'financial_rag/retrieval.py',
              ROOT/'financial_rag/llm.py', *source_files]
    protocol = {'created_at':now(), 'model':model, 'auth_mode':'chatgpt_oauth',
                'max_attempts':8, 'modes':MODES, 'answer_key_used_in_retrieval':False,
                'filter_policy':'all explicitly mentioned company names and years',
                'index':json.loads((INDEX/'version.json').read_text(encoding='utf-8')),
                'inputs':[{'path':str(p.relative_to(ROOT)), 'sha256':digest(p)} for p in inputs],
                'records':[], 'limitations':['Enhanced retrieval may supply more context; this compares complete pipelines, not equal token budgets.',
                'Four source-designed challenge questions, one generation each per mode; not a representative test set.']}
    retriever = Retriever()
    for q in questions:
        companies, years = filters(q['question'])
        for mode in MODES:
            start = time.perf_counter()
            chunks = (retriever.search(q['question'],'hybrid',8,companies,years) if mode=='hybrid'
                      else retriever.expanded(q['question'],companies,years))
            evidence = {'id':q['id'], 'question':q['question'], 'mode':mode,
                        'retrieval_companies':companies, 'years':years, 'chunks':chunks,
                        'retrieval_seconds':round(time.perf_counter()-start,3),
                        'evidence_characters':sum(len(c['text']) for c in chunks)}
            name=f"{q['id']}_{mode}_evidence.json"
            write(DIRECTORY/name,evidence)
            protocol['records'].append({'id':q['id'],'mode':mode,'evidence_file':name,
                                        'sha256':digest(DIRECTORY/name)})
            print(q['id'],mode,len(chunks),'chunks',evidence['evidence_characters'],'characters',flush=True)
    write(DIRECTORY/'protocol.json',protocol)
    print('Frozen; no model answers requested',flush=True)


def run():
    from .llm import answer
    protocol = json.loads((DIRECTORY/'protocol.json').read_text(encoding='utf-8'))
    verify(protocol)
    if len(protocol['records'])!=8 or protocol['max_attempts']!=8:
        raise RuntimeError('Invalid eight-attempt protocol')
    for item in protocol['records']:
        path=DIRECTORY/f"{item['id']}_{item['mode']}.json"
        # A saved start/error also blocks automatic retries after interruption.
        if path.exists():
            print(path.stem,'already attempted; skipping',flush=True)
            continue
        record=json.loads((DIRECTORY/item['evidence_file']).read_text(encoding='utf-8'))
        record.update(started_at=now(),status='started',protocol_sha256=digest(DIRECTORY/'protocol.json'))
        write(path,record)
        start=time.perf_counter()
        try:
            record.update(answer(record['question'],record['chunks'],required_model=protocol['model'],
                                 required_auth_mode=protocol['auth_mode']))
            record['status']='completed'
        except Exception as exc:
            record.update(status='error',error=str(exc))
        record.update(completed_at=now(),generation_seconds=round(time.perf_counter()-start,3))
        write(path,record)
        print(path.stem,record['status'],flush=True)
        if record['status']!='completed':
            raise RuntimeError('Stopped after failure; no automatic retry or paid fallback')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('--model',default='gpt-6-luna')
    args=parser.parse_args()
    prepare(args.model) if args.action=='prepare' else run()
