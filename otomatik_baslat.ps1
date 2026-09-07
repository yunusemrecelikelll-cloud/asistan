# Asistan'i Windows'a otomatik baslayacak sekilde kurar.
#
# Gorev Zamanlayici'ya "oturum acildiginda calis" gorevi ekler. Gorev
# gozetmeni baslatir; gozetmen de iki servisi ayakta tutar. Boylece
# bilgisayar kapanip acilsa da, bir servis coksede sistem geri gelir.
#
# Yonetici yetkisi gerekmiyor: gorev mevcut kullanicinin oturumuna bagli.
# "Bilgisayar aciliminda" (oturum acilmadan) calistirmak yonetici ister ve
# mikrofon/ses gibi oturuma bagli seyleri bozar; bu yuzden oturum tetigi.
#
#   .\otomatik_baslat.ps1           kur
#   .\otomatik_baslat.ps1 -Kaldir   kaldir
#   .\otomatik_baslat.ps1 -Durum    durumu goster

param([switch]$Kaldir, [switch]$Durum)

$kok = Split-Path -Parent $MyInvocation.MyCommand.Path
$gorevAdi = 'Asistan'
$gozetmen = Join-Path $kok 'gozetmen.ps1'

function DurumYaz() {
    $g = Get-ScheduledTask -TaskName $gorevAdi -ErrorAction SilentlyContinue
    if (-not $g) {
        Write-Host "Otomatik baslatma KURULU DEGIL." -ForegroundColor Yellow
        return
    }
    $bilgi = Get-ScheduledTaskInfo -TaskName $gorevAdi
    Write-Host "Gorev      : $($g.TaskName)" -ForegroundColor Green
    Write-Host "Durum      : $($g.State)"
    Write-Host "Son calisma: $($bilgi.LastRunTime)  (sonuc: $($bilgi.LastTaskResult))"
    Write-Host "Sonraki    : $($bilgi.NextRunTime)"
    Write-Host ""
    foreach ($s in @(@{a='Ana sunucu'; u='http://127.0.0.1:8770/api/saglik'},
                     @{a='Ses servisi'; u='http://127.0.0.1:8771/saglik'})) {
        try {
            $null = Invoke-WebRequest -Uri $s.u -UseBasicParsing -TimeoutSec 5
            Write-Host "$($s.a): calisiyor" -ForegroundColor Green
        } catch {
            Write-Host "$($s.a): kapali" -ForegroundColor Red
        }
    }
}

if ($Durum) { DurumYaz; exit 0 }

if ($Kaldir) {
    Unregister-ScheduledTask -TaskName $gorevAdi -Confirm:$false -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -match 'gozetmen' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Otomatik baslatma kaldirildi. Servisler calismaya devam eder." -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path $gozetmen)) {
    Write-Host "gozetmen.ps1 bulunamadi: $gozetmen" -ForegroundColor Red
    exit 1
}

# Varsa eskisini temizle — ayar degistiginde ikili kayit kalmasin
Unregister-ScheduledTask -TaskName $gorevAdi -Confirm:$false -ErrorAction SilentlyContinue

$eylem = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$gozetmen`"" `
    -WorkingDirectory $kok

$tetik = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# Oturum acilisinda diskin ve agin oturmasi icin kisa gecikme
$tetik.Delay = 'PT30S'

$ayar = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

$asil = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask -TaskName $gorevAdi -Action $eylem -Trigger $tetik `
    -Settings $ayar -Principal $asil `
    -Description 'Asistan sunucusunu ve ses servisini ayakta tutar.' | Out-Null

Write-Host "Otomatik baslatma kuruldu." -ForegroundColor Green
Write-Host "Bilgisayar her acilip oturum acildiginda Asistan kendiliginden baslar."
Write-Host ""
Write-Host "Simdi de baslatiliyor..." -ForegroundColor Gray
Start-ScheduledTask -TaskName $gorevAdi
Start-Sleep -Seconds 3
DurumYaz
