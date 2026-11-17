<#
.SYNOPSIS
  Full local check. Runs every step, prints a summary, exits 1 if any step failed.
.DESCRIPTION
  Lockfile consistency, Ruff, pytest, TypeScript, Vitest, a production build with a
  synthetic secret sentinel in the environment followed by a bundle scan, a real-process
  smoke test (keyless start + sentinel-key start, checking /api/status), and dependency
  audits (npm audit, pip-audit). -SkipAudit skips only the audits (they need network);
  skipped audits are reported as "not run", never as clean.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\check.ps1
#>
[CmdletBinding()]
param([switch]$SkipAudit)

. "$PSScriptRoot\_common.ps1"

# Synthetic, obviously-fake sentinel. Never a real key.
$Sentinel = 'SENTINEL-not-a-real-key-check-4b8e'
$results = [System.Collections.Generic.List[object]]::new()

function Invoke-Check([string]$Name, [scriptblock]$Body) {
    Write-Step $Name
    try {
        & $Body
        $results.Add([pscustomobject]@{ Check = $Name; Result = 'passed'; Detail = '' })
    }
    catch {
        Write-Host "  FAILED: $($_.Exception.Message)" -ForegroundColor Red
        $results.Add([pscustomobject]@{ Check = $Name; Result = 'failed'; Detail = $_.Exception.Message })
    }
}

function Test-ServerStatus([hashtable]$Vars, [string]$Label) {
    $port = Get-FreeLoopbackPort
    $dataDir = Join-Path ([IO.Path]::GetTempPath()) "gta lab check $port"
    $Vars['GTA_LAB_PORT'] = "$port"
    $Vars['GTA_LAB_DATA_DIR'] = $dataDir
    $Vars['GTA_LAB_ENV_FILE'] = Join-Path $dataDir 'no-private.env'
    $proc = $null
    try {
        Invoke-WithEnv $Vars {
            $script:proc = Start-Process -FilePath 'uv' `
                -ArgumentList @('run', '--locked', 'python', '-m', 'gta_lab', 'serve') `
                -WorkingDirectory $RepoRoot -NoNewWindow -PassThru
        }
        $proc = $script:proc
        $body = $null
        for ($i = 0; $i -lt 60 -and $null -eq $body; $i++) {
            if ($proc.HasExited) { throw "$Label server exited early (code $($proc.ExitCode))" }
            try {
                $body = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 `
                        -Uri "http://127.0.0.1:$port/api/status").Content
            }
            catch { Start-Sleep -Milliseconds 500 }
        }
        if ($null -eq $body) { throw "$Label server did not answer /api/status" }
        if ($body.Contains($Sentinel)) { throw "$Label /api/status leaked the key value" }
        $status = $body | ConvertFrom-Json
        if ($status.api -ne 'ok') { throw "$Label api != ok" }
        Write-Host "  $Label -> mode=$($status.mode) youtube_api_key=$($status.youtube_api_key) ui_build=$($status.ui_build)"
        return $status
    }
    finally {
        Stop-ProcessTree $proc
        if (Test-Path -LiteralPath $dataDir) { Remove-Item -LiteralPath $dataDir -Recurse -Force }
    }
}

try { Assert-Toolchain } catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }

Invoke-Check 'uv.lock is in sync with pyproject.toml' { Invoke-Native uv @('lock', '--check') }
Invoke-Check 'Ruff lint' { Invoke-Native uv @('run', '--locked', 'ruff', 'check', '.') }
Invoke-Check 'Ruff format' { Invoke-Native uv @('run', '--locked', 'ruff', 'format', '--check', '.') }
Invoke-Check 'Backend tests (pytest)' { Invoke-Native uv @('run', '--locked', 'pytest') }
Invoke-Check 'Frontend typecheck (tsc)' {
    Invoke-Native npm @('run', 'typecheck') -WorkingDirectory $FrontendDir
}
Invoke-Check 'Frontend tests (vitest)' { Invoke-Native npm @('test') -WorkingDirectory $FrontendDir }
Invoke-Check 'Production build with secret sentinel + bundle scan' {
    Invoke-WithEnv @{ YOUTUBE_API_KEY = $Sentinel; SECRET_SENTINEL = $Sentinel } {
        Invoke-Native npm @('run', 'build') -WorkingDirectory $FrontendDir
        Invoke-Native npm @('run', 'scan:bundle') -WorkingDirectory $FrontendDir
    }
}
Invoke-Check 'Real server starts with no key' {
    $s = Test-ServerStatus @{ YOUTUBE_API_KEY = $null; GTA_LAB_MODE = $null } 'keyless'
    if ($s.youtube_api_key -ne 'not configured' -or $s.mode -ne 'demo') { throw 'unexpected keyless status' }
}
Invoke-Check 'Real server never returns the key in /api/status' {
    $s = Test-ServerStatus @{ YOUTUBE_API_KEY = $Sentinel; GTA_LAB_MODE = 'live' } 'sentinel-key'
    if ($s.youtube_api_key -ne 'configured') { throw 'key not detected' }
}

if ($SkipAudit) {
    $results.Add([pscustomobject]@{ Check = 'Dependency audits'; Result = 'not run'; Detail = '-SkipAudit' })
}
else {
    Invoke-Check 'npm audit (all deps, high+ fails)' {
        Invoke-Native npm @('audit', '--audit-level=high') -WorkingDirectory $FrontendDir
    }
    Invoke-Check 'pip-audit (locked Python env)' {
        Invoke-Native uv @('run', '--locked', 'pip-audit', '--skip-editable', '--progress-spinner', 'off')
    }
}

Write-Host ''
$results | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
$failed = @($results | Where-Object { $_.Result -eq 'failed' })
if ($failed.Count -gt 0) {
    Write-Host "check FAILED: $($failed.Count) step(s) failed" -ForegroundColor Red
    exit 1
}
Write-Host 'check passed' -ForegroundColor Green
exit 0
