import zlib, base64, re
from urllib.parse import unquote

path = r'C:\Users\yanzichen\Documents\ad_mp_top.drawio'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

diagrams = re.findall(r'<diagram[^>]*>(.*?)</diagram>', content, re.DOTALL)
print(f'页面数量: {len(diagrams)}')

for i, d in enumerate(diagrams):
    decoded = base64.b64decode(d)
    xml_raw = zlib.decompress(decoded, -15)
    xml = unquote(xml_raw.decode('utf-8'))
    print(f'--- 页面 {i+1} 解压后长度: {len(xml)} ---')
    verts = len(re.findall(r'vertex="1"', xml))
    edges = len(re.findall(r'edge="1"', xml))
    cells = len(re.findall(r'<mxCell', xml))
    print(f'  顶点: {verts}, 边: {edges}, mxCell: {cells}')
    # 保存解压后的XML供后续分析
    with open(f'page{i+1}.xml', 'w', encoding='utf-8') as f:
        f.write(xml)
