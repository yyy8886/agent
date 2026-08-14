import zlib, base64, re

path = r'C:\Users\yanzichen\Documents\ad_mp_top.drawio'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

diagrams = re.findall(r'<diagram[^>]*>(.*?)</diagram>', content, re.DOTALL)
print(f'页面数量: {len(diagrams)}')

for i, d in enumerate(diagrams):
    print(f'--- 页面 {i+1} ---')
    try:
        decoded = base64.b64decode(d)
        print(f'  base64解码后长度: {len(decoded)}')
        # 尝试多种解压方式
        methods = {
            'zlib': lambda x: zlib.decompress(x),
            'raw-deflate': lambda x: zlib.decompress(x, -15),
            'gzip': lambda x: zlib.decompress(x, 16 + zlib.MAX_WBITS),
        }
        for name, fn in methods.items():
            try:
                result = fn(decoded)
                print(f'  {name} 解压成功, 长度: {len(result)}')
                print(f'  前200字符: {result[:200]}')
                break
            except Exception as e:
                print(f'  {name} 失败: {e}')
    except Exception as e:
        print(f'  base64解码失败: {e}')
