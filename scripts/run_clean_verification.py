"""Verify clean copy using prepared interpreter and existing cache; restore portable manifest."""
import json,os,subprocess,sys,uuid,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from restaurant_system.environment import load_environment
load_environment(ROOT/'.env')
clean=ROOT/'SmartRestaurant_Submission';manifest=clean/'ai_models/pretrained/manifest.json';portable=manifest.read_bytes()
env={**os.environ,'DJANGO_SECRET_KEY':uuid.uuid4().hex+uuid.uuid4().hex,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
try:
    subprocess.run([sys.executable,'scripts/setup_models.py','--cache-root','D:/SmartRestaurant-AI-cache','--reuse-existing'],cwd=clean,env=env,check=True)
    subprocess.run([sys.executable,'scripts/verify_submission.py'],cwd=clean,env=env,check=True)
    result=json.loads((clean/'submission_verification.json').read_text(encoding='utf-8'))
    (ROOT/'evidence/clean_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(ROOT/'evidence/clean_verification.json',clean/'evidence/clean_verification.json')
finally:manifest.write_bytes(portable)
