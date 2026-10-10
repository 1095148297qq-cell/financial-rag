"""Build independently sourced answer key from the original PDF indicator tables."""
import json
import re
from decimal import Decimal
import fitz
from .paths import ROOT, MANIFEST, OUTPUT, COMPANIES

def main():
    OUTPUT.mkdir(exist_ok=True)
    reports=json.loads(MANIFEST.read_text(encoding='utf-8'))
    refs=[]
    for report in reports:
        with fitz.open(ROOT/report['local_file']) as doc:
            for page_no,page in enumerate(list(doc)[:22],1):
                text=page.get_text(sort=True)
                if '营业收入' in text and ('主要会计数据' in text or '主要财务指标' in text):
                    refs.append({'company':report['company'],'year':report['year'],'page':page_no,'text':text})
                    break
            else: raise RuntimeError('Primary indicator page not found: '+report['report_id'])
    (OUTPUT/'ground_truth_pages.json').write_text(json.dumps(refs,ensure_ascii=False,indent=2),encoding='utf-8')
    facts=[]
    for ref in refs:
        report=next(r for r in reports if r['company']==ref['company'] and r['year']==ref['year'])
        with fitz.open(ROOT/report['local_file']) as doc:
            rows=[row for t in doc[ref['page']-1].find_tables(strategy='lines_strict').tables for row in t.extract()]
        metrics={}
        for row in rows:
            label=re.sub(r'\s','',row[0] or '')
            key=None
            if label in ('营业收入','营业收入（元）'): key='revenue'
            elif label in ('归属于上市公司股东的净利润','归属于上市公司股东的净利润（元）'): key='net_profit'
            elif label in ('经营活动产生的现金流量净额','经营活动产生的现金流量净额（元）'): key='operating_cash_flow'
            elif label in ('加权平均净资产收益率','加权平均净资产收益率（%）'): key='roe'
            if key and key not in metrics:
                values=[re.sub(r'\s','',x or '') for x in row[1:]]
                metrics[key]={'current':values[0],'prior':values[1],'source_row':row}
        if 'revenue' not in metrics: raise RuntimeError('No independently extracted revenue row')
        facts.append({'company':ref['company'],'year':ref['year'],'page':ref['page'],'url':report['url'],'metrics':metrics})
    (OUTPUT/'financial_facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
    def f(name,year,key):
        return next(x for x in facts if x['company']==name and x['year']==year)['metrics'][key]['current']
    def p(name,year): return next(x for x in facts if x['company']==name and x['year']==year)['page']
    def item(id,question,names,years,expected,notes,kind='single'):
        return {'id':id,'question':question,'companies':names,'years':years,'type':kind,
            'expected_values':expected,'reference_answer':notes,
            'reference_pages':[{'company':n,'year':y,'page':p(n,y)} for n in names for y in years]}
    questions=[
        item('Q01','贵州茅台 2024、2025 年营业收入和归母净利润分别是多少？请按亿元列出并给出两份年报出处。',['贵州茅台'],[2024,2025],
            [f('贵州茅台',y,k) for y in [2024,2025] for k in ['revenue','net_profit']],'四个数字都须正确，覆盖两份年报。','cross_year'),
        item('Q02','五粮液 2025 年营业收入、归母净利润及其同比分别是多少？',['五粮液'],[2025],
            [f('五粮液',2025,'revenue'),f('五粮液',2025,'net_profit'),'-54.55%','-71.89%'],'不能把上年数字当作本年。'),
        item('Q03','泸州老窖 2025 年经营活动现金流量净额和归母净利润是多少？前者约占后者多少百分比？',['泸州老窖'],[2025],
            [f('泸州老窖',2025,'operating_cash_flow'),f('泸州老窖',2025,'net_profit'),
             str(round(float(f('泸州老窖',2025,'operating_cash_flow').replace(',',''))/float(f('泸州老窖',2025,'net_profit').replace(',',''))*100,2))+'%'],
             '现金流/归母净利润，分母不能取营业收入。','calculation'),
        item('Q04','对照洋河股份 2024 和 2025 年年报，经营活动现金流量净额分别是多少？是否由正转负？',['洋河股份'],[2024,2025],
            [f('洋河股份',y,'operating_cash_flow') for y in [2024,2025]],'2024 正、2025 负；金额不能丢负号。','cross_year'),
        item('Q05','古井贡酒 2025 年加权平均净资产收益率是多少？较 2024 年下降多少个百分点？',['古井贡酒'],[2025],
            [f('古井贡酒',2025,'roe'),'9.61'],'14.28%，较23.89%下降9.61个百分点；不能写下降9.61%。','calculation'),
        item('Q06','山西汾酒 2025 年营业收入和归母净利润同比增幅分别是多少？两者相差多少个百分点？',['山西汾酒'],[2025],
            ['7.52%','0.03%','7.49'],'7.52%、0.03%，相差7.49个百分点。','calculation'),
        item('Q07','对照舍得酒业 2024 和 2025 年年报，两年经营活动现金流量净额是多少？2025 年仍为负吗？',['舍得酒业'],[2024,2025],
            [f('舍得酒业',y,'operating_cash_flow') for y in [2024,2025]],'两年均负，2025现金净流出缩小。','cross_year'),
        {'id':'Q08','question':'水井坊 2025 年年报“可能面对的风险”列出哪两类风险？每类概括一项应对措施。',
         'companies':['水井坊'],'years':[2025],'type':'explanation','expected_values':[],
         'expected_terms':['行业周期调整','市场竞争'],
         'reference_answer':'行业周期调整：核心品类/真实年份品质/重点经销商/营销能力；市场竞争：品质及渠道健康、井18和第一坊、合伙人或平台商模式。',
         'reference_pages':[{'company':'水井坊','year':2025,'page':32}]},
    ]
    names=[n for _,n in COMPANIES]
    ranking=sorted([(n,Decimal(f(n,2025,'revenue').replace(',',''))) for n in names],key=lambda x:x[1],reverse=True)
    questions.append(item('Q09','在本库 12 家白酒公司中，按 2025 年营业收入由高到低完整排序，列出各家金额（亿元）。覆盖不足时说明缺失公司。',names,[2025],
        [str(v) for _,v in ranking],'正确排序：'+'、'.join(n for n,_ in ranking),'panoramic'))
    growth=[]
    for n in names:
        a=Decimal(f(n,2025,'revenue').replace(',','')); b=Decimal(f(n,2024,'revenue').replace(',',''))
        growth.append((n,round((a/b-1)*100,2)))
    questions.append(item('Q10','逐一列出本库 12 家公司的 2025 年营业收入同比增幅；共有几家增长，分别是谁？使用 2025 年年报中披露的 2024 年可比数据，列明证据覆盖。',names,[2025],
        [str(v)+'%' for _,v in growth],'仅1家增长：山西汾酒（7.52%）；其余11家下降。','panoramic'))
    (OUTPUT/'questions.json').write_text(json.dumps(questions,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared 10 questions and independently sourced financial facts.')

if __name__=='__main__': main()
