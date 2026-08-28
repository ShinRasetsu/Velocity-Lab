#!/usr/bin/env pwsh
# Velocity-Lab Deployment Verification Script

param(
    [string]$Phase = "after",
    [string]$Url = "https://shinrasetsu.github.io/Velocity-Lab/index.html"
)

Write-Host "=== Velocity-Lab Deploy Verification ($Phase) ===" -ForegroundColor Cyan
Write-Host "URL: $Url" -ForegroundColor Gray

try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 30
    $content = $response.Content
    
    $checks = @{
        "Page loads" = $response.StatusCode -eq 200
        "G-force ring CSS" = $content -match '\.g-force-ring\s*\{'
        "Conic-gradient" = $content -match 'conic-gradient'
        "CSS custom properties" = $content -match '--fore-pos'
        "Boot animations" = $content -match 'g-force-boot|tick-draw|ring-expand'
        "Larger gauge" = $content -match 'clamp\(12rem.*min\(80vw'
        "Purge button" = $content -match 'id="purge-btn"'
        "Gauge wrap large" = $content -match 'gauge-wrap.*large'
        "JS custom properties" = $content -match 'setProperty.*fore-pos'
        "No child bars" = $content -notmatch 'g-force-bar fore pos'
    }
    
    $passed = 0
    $failed = 0
    
    foreach ($check in $checks.Keys) {
        if ($checks[$check]) {
            Write-Host "  [PASS] $check" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "  [FAIL] $check" -ForegroundColor Red
            $failed++
        }
    }
    
    Write-Host ""
    $color = if ($failed -eq 0) { "Green" } else { "Red" }
Write-Host "Results: $passed passed, $failed failed" -ForegroundColor $color
    
    if ($failed -gt 0) { exit 1 } else { exit 0 }
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}