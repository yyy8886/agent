#!/usr/bin/env python3
"""IP 地址定位查询脚本。

用法:
    python ip_lookup.py [IP地址]
    不带参数则查询本机公网 IP 的位置。

示例:
    python ip_lookup.py 8.8.8.8
    python ip_lookup.py
"""

import json
import sys
import urllib.request


def get_public_ip() -> str:
    """获取本机公网 IP。"""
    with urllib.request.urlopen("https://api.ipify.org", timeout=10) as resp:
        return resp.read().decode("utf-8").strip()


def lookup_ip(ip: str) -> dict:
    """查询 IP 地理位置信息（使用 ip-api.com 免费接口）。"""
    url = f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,lat,lon,timezone,isp,org,as,query"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else get_public_ip()
    print(f"查询 IP: {ip}")
    print("-" * 40)

    result = lookup_ip(ip)

    if result.get("status") != "success":
        print(f"查询失败: {result.get('message', '未知错误')}")
        sys.exit(1)

    print(f"国家:     {result.get('country', 'N/A')}")
    print(f"地区:     {result.get('regionName', 'N/A')}")
    print(f"城市:     {result.get('city', 'N/A')}")
    print(f"纬度:     {result.get('lat', 'N/A')}")
    print(f"经度:     {result.get('lon', 'N/A')}")
    print(f"时区:     {result.get('timezone', 'N/A')}")
    print(f"ISP:      {result.get('isp', 'N/A')}")
    print(f"组织:     {result.get('org', 'N/A')}")
    print(f"ASN:      {result.get('as', 'N/A')}")


if __name__ == "__main__":
    main()
