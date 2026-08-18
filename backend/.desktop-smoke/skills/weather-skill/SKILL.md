---
name: weather-skill
description: Query current weather conditions for any city using the free wttr.in API (no API key required). Use when the user asks about the weather, temperature, humidity, wind, or air quality for a specific city or location, such as "北京天气", "今天上海天气怎么样", "what's the weather in Tokyo". Automatically recognizes city names from natural language and returns temperature, weather condition, humidity, wind, and air quality. Best suited for quick weather lookups on the host machine.
license: MIT
metadata: {"author":"this application","version":"1.0.0","platforms":["windows","macos","linux"]}
---

# Weather Skill

## Overview

Query current weather conditions for any city using the free [wttr.in](https://wttr.in) API. No API key or registration required. Returns temperature, weather condition, humidity, wind, and air quality.

## When to use

- User asks "今天天气如何", "北京天气", "what's the weather in Tokyo".
- User mentions a city name and wants weather information.
- User needs temperature, humidity, wind, or air quality for a location.

## Usage

Run the bundled script with a city name:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/get_weather.ps1 -City "Beijing"
```

Or on macOS/Linux:

```bash
bash scripts/get_weather.sh "Beijing"
```

### City name handling

- The script accepts a city name in English or Chinese (e.g., `Beijing`, `北京`, `Tokyo`, `上海`).
- If the user says a city in Chinese, pass it directly (wttr.in supports Chinese city names).
- **If no city is provided, the script auto-detects the location by IP address** (wttr.in's `@auto_location`). This is useful when the user asks "今天天气怎么样" without specifying a city.
- When auto-detecting, the result is based on the exit IP and may be approximate. If the user is not in the detected city, ask them for the exact city name.

## Output

The script prints the following weather details in a concise format:
- Location and current temperature
- Weather condition (with emoji)
- Feels-like temperature
- Humidity
- Wind speed and direction
- Air quality (if available)

## Notes

- Uses the free wttr.in API, no key required.
- Requires internet access.
- Air quality data may not be available for all cities.
