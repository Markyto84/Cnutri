[CmdletBinding()]
param([switch]$InstalarDependencias, [switch]$SessaoIndependente)

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
$httpsConfigPath = Join-Path $runtimeRoot 'https\active.json'
$httpsSettings = if (Test-Path -LiteralPath $httpsConfigPath) { Get-Content -LiteralPath $httpsConfigPath -Raw | ConvertFrom-Json } else { $null }
$httpsEnabled = $null -ne $httpsSettings -and $httpsSettings.habilitado
$frontendPort = if ($httpsEnabled) { 443 } else { 5173 }
$frontendBase = if ($httpsEnabled) { $httpsSettings.url } else { 'http://127.0.0.1:5173' }
$frontendHealth = "$frontendBase/api/health"

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

function Show-ServiceInfo {
    Write-Host "Cnutri em execucao a partir de: $projectRoot" -ForegroundColor Green
    Write-Host "Formulario: $frontendBase/unidade-havai"
    Write-Host "Login:      $frontendBase/login"
    Write-Host "Logs:       $logsRoot"
}

$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$npmPath = (Get-Command npm.cmd -ErrorAction Stop).Source
Get-Command docker.exe -ErrorAction Stop | Out-Null
$backendProcess = Get-OwnedListener 8000
$frontendProcess = Get-OwnedListener $frontendPort
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

& $pythonPath (Join-Path $backendRoot 'configurar_ambiente.py') --inicializar-admin
Assert-CommandSucceeded 'preparar a configuracao privada'
if ($httpsEnabled) {
    & $pythonPath (Join-Path $backendRoot 'https_config.py') --conferir-config $httpsConfigPath
    Assert-CommandSucceeded 'conferir o certificado HTTPS'
    if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot 'runtime\caddy\caddy.exe'))) { throw 'Execute configurar-https.ps1 para preparar o Caddy.' }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'dist\index.html'))) { throw 'Gere o frontend com npm run build antes de iniciar em HTTPS.' }
}

# O WMI inicia o supervisor fora da arvore do terminal. Interromper um comando de
# desenvolvimento nao deve encerrar junto a API e o frontend que atendem a rede.
# Dependencias foram preparadas acima; a sessao independente apenas as reutiliza.
if (-not $SessaoIndependente -and (-not $backendProcess -or -not $frontendProcess)) {
    $startupInfo = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
    $scriptPath = Join-Path $projectRoot 'start.ps1'
    $commandLine = 'powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -SessaoIndependente' -f $scriptPath
    $launch = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $commandLine
        CurrentDirectory = $projectRoot
        ProcessStartupInformation = $startupInfo
    }
    if ($launch.ReturnValue -ne 0) { throw "Falha ao iniciar a sessao independente (codigo $($launch.ReturnValue))." }
    Wait-Http 'http://127.0.0.1:8000/api/health'
    Wait-Http $frontendHealth
    if (-not (Get-OwnedListener 8000) -or -not (Get-OwnedListener $frontendPort)) { throw 'Os servicos iniciados nao pertencem a esta copia.' }
    Show-ServiceInfo
    return
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
    if ($httpsEnabled) {
        $frontendExecutable = Join-Path $runtimeRoot 'runtime\caddy\caddy.exe'
        $frontendArguments = 'run --config "{0}" --adapter caddyfile' -f $httpsSettings.caddyfile
    } else {
        $frontendExecutable = $nodePath
        $vitePath = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
        $frontendArguments = '"{0}" --host 0.0.0.0 --port 5173 --strictPort' -f $vitePath
    }
    $frontendProcess = Start-Process -FilePath $frontendExecutable -ArgumentList $frontendArguments `
        -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logsRoot 'frontend.log') `
        -RedirectStandardError (Join-Path $logsRoot 'frontend-error.log')
}
$serviceState.frontend = @{ id = $frontendProcess.Id; startedAt = $frontendProcess.StartTime.ToUniversalTime().ToString('o') }
$serviceState | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
Wait-Http $frontendHealth
$frontendProcess = Get-OwnedListener $frontendPort
if (-not $frontendProcess) { throw 'O processo do frontend nao foi identificado.' }
$serviceState.frontend = @{ id = $frontendProcess.Id; startedAt = $frontendProcess.StartTime.ToUniversalTime().ToString('o'); https = $httpsEnabled; url = $frontendBase }
$serviceState | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8

Show-ServiceInfo
