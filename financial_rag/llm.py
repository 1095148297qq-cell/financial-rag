"""Explicit authentication modes; never falls back to a paid API key."""
import json
import os
import threading
import time
from pathlib import Path
import requests
from dotenv import load_dotenv
from .paths import ROOT, OUTPUT

load_dotenv(ROOT/'.env')
CALL_LOCK=threading.Lock()
CATALOG_LOCK=threading.Lock()
CATALOG_CACHE={}

def configuration():
    mode=os.getenv('AUTH_MODE','api_key')
    if mode=='chatgpt_oauth':
        from .oauth import access_token
        base='https://api.openai.com/v1'
        token=access_token()
        with CATALOG_LOCK:
            if CATALOG_CACHE.get('expires',0)<time.time():
                catalog=requests.get(base+'/models',headers={'Authorization':'Bearer '+token},timeout=90)
                catalog.raise_for_status()
                CATALOG_CACHE.update(expires=time.time()+300,models=[m['slug'] for m in catalog.json().get('models',[]) if m.get('visibility')=='list'])
            models=CATALOG_CACHE['models']
        model=os.getenv('CHAT_MODEL','')
        if model not in models:
            model=next((m for m in models if 'luna' in m or 'mini' in m),models[0] if models else '')
        if not model: raise RuntimeError('当前授权没有可用模型')
    elif mode=='api_key':
        base=os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1').rstrip('/')
        token=os.getenv('OPENAI_API_KEY','')
        model=os.getenv('CHAT_MODEL','gpt-5.4-mini')
        if not token: raise RuntimeError('请在本地 .env 配置自己的 OPENAI_API_KEY')
    else: raise RuntimeError('AUTH_MODE 必须为 api_key 或 chatgpt_oauth')
    return mode,base,token,model

def answer(question,chunks,*,credentials=None,required_model=None,required_auth_mode=None):
    OUTPUT.mkdir(exist_ok=True)
    ledger=OUTPUT/'usage.jsonl'
    mode,base,token,model=credentials if credentials is not None else configuration()
    if required_model is not None and model != required_model:
        raise RuntimeError('模型与实验冻结配置不同；请求未发送')
    if required_auth_mode is not None and mode != required_auth_mode:
        raise RuntimeError('授权方式与实验冻结配置不同；请求未发送')
    evidence='\n\n'.join(f"[{i}] 公司={c['company']} 年报={c['year']} PDF页={c['page']} 章节={c['chapter']} 块={c['id']}\n{c['text']}" for i,c in enumerate(chunks,1))
    prompt=('只根据给定的上市公司年报证据回答中文问题。每项事实必须标明证据编号，例如[1]。'
        '金额先核对单位；区分营业收入和营业总收入、归母净利润和净利润。'
        '不同年报的上期数据可能重述，跨年比较须注明口径。证据不足时明确说无法确认，禁止用常识补数。'
        '跨公司题逐一列出证据覆盖公司和缺失公司；不能把局部结果说成全行业结论。\n问题：'+question+'\n证据：\n'+evidence)
    body={'model':model,'store':False,'stream':True,'input':[{'role':'user','content':prompt}]}
    if mode=='api_key': body['max_output_tokens']=3500
    # Count attempts too: retries must not bypass the cost guard.
    with CALL_LOCK:
        count=sum(1 for _ in ledger.open(encoding='utf-8')) if ledger.exists() else 0
        if credentials is None and count>=int(os.getenv('MAX_MODEL_CALLS','80')):
            raise RuntimeError('已达到本地模型调用次数上限；未自动切换计费方式')
        if credentials is None:
            with ledger.open('a',encoding='utf-8') as f:
                f.write(json.dumps({'attempt':count+1,'mode':mode,'model':model})+'\n')
    response=requests.post(base+'/responses',json=body,headers={'Authorization':'Bearer '+token},stream=True,timeout=(30,180))
    if response.status_code!=200:
        raise RuntimeError(f'模型请求失败（HTTP {response.status_code}）；没有启用其他计费方式')
    output=''; completed=False; usage={}
    for line in response.iter_lines():
        if not line.startswith(b'data: '): continue
        raw=line[6:]
        if raw==b'[DONE]': continue
        event=json.loads(raw)
        if event.get('type')=='response.output_text.delta': output+=event.get('delta','')
        if event.get('type')=='response.completed':
            completed=True; usage=event.get('response',{}).get('usage',{}); break
        if event.get('type') in ('response.failed','response.incomplete','error'):
            raise RuntimeError('模型未完成回答；可能是额度或服务限制，没有自动重试或转为付费')
    response.close()
    if not completed: raise RuntimeError('模型流中断，回答未完成')
    return {'answer':output,'model':model,'usage':usage,'auth_mode':mode}
