"""Refresh the task-owned clean source/ZIP; no database or model-cache mutation."""
import os,json,shutil,re,zipfile,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;clean=ROOT/'SmartRestaurant_Submission'
assert clean.resolve().parent==ROOT.resolve() and (clean/'cleanup_manifest.json').exists()
qa=json.loads((ROOT/'qa_customer_booking/results.json').read_text(encoding='utf-8'));assert qa['success'] and qa['QA_database_deleted']
checks=json.loads((ROOT/'ai_verification/results.json').read_text(encoding='utf-8'));assert len(checks)==5 and all(r['exit_code']==0 for r in checks)
log=(ROOT/'ai_verification/3.log').read_text(encoding='utf-8');match=re.search(r'Ran (\d+) tests',log);assert match and int(match[1])==482 and '\nOK\n' in log
for directory in ['customers','restaurant_system','templates','static']:
    for base,dirs,files in os.walk(ROOT/directory,followlinks=False):
        dirs[:]=[d for d in dirs if d!='__pycache__' and not (Path(base)/d).is_symlink()]
        for name in files:
            source=Path(base)/name
            if source.suffix=='.pyc' or source.is_symlink():continue
            target=clean/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
shutil.copy2(ROOT/'README.md',clean/'README.md')
evidence=clean/'evidence'
for src,name in [('new-draft-390.png','booking-draft-mobile.png'),('menu-booking-390.png','booking-menu-mobile.png'),('restored-390.png','booking-restored-mobile.png'),('confirmation-390.png','booking-confirmation-mobile.png'),('mine-payable-390.png','booking-payment-mobile.png')]:shutil.copy2(ROOT/'qa_customer_booking'/src,evidence/name)
(evidence/'customer_booking_browser_summary.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
(evidence/'test_summary.json').write_text(json.dumps({'tests':482,'baseline_retained':461,'added_tests':21,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
for p in (ROOT/'docs').glob('OPERATIONAL_*.json'):shutil.copy2(p,clean/'docs'/p.name)
report=(ROOT/'docs/CUSTOMER_BOOKING_UX_REPORT.md').read_text(encoding='utf-8')
for src,name in [('new-draft-390.png','booking-draft-mobile.png'),('menu-booking-390.png','booking-menu-mobile.png'),('restored-390.png','booking-restored-mobile.png'),('confirmation-390.png','booking-confirmation-mobile.png'),('mine-payable-390.png','booking-payment-mobile.png')]:report=report.replace('../qa_customer_booking/'+src,'../evidence/'+name)
report=report.replace('../qa_customer_booking/results.json','../evidence/customer_booking_browser_summary.json').replace('../ai_verification/results.json','../evidence/test_summary.json')
target=clean/'docs/CUSTOMER_BOOKING_UX_REPORT.md'
def link(match):
    value=match.group(1)
    if '://' in value or value.startswith('#') or (target.parent/value.split('#')[0]).exists():return match.group(0)
    return '](../evidence/ARCHIVE_NOTICE.md)'
target.write_text(re.sub(r'\]\(([^)]+)\)',link,report),encoding='utf-8')
assert 'local_path' not in (clean/'ai_models/pretrained/manifest.json').read_text(encoding='utf-8')
secrets=[]
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key,value=line.split('=',1);value=value.strip().strip('\"\'')
        if any(t in key.upper() for t in ['SECRET','PASSWORD','API_KEY','TOKEN']) and value:secrets.append(value.encode())
files=sorted(p for p in clean.rglob('*') if p.is_file())
for p in files:
    rel=p.relative_to(clean)
    if p.name=='.env' or p.suffix in {'.pyc','.log','.sqlite3','.zip'} or any(t in {'.venv','__pycache__','node_modules'} for t in rel.parts) or rel.parts[0].startswith('qa_'):raise ValueError('Forbidden clean entry '+str(rel))
    if p.suffix in {'.py','.html','.js','.css','.md','.json','.txt','.svg','.example','.ps1'} and any(secret in p.read_bytes() for secret in secrets):raise ValueError('Configured secret found in '+str(rel))
archive=ROOT/'SmartRestaurant_Submission.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in files:z.write(p,Path(clean.name)/p.relative_to(clean))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
result={'tests':482,'source_bytes':sum(p.stat().st_size for p in files),'zip_bytes':archive.stat().st_size,'files':len(files),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'secrets_and_exclusions':'PASS','model_cache_copied':False}
(ROOT/'submission_audit/customer_booking_after.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(ROOT/'SmartRestaurant_Submission.zip.sha256').write_text(result['sha256']+'  '+archive.name+'\n',encoding='ascii')
print(json.dumps(result))
