# Ses klonlama servisini baslatir (XTTS, ayri Python 3.12 ortaminda).
#
# Ayri surec olmasinin sebebi: model yuklemesi 12 saniye suruyor ve her
# istekte yeniden yuklenirse konusma kullanilamaz hale geliyor. Surec ayakta
# kalir, model bellekte durur.
#
#   .\ses_servisi.ps1          baslat (varsa once durdur)
#   .\ses_servisi.ps1 -Durdur  yalnizca durdur

param([switch]$Durdur)

$kok = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $kok '.venv-ses\Scripts\python.exe'
$betik = Join-Path $kok 'backend\klonses\sunucu.py'

# Calisan ornegi kapat (komut satirina bakarak; pkill bunlari yakalamiyor)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'klonses' } |
  ForEach-Object {
    Write-Host "Eski surec kapatiliyor: $($_.ProcessId)" -ForegroundColor DarkGray
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }

if ($Durdur) { Write-Host "Ses servisi durduruldu." -ForegroundColor Yellow; exit 0 }

if (-not (Test-Path $py)) {
  Write-Host "Ses ortami yok: $py" -ForegroundColor Red
  Write-Host "Kurulum: uv venv --python 3.12 .venv-ses" -ForegroundColor Gray
  exit 1
}

Start-Sleep -Seconds 1
$env:PYTHONIOENCODING = 'utf-8'
Start-Process -FilePath $py -ArgumentList $betik, '--isit' `
  -WorkingDirectory $kok -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $kok 'data\klonses.log') `
  -RedirectStandardError  (Join-Path $kok 'data\klonses.err.log')

Write-Host "Ses servisi baslatildi (127.0.0.1:8771)." -ForegroundColor Green
Write-Host "Model isiniyor, ilk hazir olma ~30 saniye surer." -ForegroundColor Gray
