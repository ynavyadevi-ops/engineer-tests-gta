<#
.SYNOPSIS
  Packaged same-origin run: FastAPI serves the built UI and /api from one origin
  (http://127.0.0.1:8765 by default). Binds to loopback only.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run.ps1 -Build
  powershell -ExecutionPolicy Bypass -File scripts\run.ps1 -Mode demo -Port 8800 -DataDir 'D:\GTA lab data'
#>
[CmdletBinding()]
param(
    [switch]$Build,
    [ValidateSet('demo', 'live')][string]$Mode,
    [ValidateRange(1024, 65535)][int]$Port,
    [string]$DataDir
)

. "$PSScriptRoot\_common.ps1"

try {
    Assert-Toolchain
    $index = Join-Path $FrontendDir 'dist\index.html'
    if ($Build -or -not (Test-Path -LiteralPath $index)) {
        Write-Step 'Building the UI (npm run build)'
        Invoke-Native npm @('run', 'build') -WorkingDirectory $FrontendDir
    }

    $serveArgs = @('run', '--locked', 'python', '-m', 'gta_lab', 'serve')
    if ($Mode) { $serveArgs += @('--mode', $Mode) }
    if ($Port) { $serveArgs += @('--port', "$Port") }
    if ($DataDir) { $serveArgs += @('--data-dir', $DataDir) }

    Write-Step 'Starting the local app (Ctrl+C to stop)'
    Invoke-Native uv $serveArgs
    exit 0
}
catch {
    Write-Host "run FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
