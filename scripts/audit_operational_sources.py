"""Source marker audit. Test/QA and technical keys are separated from visible labels."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;rows=[]
for folder in ['customers','restaurant_system','templates','static','ai_models','docs','scripts']:
    for p in (ROOT/folder).rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix.lower() not in {'.py','.html','.js','.css','.json','.md'} or p.name.startswith('OPERATIONAL_'):continue
        for i,line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(),1):
            if not re.search('demo',line,re.I):continue
            test='test' in p.name.lower() or p.parent.name=='scripts' or 'fixtures' in p.parts
            technical=any(key in line for key in ['recommendation-demo','recommendation_demo','demo_bank','payment-demo','data-legacy-label'])
            rows.append({'location':f'{p.relative_to(ROOT).as_posix()}:{i}','current_value':line[:500],'type':'TEST_QA' if test else 'TECHNICAL_KEY' if technical else 'DOCUMENTATION' if folder=='docs' else 'SOURCE_OR_ARTIFACT','visible_to_user':p.suffix=='.html' and not technical,'action':'KEEP test/technical/provenance' if test or technical or folder in {'docs','ai_models'} else 'Display sanitized; seed production uses clean reference catalog'})
(ROOT/'docs/OPERATIONAL_SOURCE_LABEL_AUDIT.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'source_matches':len(rows),'audit':'docs/OPERATIONAL_SOURCE_LABEL_AUDIT.json'}))
