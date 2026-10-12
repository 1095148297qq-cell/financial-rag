import json
import hashlib
from functools import lru_cache
import os
import pickle
import re
import jieba
import numpy as np
from dotenv import load_dotenv
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi
from .paths import ROOT, PROCESSED, INDEX

load_dotenv(ROOT/'.env')

def tokenize(text):
    return [t.lower() for t in jieba.cut(text) if t.strip()]

def encoder():
    return TextEmbedding(model_name=os.getenv('EMBEDDING_MODEL','BAAI/bge-small-zh-v1.5'),
        cache_dir=os.getenv('EMBEDDING_CACHE_DIR',str(ROOT/'.cache/models')),threads=int(os.getenv('EMBEDDING_THREADS','8')))

def build():
    INDEX.mkdir(parents=True,exist_ok=True)
    # Rebuild offline; restart the HTTP service after completion.
    (INDEX/'version.json').unlink(missing_ok=True)
    chunks=[]
    for file in sorted(PROCESSED.glob('*_v4.jsonl')):
        chunks.extend(json.loads(line) for line in file.open(encoding='utf-8'))
    if not chunks: raise RuntimeError('请先运行 python -m financial_rag.extract')
    if len({c['report_id'] for c in chunks}) != 24: raise RuntimeError('必须先完成全部24份报告提取')
    fingerprint=hashlib.sha256(json.dumps({'model':os.getenv('EMBEDDING_MODEL','BAAI/bge-small-zh-v1.5'),'texts':[c['embedding_text'] for c in chunks]},ensure_ascii=False).encode()).hexdigest()
    batches=INDEX/'batches'/fingerprint
    batches.mkdir(parents=True,exist_ok=True)
    (INDEX/'chunks.json').write_text(json.dumps(chunks,ensure_ascii=False),encoding='utf-8')
    corpus=[tokenize(c['embedding_text']) for c in chunks]
    with (INDEX/'bm25.pkl').open('wb') as f: pickle.dump(BM25Okapi(corpus),f)
    print(f'BM25 ready: {len(chunks)} chunks',flush=True)
    model=encoder()
    vectors=[]
    # Save resumable batches so interrupted embedding work is not repeated.
    for start in range(0,len(chunks),512):
        batch_file=batches/f'batch_{start:06d}.npy'
        if batch_file.exists(): vectors.append(np.load(batch_file)); continue
        batch=np.array(list(model.embed([c['embedding_text'] for c in chunks[start:start+512]],batch_size=32)),dtype='float32')
        temp=batch_file.with_suffix('.tmp.npy')
        np.save(temp,batch); temp.replace(batch_file); vectors.append(batch)
        print(f'Embedded {min(start+512,len(chunks))}/{len(chunks)}',flush=True)
    matrix=np.vstack(vectors); matrix/=np.maximum(np.linalg.norm(matrix,axis=1,keepdims=True),1e-12)
    np.save(INDEX/'vectors.npy',matrix)
    (INDEX/'version.json').write_text(json.dumps({'extraction_version':'v4','fingerprint':fingerprint,'chunks':len(chunks),'embedding_model':os.getenv('EMBEDDING_MODEL','BAAI/bge-small-zh-v1.5')},indent=2),encoding='utf-8')

