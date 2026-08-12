"""Full E2E: Mabel uses Agents365 drawio-skill (61 files from GitHub)."""
import uvicorn
import threading
import time
import urllib.request
import json
import sys
import io
import os
import re
import shutil

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from my_agent_next.app.web_server import app

t = threading.Thread(target=uvicorn.run, args=(app,), kwargs={'host': '127.0.0.1', 'port': 19839, 'log_level': 'error'}, daemon=True)
t.start()
time.sleep(2.5)

BASE = 'http://127.0.0.1:19839'

# 1. Verify drawio-skill is installed
skill_dir = 'my_agent_next/skills/drawio-skill'
if not os.path.isdir(skill_dir):
    print('ERROR: drawio-skill not installed. Run test_install.py first.')
    sys.exit(1)

from pathlib import Path
total_files = sum(1 for _ in Path(skill_dir).rglob('*') if _.is_file())
py_files = len([_ for _ in Path(skill_dir).rglob('*.py') if _.is_file()])
print(f'Skill: {total_files} files, {py_files} .py scripts')

# 2. Bind to Mabel
resp = urllib.request.urlopen(BASE + '/api/agents')
agents = json.loads(resp.read().decode('utf-8'))
mabel = next(a for a in agents if a['id'] == 'mabel')
new_skills = list(mabel.get('skills', [])) + ['drawio-skill']
payload = {k: v for k, v in mabel.items() if k not in ('model_name', 'model_provider')}
payload['skills'] = new_skills
body = json.dumps(payload).encode()
req = urllib.request.Request(BASE + '/api/agents', data=body, headers={'Content-Type': 'application/json'}, method='POST')
urllib.request.urlopen(req)
print(f'Mabel skills: {new_skills}')

# 3. Create thread
body = json.dumps({'agent_id': 'mabel', 'title': 'drawio e2e'}).encode()
req = urllib.request.Request(BASE + '/api/chat/threads', data=body, headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req)
thread = json.loads(resp.read().decode('utf-8'))
tid = thread['id']
print(f'Thread: {tid}')

# 4. Stream chat
print()
print('=== Mabel streaming ===')
prompt = '用 drawio 画一张图：三个椭圆分别是过去、现在、未来，用三条箭头首尾相连形成闭环（过去指向现在，现在指向未来，未来指向过去）。文件保存到 test_cycle.drawio'
body = json.dumps({'content': prompt, 'permission_mode': 'auto'}).encode()
req = urllib.request.Request(BASE + '/api/chat/threads/' + tid + '/messages', data=body,
                             headers={'Content-Type': 'application/json', 'X-Permission-Mode': 'auto'})

resp = urllib.request.urlopen(req, timeout=180)
text = ''
tc_list = []
while True:
    line = resp.readline()
    if not line:
        break
    line = line.decode('utf-8', 'replace').strip()
    if not line.startswith('data: '):
        continue
    try:
        d = json.loads(line[6:])
        if d.get('event') == 'tool_call':
            dd = d['data']
            tc_list.append(dd)
            a = json.dumps(dd.get('args', {}), ensure_ascii=False)[:150]
            print(f'  [{len(tc_list)}] {dd.get("name", "?")}: {a}')
        elif d.get('event') == 'tool_result':
            r = str(d.get('data', {}).get('result', ''))[:80]
            if r:
                print(f'       -> {r}')
        elif d.get('token'):
            text += d['token']
        elif d.get('done'):
            print(f'  [DONE]')
        elif d.get('error'):
            print(f'  [ERR] {d["error"]}')
    except Exception:
        pass

print(f'\nResponse: {len(text)} chars')
if text:
    print(text[:500])
print(f'Tool calls: {len(tc_list)}')
for tc in tc_list:
    print(f'  - {tc.get("name", "?")}')

# 5. Verify output
print()
out = 'my_agent_next/test_cycle.drawio'
if os.path.isfile(out):
    sz = os.path.getsize(out)
    with open(out, encoding='utf-8') as f:
        content = f.read()
    print(f'test_cycle.drawio: {sz} bytes')
    arrows = re.findall(r'<mxCell[^>]*edge="1"[^>]*>', content)
    print(f'Arrows found: {len(arrows)}')
    for a in arrows:
        src = re.search(r'source="([^"]*)"', a)
        tgt = re.search(r'target="([^"]*)"', a)
        val = re.search(r'value="([^"]*)"', a)
        s = src.group(1) if src else '?'
        t = tgt.group(1) if tgt else '?'
        v = val.group(1) if val else ''
        print(f'  {s} -> {t}: {v}')
    if '<mxGraphModel' in content:
        print('Valid drawio XML: YES')
else:
    print('ERROR: test_cycle.drawio not found!')

# 6. Cleanup
print()
print('=== Cleanup ===')
new_sk = [s for s in mabel.get('skills', []) if s != 'drawio-skill']
payload = {k: v for k, v in mabel.items() if k not in ('model_name', 'model_provider')}
payload['skills'] = new_sk
body = json.dumps(payload).encode()
req = urllib.request.Request(BASE + '/api/agents', data=body, headers={'Content-Type': 'application/json'}, method='POST')
urllib.request.urlopen(req)
print(f'Mabel reset: {new_sk}')

req = urllib.request.Request(BASE + '/api/marketplace/skills/drawio-skill', method='DELETE')
r = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
print(f'Delete drawio-skill: {r}')

if os.path.isfile(out):
    os.remove(out)
    print(f'Removed {out}')

print()
print('=== ALL DONE ===')
