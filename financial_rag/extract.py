"""Page-aware narrative chunks and table rows reconstructed from PDF geometry."""
import json
import re
from concurrent.futures import ProcessPoolExecutor
import fitz
from .paths import ROOT, MANIFEST, PROCESSED

def clean(value):
    return re.sub(r'[ \t]+', ' ', str(value or '')).strip()

EXTRACTION_VERSION = 'v4'

def numeric_data(value):
    value = clean(value).replace('\n', '').replace(' ', '')
    # Years alone are legitimate headers; amounts, ratios and counts are data.
    return bool(re.fullmatch(r'[-−－(（]?\d[\d,]*(?:\.\d+)?[%％)）]?', value)) and not bool(re.fullmatch(r'20\d{2}', value))

def table_header(rows, previous=None):
    rows = [[clean(c).replace('\n',' ') for c in row] for row in rows]
    depth = 0
    for row in rows[:6]:
        if any(numeric_data(v) for v in row[1:]): break
        if depth == 0 and not any(re.search(r'项目|20\d{2}|本期|上期|本年|上年|名称|类别|金额|比例|期末|期初',v) for v in row): break
        # Section labels with empty amount cells are data, not another header.
        if depth and not any(row[1:]): break
        depth += 1
    if depth:
        columns = [' / '.join(dict.fromkeys(row[i] for row in rows[:depth] if i < len(row) and row[i])) for i in range(len(rows[0]))]
        return columns, depth, 'explicit'
    if previous and len(previous['columns']) == len(rows[0]):
        return previous['columns'], 0, 'previous_page'
    return [f'未识别列{i+1}' for i in range(len(rows[0]))], 0, 'unresolved'

def extract_report(report):
    target = PROCESSED / (report['report_id'] + '_' + EXTRACTION_VERSION + '.jsonl')
    if target.exists():
        return report['report_id'], sum(1 for _ in target.open(encoding='utf-8'))
    records = []
    chapter = '封面及目录'
    previous = None
    statement = ''
    unit = ''
    with fitz.open(ROOT / report['local_file']) as doc:
        for page_no, page in enumerate(doc, 1):
            text = page.get_text(sort=True)
            headings = re.findall(r'(?:^|\n)\s*(第[一二三四五六七八九十\d]+节[^\n]{2,45})', text)
            headings=[h.strip() for h in headings if '...' not in h and '……' not in h]
            if headings:
                chapter = headings[-1]
            page_chapter=' / '.join(headings) if headings else chapter
            base = {k: report[k] for k in ['company', 'code', 'year', 'report_id', 'url']}
            base.update(page=page_no, chapter=page_chapter)
            tables = page.find_tables(strategy='lines_strict').tables
            boxes = [table.bbox for table in tables]
            narrative = []
            for block in page.get_text('blocks', sort=True):
                if len(block) < 7 or block[6] != 0:
                    continue
                x0,y0,x1,y1 = block[:4]
                if any(x0 >= b[0]-2 and x1 <= b[2]+2 and y0 >= b[1]-2 and y1 <= b[3]+2 for b in boxes):
                    continue
                narrative.append(block[4].strip())
            narrative = '\n'.join(narrative)
            for start in range(0, len(narrative), 680):
                chunk = narrative[start:start+800].strip()
                if len(chunk) > 30:
                    records.append({**base, 'kind':'text', 'text':chunk})
            for table_no, table in enumerate(tables, 1):
                rows = table.extract()
                if not rows:
                    continue
                context = page.get_text(clip=fitz.Rect(0,max(0,table.bbox[1]-65),page.rect.width,table.bbox[1]),sort=True)[-220:]
                preceding = page.get_text(clip=fitz.Rect(0,0,page.rect.width,table.bbox[1]),sort=True)
                titles = re.findall(r'(?:合并|母公司)(?:资产负债表|利润表|现金流量表|所有者权益变动表)', preceding)
                current_statement = titles[-1] if titles and preceding.rfind(titles[-1]) >= len(preceding)-600 else ''
                units = re.findall(r'单位[：:]\s*([^\n]{1,12})', preceding)
                current_unit = units[-1].strip() if units else ''
                candidate = previous if (previous and previous['page'] == page_no-1 and table_no == 1
                    and abs(previous['x0']-table.bbox[0]) < 15 and abs(previous['x1']-table.bbox[2]) < 15
                    and previous['statement'] and len(previous['columns']) == len(rows[0])
                    and sum(bool(re.search(r'20\d{2}',v)) for v in previous['columns']) >= 2
                    and (not current_statement or previous['statement']==current_statement)
                    and not re.search(r'(?:^|\n)\s*(?:[一二三四五六七八九十]+[、．]|\d+[、])',preceding)) else None
                if candidate:
                    current_statement = current_statement or candidate['statement']
                    current_unit = current_unit or candidate['unit']
                header,depth,header_source = table_header(rows,candidate)
                previous = dict(columns=header,page=page_no,x0=table.bbox[0],x1=table.bbox[2],statement=current_statement,unit=current_unit)
                statement,unit = current_statement,current_unit
                table_meta = dict(columns=header,header_source=header_source,statement=statement,unit=unit,extraction_version=EXTRACTION_VERSION)
                # Preserve each row independently with explicit indexed columns;
                # merged/blank cells remain blank rather than invented values.
                for row_no, row in enumerate(rows[depth:], depth+1):
                    values = [clean(cell).replace('\n',' ') for cell in row]
                    if not any(values):
                        continue
                    parts = [f'列{i+1}（{header[i] if i<len(header) else ""}）={v}' for i,v in enumerate(values)]
                    records.append({**base,'kind':'table_row','table':table_no,'row':row_no,
                        **table_meta,'values':values,'text':f'报表口径：{statement or "未识别"}；单位：{unit or "见原文"}；表头来源：{header_source}\n表格行：'+' | '.join(parts)+'\n表格上下文：'+context})
    # Pack whole rows from the same table into <=800-character chunks.
    packed=[]
    for record in records:
        if (packed and record['kind']=='table_row' and packed[-1]['kind']=='table_row'
                and record['page']==packed[-1]['page'] and record['table']==packed[-1]['table']
                and len(packed[-1]['text'])+len(record['text'])+1<=800):
            previous=packed[-1]
            previous['text']+='\n'+record['text']
            previous['rows'].append({'row':record['row'],'values':record['values']})
        else:
            if record['kind']=='table_row': record['rows']=[{'row':record['row'],'values':record['values']}]
            packed.append(record)
    records=packed
    with target.open('w',encoding='utf-8') as out:
        for i, record in enumerate(records):
            record['id'] = f"{report['report_id']}_p{record['page']}_{i:05d}"
            record['embedding_text'] = f"公司：{record['company']}；年报：{record['year']}；章节：{record['chapter']}；PDF页码：{record['page']}\n{record['text']}"
            out.write(json.dumps(record,ensure_ascii=False)+'\n')
    return report['report_id'], len(records)

def main():
    PROCESSED.mkdir(parents=True,exist_ok=True)
    reports = json.loads(MANIFEST.read_text(encoding='utf-8'))
    with ProcessPoolExecutor(max_workers=3) as pool:
        for report_id,count in pool.map(extract_report,reports):
            print(f'{report_id}: {count} chunks',flush=True)

if __name__ == '__main__':
    main()
