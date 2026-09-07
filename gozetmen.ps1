# Asistan gozetmeni — iki servisi de ayakta tutar.
#
# Neden ayri bir gozetmen: Gorev Zamanlayici bir gorevi "coktugunde yeniden
# baslat" diye ayarlayabiliyor ama surec cokmeden asili kalirsa (ornegin
# model yuklerken takilirsa) bunu fark etmiyor. Burada saglik ucuna bakiyoruz;
# yanit vermeyen servisi olduruyoruz ve yeniden baslatiyoruz.
#
#   .\gozetmen.ps1            surekli izle
#   .\gozetmen.ps1 -BirKez    bir kez kontrol et ve cik

param([switch]$BirKez)

$kok = Split-Path -Parent $MyInvocation.MyCommand.Path
$gunluk = Join-Path $kok 'data\gozetmen.log'
$aralik = 20          # saniye
$sesGecikme = 90      # ses servisi modeli yuklerken saglik vermez

function Yaz($mesaj) {
    $satir = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $mesaj
    Add-Content -Path $gunluk -Value $satir -Encoding utf8
    Write-Host $satir
}

function Ayakta($adres, $zamanAsimi = 5) {
    try {
        $null = Invoke-WebRequest -Uri $adres -UseBasicParsing -TimeoutSec $zamanAsimi
        return $true
    } catch { return $false }
}

function SurecVar($desen) {
    $bulunan = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match $desen }
    return ($null -ne $bulunan)
}

function AnaBaslat() {
    Yaz "Ana sunucu baslatiliyor"
    Start-Process -FilePath (Join-Path $kok '.venv\Scripts\python.exe') `
        -ArgumentList (Join-Path $kok 'backend\main.py') `
        -WorkingDirectory $kok -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $kok 'data\sunucu.log') `
        -RedirectStandardError  (Join-Path $kok 'data\sunucu.err.log')
}

function SesBaslat() {
    $py = Join-Path $kok '.venv-ses\Scripts\python.exe'
    if (-not (Test-Path $py)) { return }   # ses ortami kurulu degil, sorun yok
    Yaz "Ses servisi baslatiliyor"
    $env:PYTHONIOENCODING = 'utf-8'
    Start-Process -FilePath $py `
        -ArgumentList (Join-Path $kok 'backend\klonses\sunucu.py'), '--isit' `
        -WorkingDirectory $kok -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $kok 'data\klonses.log') `
        -RedirectStandardError  (Join-Path $kok 'data\klonses.err.log')
}

# Ses servisi yeni baslatildiysa model yuklenene kadar saglik sormuyoruz.
$sesBaslangic = [datetime]::MinValue

function Tur() {
    if (-not (Ayakta 'http://127.0.0.1:8770/api/saglik')) {
        # Surec varsa ama yanit vermiyorsa asilmis demektir; once temizle.
        if (SurecVar ([regex]::Escape((Join-Path $kok 'backend\main.py')))) {
            Yaz "Ana sunucu yanit vermiyor, kapatiliyor"
            Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
                Where-Object { $_.CommandLine -match [regex]::Escape((Join-Path $kok 'backend\main.py')) } |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 2
        }
        AnaBaslat
    }

    $py = Join-Path $kok '.venv-ses\Scripts\python.exe'
    if (Test-Path $py) {
        $gecen = ([datetime]::Now - $script:sesBaslangic).TotalSeconds
        if (-not (SurecVar 'klonses')) {
            SesBaslat
            $script:sesBaslangic = [datetime]::Now
        } elseif ($gecen -gt $sesGecikme -and
                  -not (Ayakta 'http://127.0.0.1:8771/saglik')) {
            Yaz "Ses servisi yanit vermiyor, yeniden baslatiliyor"
            Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
                Where-Object { $_.CommandLine -match 'klonses' } |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 2
            SesBaslat
            $script:sesBaslangic = [datetime]::Now
        }
    }
}

if ($BirKez) { Tur; exit 0 }

Yaz "Gozetmen basladi (aralik ${aralik}s)"
$script:sesBaslangic = [datetime]::Now
while ($true) {
    try { Tur } catch { Yaz "Hata: $($_.Exception.Message)" }
    Start-Sleep -Seconds $aralik
}
