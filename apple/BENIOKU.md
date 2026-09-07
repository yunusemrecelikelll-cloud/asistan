# NOVA — iPhone ve Apple Watch (Swift)

Bilgisayardaki NOVA sunucusunun **yerel Apple istemcisi**. iPhone uygulaması
ve Apple Watch uygulaması aynı çekirdeği paylaşıyor.

> **Derleniyor, ama cihazda çalıştırılmadı.**
>
> Bu bilgisayarda Mac yok; Xcode yalnızca macOS'ta çalışıyor. Bu yüzden
> derlemeyi GitHub Actions'ın macOS makinesinde yapıyoruz. Her itişte
> iPhone ve Apple Watch hedefleri derleniyor ve paket testleri simülatörde
> koşuyor — durum deponun üstündeki rozette görünüyor.
>
> Doğrulanan: kod derleniyor, tipler tutuyor, API'ler hedeflenen sürümlerde
> var, 12 birim testi geçiyor.
>
> **Doğrulanmayan: cihazdaki davranış.** `AVAudioEngine`in gerçekten tampon
> verip vermediği, `WatchConnectivity`nin mesaj sınırına çarpıp çarpmadığı,
> AAC kodlamasının hızı, ses oturumu kesintileri, gerçek gecikme — hiçbiri
> derleyicinin görebileceği şeyler değil. Bir iPhone'a kurulana kadar
> "çalışıyor" demiyoruz.

## Neden Swift, neden Flutter değil

Karar tek bir gerçeğe dayanıyor: **Flutter'ın watchOS desteği yok.** Ne
resmî ne de kullanılabilir bir üçüncü taraf yolu var. Saat uygulamasını
yazmak istiyorsan saat tarafı zaten SwiftUI olmak zorunda.

Böyle olunca seçenekler şunlar:

| Yol | Sonuç |
|---|---|
| Flutter (telefon) + SwiftUI (saat) | İki ayrı dil, iki ayrı ses/ağ katmanı, iki kez bakım |
| **Swift/SwiftUI (ikisi de)** | Tek dil, ortak paket, tek ses ve ağ katmanı |

Ayrıca ihtiyacın olan üç şey doğrudan Apple çerçevelerine bağlı ve Flutter'da
hepsi eklenti arkasından, gecikme ekleyerek geliyor:

- **WatchConnectivity** — saat ile telefon arası röle. Flutter eşdeğeri yok.
- **AVAudioEngine** — mikrofonu tampon tampon okuyup konuşma SÜRERKEN
  göndermek. Flutter'ın kayıt eklentileri kaydı dosyaya yazıp bitince veriyor;
  bu tur başına ~1 saniye ekliyor.
- **AVAudioPlayerNode** — cümleleri boşluksuz arka arkaya çalmak. Eklentiyle
  her parça ayrı çalıcı demek, parçalar arası 100-200 ms boşluk demek.

`mobil/` altındaki Flutter uygulaması **duruyor** — Android tarafı hâlâ onunla.
Bu klasör Apple tarafını devralıyor.

---

## Saat nasıl çalışıyor

**Saat aptal bir uç.** Hiçbir ayar tutmuyor: sunucu adresi yok, parola yok,
ayar ekranı yok. Yaptığı tek iş konuşmayı telefona vermek ve telefondan gelen
sesi çalmak.

```
saat ──konuşma──► telefon ──Tailscale──► bilgisayar
saat ◄────ses──── telefon ◄─────────────┘
```

Bilgisayara ulaşmayı, kimlik doğrulamayı ve Tailscale'i telefon hallediyor.

### Doğrudan Wi-Fi yolu neden yok

watchOS 6'dan beri saat teknik olarak kendi başına ağa çıkabiliyor, ve bir
süre kod o yolu da deniyordu. Ama işlemiyordu: `Ayarlar` sınıfı `UserDefaults`
ve Keychain kullanıyor, ikisi de **cihaz başına ayrı**. Telefona girdiğin
adres ve parola saate hiç geçmiyor. Saatte o değerler her zaman boş olduğu
için doğrudan yol hiçbir zaman kurulamıyordu — ama denenmesi her bağlanışa
1,2 saniye bindiriyordu.

Saate ayar ekranı koymak istemedik. O yüzden yol tek: telefon rölesi.
`YolSecici` kaldırıldı.

### Saate giden ses neden sıkıştırılıyor

Saat ile telefon arasındaki bağ Bluetooth ve asıl darboğaz o.

XTTS 24 kHz 16-bit mono WAV üretiyor: saniyede 48 KB. İki saniyelik bir
cümle 96 KB — bu bağda yarım saniyeden fazla aktarım demek. Üstelik
`WCSession.sendMessage` tek mesajda ~64 KB taşıyabildiği için o cümle
zaten tek parça gidemiyordu; eski kod bunu hiç hesaba katmamıştı ve
sessizce başarısız oluyordu.

Şimdi telefon sesi **AAC'ye çeviriyor**: aynı cümle ~8 KB. Kodlama telefonda
10-20 ms sürüyor, kazanılan aktarım süresi yüzlerce milisaniye. Sığmayan
olursa 40 KB'lık dilimlere bölünüp saatte birleştiriliyor.

