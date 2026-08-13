"""Full test: Mabel independently optimizes drawio colors with vision model."""
import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:19842'

# Create fresh thread
body = json.dumps({'agent_id':'mabel','title':'optimize drawio colors v2'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads',data=body,headers={'Content-Type':'application/json'})
tid = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['id']
print(f'Thread: {tid}')

prompt = (
    '请帮我优化这个 drawio 文件的第1页（ad_mp_top）的配色方案，让配色更专业美观：\n\n'
    '"C:\\Users\\yanzichen\\Documents\\ad_mp_top - 副本.drawio"\n\n'
    '背景信息：\n'
    '1. 这是一个 5MB 的 drawio 文件，有4个页面，第1页的 diagram 内容是压缩编码的（base64 + zlib）\n'
    '2. 你已安装 drawio-skill，里面有 scripts/restyle.py 可以应用配色方案：\n'
    '   python skills/drawio-skill/scripts/restyle.py <file.drawio> --preset corporate -o <out.drawio>\n'
    '   可用 preset: corporate(商务蓝), colorblind-safe, dark, default, handdrawn\n'
    '3. restyle.py 只能处理非压缩页面，所以你需要先解压第1页\n'
    '   drawio 压缩格式：XML → urlencode → base64 → zlib 压缩\n'
    '   解压：zlib.decompress(data, -15) → base64.b64decode → urllib.parse.unquote\n'
    '4. 解压后重构为有效 .drawio，再用 restyle.py 应用 corporate 配色\n'
    '5. 最终输出保存到 "C:\\Users\\yanzichen\\Documents\\ad_mp_top_optimized.drawio"\n\n'
    '请独立完成：自己写解压脚本、重构、应用配色、验证。'
)

body = json.dumps({'content':prompt,'permission_mode':'auto'}).encode()
req = urllib.request.Request(BASE+'/api/chat/threads/'+tid+'/messages',data=body,
    headers={'Content-Type':'application/json','X-Permission-Mode':'auto'})

print('\n=== Mabel working (vision model)... ===\n')
resp = urllib.request.urlopen(req, timeout=400)
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
            name = dd.get('name','?')
            args_str = json.dumps(dd.get('args',{}),ensure_ascii=False)[:200]
            print(f'  [{len(tc_list)}] {name}: {args_str}')
        elif evt == 'tool_result':
            r = str(dd.get('result',''))[:250]
            if r and r != '(无输出)':
                print(f'       -> {r}')
        elif 'token' in d:
            text += d['token']
        elif d.get('done'):
            print(f'  [DONE]')
        elif d.get('error'):
            print(f'  [ERR] {d["error"]}')
    except Exception as e:
        print(f'  [parse: {e}]')

print(f'\n=== Response ===')
print(text[:1500] if text else "(empty)")

import os
out = 'C:\\Users\\yanzichen\\Documents\\ad_mp_top_optimized.drawio'
if os.path.exists(out):
    print(f'\nSUCCESS! Output: {out} ({os.path.getsize(out):,} bytes)')
else:
    print('\nNot found at expected path. Searching workspace...')
    ws = 'C:\\Users\\yanzichen\\Desktop\\agent\\backend\\my_agent_next'
    for f in os.listdir(ws):
        if f.endswith('.drawio') and ('optim' in f.lower() or 'corp' in f.lower() or 'restyle' in f.lower()):
            print(f'  Workspace: {os.path.join(ws, f)}')
