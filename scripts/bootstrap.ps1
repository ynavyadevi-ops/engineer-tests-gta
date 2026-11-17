<#
.SYNOPSIS
  Install backend and frontend dependencies exactly as locked.
.DESCRIPTION
  Uses `uv sync --locked` and `npm ci`, so it never changes uv.lock or package-lock.json.
  -Clean removes the repo-local .venv, frontend\node_modules and frontend\dist first
  (a locked rebuild from scratch). Nothing outside the repo is deleted.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
  powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -Clean
#>
[CmdletBinding()]
param([switch]$Clean)

. "$PSScriptRoot\_common.ps1"

try {
    Write-Step 'Checking toolchain'
    Assert-Toolchain

    if ($Clean) {
        Write-Step 'Removing repo-local build state (.venv, node_modules, dist)'
        foreach ($rel in @('.venv', 'frontend\node_modules', 'frontend\dist')) {
            $path = Join-Path $RepoRoot $rel
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Recurse -Force
                Write-Host "removed $rel"
            }
        }
    }

    Write-Step 'Backend: uv sync --locked (Python pinned by .python-version)'
    Invoke-Native uv @('sync', '--locked')

    Write-Step 'Frontend: npm ci'
    Invoke-Native npm @('ci', '--no-fund') -WorkingDirectory $FrontendDir

    Write-Step 'Bootstrap complete'
    Invoke-Native uv @('run', '--locked', 'python', '--version')
    exit 0
}
catch {
    Write-Host "bootstrap FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
