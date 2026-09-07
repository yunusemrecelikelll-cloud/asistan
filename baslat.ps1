# Asistan başlatıcı
# Ollama'yı gerekiyorsa başlatır, API sunucusunu ayağa kaldırır,
# ardından arayüzü kendi penceresinde açar.

$ErrorActionPreference = 'SilentlyContinue'

$Kok    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py     = Join-Path $Kok '.venv\Scripts\pythonw.exe'
$PyCli  = Join-Path $Kok '.venv\Scripts\python.exe'
$Ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$Url    = 'http://127.0.0.1:8770'
$LogDir = Join-Path $Kok 'data\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Ayakta($url) {
    try { return (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }
    catch { return $false }
}

# 1. Ollama
if (-not (Ayakta 'http://127.0.0.1:11434/')) {
    Start-Process -FilePath $Ollama -ArgumentList 'serve' -WindowStyle Hidden
    for ($i = 0; $i -lt 25 -and -not (Ayakta 'http://127.0.0.1:11434/'); $i++) { Start-Sleep -Seconds 1 }
}

# 2. Asistan sunucusu
if (-not (Ayakta "$Url/api/saglik")) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Start-Process -FilePath $PyCli `
        -ArgumentList (Join-Path $Kok 'backend\main.py') `
        -WorkingDirectory $Kok -WindowStyle Hidden `
        -RedirectStandardOutput "$LogDir\sunucu-$stamp.log" `
        -RedirectStandardError  "$LogDir\sunucu-$stamp.err.log"
    for ($i = 0; $i -lt 60 -and -not (Ayakta "$Url/api/saglik"); $i++) { Start-Sleep -Seconds 1 }
}

# 3. Pencere — tarayıcı çubuğu olmadan
$tarayici = @(
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($tarayici) {
    Start-Process -FilePath $tarayici -ArgumentList `
        "--app=$Url", "--window-size=1340,900",
        "--user-data-dir=$Kok\data\pencere-profili"
} else {
    Start-Process $Url
}
