$ErrorActionPreference = 'Stop'
$recordPath = Join-Path $PSScriptRoot 'logs\web-processes.json'
if (-not (Test-Path -LiteralPath $recordPath)) { Write-Host 'No recorded web processes.'; exit 0 }
$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
foreach ($role in @('backend','frontend')) {
    $taskProcessId = [int]$record.$role
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$taskProcessId" -ErrorAction SilentlyContinue
    if (-not $parent) { continue }
    # PIDs can be reused: verify the recorded project launcher before stopping.
    $expected = if ($role -eq 'backend') { 'financial_rag.server:app' } else { 'http.server 3000' }
    if (-not $parent.CommandLine.Contains($PSScriptRoot) -or -not $parent.CommandLine.Contains($expected)) {
        Write-Warning "Recorded $role process does not match this project; skipped."
        continue
    }
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$taskProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        if ($child.Name -eq 'python.exe' -and $child.CommandLine.Contains($expected)) {
            Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        }
    }
    Stop-Process -Id $taskProcessId -ErrorAction SilentlyContinue
}
Write-Host 'Recorded project web services stopped.'
