import base64, zlib, re, urllib.parse, collections

path = r'C:\Users\yanzichen\Documents\ad_mp_top.drawio'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

m = re.search(r'<diagram[^>]*>(.*?)</diagram>', content, re.DOTALL)
compressed = m.group(1).strip()
decoded = base64.b64decode(compressed)
xml = zlib.decompress(decoded, -15).decode('utf-8')
# URL 解码
xml = urllib.parse.unquote(xml)

with open(r'C:\Users\yanzichen\Documents\ad_mp_top_decompressed.xml', 'w', encoding='utf-8') as f:
    f.write(xml)

print('最终XML长度:', len(xml))
colors = collections.Counter()
for mm in re.finditer(r'fillColor=#([0-9A-Fa-f]{6})', xml):
    colors[mm.group(1).upper()] += 1
print('fillColor 颜色分布:')
for c, n in colors.most_common(30):
    print('  #%s: %d' % (c, n))
print('vertex 节点数:', xml.count('vertex="1"'))
print('edge 边数:', xml.count('edge="1"'))
