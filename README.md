# Asistan

Kişisel yapay zekâ asistanı — Claude Code projelerini yöneten sesli komuta
merkezi. Ayrıca mentörlük, yaşam koçluğu ve 3D baskı atölyesi takibi.

Tamamen bu bilgisayarda çalışıyor: konuşma tanıma yerelde (Whisper),
sohbet yerelde (Ollama), yalnızca projede iş yaptırırken `claude` CLI
devreye giriyor.

**Belgeler Türkçe:**

| Dosya | İçerik |
|---|---|
| [BENIOKU.md](BENIOKU.md) | Kurulum, kullanım, mimari, sorun giderme |
| [apple/BENIOKU.md](apple/BENIOKU.md) | iPhone + Apple Watch istemcileri |

## Yapı

```
backend/     FastAPI sunucusu (127.0.0.1:8770)
frontend/    masaüstü arayüzü
apple/       Swift — iPhone + Apple Watch
testler/     398 test
```

Android tarafı ayrı depoda:
[asistan-mobil](https://github.com/yunusemrecelikelll-cloud/asistan-mobil).

## Çalıştırma

```powershell
.\baslat.ps1              # Ollama + sunucu + arayüz
.\testler\hepsi.ps1       # testler
```

## Depoda olmayanlar

`data/` klasörü depoya girmiyor — parola, tuz, imza özel anahtarı, uyku ve
harcama kayıtları, konuşma geçmişi orada duruyor. `.venv/` ve
`tools/cloudflared.exe` de dışarıda.
