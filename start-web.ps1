$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:RAG_SERVER_MODE = 'local'
$env:RAG_ALLOWED_ORIGINS = 'http://127.0.0.1:3000,http://localhost:3000'
$env:RAG_API_URL = 'http://127.0.0.1:8000'
$env:RAG_INCLUDE_EVALUATIONS = '1'
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCommand) { $nodeExe = $nodeCommand.Source } else {
    $nodeExe = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    if (-not (Test-Path -LiteralPath $nodeExe)) { throw 'Install Node.js 20+ to build the frontend.' }
}
& $nodeExe frontend/build.mjs
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$logDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
foreach ($port in @(8000,3000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is occupied; close the existing project service or reuse its address."
    }
}
$backend = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','financial_rag.server:app','--host','127.0.0.1','--port','8000','--no-access-log' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput "$logDir\web-backend.log" -RedirectStandardError "$logDir\web-backend.err" -PassThru
$frontend = Start-Process -FilePath $python -ArgumentList '-m','http.server','3000','--bind','127.0.0.1','--directory','frontend/dist' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput "$logDir\web-frontend.log" -RedirectStandardError "$logDir\web-frontend.err" -PassThru
@{backend=$backend.Id;frontend=$frontend.Id} | ConvertTo-Json | Set-Content -Encoding UTF8 "$logDir\web-processes.json"
Write-Host 'Open http://127.0.0.1:3000 ; process IDs saved in logs/web-processes.json'
