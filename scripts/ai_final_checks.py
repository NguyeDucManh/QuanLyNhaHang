"""Repeatable final verification; UTF-8 logs, actual exit codes and durations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

workspace=Path(__file__).resolve().parent.parent
checks=[['manage.py','check'],['manage.py','makemigrations','--check'],['manage.py','migrate','--noinput'],['manage.py','test','--noinput'],['-m','pip','check']]
folder=workspace/'ai_verification'; folder.mkdir(exist_ok=True)
results=[]
for index,args in enumerate(checks):
    started=time.monotonic()
    with (folder/f'{index}.log').open('w',encoding='utf-8') as output:
        result=subprocess.run([sys.executable,*args],cwd=workspace,env={**os.environ,'PYTHONIOENCODING':'utf-8'},stdout=output,stderr=output)
    record={'command':[sys.executable,*args],'exit_code':result.returncode,'seconds':round(time.monotonic()-started,3),'log':f'{index}.log'}
    results.append(record); print(json.dumps(record,ensure_ascii=True),flush=True)
    (folder/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if result.returncode: sys.exit(result.returncode)
