"""Read-only filesystem inventory; never reads .env contents or deletes files."""
import os, json, hashlib
from pathlib import Path
from collections import defaultdict
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'submission_audit'
EXCLUDED_ROOTS = {'SmartRestaurant_Submission', 'submission_audit', 'evidence'}

def classify(path):
    parts = path.parts; name = path.name.lower(); top = parts[0]
    if top == '.venv': return 'REQUIRED_RUNTIME', 'EXCLUDE_SUBMISSION', 'Local environment; recreate with requirements, keep on this machine'
    if name == '.env': return 'REQUIRED_RUNTIME', 'EXCLUDE_SUBMISSION', 'Local secrets; never package'
    if '__pycache__' in parts or path.suffix == '.pyc' or any(p in {'.pytest_cache','.mypy_cache','.ruff_cache','htmlcov','coverage'} for p in parts) or name == '.coverage':
        return 'CACHE','DELETE_CACHE','Generated cache; exclude from archive, eligible for bounded cleanup'
    if top.startswith('qa_') or top == 'ai_verification' or path.suffix == '.log': return 'QA_EVIDENCE','EXCLUDE_SUBMISSION','Keep historical evidence locally; compact evidence packaged separately'
    if top in {'.git','.vscode','node_modules'}: return 'SAFE_TO_EXCLUDE_FROM_ZIP','EXCLUDE_SUBMISSION','Local tooling; retain original'
    if name.endswith(('.tmp','.bak','.old','.orig','.download')): return 'TEMPORARY','EXCLUDE_SUBMISSION','Incomplete/temporary file; retained locally until reference verification'
    if path.suffix.lower() in {'.zip','.7z','.sqlite3'}: return 'REQUIRED_DATA','EXCLUDE_SUBMISSION','Old archive/database; do not delete or ship private data'
    if len(parts)==1 and path.suffix.lower() in {'.png','.jpg','.jpeg'}: return 'QA_EVIDENCE','EXCLUDE_SUBMISSION','Historical preview retained locally'
    if top == 'docs': return 'DOCUMENTATION','KEEP','Referenced reports retained; missing heavy QA links documented in submission'
    if top == 'ai_models': return 'REQUIRED_MODEL','KEEP','Preserve manifests, trained artifacts, RAG index and research provenance'
    if top in {'media','uploads','artifacts'}: return 'REQUIRED_DATA','KEEP','Preserve data until reference/privacy review; artifacts may be required'
    if top == 'static': return 'REQUIRED_RUNTIME','KEEP','Runtime assets; menu images and paths preserved'
    if name.endswith(('.tmp','.bak','.old','.orig')): return 'TEMPORARY','EXCLUDE_SUBMISSION','Not deleted without reference verification'
    if top in {'customers','restaurant_system','templates','scripts'} or name.startswith('requirements') or name in {'manage.py','readme.md','.env.example','.gitignore'}: return 'REQUIRED_SOURCE','KEEP','Source/setup/tests retained'
    return 'UNKNOWN','EXCLUDE_SUBMISSION','Needs review; never delete unknown files'

def main():
    rows=[]; dirs=defaultdict(int)
    for base, children, files in os.walk(ROOT):
        if Path(base)==ROOT: children[:]=[d for d in children if d not in EXCLUDED_ROOTS]
        for name in files:
            file=Path(base)/name; relative=file.relative_to(ROOT)
            if relative.suffix.lower()=='.zip': pass
            try: size=file.stat().st_size
            except OSError: continue
            category,action,reason=classify(relative)
            rows.append({'path':relative.as_posix(),'size':size,'category':category,'reason':reason,'action':action})
            for i in range(1,len(relative.parts)): dirs[Path(*relative.parts[:i]).as_posix()]+=size
    rows.sort(key=lambda r:r['size'],reverse=True)
    report={'original_bytes':sum(r['size'] for r in rows),'files':len(rows),'top20_files':rows[:20], 'directories':sorted([{'path':p,'size':s} for p,s in dirs.items()],key=lambda r:r['size'],reverse=True),'items':rows}
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT/'before.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'cleanup_manifest.json').write_text(json.dumps({'root':str(ROOT),'audit_only':True,'items':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    text=['# Audit dung lượng trước thay đổi','',f"Tổng: {report['original_bytes']:,} bytes ({report['original_bytes']/1024**2:.2f} MiB), {len(rows)} files. Không xóa file trong audit.",'','| PATH | SIZE MiB | TYPE | REQUIRED | ACTION |','|---|---:|---|---|---|']
    for r in report['directories'][:20]: text.append(f"| `{r['path']}` | {r['size']/1024**2:.2f} | directory | Theo từng item trong manifest | Xem manifest |")
    for r in rows[:20]: text.append(f"| `{r['path']}` | {r['size']/1024**2:.2f} | {r['category']} | {'yes' if r['action']=='KEEP' else 'local/excluded'} | {r['action']} |")
    (OUTPUT/'BEFORE.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps({'bytes':report['original_bytes'],'MiB':round(report['original_bytes']/1024**2,2),'files':len(rows),'top_roots':{p:s for p,s in dirs.items() if '/' not in p}},ensure_ascii=False))
if __name__=='__main__': main()