Mikrofon ters yönde **ham PCM** gidiyor — sıkıştırmak konuşma tanımanın
isabetini düşürür. Küçük tamponlar 4 KB'lık paketlerde birleştiriliyor
(saniyede 23 mesaj yerine 8); konuşma biterken kalan artık `ses_bitti`
çerçevesinden önce boşaltılıyor, yani tura gecikme eklemiyor.

### Röle protokolü

`sendMessage` sıra garantisi **vermiyor**. Bu yüzden bir ses parçasını tarif
eden başlık ile verisi **aynı mesajda** gidiyor:

```
telefon → saat   ["a": dilim, "i": kimlik, "k": sıra, "n": toplam, "b": biçim]
telefon → saat   ["c": ham protokol çerçevesi]        (yazi/yanit/bitti/hazir/
                                                       yetkisiz/hata)
saat → telefon   ["c": ham protokol çerçevesi]
saat → telefon   ["m": mikrofon PCM]
saat → telefon   ["komut": "role_ac" | "role_kapat"]
```

Saat dilimleri birleştirdikten sonra protokolün beklediği sırayı kendisi
üretiyor (önce `parca` çerçevesi, hemen ardından ikili veri). Böylece
`NovaBaglanti` rölenin varlığını hiç bilmeden çalışıyor.

---

## Gecikme için ne yapıldı

Ölçüm (bilgisayarda, yerel ağ): kullanıcı sustuktan sonra **ilk sesin
duyulmasına 2,2-3,7 saniye**. Öncesi 41 saniyeydi.

### Sunucu tarafı

1. **Kalıcı WebSocket** — HTTP'de sesli tur dört ayrı istekti; her istek yeni
   el sıkışma (yerel ağda 30-60 ms, hücreselde 150-300 ms). Şimdi bir kez.
2. **Ses kayıt biterken değil, SÜRERKEN gidiyor** — kullanıcı sustuğunda ses
   zaten sunucuda; yükleme beklemesi yok.
3. **Yanıt cümle cümle üretiliyor ve cümle cümle seslendiriliyor.**
4. **Niyet çözme ile yanıt üretme paralel.**
5. **Ses parçaları tek çalıcıya sıraya konuyor** — cümleler arası boşluk yok.
6. **Modeller sunucu açılışında ısıtılıyor.**
7. **Konuşma tanıma 10,6 saniyeden 0,22 saniyeye indi** — model `large-v3`'tü
   (`large-v3-turbo` neredeyse aynı isabette ama çok daha hızlı) ve 8 GB kart
   üç modeli birden taşırken sıkışıyordu. Whisper `int8_float16`'ya alınınca
   ~660 MB yer açıldı.
8. **Spekülatif üretimin iptali artık beklemiyor** — niyet "sohbet" çıkmayınca
   atılan metnin bitmesi bekleniyordu (yarım cümle), bu her proje komutunun
   kritik yolundaydı.

### İstemci tarafı

9. **Ses motoru tur başlarken ısıtılıyor** — `AVAudioEngine.start()` 50-150 ms
   sürüyor ve bu bedel eskiden ilk ses parçası geldiğinde, tam kritik yolun
   üstünde ödeniyordu. Artık kullanıcı sustuğu an kuruluyor.
10. **Mikrofon izni her turda sorulmuyor** — izin verilmişse eşzamanlı
    okunuyor; eskiden her tur bir eşzamansız gidiş dönüş vardı.
11. **Sessizlik eşiği 0,7 sn → 0,55 sn** — bu süre her turun sonuna doğrudan
    ekleniyor. Yoklama da 150 ms yerine 50 ms'de bir.
12. **Adres başına 1,5 saniyelik süre sınırı** — yanlış ağdayken (evden
    çıkınca yerel adres, eve girince Tailscale) hata ancak soket zaman
    aşımına uğrayınca anlaşılıyordu: 30 saniye. Uygulama her açılışta o
    kadar "Bağlanıyor…" yazıyordu.
13. **Saate giden ses AAC** — yukarıya bak.

Uygulama ölçtüğü gecikmeyi ekranda gösteriyor (`ilk ses NNN ms`), böylece
yerel ağ ile Tailscale arasındaki farkı doğrudan görüyorsun.

Ayarlar (sunucu tarafı, `ayarlar` tablosu): `stt_modeli`
(`large-v3-turbo`), `stt_kesinlik` (`int8_float16`), `stt_isin` (`1`).

---

## Dosyalar

