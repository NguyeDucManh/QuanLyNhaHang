"""Finalize only the owned submission copy, measured report and archive."""
import json,hashlib,zipfile,re,shutil
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parent.parent;clean=ROOT/'SmartRestaurant_Submission';archive=ROOT/'SmartRestaurant_Submission.zip'
assert clean.resolve().parent==ROOT.resolve() and (clean/'cleanup_manifest.json').exists()
verification=json.loads((ROOT/'evidence/clean_verification.json').read_text(encoding='utf-8'));assert verification.get('success') and verification.get('QA_database_deleted')
source_report=ROOT/'docs/PREMIUM_SUBMISSION_REPORT.md';copy_report=clean/'docs/PREMIUM_SUBMISSION_REPORT.md'
source_text=source_report.read_text(encoding='utf-8').split('\n\n### Kết quả build/verification cuối')[0];copy_text=copy_report.read_text(encoding='utf-8').split('\n\n### Kết quả build/verification cuối')[0]
suffix='\n\n### Kết quả build/verification cuối\n\n{measure}\n\nClean smoke PASS: migrate/seed/routes, FaceNet ONNX và MediaPipe CPU, embedding CPU inference, FAISS 384 chiều và latest forecast/recommendation. DB QA đã xóa. FAISS verification đọc bytes để hỗ trợ đường dẫn Windows tiếng Việt; không đổi service runtime. Không thực hiện cài mới dependencies trên máy khác. ZIP không chứa secret .env; checksum nằm ở file SHA256 bên cạnh ZIP.\n'
before_size=(ROOT/'evidence/SIZE_REPORT.md').read_text(encoding='utf-8').split('\n## Sau build')[0]
def files():return sorted(p for p in clean.rglob('*') if p.is_file())
def stats():
    entries=files();dirs=defaultdict(int)
    for p in entries:
        rel=p.relative_to(clean)
        for n in range(1,len(rel.parts)):dirs[Path(*rel.parts[:n]).as_posix()]+=p.stat().st_size
    return {'source_bytes':sum(p.stat().st_size for p in entries),'files':len(entries),'top20_files':[{'path':p.relative_to(clean).as_posix(),'size':p.stat().st_size} for p in sorted(entries,key=lambda p:p.stat().st_size,reverse=True)[:20]],'top20_directories':sorted([{'path':k,'size':v} for k,v in dirs.items()],key=lambda x:x['size'],reverse=True)[:20]}
# Exact secret values are only held in memory and never echoed.
secrets=[]
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key,value=line.split('=',1);value=value.strip().strip('\"\'')
        if any(term in key.upper() for term in ['SECRET','PASSWORD','API_KEY','TOKEN']) and value:secrets.append(value.encode())
last=None
for iteration in range(5):
    measured=stats();zip_size=archive.stat().st_size
    measure=f"Source clean: **{measured['source_bytes']/1024**2:.2f} MiB**; ZIP: **{zip_size/1024**2:.2f} MiB**. Số bytes chính xác, top 20 trước/sau và checksum tại submission_audit/after.json. Audit trước 1.669,85 MiB; .venv 1.635,45 MiB được giữ ngoài ZIP."
    source_report.write_text(source_text+suffix.format(measure=measure),encoding='utf-8');copy_report.write_text(copy_text+suffix.format(measure=measure),encoding='utf-8')
    lines=[before_size,'','## Sau build','',measure,'','| Sau: top 20 directories | MiB |','|---|---:|']+[f"| `{r['path']}` | {r['size']/1024**2:.2f} |" for r in measured['top20_directories']]
    lines+=['','| Sau: top 20 files | MiB |','|---|---:|']+[f"| `{r['path']}` | {r['size']/1024**2:.2f} |" for r in measured['top20_files']]
    for path in [ROOT/'evidence/SIZE_REPORT.md',clean/'evidence/SIZE_REPORT.md']:path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for p in files():
        rel=p.relative_to(clean)
        if p.name=='.env' or p.suffix in {'.log','.pyc','.sqlite3','.zip'} or any(part in {'.venv','__pycache__','node_modules'} for part in rel.parts) or rel.parts[0].startswith('qa_'):raise ValueError('Forbidden clean entry: '+str(rel))
        if (p.suffix in {'.py','.md','.json','.txt','.html','.js','.example','.ps1','.css','.svg','.yaml','.yml','.ini','.toml','.cfg','.csv'} or p.name=='.gitignore') and any(secret in p.read_bytes() for secret in secrets):raise ValueError('Configured secret found in '+str(rel))
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for p in files():output.write(p,Path(clean.name)/p.relative_to(clean))
    rounded=(round(stats()['source_bytes']/1024**2,2),round(archive.stat().st_size/1024**2,2))
    if rounded==last:break
    last=rounded
result={**stats(),'directory':clean.name,'zip':archive.name,'zip_bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'secret_scan':'PASS; no real .env, checked exact configured secret values','clean_verification':'PASS; isolated PostgreSQL deleted','fresh_pip_install':'NOT RUN; reused prepared compatible interpreter'}
with zipfile.ZipFile(archive) as zipped:
    assert zipped.testzip() is None
    assert len(zipped.namelist())==result['files']
(ROOT/'submission_audit/after.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'SmartRestaurant_Submission.zip.sha256').write_text(result['sha256']+'  '+archive.name+'\n',encoding='ascii')
print(json.dumps({k:v for k,v in result.items() if not k.startswith('top20')},ensure_ascii=True))
