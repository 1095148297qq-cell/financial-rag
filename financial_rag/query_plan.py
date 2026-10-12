"""Interpret ordinary questions without an answer-key or model API call."""
import re
from datetime import date
from .paths import COMPANIES

ALIASES = {
    '贵州茅台': ['茅台'], '五粮液': [], '泸州老窖': ['老窖'],
    '山西汾酒': ['汾酒'], '洋河股份': ['洋河'], '古井贡酒': ['古井'],
    '今世缘': [], '口子窖': [], '舍得酒业': ['舍得'], '水井坊': [],
    '老白干酒': ['老白干'], '金徽酒': ['金徽'],
}

def plan_question(question, today=None):
    today = today or date.today()
    names = [name for _, name in COMPANIES]
    # A final explicit instruction takes precedence over background company names.
    target = re.split(r'(?:只问|只回答|仅回答|只想(?:核对|了解|知道)|仅需(?:核对|回答))', question)[-1]
    mentioned = [name for name in names if any(alias in target for alias in [name, *ALIASES.get(name, [])])]
    rewritten = target
    for name, aliases in ALIASES.items():
        for alias in aliases:
            if alias in rewritten and name not in rewritten:
                rewritten = rewritten.replace(alias, name)
    for source, full in [('营收', '营业收入'), ('经营现金流', '经营活动产生的现金流量净额'),
                         ('归母利润', '归母净利润')]:
        rewritten = rewritten.replace(source, full)
    rewritten = re.sub(r'(?<!营业)(?<!投资)(?<!利息)(?<!其他)(?<!总)收入(?=增长|下降|同比|如何|怎么样|多少|是多少|有多少)', '营业收入', rewritten)
    if '赚了多少钱' in rewritten or '赚了多少' in rewritten:
        rewritten += ' 净利润 归属于上市公司股东的净利润（区分合并与归母口径）'
    years = sorted({int(y) for y in re.findall(r'(?<!\d)(20\d{2})(?!\d)', target)})
    years += [2000+int(y) for y in re.findall(r'(?<!\d)(\d{2})\s*年', target)]
    for word, year in [('去年', today.year-1), ('前年', today.year-2), ('今年', today.year)]:
        if word in target: years.append(year)
    for word, year in [('二〇二四', 2024), ('二零二四', 2024), ('二〇二五', 2025), ('二零二五', 2025)]:
        if word in target: years.append(year)
    notes = []
    if not years and any(w in target for w in ['最新', '最近一年']):
        years = [2025]
        notes.append('“最新”按库内最新的2025年度年报检索。')
    years = sorted(set(years)) or [2024, 2025]
    unavailable = [y for y in years if y not in (2024, 2025)]
    if unavailable:
        notes.append('库内仅有2024、2025年度年报；问题涉及的'+'、'.join(map(str, unavailable))+'年度不在库中，未用其他年度替代。')
    available = [y for y in years if y in (2024, 2025)]
    for y in available:
        if str(y) not in rewritten: rewritten += f' {y}年'
    panoramic = any(w in target for w in ['全行业', '全部公司', '所有公司', '各家公司', '各公司',
        '12家', '12 家', '十二家', '完整排序', '几家增长', '哪几家', '哪些公司'])
    if not mentioned and any(w in target for w in ['排名', '排行', '最高', '最低', '哪家', '几家', '比较', '对比']):
        panoramic = True
    return {'search_question': rewritten, 'companies': mentioned or names, 'years': available,
            'panoramic': panoramic, 'explicit_companies': bool(mentioned), 'notes': notes,
            'requested_years': years, 'unavailable_years': unavailable}
