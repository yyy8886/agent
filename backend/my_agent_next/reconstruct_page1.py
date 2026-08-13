#!/usr/bin/env python3
"""重构 drawio 文件：将第1页（ad_mp_top）的压缩内容解压为明文 XML。

其他页面保持压缩不变。
"""
import re
import zlib
import base64
import urllib.parse
import sys

def decompress_drawio(compressed_str):
    """解压 drawio 的压缩内容。compressed_str 是 base64 字符串。"""
    compressed_bytes = base64.b64decode(compressed_str)
    try:
        raw = zlib.decompress(compressed_bytes, -15)
    except Exception:
        raw = zlib.decompress(compressed_bytes)
    xml = urllib.parse.unquote(raw.decode('utf-8'))
    return xml

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'ad_mp_top.drawio'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'ad_mp_top_decompressed.drawio'

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 找到第1个 diagram 元素（ad_mp_top）
    # 匹配 <diagram ...>...</diagram>
    pattern = re.compile(r'(<diagram[^>]*name="ad_mp_top"[^>]*>)(.*?)(</diagram>)', re.DOTALL)
    m = pattern.search(content)
    if not m:
        print("未找到 ad_mp_top diagram")
        sys.exit(1)

    open_tag = m.group(1)
    compressed = m.group(2)
    close_tag = m.group(3)

    # 解压
    xml = decompress_drawio(compressed)
    print(f"解压后 XML 长度: {len(xml)}")

    # 重构：将压缩内容替换为明文 XML
    # 注意：明文 XML 中可能包含 < 和 > 字符，需要转义吗？
    # 在 drawio 中，非压缩的 diagram 内容直接是 XML，不需要转义。
    # 但 diagram 元素内的 XML 是 mxGraphModel 的 XML 表示。
    # 实际上，drawio 的非压缩 diagram 内容就是直接的 XML。
    new_diagram = open_tag + xml + close_tag

    # 替换原内容
    new_content = content[:m.start()] + new_diagram + content[m.end():]

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"已写入: {output_file}")
    print(f"输出文件大小: {len(new_content)}")

if __name__ == '__main__':
    main()
