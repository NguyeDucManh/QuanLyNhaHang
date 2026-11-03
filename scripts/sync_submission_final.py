"""Update known presentation/evidence files in this task's owned clean copy."""
import shutil,re,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;clean=ROOT/'SmartRestaurant_Submission'
assert clean.resolve().parent==ROOT.resolve() and (clean/'cleanup_manifest.json').exists()
paths=['static/ui/premium.css','static/ui/premium.js','static/ui/dashboard.js','static/admin/js/main.js','templates/customer/auth/login.html','templates/customer/auth/register.html','templates/customer/home.html','templates/customer/base.html','templates/staff/base.html','templates/index.html','scripts/verify_submission.py','scripts/submission_audit.py','scripts/submission_builder.py']
for name in paths:shutil.copy2(ROOT/name,clean/name)
for source in (ROOT/'evidence').iterdir():
    if source.is_file():shutil.copy2(source,clean/'evidence'/source.name)
doc=clean/'docs/PREMIUM_SUBMISSION_REPORT.md';text=(ROOT/'docs/PREMIUM_SUBMISSION_REPORT.md').read_text(encoding='utf-8').split('\n\n### Kết quả build/verification cuối')[0]
for src,name in [('staff-dashboard-1366.png','premium-staff.png'),('auth-0-1366.png','premium-login.png'),('manager-4-1366.png','premium-admin.png'),('customer-0-1366.png','premium-customer.png')]:text=text.replace('../qa_premium/'+src,'../evidence/'+name)
text=text.replace('../submission_audit/BEFORE.md','../evidence/BEFORE.md').replace('../submission_audit/model_assets.json','../evidence/model_assets.json').replace('../submission_audit/cache_cleanup.json','../evidence/cache_cleanup.json')
def link(match):
    target=match.group(1)
    if '://' in target or target.startswith('#') or (doc.parent/target.split('#')[0]).exists():return match.group(0)
    return '](../evidence/ARCHIVE_NOTICE.md)'
doc.write_text(re.sub(r'\]\(([^)]+)\)',link,text),encoding='utf-8')
assert 'local_path' not in (clean/'ai_models/pretrained/manifest.json').read_text(encoding='utf-8')
print('Known final files and compact evidence synchronized; portable model manifest preserved.')
