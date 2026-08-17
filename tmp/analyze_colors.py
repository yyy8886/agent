import sys, re
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\yanzichen\Documents\ad_mp_top_decompressed.xml', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract all vertex cells with their labels and colors
cells = re.findall(r'<mxCell[^>]*>', content)
vertices = [c for c in cells if 'vertex="1"' in c]

# Group by fillColor and show labels
from collections import defaultdict
color_groups = defaultdict(list)
for c in vertices:
    label = re.search(r'value="([^"]*)"', c)
    label = label.group(1) if label else ''
    fill = re.search(r'fillColor=#([0-9a-fA-F]{6})', c)
    fill = fill.group(1) if fill else 'none'
    shape = re.search(r'shape=([^;]+)', c)
    shape = shape.group(1) if shape else 'rectangle'
    color_groups[fill].append((label[:50], shape))

print('按填充色分组（含标签）:')
for color, items in sorted(color_groups.items(), key=lambda x: -len(x[1])):
    print(f'\n=== #{color} ({len(items)} 个) ===')
    for label, shape in items[:15]:
        print(f'  [{shape}] {label}')
    if len(items) > 15:
        print(f'  ... 还有 {len(items)-15} 个')
