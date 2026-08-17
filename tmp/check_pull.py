import sys, re, base64, zlib, urllib.parse

sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\yanzichen\Desktop\agent\tmp\workflow-diagnostics\ad_mp_top_optimized.drawio', 'r', encoding='utf-8') as f:
    content = f.read()

pages = re.findall(r'<diagram[^>]*>(.*?)</diagram>', content, re.DOTALL)

def decompress_page(text):
    if '%3C' in text:
        return urllib.parse.unquote(text)
    try:
        raw = base64.b64decode(text)
        inflated = zlib.decompress(raw, -zlib.MAX_WBITS).decode('utf-8')
        return urllib.parse.unquote(inflated)
    except Exception:
        return text

# Check page 3 nodes with e8f5e9 color
xml_text = decompress_page(pages[2])
cells = re.findall(r'<mxCell[^>]*>', xml_text)
vertices = [c for c in cells if 'vertex="1"' in c]

print('=== 第3页: #e8f5e9 节点 ===')
for c in vertices:
    if 'fillColor=#e8f5e9' in c:
        label = re.search(r'value="([^"]*)"', c)
        label = label.group(1) if label else ''
        label_clean = re.sub(r'<[^>]+>', '', label)[:80]
        print(f'  {label_clean}')
