"""Discover official CNINFO annual-report PDFs and download reproducibly."""
import argparse
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import fitz
import requests

from .paths import COMPANIES, MANIFEST, RAW


def discover(code, name):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'})
    form = {'pageNum': 1, 'pageSize': 100, 'tabName': 'fulltext',
            'column': 'sse' if code.startswith('6') else 'szse',
            'category': 'category_ndbg_szsh;', 'seDate': '2025-01-01~2026-09-30',
            'isHLtitle': 'false', 'searchkey': code, 'stock': ''}
    org_id = ('gssh0' if code.startswith('6') else 'gssz0') + code
    stocks = session.get('https://www.cninfo.com.cn/new/data/szse_stock.json', timeout=35).json()['stockList']
    org_id = next((item['orgId'] for item in stocks if item['code'] == code), org_id)
    form.update(stock=code + ',' + org_id, searchkey='')
    for attempt in range(3):
        try:
            response = session.post('https://www.cninfo.com.cn/new/hisAnnouncement/query', data=form, timeout=35)
            response.raise_for_status()
            data = json.loads(response.content.decode('utf-8'))
            break
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    announcements = data.get('announcements') or []
    found = []
    for year in [2024, 2025]:
        candidates = []
        for announcement in announcements:
            title = re.sub('<[^>]+>', '', announcement['announcementTitle'])
            compact = re.sub(r'\s+', '', title)
            if (announcement['secCode'] == code and re.search(rf'{year}年?年度报告', compact)
                    and not any(x in compact for x in ['摘要', '英文', '取消', '提示', '审计', '说明', '意见', '问询'])):
                candidates.append((announcement, title))
        if not candidates:
            raise RuntimeError(f'{name} {year}: annual-report full text not found')
        candidates.sort(key=lambda pair: pair[0]['announcementTime'], reverse=True)
        announcement, title = candidates[0]
        found.append({'company': name, 'code': code, 'year': year, 'report_id': f'{code}_{year}',
                      'title': title, 'source': '巨潮资讯',
                      'url': 'https://static.cninfo.com.cn/' + announcement['adjunctUrl'],
                      'published_date': datetime.fromtimestamp(announcement['announcementTime'] / 1000, timezone(timedelta(hours=8))).strftime('%Y-%m-%d'),
                      'local_file': f'data/raw/{code}_{year}.pdf',
                      'alternative_fulltext_count': len(candidates) - 1})
    return found


def download(report):
    path = RAW / f"{report['report_id']}.pdf"
    if not path.exists():
        response = requests.get(report['url'], timeout=90, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        if not response.content.startswith(b'%PDF'):
            raise RuntimeError('Source did not return PDF')
        path.write_bytes(response.content)
    with fitz.open(path) as document:
        if len(document) < 40:
            raise RuntimeError(f"Suspiciously short report: {report['report_id']}")
        cover = ''.join(p.get_text() for p in list(document)[:3])
        if '年度报告摘要' in cover[:1200]:
            raise RuntimeError('Summary PDF rejected')
        report['pages'] = len(document)
    report['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"Downloaded {report['company']} {report['year']}: {report['pages']} pages", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest-only', action='store_true')
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists():
        reports = json.loads(MANIFEST.read_text(encoding='utf-8'))
    else:
        reports = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            for found in pool.map(lambda c: discover(*c), COMPANIES):
                reports.extend(found)
                print('Discovered ' + found[0]['company'], flush=True)
        MANIFEST.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    if not args.manifest_only:
        with ThreadPoolExecutor(max_workers=3) as pool:
            reports = list(pool.map(download, reports))
        MANIFEST.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Complete: {len(reports)} reports, {sum(r["pages"] for r in reports)} pages')


if __name__ == '__main__':
    main()
