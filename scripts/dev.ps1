<#
.SYNOPSIS
  Development run: FastAPI with auto-reload on 127.0.0.1:8765 plus the Vite dev server
  on 127.0.0.1:5173, which proxies /api to the backend (same-origin in the browser).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Mode live -DataDir 'D:\GTA lab data'
  Open http://127.0.0.1:5173/ . Ctrl+C stops both servers.
#>
[CmdletBinding()]
param(
    [ValidateSet('demo', 'live')][string]$Mode,
    [string]$DataDir
)

. "$PSScriptRoot\_common.ps1"

$backend = $null
try {
    Assert-Toolchain
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir 'node_modules'))) {
        throw 'frontend\node_modules is missing. Run scripts\bootstrap.ps1 first.'
    }

    $vars = @{}
    if ($Mode) { $vars['GTA_LAB_MODE'] = $Mode }
    if ($DataDir) { $vars['GTA_LAB_DATA_DIR'] = $DataDir }

    Invoke-WithEnv $vars {
        Write-Step 'Starting backend (uvicorn --reload) on http://127.0.0.1:8765'
        # Env vars are inherited by the child process, so no quoting of paths is needed.
        $script:backend = Start-Process -FilePath 'uv' `
            -ArgumentList @('run', '--locked', 'python', '-m', 'gta_lab', 'serve', '--reload') `
            -WorkingDirectory $RepoRoot -NoNewWindow -PassThru

        Write-Step 'Starting Vite dev server on http://127.0.0.1:5173 (Ctrl+C to stop)'
        Invoke-Native npm @('run', 'dev') -WorkingDirectory $FrontendDir
    }
    exit 0
}
catch {
    Write-Host "dev FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Stop-ProcessTree $script:backend
}
