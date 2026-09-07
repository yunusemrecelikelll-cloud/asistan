# Asistan

Claude Code projelerinin komuta merkezi. Buradan verdiğin her komut, ilgili
projede **Claude tarafından** çalıştırılır. Yerel model yalnızca komutunu
ayrıntılı bir göreve dönüştürmek için kullanılır — asıl işi Claude yapar.

## Akış

```
sen yazarsın / konuşursun
      ↓
yerel model (9B, ücretsiz) komutu ayrıntılı göreve çevirir
      ↓
görev ONAYINA sunulur — düzenleyebilirsin
      ↓
onayladığında ilgili projede Claude Code çalışır
      ↓
sonuç sana döner, istersen sesli okunur
```

Onaylamadan hiçbir şey gönderilmez. Onay kutusunda **Ctrl+Enter** gönderir,
**Esc** iptal eder.

## Başlatma

Masaüstündeki **Asistan** kısayolu. Ollama'yı, sunucuyu ve pencereyi sırayla
açar. Sunucuyu elle yeniden başlatmak için `yeniden_baslat.ps1`.

## Sürekli çalışma

Sistem bilgisayar kapanıp açıldığında kendiliğinden geri gelir.

```
.\otomatik_baslat.ps1           kur (bir kez)
.\otomatik_baslat.ps1 -Durum    durumu gör
.\otomatik_baslat.ps1 -Kaldir   kaldır
```

Kurulduğunda Görev Zamanlayıcı'ya **Asistan** adında bir görev eklenir. Görev,
oturum açıldıktan 30 saniye sonra `gozetmen.ps1` betiğini başlatır.

Gözetmen 20 saniyede bir iki servisi de yoklar:

| Servis | Adres | Görevi |
|---|---|---|
| Ana sunucu | 127.0.0.1:8770 | Arayüz, projeler, mentör, koç |
| Ses servisi | 127.0.0.1:8771 | XTTS ses klonlama (isteğe bağlı) |

Bir servis **çökerse** yeniden başlatılır. **Asılı kalırsa** — süreç ayakta
ama sağlık ucuna yanıt vermiyorsa — önce öldürülüp sonra başlatılır. Görev
Zamanlayıcı'nın kendi "çökünce yeniden başlat" ayarı asılı kalmayı fark
etmediği için bu ayrı kontrol gerekiyor.

Ses servisi model yüklerken 90 saniye boyunca sağlık yoklamasından muaf
tutulur; yükleme 12 saniye sürüyor ve bu sürede yanıt vermiyor.

Gözetmen günlüğü: `data/gozetmen.log`

Görev **oturum açılışına** bağlı, bilgisayar açılışına değil. Açılışa bağlamak
yönetici yetkisi ister ve mikrofon gibi oturuma bağlı şeyleri bozar.

### Elle yönetim

```
.\yeniden_baslat.ps1       yalnızca ana sunucuyu yeniden başlat
.\yeniden_baslat.ps1 -Ses  ses servisini de yeniden başlat
.\ses_servisi.ps1          yalnızca ses servisi
.\ses_servisi.ps1 -Durdur  ses servisini durdur
```

Gözetmen çalışırken elle kapattığın servis 20 saniye içinde geri gelir.
Tamamen durdurmak istersen önce `otomatik_baslat.ps1 -Kaldir`.

## Kullanım

**Yazarak:** alttaki kutuya yaz, Enter.
**Konuşarak:** mikrofonu basılı tut (veya yazı alanı dışındayken **Boşluk**).

Soldan bir proje seç; komutların o projeye gider. Seçmezsen mesajında geçen
proje adından bulmaya çalışır, bulamazsa sorar.

### Üst çubuk

- **Brifing** — programın projeyi nasıl anladığını gösterir: README, manifest,
  dosya yapısı, son commitler, geçmiş Claude oturumlarının başlıkları,
  notların. Ücretsiz, dosyalardan derlenir.
- **Derin inceleme** — Claude projeyi okuyup kalıcı bir brifing çıkarır.
- **Otomatik devam** — aşağıya bak.
- **Rapor** — tüm projelerin ya da seçili projenin durumu. Model kullanmaz.

## Otomatik devam

Açtığın projede, belirlenen aralıkla Claude'a "kaldığın yerden devam et"
görevi gönderilir. Sıradaki adımı Claude'un kendisi seçer ve uygular — bu
kararı yerel modele bırakmıyoruz, orada güvenilir değil.

Varsayılan: 15 dakikada bir, üst üste en fazla 8 tur.

Kendini şu durumlarda kapatır:

- Claude "yapacak iş kalmadı" derse,
- tur sayısı dolduğunda,
- bir tur hata verdiğinde,
- günlük kullanım sınırı dolduğunda.

