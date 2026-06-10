param(
  [int[]]$Ports = @(8000, 5173, 8010, 5174, 8020, 5175)
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeDir = Join-Path $Root ".agenthub-runtime\parallel"
$ServicesFile = Join-Path $RuntimeDir "services.json"

function Stop-ProcessId {
  param([int]$ProcessId)

  if ($ProcessId -and (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  }
}

if (Test-Path $ServicesFile) {
  $services = Get-Content $ServicesFile -Raw | ConvertFrom-Json
  foreach ($service in @($services)) {
    Stop-ProcessId -ProcessId ([int]$service.backendPid)
    Stop-ProcessId -ProcessId ([int]$service.frontendPid)
  }
}

$processIds = @()
foreach ($port in $Ports) {
  $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
  if ($connections) {
    $processIds += $connections | Select-Object -ExpandProperty OwningProcess -Unique
  }
}

$processIds = $processIds | Where-Object { $_ -and $_ -ne $PID } | Select-Object -Unique
foreach ($processId in $processIds) {
  Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

Write-Host "AgentHub three-shell processes stopped."
