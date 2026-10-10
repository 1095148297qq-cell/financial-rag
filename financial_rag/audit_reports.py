"""Reverify official files and cross-check key values against consolidated statements."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import fitz
import requests
from .download import discover
from .paths import ROOT, MANIFEST, OUTPUT, INDEX, COMPANIES

def main():
    reports=json.loads(MANIFEST.read_text(encoding='utf-8'))
    version_path=INDEX/'version.json'
    version=json.loads(version_path.read_text(encoding='utf-8'))['extraction_version'] if version_path.exists() else 'v3'
    facts=json.loads((OUTPUT/'financial_facts.json').read_text(encoding='utf-8'))
    chunks=json.loads((INDEX/'chunks.json').read_text(encoding='utf-8'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        fresh=[r for group in pool.map(lambda c:discover(*c),COMPANIES) for r in group]
    fresh={r['report_id']:r for r in fresh}
    def check(report):
        record={'report_id':report['report_id'],'company':report['company'],'year':report['year'],'issues':[]}
        local=(ROOT/report['local_file']).read_bytes()
        remote=requests.get(report['url'],timeout=120)
        remote.raise_for_status()
        record['official_url_current']=fresh[report['report_id']]['url']==report['url']
        record['remote_hash_matches']=hashlib.sha256(remote.content).hexdigest()==hashlib.sha256(local).hexdigest()
        record['manifest_hash_matches']=hashlib.sha256(local).hexdigest()==report['sha256']
        with fitz.open(stream=local,filetype='pdf') as doc:
            texts=[p.get_text(sort=True) for p in doc]
            cover=re.sub(r'\s','', ''.join(texts[:3]))
            record['cover_year_matches']=str(report['year'])+'年' in cover
            record['cover_company_matches']=report['company'] in cover or report['code'] in ''.join(texts[:10])
            record['company_identity_basis']='cover name or stock code in first 10 PDF pages'
            record['fulltext_not_summary']='年度报告摘要' not in cover[:1800] and len(doc)>=40
            record['pages']=len(doc)
            fact=next(f for f in facts if f['company']==report['company'] and f['year']==report['year'])
            primary=''.join(texts[fact['page']-1].split())
            checks=[]
            for key,title in [('revenue','合并利润表'),('net_profit','合并利润表'),('operating_cash_flow','合并现金流量表')]:
                metric=fact['metrics'].get(key)
                if not metric:
                    checks.append({'metric':key,'status':'reference_missing'}); continue
                value=metric['current']
                starts=[i for i,t in enumerate(texts) if title in t and '...' not in t[t.index(title):t.index(title)+60] and i>20]
                matching=[]
                for start in starts:
                    for i in range(start,min(start+6,len(texts))):
                        section=texts[i]
                        if i==start: section=section[section.index(title)+len(title):]
                        boundaries=[m for m in re.finditer(r'(?:母公司|合并)(?:资产负债表|利润表|现金流量表|所有者权益变动表)',section) if m.group()!=title]
                        if boundaries: section=section[:boundaries[0].start()]
                        if value in ''.join(section.split()): matching.append(i+1)
                        if boundaries: break
                checks.append({'metric':key,'value':value,'primary_page':fact['page'],
                    'primary_text_matches':value in primary,'consolidated_statement_pages':matching,
                    'status':'matched' if matching and value in primary else 'needs_review'})
            record['key_metrics']=checks
            record['audit_report_present']=any('审计报告' in t for t in texts[20:])
            record['consolidated_balance_sheet_present']=any('合并资产负债表' in t for t in texts[20:])
        record['date_before']=report['published_date']
        record['date_china']=fresh[report['report_id']]['published_date']
        record['suspicious_header_chunks']=sum(c['report_id']==report['report_id'] and c['kind']=='table_row' and
            any(re.search(r'\d,\d{3}|\d{4,}\.\d',h) for h in c.get('columns',[])) for c in chunks)
        print(report['report_id'],record['remote_hash_matches'],[m['status'] for m in record['key_metrics']],flush=True)
        return record
    with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(check,reports))
    for report in reports: report['published_date']=fresh[report['report_id']]['published_date']
    MANIFEST.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    previous_path=OUTPUT/'report_accuracy_audit.json'
    history=json.loads(previous_path.read_text(encoding='utf-8')).get('date_correction_history',[]) if previous_path.exists() else []
    history.extend({'report_id':r['report_id'],'before':r['date_before'],'after':r['date_china']} for r in results if r['date_before']!=r['date_china'])
    output={'checked_at':datetime.now().isoformat(),'index_version':version,'scope':'24 original official PDFs; 72 key metric cross-checks; table-header risk scan, not every cell verified',
        'reports':results,'date_corrections':len(history),'date_correction_history':history}
    (OUTPUT/f'report_accuracy_audit_{version}.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 财报收录准确性核查','',
        '重新查询巨潮资讯当前年度报告全文清单；重新下载全部24份官方PDF并对照本地SHA256；核对封面、年度、公司和全文身份。',
        '将参考数据中的营收、归母净利润和经营现金流与原始主要指标页及合并报表交叉核对。文字检索到金额是一致性检查，不等于审计全部单元格。','',
        '| 公司 | 年度 | 官方文件字节一致 | 公司/年度/全文 | 三项关键数据合并报表核对 | 可疑表头块 |',
        '|---|---:|---|---|---|---:|']
    for r in results:
        identity=all(r[k] for k in ['cover_company_matches','cover_year_matches','fulltext_not_summary'])
        lines.append(f"| {r['company']} | {r['year']} | {'一致' if r['remote_hash_matches'] else '不一致'} | {'通过' if identity else '需核对'} | "+
            '、'.join(m['metric']+':'+m['status'] for m in r['key_metrics'])+f" | {r['suspicious_header_chunks']} |")
    lines+=['',f"已修正{output['date_corrections']}条发布日期：原先按UTC记录，现在按中国时区记录。文件及金额没有因日期修正而改变。",'',
        '注意：续页表格存在将第一条数据行识别为表头的风险。可疑表头计数是风险扫描，不代表每块都错误；因此不能声称整个提取库100%准确。',
        '原始财报、提取文本、参考数字和模型回答应分别评价。已有评测中的母公司/合并口径混淆、净资产误作营收、现金净流出误称亏损，属于检索/解释错误，不能据此判定官方下载文件错误。']
    (OUTPUT/f'report_accuracy_audit_{version}.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__': main()