Gönderilen görev yıkıcı işleri açıkça yasaklar: dosya/klasör silme, git
geçmişini değiştirme, bağımlılık kaldırma, üretim ayarlarına dokunma.

Otomatik kip, yarım kalmış işi belli olan projelerde iyi çalışır. Her şeyi
tamamlanmış bir projede Claude ne yapacağını sorabilir ya da iş olmadığını
bildirip kapanır.

## Yetki

`Ayarlar → Claude yetkisi`:

| Kip | Ne yapabilir |
|---|---|
| **bypassPermissions** (varsayılan) | Dosya yazar **ve** kabuk komutu çalıştırır — test, derleme, kurulum. Tam yetki. |
| acceptEdits | Sadece dosya yazar. `python tests/run_tests.py` gibi komutlar reddedilir. |
| manual | Hiçbir şey yapamaz, yalnızca okur. |

Varsayılan `bypassPermissions`, çünkü istediğin buydu: program gerçekten iş
yapabilsin. Bu, Claude'un projede sormadan komut çalıştırabileceği anlamına
gelir. Daha temkinli istersen `acceptEdits`'e al — ama o zaman testleri
çalıştıramaz.

### Geri alma

Git deposu olan projelerde, çalışma ağacı kirliyse değişiklikten önce
kurtarılabilir bir kontrol noktası bırakılır (`git stash create` +
`refs/asistan/<zaman>`). Çalışma ağacına dokunmaz.

```bash
cd <proje klasörü>
git for-each-ref refs/asistan     # kontrol noktaları
git stash apply <sha>             # geri uygula
```

Git deposu olmayan projelerde geri alma yok — orada dikkatli ol.

Her eylem `data/asistan.db` içindeki `eylemler` tablosuna yazılır: komut,
süre, tüketim, çıktı, kontrol noktası.

## Faturalandırma

**Ayrı API anahtarı kullanılmaz.** Bilgisayarındaki `claude` CLI, `~/.claude`
içindeki **Claude Max** aboneliğinin oturumuyla çalışır. Alt süreç
başlatılırken `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`ANTHROPIC_BASE_URL`, `CLAUDE_API_KEY` temizlenir; ileride bir anahtar
tanımlansa bile kullanılmaz.

Arayüzdeki "birim", CLI'ın bildirdiği liste fiyatı karşılığıdır
(`costBasis: list`) — faturaya dönüşmez, abonelik kotasının ne kadar
tüketildiğini gösterir.

Emniyet freni: **günlük kullanım sınırı**, varsayılan 25 birim. Aşılırsa komut
gönderilmez ve otomatik kip kapanır. Ayarlardan değiştirilir (0 = sınırsız).

Ölçek fikri: geniş bir keşif görevi 2-3 birim, dar bir görev 0.02-0.6 birim.
Dar ve net komutlar hem ucuz hem hızlı.

## Modeller

- **Taslak/sohbet:** `qwen3.5:9b-tr` — yerelde, ücretsiz. Bu bilgisayarda
  8 GB VRAM'e tam sığmadığı için %75 GPU / %25 CPU çalışır; taslak yazımı
  ~15 sn sürer. Hızlandırmak istersen Ayarlar'dan `qwen3.5:4b-tr`.
- **Komut:** `sonnet` (varsayılan). `haiku` daha ucuz ama basit komutları
  yanlış anlayabiliyor; `opus` en yetenekli.
- **Konuşma tanıma:** Whisper `medium`, GPU'da ~0.33 sn. Ses kaydı yerelde
  kalır, hiçbir yere gönderilmez.
- **Seslendirme:** Microsoft neural Türkçe (Ahmet/Emel). Yalnızca yanıt metni
  dışarı gider.

## Bilinen davranışlar

**Oturum sürekliliği.** Manuel komutlar projedeki önceki Claude oturumunu
sürdürür (`--resume`), böylece bağlam korunur. Otomatik turlar temiz oturumda
başlar: sürdürülen bir oturumda eski "izin reddedildi" mesajları Claude'u
denemeden pes etmeye ikna edebiliyor. Bir proje takılırsa oturum bağını
`POST /api/projeler/<id>/oturum-sifirla` ile koparabilirsin.

**Tur sınırı.** `komut_azami_tur` varsayılan 0 (sınırsız). Değer verirsen ve iş
yarıda kesilirse eylem `kesildi` olarak işaretlenir; otomatik kip bunu hata
saymaz, sonraki turda devam eder.

## Yapı

```
frontend/          masaüstü arayüzü
mobil/             Flutter (Android)
apple/             Swift — iPhone + Apple Watch
backend/
  main.py          API uçları
  store.py         SQLite
  auth.py          parola / belirteç

  ── Claude sevk ──
  dispatch.py      claude -p ile gönderim, kontrol noktası, kullanım freni
  brain.py         promptu detaylandırma, yerel model
  brief.py         proje brifingi (programın projeyi anlaması)
  auto.py          otomatik devam zamanlayıcısı
  bulk.py          toplu iş
  projects.py      proje keşfi, git durumu, raporlar

  ── plan ve koçluk ──
  mentor.py        günü bloklara böler, kaçırılanı telafiye yazar
  duzen.py         çalışma düzeni (vardiya / sabit / serbest)
  takvim.py        dış takvim (ICS)
  koc.py           ritüeller, alışkanlıklar, örüntü analizi
  yasam.py         uyku, harcama, beslenme, spor, su, ruh hâli
  ekran.py         ekran süresi (varsayılan kapalı)

  ── atölye ──
  baski.py         3D baskı takibi, yazıcı keşfi
  klasor.py        "3d Projeler" klasör izleyicisi
  istatistik.py    atölye / mentörlük / maliyet özetleri

  ── ses ──
  speech.py        Whisper + edge-tts
  dogal.py         yazı dilini konuşma diline çevirme, bürünsel parçalama
  ses_klon.py      XTTS istemcisi
  klonses/         XTTS servisi (ayrı süreç, ayrı venv)
  kanal.py         WebSocket kanalı (telefon + saat)
  niyet.py         kullanıcı ne demek istedi

  ── altyapı ──
  olay.py          canlı olay akışı
  gunluk.py        işlem günlüğü
  yedek.py         yedekleme
