"""Prepare an allowlisted, credential-free Docker data directory locally."""
import hashlib
import json
import shutil
from .paths import ROOT, INDEX

def main():
    target=ROOT/'deploy-data'
    target.mkdir(exist_ok=True)
    version=json.loads((INDEX/'version.json').read_text(encoding='utf-8'))
    if version.get('embedding_model')!='BAAI/bge-small-zh-v1.5':
        raise RuntimeError('部署打包脚本目前只支持默认 BGE 模型；请同步模型路径后再打包')
    for name in ['chunks.json','vectors.npy','bm25.pkl','version.json']:
        source=INDEX/name
        if not source.exists(): raise RuntimeError('索引未完成：'+name)
        (target/'index').mkdir(exist_ok=True)
        shutil.copy2(source,target/'index'/name)
    source=ROOT/'.cache/models/models--Qdrant--bge-small-zh-v1.5'
    if not source.exists(): raise RuntimeError('默认 BGE 模型缓存不存在；请先完成索引')
    shutil.copytree(source,target/'models'/source.name,dirs_exist_ok=True)
    manifest=[]
    for path in sorted(target.rglob('*')):
        if path.is_file() and path.name!='checksums.json':
            manifest.append({'path':path.relative_to(target).as_posix(),'bytes':path.stat().st_size,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (target/'checksums.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'Prepared {len(manifest)} allowlisted data/model files; {sum(x["bytes"] for x in manifest)/1024**2:.1f} MiB; no credentials copied.')

if __name__=='__main__': main()
