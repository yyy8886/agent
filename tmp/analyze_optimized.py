import sys, re, base64, zlib, urllib.parse
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# Read the optimized file
with open(r'C:\Users\yanzichen\Desktop\agent\tmp\workflow-diagnostics\ad_mp_top_optimized.drawio', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all diagram pages
pages = re.findall(r'<diagram[^>]*>(.*?)</diagram>', content, re.DOTALL)
print(f'共 {len(pages)} 页')

def decompress_page(text):
    if '%3C' in text:
        return urllib.parse.unquote(text)
    try:
        raw = base64.b64decode(text)
        inflated = zlib.decompress(raw, -zlib.MAX_WBITS).decode('utf-8')
        return urllib.parse.unquote(inflated)
    except Exception:
        return text

all_vertices = []
for i, page in enumerate(pages):
    xml_text = decompress_page(page)
    cells = re.findall(r'<mxCell[^>]*>', xml_text)
    vertices = [c for c in cells if 'vertex="1"' in c]
    print(f'\n=== 第{i+1}页: {len(vertices)} 个顶点 ===')
    
    # Group by fillColor
    color_groups = defaultdict(list)
    for c in vertices:
        label = re.search(r'value="([^"]*)"', c)
        label = label.group(1) if label else ''
        # Strip HTML tags for readability
        label_clean = re.sub(r'<[^>]+>', '', label)[:30]
        fill = re.search(r'fillColor=#([0-9a-fA-F]{6})', c)
        fill = fill.group(1) if fill else 'none'
        color_groups[fill].append(label_clean)
    
    for color, labels in sorted(color_groups.items(), key=lambda x: -len(x[1])):
        print(f'  #{color} ({len(labels)}): {labels[:5]}')
