import sys, re
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\yanzichen\Documents\ad_mp_top_decompressed.xml', 'r', encoding='utf-8') as f:
    content = f.read()

# Count cells
cells = re.findall(r'<mxCell[^>]*>', content)
print('总 mxCell 数量:', len(cells))

# Find vertex cells
vertices = [c for c in cells if 'vertex="1"' in c]
print('顶点(vertex)数量:', len(vertices))

# Extract fillColor values
fill_colors = re.findall(r'fillColor=#([0-9a-fA-F]{6})', content)
color_counts = Counter(fill_colors)
print('\n填充色统计:')
for color, count in color_counts.most_common(40):
    print(f'  #{color}: {count}')

# Extract node labels and their styles
print('\n\n节点类型分析 (label + shape + fillColor):')
node_info = {}
for c in vertices:
    label = re.search(r'value="([^"]*)"', c)
    label = label.group(1) if label else ''
    shape = re.search(r'shape=([^;]+)', c)
    shape = shape.group(1) if shape else 'rectangle'
    fill = re.search(r'fillColor=#([0-9a-fA-F]{6})', c)
    fill = fill.group(1) if fill else 'none'
    key = (shape, fill)
    if key not in node_info:
        node_info[key] = {'count': 0, 'examples': []}
    node_info[key]['count'] += 1
    if len(node_info[key]['examples']) < 3:
        node_info[key]['examples'].append(label[:30])

print(f'\n共 {len(node_info)} 种 (shape, fillColor) 组合:')
for (shape, fill), info in sorted(node_info.items(), key=lambda x: -x[1]['count']):
    print(f'  shape={shape}, fill=#{fill}: {info["count"]} 个, 示例: {info["examples"]}')
