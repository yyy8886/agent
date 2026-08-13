#!/usr/bin/env python3
"""解压 drawio 文件第1页（ad_mp_top）的压缩内容。

drawio 压缩格式：XML 内容 → urlencode → base64 → zlib 压缩
解压：zlib decompress(-15) → base64 decode → url decode
"""
import re
import zlib
import base64
import urllib.parse
import sys

def decompress_drawio(compressed_str):
    """解压 drawio 的压缩内容。compressed_str 是 base64 字符串。"""
    # base64 decode
    compressed_bytes = base64.b64decode(compressed_str)
    # zlib decompress with wbits=-15 (raw deflate)
    try:
        raw = zlib.decompress(compressed_bytes, -15)
    except Exception:
        # 尝试标准 zlib
        raw = zlib.decompress(compressed_bytes)
    # url decode
    xml = urllib.parse.unquote(raw.decode('utf-8'))
    return xml

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'ad_mp_top.drawio'
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 找到第1个 diagram 元素（ad_mp_top）
    m = re.search(r'<diagram[^>]*name="ad_mp_top"[^>]*>(.*?)</diagram>', content, re.DOTALL)
    if not m:
        print("未找到 ad_mp_top diagram")
        return
    diagram_tag = m.group(0)
    compressed = m.group(1)
    print(f"diagram 标签: {diagram_tag[:200]}")
    print(f"压缩内容长度: {len(compressed)}")

    # 解压
    xml = decompress_drawio(compressed)
    print(f"解压后 XML 长度: {len(xml)}")
    print("=== 解压后 XML 前 2000 字符 ===")
    print(xml[:2000])

if __name__ == '__main__':
    main()
