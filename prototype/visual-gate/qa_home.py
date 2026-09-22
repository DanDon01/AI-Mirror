"""Offline visual QA: synthetic cases are injected only into an isolated page.
Never changes the production state endpoint or credentials. Writes shots/home-*.
"""
import base64
import json
import re
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from capture_lib import CHROME, start_server
from websockets.sync.client import connect

HERE = Path(__file__).resolve().parent

def main():
    server, port = start_server()
    profile = tempfile.mkdtemp(prefix='mirror-home-qa-')
    proc = subprocess.Popen([CHROME, '--headless=new',
        '--no-first-run', '--disable-extensions', '--remote-debugging-port=9378',
        '--remote-allow-origins=*', '--user-data-dir=' + profile, 'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = None
        for _ in range(40):
            try:
                targets=json.load(urllib.request.urlopen('http://127.0.0.1:9378/json',timeout=1))
                url=next(t['webSocketDebuggerUrl'] for t in targets if t['type']=='page')
                break
            except Exception:
                time.sleep(.25)
        if not url:
            raise RuntimeError('QA Chrome did not start')
        with connect(url, max_size=32*1024*1024) as ws:
            seq=0
            def call(method,params=None):
                nonlocal seq
                seq+=1; ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
                while True:
                    msg=json.loads(ws.recv(timeout=20))
                    if msg.get('id')==seq:
                        if 'error' in msg: raise RuntimeError(msg['error'])
                        return msg.get('result',{})
            def evaluate(js):
                result=call('Runtime.evaluate',dict(expression=js,returnByValue=True,awaitPromise=True))
                if result.get('exceptionDetails'): raise RuntimeError(result['exceptionDetails'])
                return result.get('result',{}).get('value')
            call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=2560,deviceScaleFactor=1,mobile=False))
            call('Page.navigate',dict(url=f'http://127.0.0.1:{port}/control.html'))
            time.sleep(.4)
            # Production layout and panel builder, without live requests.
            html=(HERE/'index.html').read_text(encoding='utf-8')
            html=re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S)
            html=html.replace('</body>', '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script><script src="js/home-twin.js"></script><script src="js/panels.js"></script></body>')
            call('Page.setDocumentContent',dict(frameId=call('Page.getFrameTree')['frameTree']['frame']['id'],html=html))
            for _ in range(40):
                if evaluate("typeof HomeTwin !== 'undefined' && typeof THREE !== 'undefined'"):break
                time.sleep(.1)
            if not evaluate("typeof HomeTwin !== 'undefined' && typeof THREE !== 'undefined'"):
                raise RuntimeError('Three.js did not load for visual QA')
            evaluate('document.fonts.ready.then(()=>true)')
            evaluate("document.querySelector('.fixture-mark').textContent='OFFLINE VISUAL QA - SYNTHETIC SENSOR CASE';document.querySelector('.fixture-mark').style.display='block'")
            output=HERE/'shots';output.mkdir(exist_ok=True)
            cases=[('idle', {'car':{'charge_pct':42},'rooms':{'livingroom':{'curtain':'open'}}},20),
              ('night',{'watts_now':468,'weather':{'is_night':True},'car':{'charge_pct':42},'rooms':{'livingroom':{'curtain_position':100}}},4),
              ('ground',{'watts_now':468,'solar_watts':1400,'car':{'charge_pct':42},'rooms':{'downstairs':{'temperature_c':20.4},'upstairs':{'temperature_c':19.2},'livingroom':{'curtain_position':100}}},2),
              ('export',{'watts_now':-900,'solar_watts':1400,'car':{'charge_pct':42},'rooms':{'livingroom':{'curtain_position':100}}},4),
              ('charger',{'watts_now':6200,'car':{'charge_pct':42},'rooms':{'livingroom':{'curtain_position':100}}},5),
              ('car-away',{'watts_now':468,'devices':{'car_present':False},'rooms':{'livingroom':{'curtain_position':100}}},5),
              ('heavy-rain',{'watts_now':468,'weather':{'rain_mm_h':5.2,'wind_mph':42,'temperature_c':12,'condition':'rain'},'car':{'charge_pct':42},'rooms':{'livingroom':{'curtain_position':100}}},7),
              ('door-open',{'watts_now':468,'car':{'charge_pct':42},'devices':{'front_door_open':True},'rooms':{'livingroom':{'curtain_position':100}}},8),
              ('first',{'car':{'charge_pct':42},'rooms':{'downstairs':{'temperature_c':20.4},'upstairs':{'temperature_c':19.2},'livingroom':{'curtain_position':100}}},6),
              ('closed',{'solar_watts':2500,'car':{'charge_pct':42,'charging':True},'rooms':{'livingroom':{'curtain_position':0,'light':True,'occupied':True},'bedroom':{'occupied':True,'light':True},'porch':{'occupied':True},'external':{'occupied':True}}},16.7),
              ('partial',{'car':{'charge_pct':42},'rooms':{'livingroom':{'curtain_position':50,'light':True}}},3)]
            for name,data,t in cases:
                data.setdefault('watts_now',468)
                evaluate(f'Panels.apply({json.dumps({"energy": data})});Panels.frame(10,0)')
                evaluate(f'HomeTwin.update({json.dumps(data)},0)')
                for i in range(1,121): evaluate(f'Panels.frame(10,{i/24})')
                # Keep the scene clock deterministic for the captured frame.
                # Omitting the second argument would jump the camera to the
                # browser's unrelated performance clock immediately before
                # capture, masking actual layout regressions.
                evaluate(f'Panels.frame(10,{t},{t})')
                time.sleep(.1)
                shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
                (output/f'home-{name}.png').write_bytes(base64.b64decode(shot['data']))
                shot=call('Page.captureScreenshot',{'format':'png','clip':{'x':70,'y':330,'width':620,'height':480,'scale':2}})
                (output/f'home-{name}-detail.png').write_bytes(base64.b64decode(shot['data']))
                print(name,flush=True)
    finally:
        proc.terminate();server.shutdown()

if __name__=='__main__': main()
