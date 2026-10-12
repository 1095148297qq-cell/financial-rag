"""Server-owned provider endpoints; keys are never used to guess a provider."""
import json
from pathlib import Path

PROVIDERS={p['id']:p for p in json.loads(Path(__file__).with_name('providers.json').read_text(encoding='utf-8'))}


def provider_config(provider):
    if provider not in PROVIDERS:
        raise ValueError('不支持的模型服务商')
    return PROVIDERS[provider]


def public_providers():
    return [{k:p[k] for k in ('id','name','default_model','note','docs_url')} for p in PROVIDERS.values()]
