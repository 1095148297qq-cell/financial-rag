"""Publish local, fingerprint-locked human reviews including failures."""
import hashlib
import json
from html import escape
import shutil
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from .paths import OUTPUT
from .challenge_evaluate import DIRECTORY, MODES, digest, verify, write
from .review_checks import citation_coverage, percentage_match


def main():
    protocol=json.loads((DIRECTORY/'protocol.json').read_text(encoding='utf-8'))
    verify(protocol)
    questions=json.loads((DIRECTORY/'questions.json').read_text(encoding='utf-8'))
    reviews=json.loads((DIRECTORY/'manual_review.json').read_text(encoding='utf-8'))
    records=[]
    for q in questions:
        for mode in MODES:
            stem=q['id']+'_'+mode
            r=json.loads((DIRECTORY/(stem+'.json')).read_text(encoding='utf-8'))
            if r.get('status')!='completed' or r.get('model')!=protocol['model'] or r.get('auth_mode')!=protocol['auth_mode']:
                raise RuntimeError('Incomplete or confounded answer: '+stem)
            frozen=json.loads((DIRECTORY/(stem+'_evidence.json')).read_text(encoding='utf-8'))
            if r['chunks']!=frozen['chunks'] or r['question']!=frozen['question']:
                raise RuntimeError('Answer evidence differs from frozen retrieval: '+stem)
            fingerprint=hashlib.sha256(json.dumps({k:r[k] for k in ['question','answer','chunks']},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            review=reviews[stem]
            if fingerprint!=review['evidence_sha256']:
                raise RuntimeError('New manual review required: '+stem)
            company=q['expected_companies'][0]
            pages={'C01':[[82],[83]],'C02':[[17,18],[17],[58,102]],'C03':[[17,18]],'C04':[[153]]}[q['id']]
            groups=[[{'company':company,'year':2025,'page':p} for p in group] for group in pages]
            r['review']=review
            r['review_aids']=citation_coverage(r,groups)
            if q['id']=='C03':r['review_aids']['percentage_at_2_decimals']=percentage_match('50.09',r['answer'],2)
            records.append(r)
    summary={'model':protocol['model'],'index':protocol['index'],'protocol_sha256':digest(DIRECTORY/'protocol.json'),
             'questions':4,'runs':8,'auth_mode':protocol['auth_mode'],
             'modes':{mode:{'fully_correct':sum(r['review']['correct'] for r in records if r['mode']==mode),'total':4,
                           'input_tokens':sum(r['usage'].get('input_tokens',0) for r in records if r['mode']==mode),
                           'output_tokens':sum(r['usage'].get('output_tokens',0) for r in records if r['mode']==mode)} for mode in MODES},
             'limitations':protocol['limitations'],
             'grading':'Full completion, calculations, scope, units and supporting citations required. Partial/refusal is not fully correct; truthful refusal is distinguished from hallucination.'}
    expected=['correct','incomplete','partial','partial','correct','incorrect','partial','partial']
    if [r['review']['status'] for r in records]!=expected:
        raise RuntimeError('Results changed; revise narrative and conclusion before publishing')
    write(DIRECTORY/'summary.json',summary)
    lines=['# 4道挑战题：同索引、同模型对照','',
           '2026-10-10；v4索引；模型 '+protocol['model']+'；现有本地授权；8次实际回答，无自动重试。',
           '原10题继续作为开发回归集，未替换题目、回答或原自动诊断。本轮4题先对照原文冻结题目、参考、索引及召回，再运行模型。',
           '普通混合8块；增强混合沿用原有规则，块数随页面和公司而变化。两者上下文预算不同，比较的是完整流程。',
           '公司筛选从题干全部显式公司名提取；C03包含四家公司，没有提前用参考答案只筛贵州茅台。',
           '人工评分指助手对照原文复核，不是教师评分。完整完成才判答对；诚实拒答单独记录。','',
           '| 题目 | 普通混合 | 增强混合 |','|---|---|---|']
    for q in questions:
        lines.append('| '+q['id']+' '+q['type']+' | '+' | '.join(reviews[q['id']+'_'+m]['label'] for m in MODES)+' |')
    lines += ['', '完整答对：普通混合2/4；增强混合0/4。样本仅4题、每格单次生成，不代表总体准确率。',
              '增强方式在C01漏目标报表行，C04年度表优先挤掉附注关键行；C02两者都漏合同负债。C03增强召回正确金额却算错，不能归因于检索错误或断言由干扰引起。',
              '下一步：多事项分开检索并检查覆盖；按报表口径/附注分层定位，再补全相关表；计算交给Decimal并显示公式；缩减无关公司的上下文。检索算法尚未据这4题再调参，未宣称修复效果。','']
    for q in questions:
        lines += ['## '+q['id']+' · '+q['type'],q['question'],'','冻结标准：'+q['criteria'],
                  '参考数值：'+', '.join(q['expected_values']),
                  '原文：'+'；'.join(s['file']+' PDF物理页 '+','.join(map(str,s['pages'])) for s in q['sources']),'']
        for r in [r for r in records if r['id']==q['id']]:
            lines += ['### '+r['mode']+' · '+r['review']['label'],r['review']['reason'],
                      '失败类型：'+r['review']['failure_type'],
                      f"实际召回{len(r['chunks'])}块，正文{r['evidence_characters']}字；检索{r['retrieval_seconds']}秒，生成{r['generation_seconds']}秒。",'',
                      '原始回答：',r['answer'],'','实际召回块：']
            used=set(r['review']['citation_numbers'])
            lines += [f"- [{i}] {c['id']} | {c['company']} | {c['year']} | PDF p{c['page']} | {c['chapter']}"+(' | 已引用' if i in used else '') for i,c in enumerate(r['chunks'],1)]
            lines += ['', '引用页覆盖诊断（仅辅助）：'+json.dumps(r['review_aids'],ensure_ascii=False),'']
    (DIRECTORY/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # Offline review view contains actual saved answers, not new generations.
    html=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>挑战题评测原始记录</title>',
          '<style>body{margin:0;background:#eef3f0;color:#243349;font:16px/1.7 "Microsoft YaHei",sans-serif}main{max-width:1150px;margin:auto;padding:36px}h1{margin:0;color:#176653}header{margin-bottom:24px}section{margin:24px 0;background:white;padding:24px;border-radius:12px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}.answer{white-space:pre-wrap;background:#f6f8fa;padding:16px;font:15px/1.75 "Microsoft YaHei",sans-serif}.review{padding:12px;border-left:4px solid #bd7754;background:#fff7ed}small{color:#526578}article{min-width:0}</style><main>',
          '<header><h1>挑战题评测：原始回答与复核</h1><p>同一v4索引 · gpt-6-luna · 4题 × 2种检索 · 8次真实回答</p><small>离线评测记录；原10题保持不变。完整答对：普通混合2/4，增强混合0/4。每格单次生成，不能推断总体准确率。</small></header>']
    for q in questions:
        html += ['<section data-id="'+escape(q['id'])+'"><h2>'+escape(q['id']+' · '+q['type'])+'</h2><p>'+escape(q['question'])+'</p><div class="pair">']
        for r in [r for r in records if r['id']==q['id']]:
            html += ['<article><h3>'+('普通混合' if r['mode']=='hybrid' else '增强混合')+' · '+escape(r['review']['label'])+'</h3>',
                     '<small>实际召回'+str(len(r['chunks']))+'块 · 输入'+str(r['usage'].get('input_tokens',0))+' tokens</small>',
                     '<div class="answer">'+escape(r['answer'])+'</div><p class="review">'+escape(r['review']['reason'])+'</p>',
                     '<details><summary>实际召回块与页码</summary><ul>']
            html += ['<li>'+escape(f"[{i}] {c['id']} · {c['company']} · {c['year']} · PDF p{c['page']}")+'</li>' for i,c in enumerate(r['chunks'],1)]
            html += ['</ul></details></article>']
        html += ['</div></section>']
    html += ['</main></html>']
    (DIRECTORY/'report.html').write_text(''.join(html),encoding='utf-8')
    # Preserve the pre-challenge development conclusion once.
    pdfdir=OUTPUT/'pdf';pdfdir.mkdir(exist_ok=True)
    old=pdfdir/'conclusion_v4_before_challenge.pdf'
    if (pdfdir/'conclusion.pdf').exists() and not old.exists():shutil.copy2(pdfdir/'conclusion.pdf',old)
    pdfmetrics.registerFont(TTFont('Chinese','C:/Windows/Fonts/simhei.ttf'))
    body=ParagraphStyle('body',fontName='Chinese',fontSize=9.2,leading=13.5,spaceAfter=5,textColor=colors.HexColor('#243349'))
    small=ParagraphStyle('small',parent=body,fontSize=8.4,leading=11.8)
    heading=ParagraphStyle('heading',parent=body,fontSize=11.5,leading=16,spaceBefore=7,textColor=colors.HexColor('#176653'))
    title=ParagraphStyle('title',parent=body,fontSize=20,leading=27,spaceAfter=8)
    p=lambda text,style=body:Paragraph(escape(text),style)
    story=[p('白酒财报问答：建库之后仍需核验',title),p('第三周作业 · 方向A · 回归与挑战对照 · 2026-10-10',small),Spacer(1,8),
           p('材料与方法',heading),p('12家白酒上市公司，2024与2025年24份巨潮资讯官方年报全文，共4,408页。v4提取23,620块，含17,872个表格块，保留公司、章节、PDF页码、行列及可识别的表头/口径。本地BGE向量 + BM25，RRF融合；GPT按召回证据回答并标注出处。'),
           p('原10题：开发回归集人工复核10/10',heading),p('含2道跨12家公司全景题，增强混合、gpt-6-luna。年度金额、跨年变化与全景指标表现较好；自动诊断9/10，Q03将正确约数65.8%漏判，原检查保留。题目已用于开发，不能外推总体准确率。'),
           p('新增4题：同一v4索引、同一模型，8次真实回答',heading),
           p('题目与原文参考在生成前冻结，普通混合与现有增强各答一次。完整完成、计算和引用均正确才通过；部分回答、诚实拒答不计完整答对。',small)]
    data=[[p('挑战题',small),p('普通混合',small),p('增强混合',small)]]
    labels=[('C01 合并/母公司现金流','答对','关键行未召回，拒答'),('C02 渠道/经销商/合同负债','部分完成','部分完成'),('C03 干扰公司与渠道占比','答对：50.09%','算错：50.18%'),('C04 附注现金流调节','数值正确，排名未确认','负向调整项未召回')]
    data += [[p(t,small) for t in row] for row in labels]
    table=Table(data,colWidths=[190,130,195]);table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4eee9')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d6e0db')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story += [table,Spacer(1,5),p('完整答对：普通混合2/4，增强混合0/4。两者上下文量不同，比较的是完整流程；四题单次结果不能证明谁总体更好。C03增强使用40块而普通为8块，虽然金额正确，计算仍出错；不能仅凭一次结果认定干扰导致算错。',small),
              p('翻车原因与下一步',heading),p('年度表优先适合常见指标，但不能替代母公司报表或深层附注。只补最相关一页会漏掉多事项中的合同负债；召回片段也不足以证明“所有调整中最大”。下一步应按子问题与口径分别检索、补全相关表并检查覆盖；数值计算用确定性程序验证。现有失败未改写，也未以新问题再次调参后冒充独立测试。'),
              p('结论',heading),p('同一批财报，年度金额、跨年变化、跨公司比较适合建库，因为事实会更新且答案需要出处。微调可学习稳定格式与术语，不能替代事实更新、检索完整性和计算核验。增强规则须按题型验证，不能把固定10题全对视为通用可靠。'),
              p('边界与证据：5,912个表格块未确认表头（不等于均错误）；72项关键金额、169处续表首行回归不代表全库准确。本地交付材料保留10题原始记录、挑战题原始8答、完整召回、冻结协议、逐项复核与v3失败历史。',small)]
    SimpleDocTemplate(str(pdfdir/'conclusion.pdf'),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=32,bottomMargin=30).build(story)
    import fitz
    with fitz.open(pdfdir/'conclusion.pdf') as doc:
        if len(doc)!=1:raise RuntimeError('Conclusion must fit one page')
        doc[0].get_pixmap(matrix=fitz.Matrix(1.6,1.6)).save(pdfdir/'conclusion_preview.png')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
