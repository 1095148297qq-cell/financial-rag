"""Generate the one-page conclusion and readable experiment records after review."""
import json
from collections import Counter
from html import escape
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from .paths import OUTPUT

def main():
    reviews=json.loads((OUTPUT/'manual_review.json').read_text(encoding='utf-8'))
    questions=json.loads((OUTPUT/'questions.json').read_text(encoding='utf-8'))
    records=[]
    for path in sorted((OUTPUT/'evaluation').glob('*.json')):
        record=json.loads(path.read_text(encoding='utf-8'))
        review=reviews[path.stem]
        record['manual_review']=review
        record['checks']['review_status']='reviewed'
        path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        records.append(record)
    counts=Counter(r['mode'] for r in records if r['manual_review']['correct'])
    summary={'questions':10,'runs':len(records),'correct_by_mode':dict(counts),
        'model':sorted({r.get('model','unavailable') for r in records}),
        'input_tokens':sum(r.get('usage',{}).get('input_tokens',0) for r in records),
        'output_tokens':sum(r.get('usage',{}).get('output_tokens',0) for r in records)}
    (OUTPUT/'evaluation_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 实际问答与逐题评测','',
        '固定10题，分别比较向量、BM25和RRF混合检索；全景题增加逐公司召回；增强版本增加术语展开、分年度召回和页面补全。',
        '通过要求：回答满足题意，金额/符号/单位/计算/排序正确，关键结论能从实际引用块核对；拒答保留但不算答对。覆盖数表示召回覆盖，不能代替事实完整性。',
        '', '所有结果是本次实际运行，人工复核说明也在各 JSON 中。完整参考数值见 financial_facts.json；源页文字见 ground_truth_pages.json。','']
    for q in questions:
        lines += [f"## {q['id']} · {q['type']}",q['question'],'',f"参考判断：{q['reference_answer']}",'']
        for r in records:
            if r['id']!=q['id']: continue
            review=r['manual_review']
            lines += [f"### {r['mode']} · {'答对' if review['correct'] else '未答对'}",
                '复核：'+review['reason'],'',r.get('answer',r.get('error','')),'','召回块：','']
            lines += [f"- [{i}] {c['id']}：{c['company']} / {c['year']} / PDF p{c['page']} / {c['chapter']}" for i,c in enumerate(r['chunks'],1)]
            lines += ['']
    (OUTPUT/'evaluation_records.md').write_text('\n'.join(line.rstrip() for line in '\n'.join(lines).splitlines())+'\n',encoding='utf-8')
    pdfdir=OUTPUT/'pdf'; pdfdir.mkdir(exist_ok=True)
    pdfmetrics.registerFont(TTFont('Chinese',str(Path('C:/Windows/Fonts/simhei.ttf'))))
    body=ParagraphStyle('body',fontName='Chinese',fontSize=9.5,leading=14,textColor=colors.HexColor('#243349'),spaceAfter=6)
    small=ParagraphStyle('small',parent=body,fontSize=8.4,leading=11.5,spaceAfter=0)
    heading=ParagraphStyle('heading',parent=body,fontSize=11.5,leading=16,textColor=colors.HexColor('#135c77'),spaceBefore=5)
    title=ParagraphStyle('title',parent=body,fontSize=21,leading=28,textColor=colors.HexColor('#122c44'),spaceAfter=8)
    def p(text,style=body): return Paragraph(escape(text),style)
    story=[p('白酒财报问答：检索的边界',title),p('第三周作业 · 方向 A  |  2024—2025 年年报  |  12 家公司 / 24 份全文 / 4,408 页',small),Spacer(1,10)]
    story += [p('材料与方法',heading),p('官方巨潮资讯下载；文本按约800字、120字重叠切块，表格保留行列；每块带公司、年度、章节及PDF页码。下列v3历史实验共20,979块。本地BGE向量 + jieba/BM25，RRF融合；GPT根据证据回答并给出处。')]
    score='；'.join(f'{label} {counts[mode]}/10' for mode,label in [('vector','向量'),('bm25','BM25'),('hybrid','混合'),('hybrid_expanded','增强混合')])
    story += [p('v3真实历史实验结果（固定10题）',heading),p(score+'。增强版本包含术语展开、分年度召回；单公司题补全相关页面，全景题逐公司检索。')]
    data=[[p('题目',small),p('增强结果',small),p('复核要点 / 错误原因',small)]]
    topics=['茅台两年营收/归母','五粮液金额及同比','泸州现金流/利润比','洋河现金流正负','古井ROE百分点','汾酒两项增幅差','舍得两年现金流','水井坊风险及措施','12家公司营收排序','12家公司同比全景']
    for q,topic in zip(questions,topics):
        review=reviews[q['id']+'_hybrid_expanded']
        data.append([p(q['id']+' '+topic,small),p('答对' if review['correct'] else '未答对',small),p(review['reason'],small)])
    table=Table(data,colWidths=[151,54,310],hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5eff4')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#d7e1e8')),('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story += [table,Spacer(1,6),p('为什么会翻车',heading),
        p('BM25全景top-8仅覆盖5～6家公司，无法完整排序；“归母”等简称与报告原词不同，可能漏掉关键行。金额相同而年度、合并口径或表头不同也会误导模型；现金流倒算出现过错误。复杂/跨页表格仍需原文核对。'),
        p('一页结论',heading),p('同一批财报，年度金额、跨年变化和跨公司比较适合建库：事实会更新，需要出处、口径核对及完整覆盖。检索找到局部证据不等于答对全景题。微调更适合稳定的表达格式和业务术语，不能替代这批财报的检索与数字核验。'),
        p('版本说明：v4已修复续表金额首行误作表头；72项关键指标保留、169处已识别续表首行回归通过。仍有无法确认的表头，未做全库逐单元格校验。上表为v3历史结果，不是v4生成正确率。',small),
        Spacer(1,4),p('限制：仅固定10题，不能外推总体准确率；复杂表格及长块截断可能漏召回。完整回答、召回块、标准数据、人工复核与新旧版本说明随项目保存。',small)]
    path=pdfdir/'conclusion.pdf'
    SimpleDocTemplate(str(path),pagesize=A4,rightMargin=40,leftMargin=40,topMargin=35,bottomMargin=32).build(story)
    import fitz
    doc=fitz.open(path)
    if len(doc)!=1: raise RuntimeError(f'Conclusion must be one page, got {len(doc)}')
    doc[0].get_pixmap(matrix=fitz.Matrix(1.8,1.8)).save(pdfdir/'conclusion_preview.png')
    (OUTPUT/'submission.txt').write_text('方向：A\n代码仓库：待填写项目完工后提供的仓库地址\n一句话结论：同一批财报，年度金额、跨年变化和跨公司比较适合建库，因为事实会更新，答案需要可追溯出处、口径核对和完整覆盖。\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()
