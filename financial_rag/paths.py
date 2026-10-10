from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
RAW = DATA / 'raw'
PROCESSED = DATA / 'processed'
INDEX = Path(os.getenv('RAG_INDEX_DIR',str(DATA / 'index_v4')))
OUTPUT = ROOT / 'output'
MANIFEST = DATA / 'manifest.json'

COMPANIES = [
    ('600519', '贵州茅台'), ('000858', '五粮液'), ('000568', '泸州老窖'),
    ('600809', '山西汾酒'), ('002304', '洋河股份'), ('000596', '古井贡酒'),
    ('603369', '今世缘'), ('603589', '口子窖'), ('600702', '舍得酒业'),
    ('600779', '水井坊'), ('600559', '老白干酒'), ('603919', '金徽酒'),
]
