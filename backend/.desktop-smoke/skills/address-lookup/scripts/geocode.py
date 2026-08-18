#!/usr/bin/env python3
"""地址解析（地理编码）脚本。

将地址文本转换为经纬度坐标，使用 OpenStreetMap Nominatim 免费 API。

用法:
    python geocode.py "地址文本"

示例:
    python geocode.py "北京市朝阳区建国路88号"
    python geocode.py "上海市浦东新区世纪大道100号"
"""

import json
import sys
import urllib.parse
import urllib.request


def geocode(address: str) -> list:
    """将地址文本解析为经纬度坐标列表。"""
    params = urllib.parse.urlencode({
        "q": address,
        "format": "json",
        "limit": 5,
        "addressdetails": 1,
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "address-lookup-skill/1.0",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    if len(sys.argv) < 2:
        print("用法: python geocode.py \"地址文本\"")
        sys.exit(1)

    address = " ".join(sys.argv[1:])
    print(f"解析地址: {address}")
    print("-" * 40)

    results = geocode(address)

    if not results:
        print("未找到匹配的地址。")
        sys.exit(1)

    for i, r in enumerate(results, 1):
        print(f"结果 {i}:")
        print(f"  显示名: {r.get('display_name', 'N/A')}")
        print(f"  纬度:   {r.get('lat', 'N/A')}")
        print(f"  经度:   {r.get('lon', 'N/A')}")
        addr = r.get("address", {})
        if addr:
            print(f"  城市:   {addr.get('city', addr.get('town', addr.get('county', 'N/A')))}")
            print(f"  省份:   {addr.get('state', 'N/A')}")
            print(f"  国家:   {addr.get('country', 'N/A')}")
        print()


if __name__ == "__main__":
    main()
