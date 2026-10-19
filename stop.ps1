[CmdletBinding()]
param([switch]$PararBanco)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$rootInfo = Get-Item -LiteralPath $projectRoot -Force
if ($rootInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    $projectRoot = @($rootInfo.Target)[0]
}
$statePath = Join-Path $projectRoot 'work\servicos.json'

if (Test-Path -LiteralPath $statePath) {
    $serviceState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    foreach ($serviceName in @('frontend', 'backend')) {
        $record = $serviceState.$serviceName
        if (-not $record) { continue }
        $serviceProcess = Get-Process -Id $record.id -ErrorAction SilentlyContinue
        if (-not $serviceProcess) { continue }
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.id)"
        $recordStart = [DateTimeOffset]$record.startedAt
        $sameStart = $serviceProcess.StartTime.ToUniversalTime().Ticks -eq $recordStart.UtcDateTime.Ticks
        if (-not $sameStart -or -not $processInfo.CommandLine -or
            $processInfo.CommandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw "O identificador de $serviceName pertence a outro processo; parada cancelada."
        }
        Stop-Process -Id $record.id -Force
        Wait-Process -Id $record.id -Timeout 10 -ErrorAction SilentlyContinue
        Write-Host "$serviceName encerrado."
    }
    Remove-Item -LiteralPath $statePath
} else {
    Write-Host 'Nao ha servicos registrados por esta copia do projeto.'
}

if ($PararBanco) {
    & docker compose --project-directory $projectRoot -f (Join-Path $projectRoot 'docker-compose.yml') stop db
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel parar o PostgreSQL.' }
} else {
    Write-Host 'PostgreSQL mantido em execucao. Use -PararBanco para encerra-lo tambem.'
}