```

**Windows notu:** Prompt, `claude`'a argüman olarak değil **stdin'den**
verilir. `claude` bir `.CMD` sarmalayıcısıdır; çok satırlı bir metin argüman
olarak geçildiğinde satır sonu komut satırını böler ve arkadan gelen bayraklar
(`--output-format json`, `--permission-mode`) sessizce düşer.

## Sorun giderme

**Komut çalışıyor ama "izin yok" diyor:** Ayarlar'dan yetkiyi
`bypassPermissions` yap.

**Ollama noktası kırmızı:** Ollama kapalı; kısayolu tekrar çalıştır.

**Taslak çok yavaş:** Ayarlar'dan taslak modelini `qwen3.5:4b-tr` yap.

**Sunucu takıldı:** `yeniden_baslat.ps1`. (`pkill` bu süreçleri yakalamaz.)

**Komut iptal edilmiyor:** Artık ediliyor. `claude` bir `.CMD` sarmalayıcısı
(cmd.exe → node); `p.kill()` yalnızca cmd'yi öldürüyor, asıl işi yapan node
hayatta kalıyordu. `taskkill /T` ile bütün ağaç alınıyor.

**Loglar:** `data/sunucu.log`, `data/sunucu.err.log`.

## Kaldırma

`Asistan` klasörünü ve kısayolları sil. Ollama ve Claude Code kurulumuna
dokunmaz.

---

## Tüm projelerin özeti

**Tümünü özetle** düğmesi, her projenin köküne `ASISTAN-OZET.md` yazdırır:
ne işe yaradığı, teknolojisi, yapısı, şu anki durumu, **yapılan değişiklikler
listesi** ve sıradaki adımlar. Değişiklik listesi hiç silinmez, üstüne eklenir;
git geçmişi varsa geriye dönük doldurulur.

Asistan bu dosyayı her brifingde **en öncelikli kaynak** olarak okur. Yani
projeler kendi özetlerini tutar, program da onları sürekli okuyup üstüne
konuşur.

Projelere sırayla gider, paralel değil. Her projeden sonra kullanım sınırını
kontrol eder; sınır dolarsa kalanları atlar ve bunu rapor eder. 16 projede
ölçülen toplam tüketim: **3.33 birim** (proje başına ~0.2).

Tek tek de çalıştırılabilir: `POST /api/toplu/ozet` gövdesine
`{"proje_idler": [18, 10]}` verirsen sadece onlara gider.
`POST /api/toplu/komut` ile aynı komutu birden çok projeye gönderebilirsin.

## Telefondan kullanma — sabit adres

Adres **Tailscale** ile veriliyor ve bir daha değişmiyor. Tailnet yalnızca
kendi cihazlarına açık, herkese açık bir adres değil.

**Kendi adresini öğrenmek için** `telefon.ps1` çalıştır; Tailscale adını ve
parolayı yazdırır. Biçim şöyle:

```
http://<bilgisayar-adi>.<tailnet>.ts.net:8770
```

Adres depoya yazılmıyor — depo herkese açık, tailnet adı da makineni
adlandıran bir bilgi. Parola `data/parola.txt` içinde ve o da depoda değil.

### iPhone'da

1. App Store'dan **Tailscale** uygulamasını kur, aynı hesapla giriş yap.
2. Asistan uygulamasını aç, yukarıdaki adresi ve parolayı gir.

Bu adres Flutter uygulamasında sorunsuz çalışır — **mikrofon dahil**. Yerel
uygulamalar tarayıcının "güvenli bağlam" kısıtına tabi değildir.

### Safari / PWA da kullanmak istersen

Tarayıcıda mikrofon için HTTPS şart. Tailscale bunu ücretsiz veriyor ama
varsayılan olarak kapalı:

1. https://login.tailscale.com/admin/dns adresini aç
2. **HTTPS Certificates** → Enable
3. `telefon.ps1` çalıştır — bu kez `https://<bilgisayar-adi>.<tailnet>.ts.net`
   verecek (port yok)

