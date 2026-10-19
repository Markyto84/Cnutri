[CmdletBinding()]
param([switch]$InstalarDependencias)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$rootInfo = Get-Item -LiteralPath $projectRoot -Force
if ($rootInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    $projectRoot = @($rootInfo.Target)[0]
}
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$runtimeRoot = Join-Path $projectRoot 'work'
$logsRoot = Join-Path $runtimeRoot 'logs'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$statePath = Join-Path $runtimeRoot 'servicos.json'

function Assert-CommandSucceeded([string]$Action) {
    if ($LASTEXITCODE -ne 0) { throw "Falha ao $Action (codigo $LASTEXITCODE)." }
}

function Get-OwnedListener([int]$Port) {
    $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -eq 0) { return $null }
    if ($owners.Count -ne 1) { throw "A porta $Port tem mais de um processo associado." }
    $listener = Get-CimInstance Win32_Process -Filter "ProcessId=$($owners[0])"
    if (-not $listener.CommandLine -or
        $listener.CommandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "A porta $Port esta ocupada por outro projeto. Nenhum processo foi encerrado."
    }
    return Get-Process -Id $owners[0]
}

function Wait-Http([string]$Url) {
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Milliseconds 300
    }
    throw "O servico nao respondeu em $Url. Consulte os arquivos em $logsRoot."
}

$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$npmPath = (Get-Command npm.cmd -ErrorAction Stop).Source
Get-Command docker.exe -ErrorAction Stop | Out-Null
$backendProcess = Get-OwnedListener 8000
$frontendProcess = Get-OwnedListener 5173
if ($InstalarDependencias -and ($backendProcess -or $frontendProcess)) {
    throw 'Execute .\stop.ps1 antes de reinstalar as dependencias.'
}
New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null

& docker compose --project-directory $projectRoot -f (Join-Path $projectRoot 'docker-compose.yml') up -d db
Assert-CommandSucceeded 'iniciar o PostgreSQL'

$createdEnvironment = -not (Test-Path -LiteralPath $pythonPath)
if ($createdEnvironment) {
    $basePython = (Get-Command python.exe -ErrorAction Stop).Source
    & $basePython -m venv (Join-Path $backendRoot '.venv')
    Assert-CommandSucceeded 'criar o ambiente Python'
}
if ($createdEnvironment -or $InstalarDependencias) {
    & $pythonPath -m pip install -r (Join-Path $backendRoot 'requirements.txt')
    Assert-CommandSucceeded 'instalar as dependencias do backend'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules\vite\bin\vite.js')) -or $InstalarDependencias) {
    Push-Location $frontendRoot
    try {
        & $npmPath ci
        Assert-CommandSucceeded 'instalar as dependencias do frontend'
    } finally { Pop-Location }
}

if (-not $backendProcess) {
    $backendArguments = '-m uvicorn app.main:app --app-dir "{0}" --host 127.0.0.1 --port 8000' -f $backendRoot
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList $backendArguments `
        -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logsRoot 'backend.log') `
        -RedirectStandardError (Join-Path $logsRoot 'backend-error.log')
}

# Registra o backend imediatamente para permitir a parada mesmo se o frontend falhar.
$serviceState = @{
    projectRoot = $projectRoot
    backend = @{ id = $backendProcess.Id; startedAt = $backendProcess.StartTime.ToUniversalTime().ToString('o') }
}
$serviceState | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
Wait-Http 'http://127.0.0.1:8000/api/health'
# No Windows, o Python do venv pode iniciar um processo filho. Registra quem atende a porta.
$backendProcess = Get-OwnedListener 8000
if (-not $backendProcess) { throw 'O processo da API nao foi identificado.' }
$serviceState.backend = @{ id = $backendProcess.Id; startedAt = $backendProcess.StartTime.ToUniversalTime().ToString('o') }
$serviceState | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8

if (-not $frontendProcess) {
    $vitePath = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
    $frontendArguments = '"{0}" --host 0.0.0.0 --port 5173 --strictPort' -f $vitePath
    $frontendProcess = Start-Process -FilePath $nodePath -ArgumentList $frontendArguments `
        -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logsRoot 'frontend.log') `
        -RedirectStandardError (Join-Path $logsRoot 'frontend-error.log')
}
$serviceState.frontend = @{ id = $frontendProcess.Id; startedAt = $frontendProcess.StartTime.ToUniversalTime().ToString('o') }
$serviceState | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
Wait-Http 'http://127.0.0.1:5173/api/health'
$frontendProcess = Get-OwnedListener 5173
if (-not $frontendProcess) { throw 'O processo do frontend nao foi identificado.' }
$serviceState.frontend = @{ id = $frontendProcess.Id; startedAt = $frontendProcess.StartTime.ToUniversalTime().ToString('o') }
$serviceState | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host "Cnutri em execucao a partir de: $projectRoot" -ForegroundColor Green
Write-Host 'Formulario: http://localhost:5173/unidade-havai'
Write-Host 'Login:      http://localhost:5173/login'
Write-Host "Logs:       $logsRoot"
