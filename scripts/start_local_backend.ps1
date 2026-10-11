param([int]$Port = 8000, [switch]$CopyToken)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'The local .venv is missing. Create it and install the README dependencies first.'
}
# Docker Desktop may be installed per-user and absent from an older shell's PATH.
foreach ($toolDirectory in @(
    (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'),
    (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'),
    (Join-Path $env:ProgramFiles 'Git\usr\bin')
)) {
    if (Test-Path -LiteralPath $toolDirectory) {
        $env:PATH = $toolDirectory + ';' + $env:PATH
    }
}
# Load demo defaults first, then local overrides. Never print configuration values.
foreach ($configFile in @('.env.example', '.env')) {
    $configPath = Join-Path $projectRoot $configFile
    if (-not (Test-Path -LiteralPath $configPath)) { continue }
    foreach ($line in Get-Content -LiteralPath $configPath -Encoding UTF8) {
        if ($line -match '^\s*([A-Z][A-Z0-9_]*)\s*=(.*)$') {
            $key = $Matches[1]
            $value = $Matches[2].Trim()
            if ($value.Length -ge 2 -and (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            )) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    }
}
if (-not $env:SENTINEL_OPERATOR_TOKEN) {
    $env:SENTINEL_OPERATOR_TOKEN = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    Write-Host 'Created a session operator token in $env:SENTINEL_OPERATOR_TOKEN. The value is not logged.'
}
if ($CopyToken) {
    Set-Clipboard -Value $env:SENTINEL_OPERATOR_TOKEN
    Write-Host 'Operator token copied to clipboard. Paste it into the dashboard connection screen.'
}
$runtimePath = Join-Path $projectRoot 'local-audit'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
$env:SENTINEL_DB_PATH = Join-Path $runtimePath 'local-server.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
Write-Host "Starting backend at http://127.0.0.1:$Port/docs. Ctrl+C stops it."
Push-Location $projectRoot
try {
    & $pythonPath -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
