"""Test Mabel can now access any path (no more out-of-bounds errors)."""
import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:19842'

body = json.dumps({'agent_id':'mabel','title':'test path access'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads',data=body,headers={'Content-Type':'application/json'})
tid = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['id']
print(f'Thread: {tid}')

prompt = (
    '请用 read_file 工具读取下面这个文件的前 5 行，然后告诉我结果：\n\n'
    'C:\\Windows\\System32\\drivers\\etc\\hosts\n\n'
    '这个文件在系统目录 C:\\Windows 下。只需读取并报告前几行内容。'
)

body = json.dumps({'content':prompt,'permission_mode':'auto'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads/'+tid+'/messages',data=body,
    headers={'Content-Type':'application/json','X-Permission-Mode':'auto'})

print('\n=== Testing C:\\Windows path access ===\n')
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
            r = str(dd.get('result',''))[:400]
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
print(text[:800] if text else "(empty)")
