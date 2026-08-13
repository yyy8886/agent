"""Test whether Mabel can use draw.io CLI (with correct command name)."""
import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:19842'

body = json.dumps({'agent_id':'mabel','title':'test drawio cli v2'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads',data=body,headers={'Content-Type':'application/json'})
tid = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['id']
print(f'Thread: {tid}')

prompt = (
    '请依次运行下面两条命令，并把各自的完整输出告诉我：\n\n'
    '1. draw.io --version\n'
    '2. drawio --version\n\n'
    '两条都要运行，报告各自结果。'
)

body = json.dumps({'content':prompt,'permission_mode':'auto'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads/'+tid+'/messages',data=body,
    headers={'Content-Type':'application/json','X-Permission-Mode':'auto'})

print('\n=== Testing draw.io command names ===\n')
resp = urllib.request.urlopen(req, timeout=120)
text = ''
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
            print(f'  [tool] {dd.get("name","?")}: {json.dumps(dd.get("args",{}),ensure_ascii=False)[:120]}')
        elif evt == 'tool_result':
            r = str(dd.get('result',''))[:300]
            if r and r != '(无输出)':
                print(f'    -> {r}')
        elif 'token' in d:
            text += d['token']
        elif d.get('done'):
            print(f'  [DONE]')
        elif d.get('error'):
            print(f'  [ERR] {d["error"]}')
    except: pass

print(f'\n=== Mabel response ===')
print(text[:1000] if text else "(empty)")