```
apple/
├── NovaPaylasilan/                 Swift Package — iOS + watchOS ortak
│   └── Sources/NovaPaylasilan/
│       ├── Protokol.swift          kanal.py protokolünün Swift karşılığı
│       ├── Tasiyici.swift          taşıma katmanı arayüzü
│       ├── SoketTasiyici.swift     doğrudan WebSocket
│       ├── NovaBaglanti.swift      protokol katmanı (taşıyıcıdan bağımsız)
│       ├── SesOturumu.swift        AVAudioSession — kayıt ve çalma ortak
│       ├── SesKayit.swift          mikrofon, konuşurken gönderim
│       ├── SesCalar.swift          boşluksuz sıralı çalma + WAV/mp3/AAC çözme
│       ├── SesSikistirici.swift    saate giden sesi AAC'ye çevirir
│       ├── Ayarlar.swift           adresler + Keychain'de parola (SADECE telefon)
│       └── Oturum.swift            arayüzün bağlandığı tek durum nesnesi
├── NovaTelefon/
│   ├── NovaTelefonApp.swift
│   ├── AnaGorunum.swift            küre + döküm + konuşma düğmesi
│   ├── KureGorunumu.swift          neon küre (masaüstündekinin eşi)
│   ├── YanBar.swift                bölümler + ayarlar
│   └── SaatRolesi.swift            saat için röle (AAC + dilimleme)
└── NovaSaat/
    ├── NovaSaatApp.swift
    ├── SaatGorunumu.swift          küçük küre + tek düğme
    └── RoleTasiyici.swift          telefon üzerinden taşıma (tek yol)
```

`Ayarlar` yalnızca telefonda anlamlı — saat hiç okumuyor.

## Derleme

### GitHub'da (Mac gerekmeden)

`.github/workflows/apple.yml` her itişte çalışıyor:

| Adım | Ne doğruluyor |
|---|---|
| Ortak paket — iOS | `NovaPaylasilan` iPhone için derleniyor |
| Ortak paket — watchOS | aynısı saat için |
| iPhone uygulaması | `NovaTelefon` + gömülü saat uygulaması |
| Apple Watch uygulaması | `NovaSaat` |
| Paket testleri | protokol ve WAV çözücü testleri, iOS simülatöründe |

Adımlar hata alsa da devam ediyor: derleme hatalarını teker teker bulmak
yerine tek çalıştırmada hepsini görmek istiyoruz. İmza yok — amaç
derleyiciden geçmek, mağazaya çıkmak değil.

Elle tetiklemek için Actions sekmesinden **Run workflow**.

### Mac'te

Xcode projesi depoda **tutulmuyor**; `apple/project.yml`den üretiliyor.
`.xcodeproj` makine üretimi, birleştirmesi imkânsız bir XML — okunabilir
bir tanım tutup ondan üretmek hem daha temiz hem de kurulum adımlarını
belgelemekten kurtarıyor.

```bash
brew install xcodegen
cd apple
xcodegen generate
open Nova.xcodeproj
```

Bu kadar. Hedefler, dosya-hedef eşleşmeleri, `Info.plist` anahtarları
(mikrofon izni, yerel ağ izni, Bonjour, arka planda ses, şifresiz ws://)
ve saat uygulamasının telefona gömülmesi — hepsi `project.yml` içinde.

Cihaza kurmak için tek gereken imza: Xcode → hedef → Signing &
Capabilities → kendi Apple hesabını seç. Ücretsiz hesap yeterli, uygulama
yedi günde bir yeniden kurulmak ister.

### İlk çalıştırma

Telefon uygulamasını aç → yan bar → Ayarlar:

- **Yerel ağ adresi:** `192.168.1.X:8770` (bilgisayarın ev ağındaki adresi)
- **Tailscale adresi:** `100.x.y.z:8770`
- **Parola:** sunucudaki parola (`telefon.ps1` yazdırıyor)

**Saatte yapılacak bir şey yok** — telefon bağlanınca saat de çalışıyor.

## Bilinen sınır

**watchOS 10'da kulaklık mikrofonu kullanılmıyor.** `.allowBluetooth`
(kulaklığın mikrofonunu da devreye alan HFP kipi) watchOS'ta ancak 11.0'da
geldi. Hedefimiz watchOS 10 olduğu için koşullu ekliyoruz: 10'da ses
kulaklıktan çalıyor ama mikrofon saatin kendisi oluyor, 11'de ikisi de
kulaklıktan. Bunu ilk derlemede derleyici yakaladı.

## Sunucu tarafında ne değişti

- `backend/kanal.py` — akışlı sohbet, spekülatif üretim, `.pcm` kabulü.
  Bağlantıdan sonraki ilk mesajı 25 saniye geciktiren hata düzeltildi
  (olay akışını bloke eden `bekle()` çağrısını doğrudan olay döngüsünde
  çalıştırıyordu). Olay çerçevesi artık **iç içe** gidiyor:
  `{"tur": "olay", "olay": {...}}` — düz yayıldığında olayın kendi `tur`
  alanı dıştakini eziyor ve istemciye hiç `{"tur": "olay"}` ulaşmıyordu.
- `backend/brain.py` — `yerel_sohbet_akis()`, cümle cümle üretim.
- `backend/main.py` — `sohbet_akisi()`, `taslak_uret(hazir_niyet:)`,
  açılışta model ısıtma, `lifespan` (eski `on_event` kaldırıldı).
- `backend/dogal.py` — `sesli_ek()`; işaretleri yanıtı üreten model koyuyor.

Sunucu testleri: `.\testler\hepsi.ps1` (398 test).
