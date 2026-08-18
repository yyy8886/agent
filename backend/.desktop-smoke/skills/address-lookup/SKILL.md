---
name: address-lookup
description: 查询IP地址定位和地址地理编码。当用户需要查询某个IP地址的地理位置、获取本机公网IP位置，或将地址文本（如"北京市朝阳区建国路88号"）转换为经纬度坐标时使用此skill。
---

# 地址查询

## 概述

提供两种地址查询能力：
1. **IP 定位**：根据 IP 地址查询地理位置（国家、城市、经纬度、ISP 等）
2. **地址解析**：将地址文本转换为经纬度坐标

## 快速开始

### IP 地址定位

```bash
python skills/address-lookup/scripts/ip_lookup.py [IP地址]
```

- 带参数：查询指定 IP 的位置
- 不带参数：查询本机公网 IP 的位置

### 地址解析（地理编码）

```bash
python skills/address-lookup/scripts/geocode.py "地址文本"
```

示例：
```bash
python skills/address-lookup/scripts/geocode.py "北京市朝阳区建国路88号"
```

## 使用场景

### 场景 1：查询 IP 位置

用户说"帮我查一下 8.8.8.8 在哪"，运行：
```bash
python skills/address-lookup/scripts/ip_lookup.py 8.8.8.8
```

### 场景 2：查询本机位置

用户说"我在哪"，运行：
```bash
python skills/address-lookup/scripts/ip_lookup.py
```

### 场景 3：地址转坐标

用户说"帮我查一下上海外滩的经纬度"，运行：
```bash
python skills/address-lookup/scripts/geocode.py "上海市黄浦区中山东一路"
```

## 注意事项

- 两个 API 均免费、无需 key
- Nominatim 有 1 次/秒 的速率限制，连续查询需间隔
- 详细 API 文档见 [references/api_reference.md](references/api_reference.md)
