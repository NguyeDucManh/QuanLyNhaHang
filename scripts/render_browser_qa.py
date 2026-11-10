"""Read-only public home responsive checks in a separate headless Edge profile."""
import base64
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import websocket

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'artifacts'/'stripe-batch-browser'
OUT.mkdir(exist_ok=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8000/')
    parser.add_argument('--out',type=Path,default=OUT)
    parser.add_argument('--full-page',action='store_true')
    parser.add_argument('--browser',default=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sr-browser-',ignore_cleanup_errors=True) as profile:
        process=subprocess.Popen([args.browser,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=9347','--user-data-dir='+profile,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        ws=None
        try:
            for _ in range(40):
                try:
                    targets=json.load(urllib.request.urlopen('http://127.0.0.1:9347/json',timeout=2))
                    page=next(p for p in targets if p['type']=='page')
                    break
                except (OSError,StopIteration): time.sleep(.25)
            else: raise RuntimeError('Headless browser unavailable')
            ws=websocket.create_connection(page['webSocketDebuggerUrl'],timeout=20,suppress_origin=True)
            serial=0
            errors=[]
            responses=[]
            def call(method,params=None):
                nonlocal serial
                serial+=1
                ws.send(json.dumps({'id':serial,'method':method,'params':params or {}}))
                while True:
                    result=json.loads(ws.recv())
                    if result.get('method')=='Network.responseReceived':
                        response=result['params']['response']
                        if '/static/' in response['url']:
                            responses.append({'url':response['url'],'status':response['status'],'mimeType':response['mimeType']})
                    if result.get('method')=='Runtime.exceptionThrown':
                        detail=result['params']['exceptionDetails']
                        errors.append(detail.get('exception',{}).get('description',detail.get('text')))
                    if result.get('id')==serial:
                        if 'error' in result: raise RuntimeError(result['error'])
                        return result.get('result',{})
            call('Page.enable')
            call('Runtime.enable')
            rows=[]
            call('Network.enable')
            call('Network.setExtraHTTPHeaders',{'headers':{'X-Forwarded-Proto':'https'}})
            for width in [320,375,390,768,1024,1440]:
                call('Emulation.setDeviceMetricsOverride',{'width':width,'height':1000,'deviceScaleFactor':1,'mobile':False})
                call('Page.navigate',{'url':args.url})
                for _ in range(100):
                    state=call('Runtime.evaluate',{'expression':'document.readyState','returnByValue':True})
                    if state.get('result',{}).get('value')=='complete': break
                    time.sleep(.15)
                call('Runtime.evaluate',{'expression':'document.fonts.ready.then(()=>true)','awaitPromise':True,'returnByValue':True})
                time.sleep(.3)
                navigation=call('Runtime.evaluate',{'expression':"(()=>{const b=document.querySelector('#nav-toggle');if(!b)return null;b.click();const opened=b.getAttribute('aria-expanded')==='true';b.click();return opened&&b.getAttribute('aria-expanded')==='false'})()",'returnByValue':True})
                row=call('Runtime.evaluate',{'expression':"JSON.stringify({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,font:getComputedStyle(document.body).fontFamily,iconWidth:document.querySelector('svg.icon')?.getBoundingClientRect().width,guestMax:document.querySelector('[name=guests]')?.max,title:document.title,charts:document.querySelectorAll('[data-chart] svg').length,connection:document.querySelector('[data-connection]')?.textContent,bookingRows:document.querySelectorAll('.cc-booking-monitor tbody tr').length,forecastModel:document.querySelector('#forecast-chart')?.dataset.model,forecastPeriod:document.querySelector('select[name=days]')?.value,forecastNotice:document.querySelector('[data-forecast-chart-status]')?.textContent,checkboxWidth:document.querySelector('.booking-policy-actions input[type=checkbox]')?.getBoundingClientRect().width,qaChartModelPassed:window.__qaChartLines?Math.abs(window.__qaChartLines.at(-1).y-((document.querySelector('canvas').clientWidth<600?240:320)-40-0.5*((document.querySelector('canvas').clientWidth<600?240:320)-25-40)))<0.1:undefined})",'returnByValue':True})
                measurement=json.loads(row['result']['value'])
                measurement['mobileMenuToggle']=navigation.get('result',{}).get('value')
                rows.append(measurement)
                params={'format':'png','captureBeyondViewport':args.full_page}
                if args.full_page:
                    size=call('Page.getLayoutMetrics')['cssContentSize']
                    params['clip']={'x':0,'y':0,'width':size['width'],'height':min(size['height'],15000),'scale':1}
                shot=call('Page.captureScreenshot',params)
                (args.out/f'home-{width}.png').write_bytes(base64.b64decode(shot['data']))
            (args.out/'results.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
            (args.out/'asset-responses.json').write_text(json.dumps(responses,indent=2),encoding='utf-8')
            print(json.dumps(rows,ensure_ascii=True))
            (args.out/'javascript-errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
            print('JAVASCRIPT_ERRORS',len(errors))
        finally:
            if ws:
                try: call('Browser.close')
                except (OSError,websocket.WebSocketException): pass
            if ws: ws.close()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=15)


if __name__=='__main__': main()
