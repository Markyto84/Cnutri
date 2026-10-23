[CmdletBinding(DefaultParameterSetName='PEM')]
param(
    [Parameter(Mandatory=$true)][string]$Dominio,
    [Parameter(Mandatory=$true, ParameterSetName='PEM')][string]$Certificado,
    [Parameter(Mandatory=$true, ParameterSetName='PEM')][string]$Chave,
    [Parameter(Mandatory=$true, ParameterSetName='PFX')][string]$Pfx,
    [switch]$Aplicar
)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$python = Join-Path $taskRoot 'backend\.venv\Scripts\python.exe'
$helper = Join-Path $taskRoot 'backend\https_config.py'
$caddy = Join-Path $taskRoot 'work\runtime\caddy\caddy.exe'
$activePath = Join-Path $taskRoot 'work\https\active.json'

if (-not (Test-Path -LiteralPath $python)) { throw 'Prepare as dependências com start.ps1 primeiro.' }
$prepareArgs = @($helper, '--dominio', $Dominio)
if ($PSCmdlet.ParameterSetName -eq 'PFX') { $prepareArgs += @('--pfx', (Resolve-Path -LiteralPath $Pfx).Path) }
else { $prepareArgs += @('--certificado', (Resolve-Path -LiteralPath $Certificado).Path, '--chave', (Resolve-Path -LiteralPath $Chave).Path) }
$prepared = & $python @prepareArgs
if ($LASTEXITCODE -ne 0) { throw 'Certificado não preparado. O serviço atual foi preservado.' }
$candidate = $prepared | ConvertFrom-Json
$candidatePath = Join-Path (Split-Path -Parent $candidate.caddyfile) 'config.json'
& (Join-Path $taskRoot 'infra\instalar-caddy.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o Caddy.' }
Push-Location (Join-Path $taskRoot 'frontend')
try { & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Build do frontend falhou.' } }
finally { Pop-Location }
& $caddy validate --config $candidate.caddyfile --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw 'Configuração HTTPS inválida. O acesso atual foi preservado.' }
if (-not $Aplicar) {
    Write-Host 'Configuração preparada e validada. O acesso atual não foi alterado.'
    Write-Host 'Use os mesmos parâmetros com -Aplicar após a TI confirmar o DNS e a confiança do certificado.'
    return
}

$targetIPs = @([System.Net.Dns]::GetHostAddresses($candidate.dominio) | ForEach-Object { $_.ToString() })
$localIPs = @('127.0.0.1','::1') + @(Get-NetIPAddress | Select-Object -ExpandProperty IPAddress)
if (-not @($targetIPs | Where-Object { $localIPs -contains $_ }).Count) {
    throw 'O endereço informado não resolve para esta estação. Ajuste o DNS na TI antes de aplicar aqui.'
}
if (Get-NetTCPConnection -State Listen -LocalPort 8443 -ErrorAction SilentlyContinue) { throw 'Porta de conferência 8443 ocupada; nenhum serviço encerrado.' }
# Confere confiança TLS real antes de tocar no frontend que atende a rede.
$probe = Start-Process -FilePath $caddy -ArgumentList ('run --config "{0}" --adapter caddyfile' -f $candidate.sonda) -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $taskRoot 'work\https\sonda.log') -RedirectStandardError (Join-Path $taskRoot 'work\https\sonda-error.log')
try {
    $deadline = (Get-Date).AddSeconds(10)
    while (-not (Get-NetTCPConnection -State Listen -LocalPort 8443 -ErrorAction SilentlyContinue)) {
        if ($probe.HasExited -or (Get-Date) -gt $deadline) { throw 'Conferência HTTPS não iniciou.' }
        Start-Sleep -Milliseconds 200
    }
    & $python $helper --conferir-config $candidatePath --testar-porta 8443
    if ($LASTEXITCODE -ne 0) { throw 'A confiança TLS não foi confirmada; nenhum serviço atual alterado.' }
} finally {
    $probe.Refresh()
    if (-not $probe.HasExited) { Stop-Process -Id $probe.Id -ErrorAction Stop }
}

$statePath = Join-Path $taskRoot 'work\servicos.json'
$liveState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$frontRecord = $liveState.frontend
$frontProcess = Get-Process -Id $frontRecord.id -ErrorAction Stop
$frontStart = [DateTimeOffset]$frontRecord.startedAt
$frontCommand = (Get-CimInstance Win32_Process -Filter "ProcessId=$($frontRecord.id)").CommandLine
if ($frontProcess.StartTime.ToUniversalTime().Ticks -ne $frontStart.UtcDateTime.Ticks -or $frontCommand.IndexOf($taskRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw 'O frontend não corresponde a esta cópia; nenhum processo encerrado.'
}
foreach ($requiredPort in @(80,443,5173)) {
    $owners = @(Get-NetTCPConnection -State Listen -LocalPort $requiredPort -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    if (@($owners | Where-Object { $_ -ne $frontRecord.id }).Count) { throw "Porta $requiredPort ocupada por outro processo; nenhum serviço encerrado." }
}
$oldConfig = if (Test-Path -LiteralPath $activePath) { Get-Content -LiteralPath $activePath -Raw } else { $null }
Stop-Process -Id $frontRecord.id -ErrorAction Stop
try {
    Copy-Item -LiteralPath $candidatePath -Destination $activePath -Force
    & (Join-Path $taskRoot 'start.ps1')
    & $python $helper --conferir-config $activePath --testar-porta 443
    if ($LASTEXITCODE -ne 0) { throw 'Conferência final HTTPS falhou.' }
    Write-Host "HTTPS ativo em https://$($candidate.dominio). HTTP e o endereço antigo redirecionam para esse domínio."
} catch {
    # Reverte somente o frontend desta cópia; API, banco e dados permanecem em uso.
    $failedState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $failedRecord = $failedState.frontend
    if ($failedRecord) {
        $failedProcess = Get-Process -Id $failedRecord.id -ErrorAction SilentlyContinue
        if ($failedProcess) {
            $failedStart = [DateTimeOffset]$failedRecord.startedAt
            $failedCommand = (Get-CimInstance Win32_Process -Filter "ProcessId=$($failedRecord.id)").CommandLine
            if ($failedProcess.StartTime.ToUniversalTime().Ticks -eq $failedStart.UtcDateTime.Ticks -and $failedCommand -like '*caddy*' -and $failedCommand.IndexOf($taskRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                Stop-Process -Id $failedRecord.id -ErrorAction Stop
            }
        }
    }
    if ($null -ne $oldConfig) { [IO.File]::WriteAllText($activePath, $oldConfig, [Text.UTF8Encoding]::new($false)) }
    else { Remove-Item -LiteralPath $activePath -ErrorAction SilentlyContinue }
    & (Join-Path $taskRoot 'start.ps1')
    throw 'HTTPS não aplicado. A configuração anterior foi restaurada; consulte os logs em work/https/.'
}
