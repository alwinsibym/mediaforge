# Finds ffmpeg.exe on this PC and shows how to point MediaForge at it.
#
# Run from the mediaforge folder:
#   powershell -ExecutionPolicy Bypass -File scripts\find-ffmpeg.ps1

$ErrorActionPreference = "SilentlyContinue"

Write-Host ""
Write-Host "1. Can this terminal see ffmpeg on its PATH?"
$onPath = Get-Command ffmpeg
if ($onPath) {
    Write-Host "   Yes: $($onPath.Source)"
} else {
    Write-Host "   No. That is why MediaForge reports ffmpeg: false."
}

Write-Host ""
Write-Host "2. Searching for ffmpeg.exe (this can take a minute)..."
$roots = @(
    "$env:LOCALAPPDATA\Microsoft\WinGet",
    "$env:ProgramFiles",
    "${env:ProgramFiles(x86)}",
    "$env:ProgramData\chocolatey",
    "$env:USERPROFILE\scoop",
    "C:\ffmpeg"
) | Where-Object { $_ -and (Test-Path $_) }

$found = foreach ($root in $roots) {
    Get-ChildItem -Path $root -Filter ffmpeg.exe -Recurse -File
}
$found = @($found | Where-Object { $_ } | Sort-Object FullName -Unique)

if ($found.Count -eq 0) {
    Write-Host "   ffmpeg.exe was not found in the usual places."
    Write-Host ""
    Write-Host "   Install it again, then run this script once more:"
    Write-Host "     winget uninstall Gyan.FFmpeg"
    Write-Host "     winget install Gyan.FFmpeg"
    exit 1
}

foreach ($file in $found) {
    Write-Host "   Found: $($file.FullName)"
}

# Prefer a copy that actually runs.
$working = $null
foreach ($file in $found) {
    $version = & $file.FullName -version 2>$null | Select-Object -First 1
    if ($version) {
        $working = $file
        Write-Host ""
        Write-Host "3. Working copy: $($file.FullName)"
        Write-Host "   $version"
        break
    }
}

if (-not $working) {
    Write-Host ""
    Write-Host "   ffmpeg.exe exists but could not be run. Reinstall it:"
    Write-Host "     winget uninstall Gyan.FFmpeg"
    Write-Host "     winget install Gyan.FFmpeg"
    exit 1
}

$folder = $working.DirectoryName
Write-Host ""
Write-Host "4. Tell MediaForge where it is."
Write-Host ""
Write-Host "   For this terminal only (then start MediaForge from this same window):"
Write-Host "     `$env:MEDIAFORGE_FFMPEG_DIR = `"$folder`""
Write-Host ""
Write-Host "   Permanently (open a NEW terminal afterwards):"
Write-Host "     setx MEDIAFORGE_FFMPEG_DIR `"$folder`""
Write-Host ""
Write-Host "   Then check http://localhost:8000/api/health shows `"ffmpeg`": true."
