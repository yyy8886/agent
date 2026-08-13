#!/usr/bin/env python3
"""检查 drawio 文件的所有页面结构。"""
import re
import sys

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'ad_mp_top.drawio'
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 找到所有 diagram 元素
    diagrams = re.findall(r'<diagram[^>]*>', content)
    print(f"diagram 元素数量: {len(diagrams)}")
    for i, d in enumerate(diagrams):
        print(f"\n--- diagram {i} ---")
        print(d[:300])
        # 检查是否包含 mxGraphModel（非压缩）
        # 找到该 diagram 的结束位置
        start = content.find(d)
        end = content.find('</diagram>', start)
        body = content[start:end]
        if '<mxGraphModel' in body:
            print("  状态: 非压缩（包含 mxGraphModel）")
        else:
            print("  状态: 压缩")

if __name__ == '__main__':
    main()
