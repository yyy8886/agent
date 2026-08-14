"""Check available models on the OpenAI proxy."""
import json
import urllib.request
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent / "my_agent_next"

with (PROJECT_DIR / ".env").open(encoding="utf-8") as f:
    for line in f:
        if line.startswith('OPENAI_API_KEY='):
            api_key = line.strip().split('=', 1)[1]
            break

url = 'https://sapi.nyro.lol/v1/models'
req = urllib.request.Request(url, headers={'Authorization': f'Bearer {api_key}'})
try:
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    models = sorted([m['id'] for m in data.get('data', [])])
    for m in models:
        print(m)
except Exception as e:
    print(f'Error: {e}')
