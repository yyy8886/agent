$ErrorActionPreference = "Stop"

$backendRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing backend virtual environment: $python"
}

Push-Location $backendRoot
try {
    & $python -m PyInstaller --noconfirm --clean "my-agent-next-backend.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