### Sunucunun dinleme adresi

Telefondan erişim için sunucu `0.0.0.0` dinliyor (ayar: `dinleme_adresi`).
Yerel olmayan **her** istek parola ister — ev ağından gelen de dahil. Yalnızca
bu bilgisayardan kullanacaksan `127.0.0.1` yapabilirsin.

### Yedek: geçici tünel

Tailscale çalışmazsa `telefon.ps1` eski cloudflared tüneline düşer; o adres
her açılışta değişir.

### PWA mı, uygulama mı

Tarayıcıdan açılan PWA hâlâ çalışıyor (HTTPS açarsan). Ama asıl kullanım
`mobil/` klasöründeki Flutter uygulaması — App Store gerekmeden, imzasız IPA
olarak kurulabiliyor. Ayrıntılar: `mobil/BENIOKU.md`.

---

## Mobil uygulama (Flutter)

`mobil/` klasöründe iOS + Android uygulaması var. Masaüstü arayüzünün aynısı:
komut ver, taslağı onayla, sonucu gör, sesli konuş.

Ayrıntılar ve Codemagic adımları: `mobil/BENIOKU.md`.

### Senkronizasyon

Sunucuya bir olay akışı eklendi: `/api/olaylar` (uzun yoklama). Mesaj, taslak,
komut sonucu, otomatik tur, toplu iş ilerlemesi — her değişiklik yayınlanır ve
bekleyen bütün istemciler o anda uyanır.

```
telefonda komut ver ──┐
                      ├──► sunucu ──► olay ──► iki taraf da tazelenir
masaüstünde komut ver ┘
```

Mobil uygulamada hiçbir durum yerelde tutulmaz; her şey sunucudan okunur. Bu
yüzden ayrı bir eşitleme mantığı yok — iki istemci de tek kaynağa bakıyor.
Telefonda bıraktığın onay bekleyen görevi masaüstünde onaylayabilirsin.

### Ses neden sunucuda

Telefonun kendi konuşma tanıma ve seslendirmesi kullanılmıyor:

- **Dinleme** telefonda kaydedilip sunucudaki Whisper'a gönderilir — Türkçede
  cihaz tanımasından belirgin daha isabetli.
- **Konuşma** sunucudaki Microsoft neural Türkçe sesle üretilip mp3 olarak
  çalınır. iOS'un Türkçe sistem sesi robotik duruyor; bu yolla masaüstündekiyle
  birebir aynı doğal ses duyulur.

---

## iPhone ve Apple Watch (Swift)

`apple/` klasöründe iPhone ve Apple Watch uygulamaları var. İkisi ortak bir
Swift paketini paylaşıyor.

Flutter yerine Swift seçilmesinin tek sebebi var: **Flutter'ın watchOS
desteği yok.** Saat uygulaması yazılacaksa saat tarafı zaten SwiftUI olmak
zorunda; o hâlde telefonu da aynı dilde yazmak tek ses ve ağ katmanı demek.

**Saat aptal bir uç.** Ayar tutmuyor: sunucu adresi yok, parola yok, ayar
ekranı yok. Konuşmayı telefona veriyor, telefondan gelen sesi çalıyor.

```
saat ──konuşma──► telefon ──Tailscale──► bilgisayar
saat ◄────ses──── telefon ◄─────────────┘
```

Saate giden ses AAC'ye sıkıştırılıyor: iki saniyelik bir cümle 96 KB yerine
~8 KB. Aradaki bağ Bluetooth olduğu için asıl darboğaz orası.

> **Bu kod hiç derlenmedi.** Xcode yalnızca macOS'ta çalışıyor, burada Mac
> yok. Kaynak eksiksiz, sunucu tarafı ölçülerek doğrulandı, ama Swift
> derleyicisinden geçmedi ve cihazda çalıştırılmadı.

Ayrıntılar, Mac'te kurulum adımları ve gecikme ölçümleri:
`apple/BENIOKU.md`.
