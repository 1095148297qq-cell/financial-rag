"""Real model runs with complete retrieval traces, answer key and diagnostic checks."""
import json
import argparse
import shutil
import re
from concurrent.futures import ThreadPoolExecutor,as_completed
from .paths import OUTPUT, INDEX
from .retrieval import Retriever
from .llm import answer

def numeric_match(expected,text):
    text=text.replace('−','-').replace('－','-').replace('％','%')
    target=float(expected.replace(',','').replace('%',''))
    money=abs(target)>100000
    for m in re.finditer(r'-?\d[\d,]*(?:\.\d+)?',text):
        try: value=float(m.group().replace(',',''))
        except ValueError: continue
        if target<0 and value>0 and any(w in text[max(0,m.start()-14):m.start()] for w in ['下降','减少','降低','净流出','负']): value=-value
        if abs(value-target)<=max(.011,abs(target)*1e-8): return True
        if money and abs(value-target/1e8)<=.011: return True
        if money and abs(value-target/1e4)<=.011: return True
    return False

def diagnose(question,result):
    text=result.get('answer','')
    missing=[v for v in question['expected_values'] if not numeric_match(v,text)]
    missing_terms=[t for t in question.get('expected_terms',[]) if t not in text]
    cited={int(i) for i in re.findall(r'\[(\d+)\]',text)}
    valid_cited=[result['chunks'][i-1] for i in cited if 1<=i<=len(result['chunks'])]
    covered={(c['company'],c['year'],c['page']) for c in valid_cited}
    missed_refs=[p for p in question['reference_pages'] if (p['company'],p['year'],p['page']) not in covered]
    reasons=[]
    if missing: reasons.append('关键数字缺失或不匹配：'+'、'.join(missing))
    if missing_terms: reasons.append('风险类别缺失：'+'、'.join(missing_terms))
    if not cited: reasons.append('答案没有编号引用')
    if any(i<1 or i>len(result['chunks']) for i in cited): reasons.append('存在无效证据编号')
    if result.get('error'): reasons.append(result['error'])
    return {'preliminary_pass':not reasons,'missing_values':missing,'missing_reference_pages':missed_refs,
        'diagnostic':'；'.join(reasons) or '关键数字检查通过；需人工核对引用原文、计算、排序及解释。',
        'review_status':'pending_manual_review'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--modes',nargs='+',default=['vector','bm25','hybrid','hybrid_coverage','hybrid_expanded'])
    parser.add_argument('--retry-errors',action='store_true',help='Explicitly rerun transport failures, preserving previous attempt files')
    parser.add_argument('--question-ids',nargs='+',help='Only these question IDs, e.g. Q02 Q03; each selected mode calls the model')
    args=parser.parse_args()
    questions=json.loads((OUTPUT/'questions.json').read_text(encoding='utf-8'))
    if args.question_ids: questions=[q for q in questions if q['id'] in args.question_ids]
    version=json.loads((INDEX/'version.json').read_text(encoding='utf-8'))
    directory=OUTPUT/('evaluation_'+version['extraction_version']); directory.mkdir(exist_ok=True)
    r=Retriever(); tasks=[]
    for q in questions:
        modes=['vector','bm25','hybrid','hybrid_expanded']+(['hybrid_coverage'] if q['type']=='panoramic' else [])
        for mode in modes:
            if mode not in args.modes: continue
            path=directory/f"{q['id']}_{mode}.json"
            if path.exists():
                previous=json.loads(path.read_text(encoding='utf-8'))
                if not args.retry_errors or not previous.get('error'): continue
                attempts=OUTPUT/('evaluation_attempts_'+version['extraction_version']); attempts.mkdir(exist_ok=True)
                suffix=len(list(attempts.glob(path.stem+'*')))+1
                shutil.copy2(path,attempts/f'{path.stem}_attempt{suffix}.json')
            chunks=(r.expanded(q['question'],q['companies'],q['years'],q['type']=='panoramic') if mode=='hybrid_expanded'
                else r.panoramic(q['question'],q['companies'],q['years']) if mode=='hybrid_coverage'
                else r.search(q['question'],mode,8,q['companies'],q['years']))
            tasks.append((q,mode,path,chunks))
    def run(task):
        q,mode,path,chunks=task
        record={'id':q['id'],'question':q['question'],'mode':mode,'chunks':chunks,'index_version':version['extraction_version'],'index_fingerprint':version['fingerprint']}
        try: record.update(answer(q['question'],chunks))
        except Exception as exc: record['error']=str(exc)
        record['checks']=diagnose(q,record)
        path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        return q['id'],mode,record['checks']['preliminary_pass']
    with ThreadPoolExecutor(max_workers=3) as pool:
        for task in as_completed([pool.submit(run,t) for t in tasks]):
            print(task.result(),flush=True)

if __name__=='__main__': main()
