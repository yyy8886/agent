import sys, re, base64, zlib, urllib.parse
from collections import defaultdict

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

# Look at page 3 and 4 nodes with fillColor=none that have labels
for page_idx in [2, 3]:
    xml_text = decompress_page(pages[page_idx])
    cells = re.findall(r'<mxCell[^>]*>', xml_text)
    vertices = [c for c in cells if 'vertex="1"' in c]
    
    print(f'\n=== 第{page_idx+1}页: fillColor=none 且有标签的节点 ===')
    for c in vertices:
        if 'fillColor' not in c:
            label = re.search(r'value="([^"]*)"', c)
            label = label.group(1) if label else ''
            label_clean = re.sub(r'<[^>]+>', '', label)[:40]
            if label_clean.strip():
                shape = re.search(r'shape=([^;]+)', c)
                shape = shape.group(1) if shape else 'rectangle'
                style = re.search(r'style="([^"]*)"', c)
                style = style.group(1) if style else ''
                is_image = 'shape=image' in style
                print(f'  [{shape}]{"" if not is_image else " [IMG]"} {label_clean}')
