# Telefondan erişim — sabit adres.
#
# Tailscale kullanır: adres bir kez belirlenir ve bir daha değişmez.
# Adres yalnızca kendi cihazlarına açıktır (herkese açık değil) ve gerçek
# TLS sertifikası taşır — iOS Safari mikrofona ancak HTTPS'te izin verdiği
# için bu şart.
#
# Tailscale hazır değilse eski geçici tünele (cloudflared) düşer.

$ErrorActionPreference = 'Continue'
$kok = Split-Path -Parent $MyInvocation.MyCommand.Path
$ts  = "$env:ProgramFiles\Tailscale\tailscale.exe"
$cf  = Join-Path $kok 'tools\cloudflared.exe'
$log = Join-Path $kok 'data\tunel.log'

function Yaz($m, $renk = 'Gray') { Write-Host $m -ForegroundColor $renk }

# ── Sunucu ayakta mı ──────────────────────────────────────────────────────
try {
    $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8770/api/saglik' `
                              -UseBasicParsing -TimeoutSec 5
} catch {
    Yaz "Asistan sunucusu calismiyor." Red
    Yaz "Once masaustundeki Asistan kisayolunu ac, sonra bunu calistir." Yellow
    Read-Host "`nKapatmak icin Enter"
    exit 1
}

# ── Parola ────────────────────────────────────────────────────────────────
$parola = '(okunamadi)'
try {
    $parola = ((Invoke-WebRequest -Uri 'http://127.0.0.1:8770/api/parola' `
                -UseBasicParsing -TimeoutSec 5).Content | ConvertFrom-Json).parola
} catch {}

# ── 1. tercih: Tailscale (sabit adres) ────────────────────────────────────
if (Test-Path $ts) {
    $durum = & $ts status 2>&1 | Out-String

    if ($durum -match 'Logged out|NeedsLogin') {
        Yaz ""
        Yaz "Tailscale'e giris yapilmamis." Yellow
        Yaz "Su komutu calistir, tarayicida acilan sayfadan giris yap:" Cyan
        Yaz ""
        Yaz "   & '$ts' up" White
        Yaz ""
        Yaz "Giris yaptiktan sonra bu betigi tekrar calistir." Gray
        Read-Host "`nKapatmak icin Enter"
        exit 1
    }

    # Adresi (MagicDNS adı) al
    $ad = (& $ts status --json 2>$null | ConvertFrom-Json).Self.DNSName
    if ($ad) {
        $ad = $ad.TrimEnd('.')

        # HTTPS sertifikası var mı? (tailnet ayarından açılması gerekir)
        $httpsVar = $false
        $job = Start-Job -ScriptBlock {
            param($t, $a) & $t cert $a 2>&1
        } -ArgumentList $ts, $ad
        if (Wait-Job $job -Timeout 45) {
            $r = Receive-Job $job | Out-String
            $httpsVar = ($r -notmatch 'does not support|error')
        } else { Stop-Job $job }
        Remove-Job $job -Force

        Yaz ""
        if ($httpsVar) {
            & $ts serve --bg --https=443 http://127.0.0.1:8770 2>&1 | Out-Null
            Yaz "  SABIT ADRES : https://$ad" Green
            Yaz "  PAROLA      : $parola" Green
            Yaz ""
            Yaz "  Hem uygulamadan hem Safari'den kullanilabilir." Cyan
        } else {
            Yaz "  SABIT ADRES : http://${ad}:8770" Green
            Yaz "  PAROLA      : $parola" Green
            Yaz ""
            Yaz "  Bu adres Flutter uygulamasinda calisir (mikrofon dahil)." Cyan
            Yaz ""
            Yaz "  Safari/PWA'da da kullanmak istersen HTTPS'i ac:" Yellow
            Yaz "    https://login.tailscale.com/admin/dns" White
            Yaz "    -> 'HTTPS Certificates' -> Enable, sonra bunu tekrar calistir." Gray
        }

        Yaz ""
        Yaz "  Bu adres bir daha degismez." Cyan
        Yaz ""
        Yaz "  iPhone'da:" Cyan
        Yaz "   1. App Store'dan Tailscale kur, ayni hesapla giris yap"
        Yaz "   2. Asistan uygulamasini ac, yukaridaki adresi ve parolayi gir"
        Yaz ""
        Read-Host "Kapatmak icin Enter"
        exit 0
    }
}

# ── 2. tercih: cloudflared (adres her seferinde degisir) ──────────────────
Yaz ""
Yaz "Tailscale hazir degil, gecici tunele dusuluyor (adres her acilista degisir)." Yellow

if (-not (Test-Path $cf)) {
    Yaz "cloudflared.exe da bulunamadi: $cf" Red
    Read-Host "`nKapatmak icin Enter"
    exit 1
}

Remove-Item $log -ErrorAction SilentlyContinue
$is = Start-Process -FilePath $cf `
    -ArgumentList 'tunnel', '--url', 'http://127.0.0.1:8770', '--no-autoupdate' `
    -RedirectStandardError $log -RedirectStandardOutput "$log.out" `
    -WindowStyle Hidden -PassThru

$adres = $null
for ($i = 0; $i -lt 40 -and -not $adres; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' `
             -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $adres = $m.Matches[0].Value }
    }
}

if (-not $adres) {
    Yaz "Tunel adresi alinamadi. Log: $log" Red
    Stop-Process -Id $is.Id -Force -ErrorAction SilentlyContinue
    Read-Host "`nKapatmak icin Enter"
    exit 1
}

Yaz ""
Yaz "  ADRES  : $adres" Green
Yaz "  PAROLA : $parola" Green
Yaz ""
Yaz "  Bu pencereyi kapatma; kapatinca tunel kapanir." Yellow
Yaz ""

try { Wait-Process -Id $is.Id } finally {
    Stop-Process -Id $is.Id -Force -ErrorAction SilentlyContinue
    Yaz "Tunel kapatildi." DarkGray
}
