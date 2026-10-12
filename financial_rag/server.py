"""HTTP backend. Public mode never uses the owner's credentials."""
import json
import os
import re
import threading
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .paths import COMPANIES, INDEX, OUTPUT, ROOT
from .retrieval import Retriever
from .llm import answer, ModelRequestError
from .providers import PROVIDERS,provider_config,public_providers

LOCAL = os.getenv('RAG_SERVER_MODE','public') == 'local'
ORIGINS = [x.strip() for x in os.getenv('RAG_ALLOWED_ORIGINS','http://127.0.0.1:3000,http://localhost:3000').split(',') if x.strip()]
app = FastAPI(title='Financial Report RAG',docs_url=None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=ORIGINS,allow_methods=['GET','POST'],allow_headers=['Content-Type'])
SEARCH_LOCK = threading.Lock()
SLOTS = threading.BoundedSemaphore(2)
NAMES = [name for _,name in COMPANIES]

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    # Do not echo request input: it can contain the visitor's API key.
    return JSONResponse(status_code=422,content={'detail':'请求参数不符合要求，请检查问题、年度、检索方式和模型名称。'})

class Query(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question: str = Field(min_length=2,max_length=1000)
    companies: list[str] = Field(default_factory=list,max_length=12)
    years: list[Literal[2024,2025]] = Field(default_factory=lambda:[2024,2025],min_length=1,max_length=2)
    mode: Literal['hybrid','vector','bm25'] = 'hybrid'
    enhanced: bool = True
    panoramic: bool = False
    k: int = Field(default=8,ge=4,le=16)
    generate: bool = False
    auth: Literal['own_key','local'] = 'own_key'
    api_key: SecretStr | None = None
    provider: str = Field(default='openai',pattern=r'^[a-z][a-z0-9_]{0,31}$')
    model: str | None = Field(default=None,pattern=r'^[a-zA-Z0-9][a-zA-Z0-9._:/\-]{0,127}$')

@lru_cache(maxsize=1)
def retriever(fingerprint): return Retriever()

@app.get('/health')
def health():
    ready = all((INDEX/f).exists() for f in ['chunks.json','bm25.pkl','vectors.npy','version.json'])
    return JSONResponse(status_code=200 if ready else 503,content={'ready':ready,'local_auth':LOCAL,'index':json.loads((INDEX/'version.json').read_text()) if ready else None})

@app.get('/api/config')
def config():
    return {'companies':NAMES,'years':[2024,2025],'local_auth':LOCAL,
        'providers':public_providers(),
        'questions':[{k:q[k] for k in ['id','question','companies','years','type']} for q in json.loads((ROOT/'financial_rag/example_questions.json').read_text(encoding='utf-8'))]}

@app.get('/api/examples/{qid}')
def example(qid:str,version:Literal['v3','v4']='v4'):
    if not re.fullmatch(r'Q(?:0[1-9]|10)',qid): raise HTTPException(404,'记录不存在')
    path=OUTPUT/('evaluation_v4' if version=='v4' else 'evaluation')/f'{qid}_hybrid_expanded.json'
    if not path.exists(): raise HTTPException(404,'记录不存在')
    result=json.loads(path.read_text(encoding='utf-8'))
    return {**result,'record_kind':'evaluation','historical':version=='v3','index_version':version,
        'notice':'历史真实实验：修复前v3结果，不代表当前v4质量。' if version=='v3' else 'v4固定题评测记录，非实时生成；不代表总体准确率。'}

@app.post('/api/query')
def query(q:Query,request:Request):
    if any(name not in NAMES for name in q.companies): raise HTTPException(422,'公司不在材料范围内')
    if q.provider not in PROVIDERS: raise HTTPException(422,'不支持的模型服务商')
    credentials=None
    if q.generate:
        if q.auth=='local':
            if (not LOCAL or not request.client or request.client.host not in ('127.0.0.1','::1','testclient')
                    or request.headers.get('origin','') not in ORIGINS):
                raise HTTPException(403,'本地授权仅供本机使用；公开站点请使用自己的 API key')
        else:
            key=q.api_key.get_secret_value().strip() if q.api_key else ''
            if not key or len(key)>512: raise HTTPException(400,'生成回答需要所选服务商的API key')
            spec=provider_config(q.provider)
            credentials=('api_key',spec['base_url'],key,q.model or spec['default_model'])
    if not SLOTS.acquire(blocking=False): raise HTTPException(429,'正在处理其他查询，请稍后重试')
    try:
        if not (INDEX/'version.json').exists(): raise HTTPException(503,'索引正在准备，请稍后重试')
        names=q.companies or [n for n in NAMES if n in q.question] or NAMES
        years=[y for y in q.years if str(y) in q.question] or q.years
        panorama=q.panoramic or len(names)>3 or any(w in q.question for w in ['12 家','12家','逐一','完整排序','几家增长'])
        with SEARCH_LOCK:
            version=json.loads((INDEX/'version.json').read_text(encoding='utf-8'))
            r=retriever(version['fingerprint'])
            if q.enhanced and q.mode=='hybrid': chunks=r.expanded(q.question,names,years,panorama)
            elif panorama: chunks=r.panoramic(q.question,names,years,q.mode)
            else: chunks=r.search(q.question,q.mode,q.k,names,years)
        result={'question':q.question,'chunks':chunks,'mode':q.mode,'enhanced':q.enhanced,'panoramic':panorama,
            'index_version':'v4','retrieval_revision':'annual_table_routing','companies':names,'years':years,'covered':sorted({c['company'] for c in chunks})}
        if q.generate:
            if not chunks: result['error']='未找到证据，未调用模型。'
            elif sum(len(c['text']) for c in chunks)>60000:
                result['error']='本次证据超过 60,000 字符，未调用模型。请缩小公司或年度范围，以控制输入成本。'
            else:
                try: result.update(answer(q.question,chunks,credentials=credentials,provider=q.provider if credentials else 'openai'))
                except ModelRequestError as exc: result['error']=str(exc)
                except Exception: result['error']='模型调用未完成。请检查自己的 key、额度及模型权限；未自动重试或切换账户。'
        return result
    finally: SLOTS.release()
