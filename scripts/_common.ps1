# Shared helpers for the PowerShell wrappers. Windows PowerShell 5.1 compatible.
# Dot-source only:  . "$PSScriptRoot\_common.ps1"

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script:FrontendDir = Join-Path $script:RepoRoot 'frontend'
$script:MinNodeMajor = 24

function Write-Step([string]$Message) {
    Write-Host ''
    Write-Host "==> $Message" -ForegroundColor Cyan
}

# Run a native command; throw if it exits nonzero. Arguments are passed as an array,
# so paths with spaces survive intact.
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $script:RepoRoot
    )
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @Arguments
        $code = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($code -ne 0) {
        throw "'$FilePath $($Arguments -join ' ')' failed with exit code $code"
    }
}

function Assert-Tool([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found on PATH. Install it with: $InstallHint"
    }
}

function Assert-Toolchain {
    Assert-Tool 'uv' 'winget install --id astral-sh.uv -e'
    Assert-Tool 'node' 'winget install --id OpenJS.NodeJS.LTS -e'
    Assert-Tool 'npm' 'winget install --id OpenJS.NodeJS.LTS -e'
    $nodeVersion = (& node --version).Trim()
    $major = [int]($nodeVersion.TrimStart('v').Split('.')[0])
    if ($major -lt $script:MinNodeMajor) {
        throw "Node $nodeVersion is too old; need v$($script:MinNodeMajor) LTS or newer."
    }
    $uvVersion = (& uv --version).Trim()
    Write-Host "uv: $uvVersion | node: $nodeVersion | npm: $((& npm --version).Trim())"
}

# Run a script block with temporary process-scoped env vars, restoring them afterwards.
# A $null value removes the variable for the duration.
function Invoke-WithEnv {
    param([hashtable]$Vars, [scriptblock]$Body)
    $saved = @{}
    foreach ($name in $Vars.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $Vars[$name], 'Process')
    }
    try { & $Body }
    finally {
        foreach ($name in $saved.Keys) {
            [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
        }
    }
}

function Get-FreeLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return $listener.LocalEndpoint.Port } finally { $listener.Stop() }
}

function Stop-ProcessTree([System.Diagnostics.Process]$Process) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F *> $null
    }
}
