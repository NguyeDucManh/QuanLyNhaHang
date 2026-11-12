"""Host-side driver. Measures only the Docker cgroup containing one Daphne process."""
import atexit,urllib.parse
import concurrent.futures,http.cookiejar,json,re,subprocess,time,urllib.request,urllib.error,zlib,struct,base64
from pathlib import Path
BASE='http://127.0.0.1:8100'
NAME='smart-restaurant-ci512'
def sample():
    script="cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/memory.current; cat /sys/fs/cgroup/memory.peak; cat /sys/fs/cgroup/memory.events"
    out=subprocess.check_output(['docker','exec',NAME,'sh','-c',script],text=True).splitlines()
    return {'limit_bytes':int(out[0]),'current_bytes':int(out[1]),'peak_bytes':int(out[2]),'events':dict(line.split() for line in out[3:])}
def client():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(opener,path,data=None,json_body=False,timeout=90):
    headers={}
    if data is not None:
        if json_body:
            jar=next(h.cookiejar for h in opener.handlers if isinstance(h,urllib.request.HTTPCookieProcessor))
            headers={'Content-Type':'application/json','X-CSRFToken':next(c.value for c in jar if c.name=='csrftoken')}
            data=json.dumps(data).encode()
        else:data=urllib.parse.urlencode(data).encode()
    started=time.perf_counter()
    try:
        response=opener.open(urllib.request.Request(BASE+path,data=data,headers=headers),timeout=timeout)
    except urllib.error.HTTPError as error:response=error
    body=response.read()
    return {'path':path,'status':response.code,'seconds':round(time.perf_counter()-started,3),'content_type':response.headers.get_content_type()},body
def login(role):
    opener=client();_,body=request(opener,'/login/')
    token=re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"',body)[1].decode()
    result,_=request(opener,'/login/',{'username':'business-'+role,'password':'CI-resource-probe-only-2026!','csrfmiddlewaretoken':token})
    assert result['status']==200,result
    return opener
def png():
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',320,320,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x80'*960)*320))+chunk(b'IEND',b'')
    return 'data:image/png;base64,'+base64.b64encode(data).decode()
report={'environment':'Docker cgroup512MiB,swap disabled,1 CPU,1 Daphne process; DB/browser/driver outside cgroup; CI-only loopback HTTP, production TLS not measured','phases':[]}
def preserve_report():
    try:report['last_memory']=sample()
    except Exception as exc:report['diagnostic_error']=type(exc).__name__
    Path('render512-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
atexit.register(preserve_report)
for _ in range(60):
    try:
        probe,_=request(client(),'/healthz/',timeout=2)
        if probe['status']==200:break
    except Exception:time.sleep(1)
else:raise RuntimeError('Daphne did not become ready')
report['baseline']=sample();assert report['baseline']['limit_bytes']==512*1024**2
admin=login('admin');customer=login('customer');staff=login('staff')
cases=[('public',client(),['/','/login/','/menu/']),('booking',customer,['/booking/','/membership/','/recommendations/']),('management',admin,['/management/','/management/tables/','/management/orders/','/management/kitchen/','/management/ingredients/','/management/payroll/','/management/payments/','/management/loyalty/']),('staff',staff,['/work/faceid/','/staff/','/work/'])]
for label,opener,paths in cases:
    results=[]
    for path in paths:
        result,_=request(opener,path);results.append(result)
        assert result['status']==200,result
    report['phases'].append({'name':label,'requests':results,'memory':sample()})
result,_=request(admin,'/management/ai/faces/quality/',{'frame':png()},True)
assert result['status']==400,result  # Valid image, deliberately no human face.
tensor,body=request(admin,'/__ci_face_tensor',{},True)
assert tensor['status']==200,tensor
report['phases'].append({'name':'real_face_models_no_identity','tensor':json.loads(body),'memory':sample()})
for message in ('Xin chào','nhà hàng có gì','chính sách đặt bàn'):
    result,_=request(customer,'/ai/chat/message/',{'message':message},True)
    assert result['status']==200,result
report['phases'].append({'name':'chatbot_grounded_tools_and_rag_fallback','memory':sample()})
before=sample()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results=list(pool.map(lambda _:request(client(),'/menu/')[0],range(30)))
assert all(row['status']==200 for row in results)
report['phases'].append({'name':'30_requests_3_concurrent','before':before,'memory':sample(),'requests':results})
report['final']=sample();report['oom']=int(report['final']['events'].get('oom_kill','0'))
assert report['oom']==0,report
assert int(report['final']['events'].get('oom','0'))==0,report
Path('render512-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