class Retriever:
    def __init__(self):
        self.chunks=json.loads((INDEX/'chunks.json').read_text(encoding='utf-8'))
        with (INDEX/'bm25.pkl').open('rb') as f: self.bm25=pickle.load(f)
        self.vectors=None
        self.model=None

    @lru_cache(maxsize=128)
    def query_vector(self,question):
        if self.model is None: self.model=encoder()
        q=np.array(next(self.model.embed([question])),dtype='float32')
        q/=max(np.linalg.norm(q),1e-12)
        return q

    @lru_cache(maxsize=16)
    def keyword_scores(self,question):
        return self.bm25.get_scores(tokenize(question))

    def search(self,question,mode='hybrid',k=8,companies=None,years=None):
        eligible=np.array([i for i,c in enumerate(self.chunks) if
            (not companies or c['company'] in companies) and (not years or c['year'] in years)])
        if not len(eligible): return []
        ranks=[]
        if mode in ('bm25','hybrid'):
            scores=self.keyword_scores(question)[eligible]
            ranks.append(eligible[np.argsort(-scores)[:60]])
        if mode in ('vector','hybrid'):
            if self.vectors is None: self.vectors=np.load(INDEX/'vectors.npy',mmap_mode='r')
            q=self.query_vector(question)
            scores=self.vectors[eligible]@q
            ranks.append(eligible[np.argsort(-scores)[:60]])
        if len(ranks)==1: ids=ranks[0][:k]
        else:
            fused={}
            for ranking in ranks:
                for pos,idx in enumerate(ranking): fused[int(idx)]=fused.get(int(idx),0)+1/(60+pos+1)
            ids=sorted(fused,key=fused.get,reverse=True)[:k]
        return [self.chunks[int(i)] for i in ids]

    def panoramic(self,question,companies,years,mode='hybrid',per_company=2):
        results=[]
        for company in companies:
            results.extend(self.search(question,mode,per_company,[company],years))
        return results

    @lru_cache(maxsize=128)
    def annual_rows(self,question,company,year):
        """Locate source rows by annual columns and labels, never answer-key data."""
        wanted=[]
        if '营业收入' in question: wanted.append('revenue')
        if '归母' in question or '归属于' in question: wanted.append('attributable_profit')
        if '现金流' in question: wanted.append('cashflow')
        if '净资产收益率' in question or 'ROE' in question.upper(): wanted.append('roe')
        found={}
        for c in self.chunks:
            if c['company']!=company or c['year']!=year or c['kind']!='table_row' or c['page']>25: continue
            header='|'.join(c['columns'])
            if len(set(re.findall(r'20\d{2}',header)))<2 or '季度' in header:continue
            for row in c.get('rows',[]):
                label=''.join(row['values'][0].split()) if row['values'] else ''
                matches={'revenue':label.startswith('营业收入'),
                    'attributable_profit':label.startswith(('归属于上市公司股东的净利润','归属于母公司所有者的净利润')),
                    'cashflow':label.startswith(('经营活动产生的现金流量净额','经营活动现金流量净额')),
                    'roe':'加权平均净资产收益率' in label}
                for metric in wanted:
                    if matches[metric] and (metric not in found or c['page']<found[metric]['page']):found[metric]=c
        return list({c['id']:c for c in found.values()}.values())

    def expanded(self,question,companies,years,panoramic=False):
        rewritten=question.replace('归母净利润','归属于上市公司股东的净利润').replace('经营活动现金流量净额','经营活动产生的现金流量净额')
        if any(word in question for word in ['营业收入','净利润','现金流量','净资产收益率']):
            rewritten+=' 主要会计数据和财务指标'
        seeds=[]
        for company in companies:
            # Separate year retrieval prevents one report crowding out the other.
            for year in years:
                seeds.extend(self.annual_rows(question,company,year))
                seeds.extend(self.search(rewritten,'hybrid',2 if panoramic else 3,[company],[year]))
        chunks=[]; seen=set()
        for seed in seeds:
            if seed['id'] not in seen: chunks.append(seed); seen.add(seed['id'])
        if not panoramic:
            # Recover whole page context for the highest-ranked page in each year.
            pages={}
            for seed in seeds: pages.setdefault((seed['company'],seed['year']),seed['page'])
            for chunk in self.chunks:
                if pages.get((chunk['company'],chunk['year']))==chunk['page'] and chunk['id'] not in seen:
                    chunks.append(chunk); seen.add(chunk['id'])
        return chunks

    def automatic(self, plan):
        """Fixed hybrid retrieval; broaden general questions, preserve statement scope."""
        question, companies, years = plan['search_question'], plan['companies'], plan['years']
        if not years: return []
        scoped = any(w in question for w in ['母公司', '附注', '补充资料', '调节', '调整项目', '间接法'])
        annual = any(w in question for w in ['营业收入', '净利润', '现金流', '净资产收益率', 'ROE'])
        if annual and not scoped and (plan['explicit_companies'] or plan['panoramic']):
            return self.expanded(question, companies, years, plan['panoramic'])
        if plan['panoramic']:
            return self.panoramic(question, companies, years, 'hybrid', per_company=3)
        if not plan['explicit_companies']:
            return self.search(question, 'hybrid', 12, companies, years)
        # Reserve space for each requested company/year; never let a single report dominate.
        seeds = []
        for company in companies:
            for year in years:
                seeds.extend(self.search(question, 'hybrid', 4, [company], [year]))
        if '母公司' in question and '现金流' in question:
            labels=['经营活动产生的现金流量净额'] if '经营' in question else [
                '经营活动产生的现金流量净额','投资活动产生的现金流量净额','筹资活动产生的现金流量净额']
            for c in self.chunks:
                if c['company'] not in companies or c['year'] not in years: continue
                if c.get('statement') not in ['母公司现金流量表','合并现金流量表']: continue
                if any(any(label in ''.join(row['values'][0].split()) for label in labels)
                       for row in c.get('rows',[]) if row.get('values')):
                    seeds.append(c)
        seen = {c['id'] for c in seeds}
        chunks = list({c['id']: c for c in seeds}.values())
        # Restore the leading evidence page and other rows of selected source tables.
        tables = {(c['report_id'], c['page'], c.get('table')) for c in seeds if c.get('kind') == 'table_row'}
        pages={}
        for c in seeds: pages.setdefault((c['company'],c['year']),c['page'])
        for c in self.chunks:
            if c['id'] not in seen and (pages.get((c['company'],c['year']))==c['page'] or
                    (c['report_id'], c['page'], c.get('table')) in tables):
                chunks.append(c); seen.add(c['id'])
        return chunks

if __name__=='__main__': build()
