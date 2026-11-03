"""Parse local application JavaScript in the running QA Edge; do not execute it."""
import json,urllib.request,websocket
from pathlib import Path
root=Path(__file__).resolve().parent.parent
targets=json.load(urllib.request.urlopen('http://127.0.0.1:9338/json'));target=next(t for t in targets if t['type']=='page')
ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=20,suppress_origin=True)
for index,path in enumerate([root/'static/admin/js/main.js',root/'static/ui/product.js',root/'static/ui/reports.js',root/'static/ui/dashboard.js',root/'static/location/maps.js',root/'static/ai/face-flow.js',root/'static/ai/assistant.js'],1):
    source=json.dumps(path.read_text(encoding='utf-8'));expression='(()=>{try{new Function('+source+');return "PASS";}catch(e){return e.stack;}})()'
    ws.send(json.dumps({'id':index,'method':'Runtime.evaluate','params':{'expression':expression,'returnByValue':True}}))
    while True:
        response=json.loads(ws.recv())
        if response.get('id')==index:print(path.name,json.dumps(response.get('result'),ensure_ascii=True));break
ws.close()
