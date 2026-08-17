import sys, re

sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\yanzichen\Documents\ad_mp_top_decompressed.xml', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract all vertex cells with fillColor=none or no fillColor
cells = re.findall(r'<mxCell[^>]*>', content)
vertices = [c for c in cells if 'vertex="1"' in c]

print('=== fillColor=none 或未设置填充色的节点 ===')
for c in vertices:
    if 'fillColor' not in c:
        label = re.search(r'value="([^"]*)"', c)
        label = label.group(1) if label else '(空)'
        shape = re.search(r'shape=([^;]+)', c)
        shape = shape.group(1) if shape else 'rectangle'
        style = re.search(r'style="([^"]*)"', c)
        style = style.group(1) if style else ''
        # Check if it's an image
        is_image = 'shape=image' in style
        print(f'  [{shape}]{"" if not is_image else " [IMAGE]"} label={label[:40]}')
