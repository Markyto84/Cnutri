[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'caddy-release.json') -Raw | ConvertFrom-Json
$runtimePath = Join-Path $taskRoot 'work\runtime\caddy'
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$archivePath = Join-Path $runtimePath 'caddy.zip'
if ($manifest.url -notmatch '^https://github\.com/caddyserver/caddy/releases/download/v[0-9.]+/caddy_[0-9.]+_windows_amd64\.zip$' -or $manifest.sha256 -notmatch '^[a-f0-9]{64}$') {
    throw 'Manifesto de instalação inválido.'
}
if (-not (Test-Path -LiteralPath $archivePath) -or (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.sha256) {
    Invoke-WebRequest -Uri $manifest.url -OutFile $archivePath -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.sha256) {
    throw 'O arquivo recebido não corresponde ao SHA-256 oficial. Nenhum executável iniciado.'
}
$binaryPath = Join-Path $runtimePath 'caddy.exe'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    $entry = $zip.GetEntry('caddy.exe')
    if (-not $entry) { throw 'Executável não encontrado no pacote verificado.' }
    $stream = $entry.Open()
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $expectedBinaryHash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
} finally { $zip.Dispose() }
if (-not (Test-Path -LiteralPath $binaryPath) -or (Get-FileHash -LiteralPath $binaryPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedBinaryHash) {
    Expand-Archive -LiteralPath $archivePath -DestinationPath $runtimePath -Force
}
if (-not (Test-Path -LiteralPath $binaryPath)) { throw 'Executável não encontrado no pacote.' }
Write-Output "Caddy $($manifest.version) preparado; SHA-256 do pacote conferido."
