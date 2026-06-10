param(
  [int]$LocalBackendPort = 8000,
  [int]$LocalFrontendPort = 5173,
  [int]$SaasBackendPort = 8010,
  [int]$SaasFrontendPort = 5174,
  [int]$MobileBackendPort = 8020,
  [int]$MobileFrontendPort = 5175
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeDir = Join-Path $Root ".agenthub-runtime\parallel"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$PortMatrix = @(
  $LocalBackendPort,
  $LocalFrontendPort,
  $SaasBackendPort,
  $SaasFrontendPort,
  $MobileBackendPort,
  $MobileFrontendPort
)

function Stop-Ports {
  param([int[]]$Ports)

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
  Start-Sleep -Milliseconds 700
}

function Wait-HttpOk {
  param(
    [string]$Url,
    [int]$Seconds = 45
  )

  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        return $response
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  throw "Timed out waiting for $Url"
}

function Start-Backend {
  param(
    [string]$Label,
    [string]$Edition,
    [string]$Surface,
    [int]$Port
  )

  $python = Join-Path $Root "backend\venv\Scripts\python.exe"
  $stdout = Join-Path $RuntimeDir "$Label-backend.out.log"
  $stderr = Join-Path $RuntimeDir "$Label-backend.err.log"
  $authRequired = if ($Edition -eq "saas") { "true" } else { "false" }
  $command = "set AGENTHUB_EDITION=$Edition&& set AGENTHUB_SURFACE=$Surface&& set AGENTHUB_API_BASE_URL=/api&& set AGENTHUB_AUTH_REQUIRED=$authRequired&& `"$python`" -m uvicorn app.main:app --host 127.0.0.1 --port $Port"

  $process = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList @("/d", "/c", $command) `
    -WorkingDirectory (Join-Path $Root "backend") `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

  $capabilitiesUrl = "http://127.0.0.1:$Port/api/capabilities"
  $capabilities = (Wait-HttpOk $capabilitiesUrl).Content | ConvertFrom-Json
  if ($capabilities.edition -ne $Edition -or $capabilities.surface -ne $Surface) {
    throw "$Label backend capabilities mismatch: $($capabilities.edition)/$($capabilities.surface)"
  }

  return $process
}

function Start-Frontend {
  param(
    [string]$Label,
    [string]$Script,
    [int]$Port,
    [int]$BackendPort,
    [bool]$DevAuth
  )

  $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
  $stdout = Join-Path $RuntimeDir "$Label-frontend.out.log"
  $stderr = Join-Path $RuntimeDir "$Label-frontend.err.log"
  $devAuthValue = if ($DevAuth) { "true" } else { "false" }
  $command = "set VITE_AGENTHUB_API_BASE=/api&& set VITE_AGENTHUB_PROXY_TARGET=http://127.0.0.1:$BackendPort&& set VITE_AGENTHUB_DEV_AUTH=$devAuthValue&& `"$npm`" run $Script -- --host 127.0.0.1 --port $Port --strictPort"

  $process = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList @("/d", "/c", $command) `
    -WorkingDirectory (Join-Path $Root "frontend") `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

  $capabilitiesUrl = "http://127.0.0.1:$Port/api/capabilities"
  Wait-HttpOk $capabilitiesUrl | Out-Null

  return $process
}

Stop-Ports $PortMatrix

$shells = @(
  @{
    Label = "local"
    Edition = "local"
    Surface = "desktop"
    BackendPort = $LocalBackendPort
    FrontendPort = $LocalFrontendPort
    FrontendScript = "dev:local"
    DevAuth = $false
  },
  @{
    Label = "saas"
    Edition = "saas"
    Surface = "desktop"
    BackendPort = $SaasBackendPort
    FrontendPort = $SaasFrontendPort
    FrontendScript = "dev:saas"
    DevAuth = $true
  },
  @{
    Label = "mobile"
    Edition = "saas"
    Surface = "mobile"
    BackendPort = $MobileBackendPort
    FrontendPort = $MobileFrontendPort
    FrontendScript = "dev:mobile"
    DevAuth = $true
  }
)

$started = @()
foreach ($shell in $shells) {
  $backend = Start-Backend `
    -Label $shell.Label `
    -Edition $shell.Edition `
    -Surface $shell.Surface `
    -Port $shell.BackendPort

  $frontend = Start-Frontend `
    -Label $shell.Label `
    -Script $shell.FrontendScript `
    -Port $shell.FrontendPort `
    -BackendPort $shell.BackendPort `
    -DevAuth $shell.DevAuth

  $capabilities = (Invoke-WebRequest -Uri "http://127.0.0.1:$($shell.FrontendPort)/api/capabilities" -UseBasicParsing -TimeoutSec 5).Content | ConvertFrom-Json
  if ($capabilities.edition -ne $shell.Edition -or $capabilities.surface -ne $shell.Surface) {
    throw "$($shell.Label) frontend proxy capabilities mismatch: $($capabilities.edition)/$($capabilities.surface)"
  }

  $started += [pscustomobject]@{
    label = $shell.Label
    edition = $shell.Edition
    surface = $shell.Surface
    backendUrl = "http://127.0.0.1:$($shell.BackendPort)"
    frontendUrl = "http://127.0.0.1:$($shell.FrontendPort)"
    docsUrl = "http://127.0.0.1:$($shell.BackendPort)/docs"
    backendPid = $backend.Id
    frontendPid = $frontend.Id
  }
}

$started | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $RuntimeDir "services.json") -Encoding UTF8

Write-Host ""
Write-Host "AgentHub three shells are running:"
foreach ($item in $started) {
  Write-Host ("- {0,-6} front={1} backend={2} docs={3}" -f $item.label, $item.frontendUrl, $item.backendUrl, $item.docsUrl)
}
Write-Host ""
Write-Host "Stop all: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop-three-shells.ps1"
Write-Host "Logs: $RuntimeDir"
