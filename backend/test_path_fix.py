"""Test: Mabel reads file from Documents (outside workspace)."""
import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:19842'

resp = urllib.request.urlopen(BASE+'/api/agents')
mabel = next(a for a in json.loads(resp.read().decode('utf-8')) if a['id']=='mabel')

if 'drawio-skill' not in mabel.get('skills',[]):
    new_sk = list(mabel.get('skills',[])) + ['drawio-skill']
    payload = {k:v for k,v in mabel.items() if k not in ('model_name','model_provider')}
    payload['skills'] = new_sk
    body = json.dumps(payload).encode()
    req = urllib.request.Request(BASE+'/api/agents',data=body,headers={'Content-Type':'application/json'},method='POST')
    urllib.request.urlopen(req)

body = json.dumps({'agent_id':'mabel','title':'test path'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads',data=body,headers={'Content-Type':'application/json'})
tid = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['id']
print(f'Thread: {tid}')

prompt = '请读取 "C:\\Users\\yanzichen\\Documents\\ad_mp_top - 副本.drawio" 这个文件，告诉我它有几页，每一页叫什么名字'
body = json.dumps({'content':prompt,'permission_mode':'auto'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads/'+tid+'/messages',data=body,
    headers={'Content-Type':'application/json','X-Permission-Mode':'auto'})

resp = urllib.request.urlopen(req,timeout=120)
text = ''
tc_list = []
while True:
    line = resp.readline()
    if not line: break
    line = line.decode('utf-8','replace').strip()
    if not line.startswith('data: '): continue
    try:
        d = json.loads(line[6:])
        evt = d.get('event','')
        dd = d.get('data',{})
        if evt == 'tool_call':
            tc_list.append(dd)
            a = json.dumps(dd.get('args',{}),ensure_ascii=False)[:200]
            print(f'  [{len(tc_list)}] {dd.get("name","?")}: {a}')
        elif evt == 'tool_result':
            r = str(dd.get('result',''))[:120]
            if r: print(f'       -> {r}')
        elif d.get('token'): text += d['token']
        elif d.get('done'): print(f'  [DONE]')
        elif d.get('error'): print(f'  [ERR] {d["error"]}')
    except: pass

print(f'\nResponse ({len(text)} chars):')
print(text[:800] if text else '(empty)')
print(f'\nTool calls: {len(tc_list)}')

# Reset
new_sk = [s for s in mabel.get('skills',[]) if s != 'drawio-skill']
payload = {k:v for k,v in mabel.items() if k not in ('model_name','model_provider')}
payload['skills'] = new_sk
body = json.dumps(payload).encode()
req = urllib.request.Request(BASE+'/api/agents',data=body,headers={'Content-Type':'application/json'},method='POST')
urllib.request.urlopen(req)
print('Done - Mabel reset')
