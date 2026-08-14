---
name: weather
description: 查询指定城市的实时天气、温度、湿度、风速和未来预报。当用户询问天气、气温、是否下雨、穿衣建议等时使用。需要联网获取实时数据。
---

# Weather Skill

查询指定城市的实时天气信息。

## 功能

- 实时温度、体感温度
- 天气状况（晴/雨/多云等）
- 湿度、风速
- 未来 3 天预报

## 使用方式

调用脚本并传入城市名（支持中文或英文）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\get_weather.ps1 -City "北京"
```

或使用 Python 版本（跨平台，推荐）：

```bash
python scripts/get_weather.py "北京"
```

## 数据来源

使用 [wttr.in](https://wttr.in) 免费天气服务，无需 API key。

## 输出示例

```
城市: 北京
天气: 晴
温度: 25°C (体感 26°C)
湿度: 40%
风速: 12 km/h
未来3天: 晴 26°C / 多云 24°C / 小雨 20°C
```

## 注意事项

- 需要联网
- 城市名支持中文或英文（如 "北京" 或 "Beijing"）
- 若城市名含空格，请用引号包裹
