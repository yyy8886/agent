# 地址查询 API 参考

本 skill 使用两个免费 API 实现地址查询功能。

## 1. IP 地址定位 — ip-api.com

- **接口**: `http://ip-api.com/json/{ip}`
- **免费额度**: 非商业用途 45 次/分钟
- **无需 API key**

### 请求参数

| 参数 | 说明 |
|------|------|
| `fields` | 指定返回字段，用逗号分隔 |

### 常用字段

| 字段 | 说明 |
|------|------|
| `status` | 查询状态（success/fail） |
| `country` | 国家 |
| `regionName` | 省份/地区 |
| `city` | 城市 |
| `lat` / `lon` | 纬度 / 经度 |
| `timezone` | 时区 |
| `isp` | 互联网服务提供商 |
| `org` | 组织名称 |
| `as` | ASN 编号 |
| `query` | 查询的 IP |

### 示例响应

```json
{
  "status": "success",
  "country": "United States",
  "regionName": "California",
  "city": "Mountain View",
  "lat": 37.4056,
  "lon": -122.0775,
  "timezone": "America/Los_Angeles",
  "isp": "Google LLC",
  "org": "Google LLC",
  "as": "AS15169 Google LLC",
  "query": "8.8.8.8"
}
```

## 2. 地址解析（地理编码）— OpenStreetMap Nominatim

- **接口**: `https://nominatim.openstreetmap.org/search`
- **免费额度**: 1 次/秒（请遵守使用政策）
- **无需 API key**

### 请求参数

| 参数 | 说明 |
|------|------|
| `q` | 地址查询文本 |
| `format` | 响应格式（json） |
| `limit` | 返回结果数量（默认 5） |
| `addressdetails` | 是否返回详细地址信息（1/0） |

### 使用注意事项

1. **必须设置 User-Agent**，否则请求会被拒绝
2. **必须遵守 1 次/秒 的速率限制**
3. 建议设置 `Accept-Language` 为 `zh-CN` 以获得中文结果

### 示例响应

```json
[
  {
    "display_name": "建国路88号, 朝阳区, 北京市, 中国",
    "lat": "39.9087",
    "lon": "116.4575",
    "address": {
      "city": "北京市",
      "state": "北京市",
      "country": "中国"
    }
  }
]
```

## 3. 本机公网 IP 获取 — ipify

- **接口**: `https://api.ipify.org`
- **用途**: 获取本机公网 IP 地址
- **无需 API key**

## 4. 备用方案

如果上述 API 不可用，可考虑以下替代：

| 用途 | 服务 | 接口 |
|------|------|------|
| IP 定位 | ipinfo.io | `https://ipinfo.io/{ip}/json` |
| IP 定位 | ipapi.co | `https://ipapi.co/{ip}/json/` |
| 地理编码 | Open-Meteo | `https://geocoding-api.open-meteo.com/v1/search` |
