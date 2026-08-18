param(
    [string]$City = ""
)

# Weather query script using free wttr.in API (no key required)
# Usage:
#   powershell -ExecutionPolicy Bypass -File get_weather.ps1 -City "Beijing"
#   powershell -ExecutionPolicy Bypass -File get_weather.ps1            # auto-detect location by IP

$ErrorActionPreference = "Stop"

try {
    # If no city specified, auto-detect location by IP
    if ([string]::IsNullOrWhiteSpace($City)) {
        $City = "@auto_location"
    }

    # Query wttr.in JSON format
    $url = "https://wttr.in/$City`?format=j1&lang=zh"
    $response = Invoke-RestMethod -Uri $url -TimeoutSec 15

    $current = $response.current_condition[0]
    $area = $response.nearest_area[0]

    $cityName = $area.areaName[0].value
    $region = $area.region[0].value
    $country = $area.country[0].value

    $temp = $current.temp_C
    $feelsLike = $current.FeelsLikeC
    $weatherDesc = $current.lang_zh[0].value
    $humidity = $current.humidity
    $windSpeed = $current.windspeedKmph
    $windDir = $current.winddir16Point
    $cloud = $current.cloudcover

    # Air quality (if available)
    $airQuality = ""
    if ($current.air_quality) {
        $aqi = $current.air_quality."us-epa-index"
        if ($aqi) {
            $aqiLabel = switch ($aqi) {
                1 { "优" } 2 { "良" } 3 { "轻度污染" } 4 { "中度污染" } 5 { "重度污染" } 6 { "严重污染" }
                default { "未知" }
            }
            $airQuality = "空气质量: $aqiLabel (AQI $aqi)"
        }
    }

    # Build output
    Write-Output "=========================================="
    Write-Output "  $cityName ($region, $country) 天气"
    Write-Output "=========================================="
    Write-Output "天气状况: $weatherDesc"
    Write-Output "当前温度: ${temp}°C"
    Write-Output "体感温度: ${feelsLike}°C"
    Write-Output "湿度: ${humidity}%"
    Write-Output "风力: ${windDir} ${windSpeed}km/h"
    Write-Output "云量: ${cloud}%"
    if ($airQuality) { Write-Output $airQuality }
    Write-Output "=========================================="
    if ([string]::IsNullOrWhiteSpace($City) -or $City -eq "@auto_location") {
        Write-Output "位置: 根据IP自动定位 (可能不准确)"
    }
    Write-Output "数据来源: wttr.in (免费, 无需API key)"
}
catch {
    Write-Output "查询天气失败: $($_.Exception.Message)"
    Write-Output "请检查网络连接或城市名称是否正确。"
    exit 1
}
