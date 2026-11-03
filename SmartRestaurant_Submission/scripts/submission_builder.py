"""Allowlist submission builder. Never deletes or mutates original source/DB."""
import argparse,hashlib,json,re,shutil,zipfile,os
from pathlib import Path
from collections import defaultdict
from submission_audit import ROOT,classify

DIRECTORIES={'customers','restaurant_system','templates','static','docs','ai_models'}
ROOT_FILES={'manage.py','.env.example','README.md','requirements.txt','requirements-dev.txt','requirements-production.txt','.gitignore'}
SCRIPTS={'build_submission.ps1','submission_builder.py','submission_audit.py','cleanup_cache.ps1','model_asset_audit.py','verify_submission.py','ai_final_checks.py','setup_models.py'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-name',default='SmartRestaurant_Submission');args=parser.parse_args()
    if not re.fullmatch(r'SmartRestaurant_Submission(?:_[A-Za-z0-9_-]+)?',args.output_name):raise ValueError('Invalid output name')
    destination=ROOT/args.output_name;archive=ROOT/(args.output_name+'.zip')
    if destination.exists() or archive.exists():raise ValueError('Output exists; choose a new --output-name. No existing files deleted.')
    if not (ROOT/'cleanup_manifest.json').exists():raise ValueError('Audit first')
    latest={p.parent.name:json.loads(p.read_text(encoding='utf-8'))['version'] for p in (ROOT/'ai_models').glob('*/latest.json')}
    selected=[];excluded=[]
    for top in [*DIRECTORIES,'scripts']:
        for base,dirs,files in os.walk(ROOT/top,followlinks=False):
            dirs[:]=[d for d in dirs if d!='__pycache__' and not (Path(base)/d).is_symlink()]
            for name in files:
                source=Path(base)/name;rel=source.relative_to(ROOT)
                if source.is_symlink():raise ValueError('Symlink requires explicit review: '+str(rel))
                category,action,reason=classify(rel)
                keep=action=='KEEP'
                if top=='scripts':keep=name in SCRIPTS
                if top=='docs' and name.startswith('employee_accounts'):keep=False
                if top=='ai_models' and len(rel.parts)>=3 and rel.parts[1] in latest and rel.parts[2] not in {latest[rel.parts[1]],'latest.json'}:
                    keep=False;reason='Historical artifact version retained locally; latest version only in submission'
                (selected if keep else excluded).append((source,rel,reason))
    for name in ROOT_FILES:
        source=ROOT/name
        if source.exists():selected.append((source,Path(name),'Required source/setup'))
    destination.mkdir()
    records=[]
    for source,rel,reason in selected:
        target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if rel==Path('ai_models/pretrained/manifest.json'):
            data=json.loads(target.read_text(encoding='utf-8'))
            for meta in data.values():meta.pop('local_path',None)
            if 'embedding' in data:data['embedding']['files']={key.replace('\\','/'):value for key,value in data['embedding']['files'].items()}
            target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        records.append({'path':rel.as_posix(),'size':target.stat().st_size,'category':classify(rel)[0],'reason':reason,'action':'KEEP'})
    evidence=destination/'evidence';evidence.mkdir()
    for name in ['test_summary.json','browser_summary.json','SIZE_REPORT.md','ARCHIVE_NOTICE.md','premium-staff.png','premium-login.png','premium-admin.png','premium-customer.png']:
        src=ROOT/'evidence'/name
        if src.exists():shutil.copy2(src,evidence/name)
    # Archived reports are retained while bulky historical QA is intentionally absent.
    for doc in (destination/'docs').glob('*.md'):
        text=doc.read_text(encoding='utf-8')
        for shot,label in [('staff-dashboard-1366.png','premium-staff.png'),('auth-0-1366.png','premium-login.png'),('manager-4-1366.png','premium-admin.png'),('customer-0-1366.png','premium-customer.png')]:
            text=text.replace('../qa_premium/'+shot,'../evidence/'+label)
        text=re.sub(r'\]\(\.\./(?:qa_[^/]+|ai_verification|artifacts)/[^)]+\)','](../evidence/ARCHIVE_NOTICE.md)',text)
        text=re.sub(r'\]\(\.\./(?:admin|customer)[^)]*\.png\)','](../evidence/ARCHIVE_NOTICE.md)',text)
        doc.write_text(text,encoding='utf-8')
    audit=ROOT/'submission_audit'
    for name in ['model_assets.json','BEFORE.md','cache_cleanup.json']:
        if (audit/name).exists():shutil.copy2(audit/name,evidence/name)
    for doc in (destination/'docs').glob('*.md'):
        text=doc.read_text(encoding='utf-8')
        def safe_link(match):
            target=match.group(1)
            if '://' in target or target.startswith('#'):return match.group(0)
            if not (doc.parent/target.split('#')[0]).exists():return '](../evidence/ARCHIVE_NOTICE.md)'
            return match.group(0)
        doc.write_text(re.sub(r'\]\(([^)]+)\)',safe_link,text),encoding='utf-8')
    (destination/'cleanup_manifest.json').write_text(json.dumps({'items':records,'excluded_artifact_versions':[r.as_posix() for _,r,_ in excluded if r.parts[0]=='ai_models'],'secrets_excluded':True,'local_environment_kept':True},ensure_ascii=False,indent=2),encoding='utf-8')
    # Check exact local secret values in memory; never print values or contents.
    secret_values=[]
    for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines() if (ROOT/'.env').exists() else []:
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1);value=value.strip().strip('\"\'')
            if any(term in key.upper() for term in ['PASSWORD','SECRET','API_KEY','TOKEN']) and value:secret_values.append(value.encode())
    files=[p for p in destination.rglob('*') if p.is_file()]
    for p in files:
        rel=p.relative_to(destination)
        if p.name=='.env' or any(part in {'.venv','__pycache__','node_modules','.pytest_cache'} for part in rel.parts) or p.suffix in {'.pyc','.log','.zip','.sqlite3'} or rel.parts[0].startswith('qa_'):raise ValueError('Forbidden package entry: '+str(rel))
        if p.suffix.lower() in {'.py','.json','.md','.txt','.html','.js','.ps1','.example','.css','.svg','.yaml','.yml','.ini','.toml','.cfg','.csv'} or p.name=='.gitignore':
            raw=p.read_bytes()
            if any(v in raw for v in secret_values):raise ValueError('Local secret found; refused packaging: '+str(rel))
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zipped:
        for p in sorted(files):zipped.write(p,Path(args.output_name)/p.relative_to(destination))
    folders=defaultdict(int)
    for p in files:
        rel=p.relative_to(destination)
        for n in range(1,len(rel.parts)):folders[Path(*rel.parts[:n]).as_posix()]+=p.stat().st_size
    result={'directory':destination.name,'zip':archive.name,'source_bytes':sum(p.stat().st_size for p in files),'zip_bytes':archive.stat().st_size,'files':len(files),'secret_scan':'PASS; excluded .env and checked exact configured secret values','top20_files':[{'path':p.relative_to(destination).as_posix(),'size':p.stat().st_size} for p in sorted(files,key=lambda p:p.stat().st_size,reverse=True)[:20]],'top20_directories':sorted([{'path':k,'size':v} for k,v in folders.items()],key=lambda x:x['size'],reverse=True)[:20]}
    (audit/'after.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if not k.startswith('top20')},ensure_ascii=True))
if __name__=='__main__':main()
