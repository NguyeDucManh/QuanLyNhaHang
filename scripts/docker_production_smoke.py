"""CI only: exact production image, disposable PostgreSQL and no provider calls."""
import json,subprocess,time,urllib.request,urllib.error
from pathlib import Path

IMAGE='smart-restaurant-release:ci'
NAME='smart-restaurant-production-smoke'
report={'production_image':IMAGE,'phases':[],'production_data_used':False}
env={'PORT':'8101','DJANGO_DEBUG':'false','RENDER':'true',
     'RENDER_EXTERNAL_HOSTNAME':'127.0.0.1',
     'DJANGO_SECRET_KEY':'ci-only-production-image-probe-0123456789-abcdefghijklmnopqrstuvwxyz',
     'DATABASE_URL':'','DB_HOST':'127.0.0.1','DB_PORT':'5432','DB_NAME':'restaurant_ci512',
     'DB_USER':'postgres','DB_PASSWORD':'ci-disposable-only',
     'TABLE_SERVICE_ASSIGNMENTS_ENABLED':'false','TABLE_SERVICE_LIFECYCLE_ENABLED':'false',
     'MEMBERSHIP_DISCOUNTS_ENABLED':'false'}
def get(path,proxy=False):
    headers={'X-Forwarded-Proto':'https'} if proxy else {}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(NoRedirect)
    try:response=opener.open(urllib.request.Request('http://127.0.0.1:8101'+path,headers=headers),timeout=3)
    except urllib.error.HTTPError as error:response=error
    return response.code,response.headers.get_content_type(),response.read()
try:
    # Reproduce the missing SONAME in a clean Debian12/Python3.14.8 base.
    missing=subprocess.run(['docker','run','--rm','python:3.14.8-slim-bookworm',
        'python','-c',"import ctypes;ctypes.CDLL('libGLESv2.so.2')"],capture_output=True,text=True)
    assert missing.returncode!=0 and 'libGLESv2.so.2' in missing.stderr,missing.stderr
    report['missing_gles_base_reproduced']=True
    args=['docker','run','-d','--name',NAME,'--memory=512m','--memory-swap=512m','--cpus=1','--network=host']
    for key,value in env.items():args.extend(['-e',key+'='+value])
    subprocess.run([*args,IMAGE],check=True,capture_output=True)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        try:
            status,mime,body=get('/healthz/')
            if status==200:break
        except (OSError,urllib.error.URLError):pass
        time.sleep(1)
    else:raise RuntimeError('Production entrypoint did not become healthy')
    assert json.loads(body)=={'status':'ok'}
    assert subprocess.check_output(['docker','exec',NAME,'id','-u'],text=True).strip()!='0'
    assert get('/robots.txt')[0]==301,'Production HTTPS redirect was bypassed'
    for path,mime in [('/robots.txt','text/plain'),('/static/customer/css/style.css','text/css'),('/static/ai/face-realtime.js','text/javascript')]:
        status,actual,body=get(path,True)
        assert status==200 and actual==mime,(path,status,actual)
        if path.endswith('face-realtime.js'):assert b'geolocation' not in body
        report['phases'].append({'path':path,'status':status,'mime':actual})
    state=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}',NAME],text=True))
    assert state['Running'] and not state['OOMKilled']
    report.update(passed=True,non_root=True,real_production_entrypoint=True,https_proxy=True,oom_killed=False)
finally:
    logs=subprocess.run(['docker','logs',NAME],capture_output=True,text=True)
    Path('production-startup.log').write_text(logs.stdout+logs.stderr,encoding='utf-8')
    Path('production-image-smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    subprocess.run(['docker','rm','-f',NAME],capture_output=True)
print(json.dumps(report))
