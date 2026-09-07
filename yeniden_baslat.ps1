# NOVA sunucusunu guvenilir bicimde yeniden baslatir.
#
# Gozetmen calisiyorsa sunucuyu BIZ baslatmiyoruz: yalnizca olduruyoruz,
# gozetmen 20 saniye icinde yenisini ayaga kaldiriyor. Ikimiz birden
# baslattigimizda iki surec olusuyor, biri portu tutuyor, digeri asili
# kaliyordu — ve portu tutan eski kod olabildigi icin degisiklikler
# yansimiyordu.
#
#   .\yeniden_baslat.ps1          sunucuyu yeniden baslat
#   .\yeniden_baslat.ps1 -Ses     ses servisini de yeniden baslat

param([switch]$Ses)

$kok = Split-Path -Parent $MyInvocation.MyCommand.Path
$anaDesen = [regex]::Escape((Join-Path $kok 'backend\main.py'))

function AnaSurecler() {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match $anaDesen }
}

function GozetmenVar() {
  $null -ne (Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
             Where-Object { $_.CommandLine -match 'gozetmen' })
}

# Butun eski surecleri kapat
AnaSurecler | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Port gercekten birakilana kadar bekle (en fazla 10 saniye)
for ($i = 0; $i -lt 20; $i++) {
  if (-not (Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue)) { break }
  Start-Sleep -Milliseconds 500
}

Remove-Item (Join-Path $kok 'backend\__pycache__') -Recurse -Force -ErrorAction SilentlyContinue

if (GozetmenVar) {
  Write-Host "Gozetmen calisiyor; sunucuyu o baslatacak (en fazla 20 sn)." -ForegroundColor Gray
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
      $null = Invoke-WebRequest 'http://127.0.0.1:8770/api/saglik' -UseBasicParsing -TimeoutSec 3
      Write-Host "Sunucu ayakta." -ForegroundColor Green
      break
    } catch { }
  }
} else {
  Start-Process -FilePath (Join-Path $kok '.venv\Scripts\python.exe') `
    -ArgumentList (Join-Path $kok 'backend\main.py') `
    -WorkingDirectory $kok -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $kok 'data\sunucu.log') `
    -RedirectStandardError  (Join-Path $kok 'data\sunucu.err.log')
}

if ($Ses) { & (Join-Path $kok 'ses_servisi.ps1') }
