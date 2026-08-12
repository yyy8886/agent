"""Mabel optimizes first page of ad_mp_top drawio file by reading XML."""
import urllib.request, json, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:19842'

# Ensure Mabel has drawio-skill
resp = urllib.request.urlopen(BASE+'/api/agents')
mabel = next(a for a in json.loads(resp.read().decode('utf-8')) if a['id']=='mabel')
if 'drawio-skill' not in mabel.get('skills',[]):
    new_sk = list(mabel.get('skills',[])) + ['drawio-skill']
    payload = {k:v for k,v in mabel.items() if k not in ('model_name','model_provider')}
    payload['skills'] = new_sk
    body = json.dumps(payload).encode()
    req = urllib.request.Request(BASE+'/api/agents',data=body,headers={'Content-Type':'application/json'},method='POST')
    urllib.request.urlopen(req)
    print(f'Mabel skills updated')

# Create thread
body = json.dumps({'agent_id':'mabel','title':'optimize drawio page 1'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads',data=body,headers={'Content-Type':'application/json'})
tid = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['id']
print(f'Thread: {tid}')

# Step 1: Extract first page XML
print('\n=== Step 1: Extract first page ===')
prompt = (
    '请帮我优化 "C:\\Users\\yanzichen\\Documents\\ad_mp_top - 副本.drawio" 这个文件的第1页（ad_mp_top）。\n\n'
    '分两步走：\n'
    '1. 先写一个 Python 脚本 extract_page1.py，从原始文件中提取第一页的完整 XML 内容，保存到 page1_original.xml\n'
    '   注意：drawio 文件是 mxfile/mxGraphModel 结构的 XML，可能有压缩编码。直接读 XML 解析即可。\n'
    '2. 运行 python extract_page1.py，确认提取成功\n\n'
    '先完成第1步，我会在下一步告诉你优化方向。'
)
body = json.dumps({'content':prompt,'permission_mode':'auto'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads/'+tid+'/messages',data=body,
    headers={'Content-Type':'application/json','X-Permission-Mode':'auto'})

resp = urllib.request.urlopen(req,timeout=180)
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
            r = str(dd.get('result',''))[:150]
            if r and r != '(无输出)': print(f'       -> {r}')
        elif d.get('token'): text += d['token']
        elif d.get('done'): print(f'  [DONE]')
        elif d.get('error'): print(f'  [ERR] {d["error"]}')
    except: pass

print(f'\nResponse: {text[:800] if text else "(empty)"}')
print(f'Tool calls: {len(tc_list)}')
for tc in tc_list[-5:]:
    print(f'  - {tc.get("name","?")}')

# Check if page1 was extracted
if os.path.isfile('my_agent_next/page1_original.xml'):
    size = os.path.getsize('my_agent_next/page1_original.xml')
    print(f'\npage1_original.xml: {size} bytes - SUCCESS')
else:
    print('\npage1_original.xml: NOT CREATED')

print('\n=== Done Step 1 ===')
