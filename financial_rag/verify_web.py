"""Real HTTP retrieval regression, with optional one-call local GPT check."""
import argparse
import json
import time
from urllib.parse import urlparse
import requests
from .paths import OUTPUT
from .evaluate import numeric_match

def normalized(s):return ''.join(str(s).split()).replace('−','-').replace('－','-')

def main():
    p=argparse.ArgumentParser();p.add_argument('--local-gpt',action='store_true');p.add_argument('--wait',type=int,default=0)
    args=p.parse_args();base='http://127.0.0.1:8000';end=time.time()+args.wait
    while True:
        try:
            health=requests.get(base+'/health',timeout=10)
            if health.ok and health.json()['ready']:break
        except requests.RequestException:pass
        if time.time()>=end:raise RuntimeError('后端/索引尚未就绪')
        time.sleep(5)
    questions=json.loads((OUTPUT/'questions.json').read_text(encoding='utf-8'));records=[]
    for q in questions:
        modes=['vector','bm25','hybrid'] if q['id']=='Q02' else ['hybrid']
        for mode in modes:
            payload={'question':q['question'],'companies':q['companies'],'years':q['years'],
                'mode':mode,'enhanced':mode=='hybrid','panoramic':q['type']=='panoramic'}
            started=time.monotonic();r=requests.post(base+'/api/query',json=payload,timeout=240);r.raise_for_status();result=r.json()
            assert result['index_version']=='v4' and result['chunks']
            assert set(result['covered'])<=set(q['companies'])
            assert all(c['year'] in q['years'] and c['page']>=1 and urlparse(c['url']).hostname=='static.cninfo.com.cn' for c in result['chunks'])
            if q['type']=='panoramic':assert len(result['covered'])==12
            result['id']=q['id'];result['elapsed_seconds']=round(time.monotonic()-started,2)
            result['expected_value_recall']={v:any(numeric_match(v,c['text']) for c in result['chunks']) for v in q['expected_values']}
            records.append(result);print(q['id'],mode,len(result['chunks']),result['elapsed_seconds'],flush=True)
    rejected=requests.post(base+'/api/query',json={'question':'五粮液营业收入是多少？','generate':True},timeout=10)
    assert rejected.status_code==400
    if args.local_gpt:
        q=questions[1]
        r=requests.post(base+'/api/query',json={'question':q['question'],'companies':q['companies'],'years':q['years'],'generate':True,'auth':'local'},headers={'Origin':'http://127.0.0.1:3000'},timeout=300)
        r.raise_for_status();live=r.json()
        (OUTPUT/'v4_live_answer.json').write_text(json.dumps(live,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Local GPT:', 'completed' if live.get('answer') else live.get('error','no answer'),flush=True)
    (OUTPUT/'v4_web_verification.json').write_text(json.dumps({'index_version':'v4','checks':len(records),'generated_answers_scored':False,'recall_note':'数字按数值比较，忽略千位分隔及百分号格式。部分参考值是计算结果，不应要求原始证据直接出现；召回数字也不等于引用正确或回答正确。','records':records},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Real HTTP retrieval verification passed; value recall is not answer accuracy.',flush=True)

if __name__=='__main__':main()
