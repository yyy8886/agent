"""Switch Mabel to the vision-capable gpt-5.6-sol model on the OpenAI proxy."""
import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:19842'

def get(path):
    return json.loads(urllib.request.urlopen(BASE+path).read().decode('utf-8'))

def post(path, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(BASE+path, data=body, headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

# 1. Update openai_proxy profile to use gpt-5.6-sol
profiles = get('/api/profiles')
proxy = next(p for p in profiles if p['id'] == 'openai_proxy')
print(f'Before: openai_proxy model = {proxy["model"]}')
proxy['model'] = 'gpt-5.6-sol'
proxy['name'] = 'OpenAI 兼容代理 (视觉)'
# api_key_env must be valid
proxy['api_key_env'] = 'OPENAI_API_KEY'
result = post('/api/profiles', proxy)
print(f'After: openai_proxy model = {result.get("model")}')

# 2. Switch Mabel to openai_proxy
agents = get('/api/agents')
mabel = next(a for a in agents if a['id'] == 'mabel')
print(f'\nBefore: mabel model_profile_id = {mabel["model_profile_id"]!r}')
# Remove model_name/model_provider if present (they were aliases)
payload = {k:v for k,v in mabel.items() if k not in ('model_name','model_provider')}
payload['model_profile_id'] = 'openai_proxy'
result = post('/api/agents', payload)
print(f'After: mabel model_profile_id = {result.get("model_profile_id")}')

print('\nDone! Mabel now uses gpt-5.6-sol (vision) via openai_proxy.')
