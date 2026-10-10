"""Copy local evaluation and submission outputs into the ignored delivery folder."""
import hashlib
import shutil
from .paths import ROOT, OUTPUT

def main():
    target=ROOT/'交付材料'
    if not OUTPUT.is_dir(): raise RuntimeError('No local output directory; generate evaluation outputs first')
    target.mkdir(exist_ok=True)
    count=0
    for source in OUTPUT.rglob('*'):
        if not source.is_file() or source.is_symlink(): continue
        dest=target/source.relative_to(OUTPUT)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,dest)
        if hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(dest.read_bytes()).digest():
            raise RuntimeError('Export checksum mismatch')
        count+=1
    print(f'Exported {count} local files into {target.name}; excluded from Git')

if __name__=='__main__': main()
