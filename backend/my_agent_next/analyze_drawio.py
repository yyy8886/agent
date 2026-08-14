import zlib, base64, re, sys

path = r'C:\Users\yanzichen\Documents\ad_mp_top.drawio'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 提取所有 diagram 内容
diagrams = re.findall(r'<diagram[^>]*>(.*?)</diagram>', content, re.DOTALL)
print(f'页面数量: {len(diagrams)}')
for i, d in enumerate(diagrams):
    try:
        # drawio 压缩格式: 先 base64 解码，再 zlib 解压
        decoded = base64.b64decode(d)
        xml = zlib.decompress(decoded).decode('utf-8')
        print(f'--- 页面 {i+1} 解压后长度: {len(xml)} ---')
        verts = len(re.findall(r'vertex="1"', xml))
        edges = len(re.findall(r'edge="1"', xml))
        cells = len(re.findall(r'<mxCell', xml))
        print(f'  顶点: {verts}, 边: {edges}, mxCell: {cells}')
    except Exception as e:
        print(f'页面 {i+1} 解压失败: {e}')
        print(f'  前100字符: {d[:100]}')
