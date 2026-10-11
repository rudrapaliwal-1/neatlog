$ErrorActionPreference = 'Stop'
$frontendPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'frontend'
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules'))) {
    throw 'Install frontend dependencies with npm install from frontend/ first.'
}
$npmPath = (Get-Command npm.cmd -ErrorAction Stop).Source
Push-Location $frontendPath
try {
    & $npmPath run dev
} finally {
    Pop-Location
}
