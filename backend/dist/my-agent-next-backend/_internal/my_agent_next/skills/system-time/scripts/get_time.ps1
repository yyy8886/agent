# Query current system date and time
$now = Get-Date
$tz = (Get-TimeZone).Id

Write-Output "当前日期: $($now.ToString('yyyy-MM-dd'))"
Write-Output "当前时间: $($now.ToString('HH:mm:ss'))"
Write-Output "时区: $tz"
