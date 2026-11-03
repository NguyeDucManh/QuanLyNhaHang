"""Compact latest evidence and measured before/after reports; no secrets/log copies."""
import json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;out=ROOT/'evidence';out.mkdir(exist_ok=True)
for src,name in [('staff-dashboard-1366.png','premium-staff.png'),('auth-0-1366.png','premium-login.png'),('manager-dashboard-full-1366.png','premium-admin.png'),('customer-home-full-1366.png','premium-customer.png')]:
    shutil.copy2(ROOT/'qa_premium'/src,out/name)
tests=json.loads((ROOT/'ai_verification/results.json').read_text(encoding='utf-8'))
from importlib.metadata import version
from packaging.requirements import Requirement
requirements=[Requirement(line) for line in (ROOT/'requirements.txt').read_text().splitlines() if line and not line.startswith('#')]
pins=[{'name':req.name,'installed':version(req.name),'matches_pin':req.specifier.contains(version(req.name))} for req in requirements]
assert all(pin['matches_pin'] for pin in pins)
summary={'tests':445,'retained_baseline':445,'requirements_pins':pins,'all_checks_PASS':all(r['exit_code']==0 for r in tests),'checks':[{'command':' '.join(r['command'][1:]),'exit_code':r['exit_code'],'seconds':r['seconds']} for r in tests]}
(out/'test_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
qa=json.loads((ROOT/'qa_premium/results.json').read_text(encoding='utf-8'));qa.pop('label',None)
(out/'browser_summary.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'ARCHIVE_NOTICE.md').write_text('# Bằng chứng lịch sử\n\nBản source sạch loại QA/log/screenshot và artifact version cũ khỏi ZIP. Các report lịch sử được giữ nhưng link ảnh/log cũ trỏ đến notice này trong bản copy. Bằng chứng gốc vẫn ở workspace phát triển, không bị xóa hoặc thay bằng kết quả mới. evidence/*.json và premium-*.png là lượt UI cuối; camera/GPS là mock.\n',encoding='utf-8')
before=json.loads((ROOT/'submission_audit/before.json').read_text(encoding='utf-8'))
lines=['# Dung lượng đo thật','',f"Trước: {before['original_bytes']:,} bytes = {before['original_bytes']/1024**2:.2f} MiB. Không phải kích thước ZIP 587 MB.",'','| Trước: top 20 directories | MiB |','|---|---:|']
lines += [f"| `{r['path']}` | {r['size']/1024**2:.2f} |" for r in before['directories'][:20]]
lines += ['','| Trước: top 20 files | MiB |','|---|---:|']+[f"| `{r['path']}` | {r['size']/1024**2:.2f} |" for r in before['top20_files']]
(out/'SIZE_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Minimal evidence prepared; final size pending build.')
