"""Publish reviewed v4 results without replacing original model answers or v3 records."""
import json
import hashlib
import re
from html import escape
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from .paths import OUTPUT

TOPICS = ['茅台两年营收/归母','五粮液金额及同比','泸州现金流/利润比','洋河现金流正负','古井ROE百分点','汾酒两项增幅差','舍得两年现金流','水井坊风险及措施','12家公司营收排序','12家公司同比全景']
SHORT = ['两份年报、四项金额与单位一致','金额及同比正确，未混用营业总收入','65.8%为正确约数；自动检查漏判','金额符号正确，确认由正转负','下降9.61个百分点，概念正确','增幅相差7.49个百分点','两年均负；现金净流出不等于亏损','两类风险与应对措施有原文支持','12家公司金额、顺序及出处完整','12项同比正确，1家公司增长']

def main():
    questions=json.loads((OUTPUT/'questions.json').read_text(encoding='utf-8'))
    records=[]
    reviews=json.loads((OUTPUT/'manual_review_v4.json').read_text(encoding='utf-8'))
    for q in questions:
        path=OUTPUT/'evaluation_v4'/f"{q['id']}_hybrid_expanded.json"
        r=json.loads(path.read_text(encoding='utf-8'))
        if r.get('error') or not r.get('answer'): raise RuntimeError(f"Incomplete evaluation: {q['id']}")
        citations=sorted({int(n) for n in re.findall(r'\[(\d+)\]',r['answer'])})
        assert citations and all(1 <= n <= len(r['chunks']) for n in citations)
        review=reviews[path.stem]
        evidence={k:r[k] for k in ['question','answer','chunks']}
        fingerprint=hashlib.sha256(json.dumps(evidence,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
        if fingerprint!=review.get('evidence_sha256'):
            raise RuntimeError(f"{q['id']}: answer or evidence changed; new manual review required")
        if not review['correct']: raise RuntimeError('Revise conclusion to reflect new reviewed results before publishing')
        r.update(manual_review=review,index_version='v4',retrieval_revision='annual_table_routing',record_kind='evaluation')
        r['checks']['review_status']='reviewed'
        path.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        records.append(r)
    (OUTPUT/'manual_review_v4.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary={'index_version':'v4','retrieval_revision':'annual_table_routing','questions':10,'runs':10,
        'mode':'hybrid_expanded','manual_correct':10,'automatic_pass':sum(r['checks']['preliminary_pass'] for r in records),
        'model':sorted({r['model'] for r in records}),'auth_mode':sorted({r['auth_mode'] for r in records}),
        'input_tokens':sum(r.get('usage',{}).get('input_tokens',0) for r in records),
        'output_tokens':sum(r.get('usage',{}).get('output_tokens',0) for r in records),
        'limitations':['固定10题，已用于开发和调试，不是独立留出测试，不能外推总体准确率。',
                       'v3与v4的模型和检索流程均变化，不能将差异归因于单个改动。',
                       '未做全库逐单元格校验；表头未识别、复杂表格和长块截断仍可能导致错误。']}
    (OUTPUT/'evaluation_summary_v4.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# v4 最终逐题评测','',
        '2026-10-10实际运行：增强混合检索（年度表定位 + 向量/BM25 + 页面补全），10次模型回答。',
        f"模型：{', '.join(summary['model'])}；本地现有授权；人工复核10/10，自动诊断9/10。",
        'Q03为自动检查小数精度漏判，原诊断保留。回答原文未改写；人工复核是助手核对，不是教师评分。',
        '这是用于开发的固定10题，不是独立测试集。旧版42次实验及失败记录保留于 evaluation/ 与 evaluation_records.md。',
        '','## 复核口径','金额、单位、年度、正负号、计算、完整性及实际引用同时符合题意才通过；约数按题目允许的精度判断。',
        '参考数据 financial_facts.json 已由原始PDF复核；Q05、Q08另核对原始页面，Q07单位在2025年报p6、金额在p7。','']
    for q,r in zip(questions,records):
        lines += [f"## {q['id']} · {q['type']}",q['question'],'',
                  '人工结论：答对。'+r['manual_review']['reason'],
                  '错误记录：无实质回答错误。'+('自动检查漏判约数，已说明，未篡改原检查。' if q['id']=='Q03' else ''),'',
                  '### 原始模型回答',r['answer'],'','### 实际召回块（编号与回答引用一致）']
        used=set(r['manual_review']['citation_numbers'])
        lines += [f"- [{i}] {c['id']} | {c['company']} | {c['year']} | PDF p{c['page']} | {c['chapter']}"+(' | 回答已引用' if i in used else '') for i,c in enumerate(r['chunks'],1)]
        lines += ['']
    (OUTPUT/'evaluation_records_v4.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    pdfmetrics.registerFont(TTFont('Chinese','C:/Windows/Fonts/simhei.ttf'))
    body=ParagraphStyle('body',fontName='Chinese',fontSize=9,leading=13,spaceAfter=5,textColor=colors.HexColor('#243349'))
    small=ParagraphStyle('small',parent=body,fontSize=8.1,leading=11,spaceAfter=0)
    heading=ParagraphStyle('heading',parent=body,fontSize=11,leading=15,spaceBefore=6,textColor=colors.HexColor('#176653'))
    title=ParagraphStyle('title',parent=body,fontSize=20,leading=27,spaceAfter=8)
    def p(t,s=body): return Paragraph(escape(t),s)
    story=[p('白酒财报问答：事实入库与核验',title),
        p('第三周作业 · 方向 A · v4 最终评测 · 2026-10-10',small),Spacer(1,8),
        p('材料与方法',heading),p('12家白酒上市公司，2024—2025年24份巨潮资讯官方年报全文，共4,408页。v4提取23,620块，其中17,872个表格块；保留公司、章节、PDF物理页码和行列。使用本地BGE向量 + BM25、RRF融合，增强模式优先定位年度指标表并补全证据；GPT按实际召回块回答并引用。'),
        p('真实结果：固定10题人工复核10/10',heading),
        p('本轮只运行增强混合10题，含2道跨12家公司全景题，模型为gpt-6-luna，使用本地已有授权。自动诊断9/10；Q03约数65.8%正确，但检查器要求65.77%，人工核对原始金额后通过，原自动诊断保留。')]
    data=[[p('题目',small),p('结果',small),p('核对要点',small)]]
    for i,(topic,reason) in enumerate(zip(TOPICS,SHORT),1): data.append([p(f'Q{i:02} {topic}',small),p('答对',small),p(reason,small)])
    table=Table(data,colWidths=[152,42,321]);table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4eee9')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d6e0db')),('LEFTPADDING',(0,0),(-1,-1),5),
        ('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story += [table,Spacer(1,5),p('哪些题适合；哪里仍会翻车',heading),
        p('年度金额、同比、跨年符号变化及有明确指标的公司比较表现良好。旧版真实失败包括全景漏公司、年度/口径混用、现金流计算及把净流出称作亏损；历史原文仍保留。修复表头、优先年度表及逐公司召回后，本轮固定题全部通过。'),
        p('仍有5,912个表格块未确认表头（不等于均错误），复杂跨页表、长块截断及新问题仍可能失败。本轮题目用于开发，并非独立测试集；v3与v4模型和流程均有变化，不能声称总体100%准确或单一改动带来提升。'),
        p('结论',heading),p('同一批财报，年度金额、跨年变化和跨公司比较适合建库，因为事实持续更新，答案需要出处、口径核对和完整覆盖。微调可学习稳定格式与术语，不能替代财报事实更新和数字核验。'),
        p('可追溯证据：evaluation_v4/保存10份原始回答及完整召回块；evaluation_records_v4.md逐题说明；v3历史42份实验另存。72项关键金额、169处已识别续表首行回归通过，不代表全库逐单元格准确。',small)]
    pdfdir=OUTPUT/'pdf';pdfdir.mkdir(exist_ok=True)
    SimpleDocTemplate(str(pdfdir/'conclusion.pdf'),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=32,bottomMargin=30).build(story)
    import fitz
    doc=fitz.open(pdfdir/'conclusion.pdf')
    if len(doc)!=1: raise RuntimeError(f'Expected one page, got {len(doc)}')
    doc[0].get_pixmap(matrix=fitz.Matrix(1.6,1.6)).save(pdfdir/'conclusion_preview.png')
    (OUTPUT/'submission.txt').write_text('方向：A\n代码仓库：待填写项目仓库地址\n一句话结论：同一批财报，年度金额、跨年变化和跨公司比较适合建库，因为事实持续更新，答案需要出处、口径核对和完整覆盖。\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()
