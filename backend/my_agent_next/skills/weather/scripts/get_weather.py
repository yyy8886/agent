#!/usr/bin/env python3
"""查询天气的脚本（跨平台，使用 wttr.in 免费服务）"""
import sys
import json
import urllib.request
import urllib.parse

def fetch_weather(city):
    """获取指定城市的天气数据"""
    encoded = urllib.parse.quote(city)
    url = f"https://wttr.in/{encoded}?format=j1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def main():
    if len(sys.argv) < 2:
        print("用法: python get_weather.py <城市名>")
        sys.exit(1)

    city = sys.argv[1]
    data = fetch_weather(city)

    if "error" in data:
        print(f"查询失败: {data['error']}")
        sys.exit(1)

    try:
        current = data["current_condition"][0]
        temp = current["temp_C"]
        feels = current["FeelsLikeC"]
        humidity = current["humidity"]
        windspeed = current["windspeedKmph"]
        desc = current["weatherDesc"][0]["value"]

        # 未来3天预报
        forecast = []
        for day in data["weather"][:3]:
            date = day["date"]
            max_t = day["maxtempC"]
            min_t = day["mintempC"]
            day_desc = day["hourly"][4]["weatherDesc"][0]["value"]
            forecast.append(f"{date} {day_desc} {min_t}~{max_t}°C")

        print(f"城市: {city}")
        print(f"天气: {desc}")
        print(f"温度: {temp}°C (体感 {feels}°C)")
        print(f"湿度: {humidity}%")
        print(f"风速: {windspeed} km/h")
        print("未来3天:")
        for f in forecast:
            print(f"  {f}")
    except Exception as e:
        print(f"解析数据失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
