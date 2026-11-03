"""Derive final presentation QA from the proven isolated staff harness."""
from pathlib import Path
p=Path(__file__).with_name('staff_live_e2e.py')
s=p.read_text(encoding='utf-8').replace("8791","8792").replace("9340","9341").replace("'qa_staff'","'qa_premium'").replace("'sr_staff_qa_'","'sr_premium_qa_'")
s=s.replace("'network_failures':[]", "'network_failures':[],'http_errors':[]")
s=s.replace("if response.get('method')=='Runtime.exceptionThrown':", "if response.get('method')=='Network.responseReceived' and response['params']['response']['status']>=400:\n                        result['http_errors'].append({'url':response['params']['response']['url'],'status':response['params']['response']['status']})\n                    if response.get('method')=='Runtime.exceptionThrown':")
start=s.index("            cookies('CUSTOMER')",s.index("hr.payroll_state"))
end=s.index("            ws.close();ws=None",start)
s=s[:start]+'''            cookies('CUSTOMER')
            for index,path in enumerate(['/','/menu/','/booking/','/cart/','/ai/chat/','/account/','/chat/']):
                navigate(path)
                assert not js('document.body.classList.contains("staff-portal")')
                for width,height in [(1920,1080),(1366,768),(768,1024),(390,844)]:
                    cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.2)
                    assert not js('document.documentElement.scrollWidth>innerWidth'),(path,width)
                    result['pages'].append({'role':'CUSTOMER','path':path,'width':width,'height':height,'horizontal_overflow':False})
                    (OUT/f'customer-{index}-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
            result['checks'].append({'kind':'customer_navigation_footer_isolated','result':'PASS'})
            cdp('Network.clearBrowserCookies')
            for index,path in enumerate(['/login/','/register/']):
                navigate(path)
                assert js('document.querySelector(".auth-photo").naturalWidth>0')
                assert js('document.querySelector("input[type=password]")!==null')
                js('document.querySelector(".password-toggle").click()')
                assert js('document.querySelector(".password-toggle").getAttribute("aria-pressed")==="true"')
                js('document.querySelector(".password-toggle").click()')
                for width,height in [(1920,1080),(1366,768),(768,1024),(390,844)]:
                    cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.2)
                    assert not js('document.documentElement.scrollWidth>innerWidth'),(path,width)
                    result['pages'].append({'role':'ANONYMOUS','path':path,'width':width,'height':height,'horizontal_overflow':False})
                    (OUT/f'auth-{index}-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
            result['checks'].append({'kind':'auth_photo_password_toggle','result':'PASS'})
            assert not result['exceptions'],result['exceptions']
            assert not [e for e in result['http_errors'] if '/static/' in e['url']],result['http_errors']
''' +s[end:]
a="                        (OUT/f'{role.lower()}-{index}-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))"
s=s.replace(a,a+"\n                        if path=='/management/' and width==1366:\n                            size=cdp('Page.getLayoutMetrics')['cssContentSize'];(OUT/'manager-dashboard-full-1366.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}})['data']))")
a="                    (OUT/f'customer-{index}-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))"
s=s.replace(a,a+"\n                    if path=='/' and width==1366:\n                        size=cdp('Page.getLayoutMetrics')['cssContentSize'];(OUT/'customer-home-full-1366.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}})['data']))")
s=s.replace("if js('document.readyState===\"complete\" && !!document.querySelector(\"h1\")'):break","if js('location.href==='+json.dumps(BASE+path)+' && document.readyState===\"complete\" && !!document.querySelector(\"h1\")'):break")
s=s.replace("            def cookies(role):\n                for cookie in clients[role].jar:","            def cookies(role):\n                cdp('Page.navigate',{'url':'about:blank'})\n                for _ in range(50):\n                    if js('location.href===\"about:blank\" && document.readyState===\"complete\"'):break\n                    time.sleep(.05)\n                for cookie in clients[role].jar:")
Path(__file__).with_name('premium_live_e2e.py').write_text(s,encoding='utf-8')
print('scripts/premium_live_e2e.py generated')
