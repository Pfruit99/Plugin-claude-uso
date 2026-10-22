$j = $input | Out-String | ConvertFrom-Json
$limitsFile = Join-Path $env:USERPROFILE ".claude\usage_limits.json"

$five = $j.rate_limits.five_hour
$week = $j.rate_limits.seven_day
$ctx = $j.context_window.used_percentage

if ($five -or $week -or ($null -ne $ctx)) {
    $old = $null
    try { $old = Get-Content $limitsFile -Raw -ErrorAction Stop | ConvertFrom-Json } catch {}
    $out = [ordered]@{
        five_hour = if ($five) { @{ used_percentage = $five.used_percentage; resets_at = $five.resets_at } } else { $old.five_hour }
        seven_day = if ($week) { @{ used_percentage = $week.used_percentage; resets_at = $week.resets_at } } else { $old.seven_day }
        context   = if ($null -ne $ctx) { $ctx } else { $old.context }
        updated   = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    }
    $json = $out | ConvertTo-Json -Depth 4
    $stale = $true
    try { $stale = (Get-Date).ToUniversalTime().Subtract((Get-Item $limitsFile -ErrorAction Stop).LastWriteTimeUtc).TotalSeconds -gt 60 } catch {}
    # Solo reescribe si cambio algun valor o el archivo tiene mas de 60 s
    $same = $false
    if (-not $stale -and $old) {
        $same = ($old.five_hour.used_percentage -eq $out.five_hour.used_percentage) -and
                ($old.seven_day.used_percentage -eq $out.seven_day.used_percentage) -and
                ($old.context -eq $out.context)
    }
    if (-not $same) {
        $tmp = "$limitsFile.tmp"
        $json | Set-Content -Path $tmp -Encoding utf8
        Move-Item -Force $tmp $limitsFile
    }
}

$parts = @()
if ($five) { $parts += "5h: $([math]::Round($five.used_percentage))%" }
if ($week) { $parts += "7d: $([math]::Round($week.used_percentage))%" }
if ($null -ne $ctx) { $parts += "ctx: $([math]::Round($ctx))%" }
Write-Host ("[" + $j.model.display_name + "] " + ($parts -join " | "))
