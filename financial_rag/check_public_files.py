"""Check candidate Git files and the built frontend without printing secret values."""
import json
import re
import subprocess
from pathlib import Path
from .paths import ROOT, OUTPUT

def main():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
    names=sorted(set(n for n in names if n))
    issues=[]
    patterns=[re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}'),
              re.compile(rb'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}'),
              re.compile(rb'(?i)(?:C:[/\\]+Users[/\\]+lenovo|credentials\.dpapi)')]
    # A literal credentials filename in OAuth implementation/docs is expected;
    # a user-specific absolute path is not. Never include matched text in reports.
    patterns[2]=re.compile(rb'(?i)C:[/\\]+Users[/\\]+lenovo')
    for name in names:
        p=ROOT/name
        if (name=='.env' or (name.startswith('.env.') and name!='.env.example') or
            any(name.startswith(x) for x in ['output/','交付材料/','data/raw/','data/index/','data/index_v4/','data/processed/','.cache/','deploy-data/','api_verification/','logs/','.credentials/'])):
            issues.append({'file':name,'issue':'private_or_large_data_path'})
        if p.is_file() and p.suffix.lower() not in ['.png','.pdf']:
            data=p.read_bytes()
            if any(pattern.search(data) for pattern in patterns):issues.append({'file':name,'issue':'credential_or_private_path_pattern'})
    built=list((ROOT/'frontend/dist').rglob('*'))
    for p in built:
        if p.is_file() and any(pattern.search(p.read_bytes()) for pattern in patterns):
            issues.append({'file':str(p.relative_to(ROOT)),'issue':'built_credential_pattern'})
    report={'candidate_files':len(names),'issues':issues,'public_author_credentials':False,
            'frontend_build_files':sum(p.is_file() for p in built),'docker_image_built':False,'cloud_deployed':False}
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT/'deployment_security_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    if issues:raise SystemExit('Public-file check failed; values were not printed.')

if __name__=='__main__':main()
