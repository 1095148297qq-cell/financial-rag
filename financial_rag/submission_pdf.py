"""Format the locally reviewed assignment conclusion; never generate or score answers."""
import json
import os
import shutil
from pathlib import Path
from xml.sax.saxutils import escape

import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle

from .paths import ROOT, OUTPUT, COMPANIES


def main():
    questions = json.loads((ROOT / 'financial_rag/example_questions.json').read_text(encoding='utf-8'))
    audit = json.loads((OUTPUT / 'assignment_audit/audit.json').read_text(encoding='utf-8'))
    assert audit['status'] == 'passed' and len(audit['listed_companies']) == 12
    assert all(c['listing_disclosed'] for c in audit['listed_companies'])
    failures = {3: '漏召回归母净利润，比例无法计算', 7: '把现金净流出称为亏损，概念错误',
                9: '仅确认4家公司营收，排序未完成'}
    for i in failures:
        record = json.loads((OUTPUT / f'evaluation/Q{i:02d}_hybrid_expanded.json').read_text(encoding='utf-8'))
        assert record['manual_review']['correct'] is False
    pdfmetrics.registerFont(TTFont('Chinese', os.getenv('RAG_REPORT_FONT', 'C:/Windows/Fonts/simhei.ttf')))
    body = ParagraphStyle('body', fontName='Chinese', fontSize=9, leading=13, spaceAfter=4,
                          textColor=colors.HexColor('#243349'))
    question = ParagraphStyle('question', parent=body, fontSize=8.6, leading=12, spaceAfter=0)
    heading = ParagraphStyle('heading', parent=body, fontSize=11, leading=15, spaceBefore=6,
                             spaceAfter=4, textColor=colors.HexColor('#176653'))
    title = ParagraphStyle('title', parent=body, fontSize=18, leading=24, spaceAfter=6)
    p = lambda text, style=body: Paragraph(text, style)
    shanghai_parts = [f'{name}（{code}）' for code, name in COMPANIES if code.startswith('6')]
    shanghai = '、'.join(shanghai_parts[:4]) + '；<br/>' + '、'.join(shanghai_parts[4:])
    shenzhen = '、'.join(f'<nobr>{name}（{code}）</nobr>' for code, name in COMPANIES if not code.startswith('6'))
    story = [p('白酒财报问答：题目与结论', title), p('方向 A · 2024、2025年度共24份巨潮资讯官方年报'),
             p('12家上市公司（证券简称与A股代码）', heading),
             p('上海证券交易所：' + shanghai + '。', question),
             p('深圳证券交易所：' + shenzhen + '。', question),
             p('向量 + BM25检索原文，答案附公司、章节和PDF页码。第9、10题为跨12家公司的全景题。'
               '<font color="#a34b28">【曾失败】</font>表示有真实失败记录，同题另有成功回答，不代表每次都失败。'),
             p('挑选的10道题与失败标注', heading)]
    rows = []
    for i, q in enumerate(questions, 1):
        text = escape(q['question'])
        if q['type'] == 'panoramic': text = '<b>【跨公司全景题】</b>' + text
        if i in failures:
            text += '<br/><font color="#a34b28"><b>【曾失败】</b>' + failures[i] + '。</font>'
        rows.append([p(f'{i:02d}', question), p(text, question)])
    table = Table(rows, colWidths=[28, 483])
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                              ('LINEBELOW', (0, 0), (-1, -1), .25, colors.HexColor('#d6e0db')),
                              ('TOPPADDING', (0, 0), (-1, -1), 3),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                              ('BACKGROUND', (0, 8), (-1, 9), colors.HexColor('#e9f0eb'))]))
    story += [table, p('哪类题答得好，为什么', heading),
              p('明确公司、年度和指标的查询表现较好：第1、2题能核对营收与归母净利润；第4、7题能比较经营现金流的跨年变化；'
                '两道全景题的已复核成功回答覆盖12家公司，完成营收排序与增长统计。指标清楚、数据相对集中，便于定位原文并逐项引用。'),
              p('哪类题翻车，为什么', heading),
              p('第3题因缺少分母无法算比例；第7题混淆现金流与利润；第9题虽召回覆盖12家公司，仍未找齐营收。'
                '其他挑战还出现母公司金额遗漏、多事项漏查合同负债、直销比例把50.09%算成50.18%，以及附注排名无法确认。'
                '主要原因是证据不齐、口径混淆和计算失误。'),
              p('结论与改进方向', heading),
              p('同一批财报，年度指标查询、跨年变化和跨公司比较适合建库，因为事实持续更新，答案需要可追溯出处。'
                '应按子问题和报表口径分别检索、补全表格，检查全部公司与所需指标，并用程序核算比例、换算与排序。说明证据不足比猜测数字更可信。'),
              p('以上来自已保存的实际回答，成功与失败可能发生在不同召回条件下；少量题答对不能代表总体准确率。'
                '表格可能存在未确认表头或跨页遗漏，须核对原文。本项目未做微调，不据此比较微调效果。', question)]
    folder = OUTPUT / 'pdf'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'submission_conclusion.pdf'
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=42, rightMargin=42, topMargin=26, bottomMargin=26).build(story)
    with fitz.open(path) as doc:
        assert len(doc) == 1, 'Conclusion must fit one page'
        text = ''.join(doc[0].get_text().split())
        for code, name in COMPANIES: assert name in text and code in text
        for q in questions: assert ''.join(q['question'].split()) in text
        assert text.count('【跨公司全景题】') == 2 and text.count('【曾失败】') == 4
        doc[0].get_pixmap(matrix=fitz.Matrix(1.8, 1.8)).save(folder / 'submission_conclusion_preview.png')
    final = ROOT / '交付材料/最终提交/方向A_问答结论.pdf'
    final.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(path, final)
    except PermissionError:
        final = final.with_name('方向A_问答结论_公司名单.pdf')
        shutil.copy2(path, final)
    print(final)


if __name__ == '__main__':
    main()
