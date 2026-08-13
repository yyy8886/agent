"""Bind new Codex system skills to Mabel."""
import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:19842'

def get(path):
    return json.loads(urllib.request.urlopen(BASE+path).read().decode('utf-8'))

def post(path, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(BASE+path, data=body, headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

# Check available skills
skills = get('/api/skills')
print('Available skills:', [s['name'] for s in skills])

# Get Mabel
agents = get('/api/agents')
mabel = next(a for a in agents if a['id'] == 'mabel')
print(f'\nMabel current skills: {mabel["skills"]}')

# Add new skills
new_skills = ['imagegen', 'openai-docs', 'plugin-creator']
current = set(mabel['skills'])
added = [s for s in new_skills if s not in current]
mabel['skills'] = list(current) + added
print(f'Adding: {added}')

payload = {k:v for k,v in mabel.items() if k not in ('model_name','model_provider')}
result = post('/api/agents', payload)
print(f'\nMabel final skills: {result["skills"]}')
print(f'Mabel model: {result["model_profile_id"]}')
