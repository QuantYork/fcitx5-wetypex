#!/usr/bin/python3
import json,sys,time,os
print(json.dumps({'event':'ready'}),flush=True)
preedit=''
for line in sys.stdin:
 r=json.loads(line);op=r.get('op')
 if op=='key':
  preedit+=r.get('key','');time.sleep(float(os.environ.get('PANEL_TEST_DELAY','0.03')))
 elif op in ('reset','close','open'):preedit=''
 candidates=['你好','测试'] if preedit and not os.environ.get('PANEL_TEST_NO_CANDIDATES') else []
 print(json.dumps(dict(session=r.get('session'),seq=r.get('seq'),epoch=r.get('epoch'),preedit=preedit,cursor=len(preedit),candidates=candidates,revision=r.get('seq')),ensure_ascii=True),flush=True)
