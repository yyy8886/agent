import uvicorn, threading, time, urllib.request, json, sys, io, os, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from my_agent_next.app.web_server import app
t = threading.Thread(target=uvicorn.run, args=(app,), kwargs={'host':'127.0.0.1','port':19838,'log_level':'error'}, daemon=True)
t.start()
time.sleep(2.5)
BASE = 'http://127.0.0.1:19838'

for d in ['my_agent_next/skills/drawio','my_agent_next/skills/drawio-skill']:
    if os.path.isdir(d): shutil.rmtree(d)

body = json.dumps({
    'source': 'skillsmp',
    'slug': 'agents365-ai-drawio-skill-skills-drawio-skill-skill-md',
    'github_url': 'https://github.com/Agents365-ai/drawio-skill/tree/main/skills/drawio-skill'
}).encode()
req = urllib.request.Request(f'{BASE}/api/marketplace/install', data=body, headers={'Content-Type':'application/json'})
resp = urllib.request.urlopen(req)
r = json.loads(resp.read().decode('utf-8'))
print(f'Name: {r["name"]}')
print(f'Extra files: {r.get("extra_files_downloaded",0)}')
print(f'Total files ({len(r["files"])}):')

skill_dir = f'my_agent_next/skills/{r["name"]}'
for f in sorted(r['files']):
    fpath = os.path.join(skill_dir, f)
    size = os.path.getsize(fpath) if os.path.isfile(fpath) else 0
    print(f'  {f} ({size} bytes)')

# Verify we have scripts
scripts_dir = os.path.join(skill_dir, 'scripts')
if os.path.isdir(scripts_dir):
    py_files = [f for f in os.listdir(scripts_dir) if f.endswith('.py')]
    print(f'\n.py files in scripts/: {len(py_files)}')
    for p in sorted(py_files)[:5]:
        print(f'  - {p}')
    if len(py_files) > 5:
        print(f'  ... and {len(py_files)-5} more')
