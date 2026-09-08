# NOVA — App Store Connect ve Codemagic kurulumu

Bu belge **tarayıcı erişimi olan bir asistan için** yazıldı. Kod tarafı bitti;
geriye yalnızca oturum açmayı gerektiren adımlar kaldı.

---

## Durum

`yunusemrecelikelll-cloud/asistan` deposunda bir iPhone + Apple Watch
uygulaması var (`apple/` klasörü, Swift/SwiftUI).

**Hazır olanlar:**

- Kod iOS ve watchOS için derleniyor — GitHub Actions her itişte doğruluyor
  ([apple.yml](../.github/workflows/apple.yml)), 12 birim testi geçiyor.
- Xcode projesi `apple/project.yml`den üretiliyor (XcodeGen). Depoda
  `.xcodeproj` tutulmuyor.
- Codemagic yapılandırması yazıldı: [codemagic.yaml](../codemagic.yaml),
  workflow adı `apple`.

**Eksik olanlar — bu belgenin konusu:**

1. Apple tarafında iki Bundle ID kaydı ve bir uygulama kaydı.
2. Codemagic'te deponun bağlanması ve ilk derlemenin başlatılması.

---

## ⚠️ Önce bunu oku — bozulmaması gerekenler

**Yeni dağıtım sertifikası (Distribution Certificate) ÜRETME.**

Apple hesabı en fazla 3 dağıtım sertifikası tutuyor ve bu havuz aynı
hesaptaki **KPSS Hazırlık** projesiyle ortak. Yeni sertifika üretmek o
projenin derlemelerini bozabilir. Mevcut sertifika zaten var ve Codemagic
onu kullanıyor.

Bir ekranda "Create Certificate" ya da "Generate new certificate" çıkarsa
**yapma**, dur ve bildir.

**Aynı hesaptaki başka uygulamalara dokunma.** Özellikle:

- `com.asistan.asistanMobil` — aynı projenin Flutter sürümü
- KPSS ile ilgili her şey

**App Store incelemesine gönderme.** Hedef yalnızca TestFlight.

---

## Görev A — App Store Connect

Hesap: `yunusemrecelikelll@gmail.com`

### A1. İki Bundle ID kaydet

<https://developer.apple.com/account/resources/identifiers/list>

**Identifiers → + → App IDs → App**

| Alan | Birinci kayıt | İkinci kayıt |
|---|---|---|
| Description | `NOVA` | `NOVA Watch` |
| Bundle ID | **Explicit** → `com.asistan.nova` | **Explicit** → `com.asistan.nova.watchkitapp` |
| Capabilities | hiçbiri işaretlenmeyecek | hiçbiri işaretlenmeyecek |

Not: Saat uygulamasının kimliği de burada, iOS App IDs altında kaydediliyor —
ayrı bir watchOS bölümü yok.

Capability gerekmiyor çünkü uygulama yalnızca mikrofon ve yerel ağ
kullanıyor; ikisi de `Info.plist` anahtarı, App ID yetkisi değil. Arka planda
ses de öyle.

### A2. Uygulama kaydı oluştur

<https://appstoreconnect.apple.com/apps> → **+ → New App**

| Alan | Değer |
|---|---|
| Platforms | **iOS** |
| Name | `Nova Asistan` (aşağıdaki nota bak) |
| Primary Language | **Turkish** |
| Bundle ID | `com.asistan.nova` (A1'de kaydedilen) |
| SKU | `nova-asistan` |
| User Access | **Full Access** |

**Ad hakkında:** App Store'da uygulama adları benzersiz olmak zorunda ve
"NOVA" neredeyse kesin alınmıştır. `Nova Asistan` alınmışsa sırayla dene:
`Nova Kisisel Asistan` → `Nova Komuta` → `NOVA Assistant TR`. **Hangisini
kullandığını bildir.**

Bu ad yalnızca mağaza/TestFlight listesinde görünüyor. Telefonun ana
ekranında yazacak ad `NOVA` ve o `project.yml` içinden geliyor, bundan
etkilenmiyor.

Kayıt **"Prepare for Submission"** durumunda kalsın. App Store'a yayınlamak
gerekmiyor; TestFlight bundan bağımsız çalışıyor.

### A3. Issuer ID'yi al

<https://appstoreconnect.apple.com/access/integrations/api>

**Users and Access → Integrations → App Store Connect API**

Sayfanın üstünde **Issuer ID** yazan bir UUID var
(`69a6de70-....` biçiminde). **Bunu kopyala ve bildir.**

Anahtar listesinde `4NJXFNWG7L` kimlikli bir anahtar görünmeli — o zaten var,
yenisini üretme. Görünmüyorsa bunu bildir.

---

## Görev B — Codemagic

<https://codemagic.io/apps> — GitHub hesabıyla giriş yapılıyor.

### B1. Entegrasyonu doğrula

**Teams / Personal Account → Integrations → App Store Connect**

`4NJXFNWG7L` **adında** bir entegrasyon olmalı (Flutter uygulaması bunu
kullanıyor). Adın birebir bu olması şart — `codemagic.yaml` ona bu adla
bakıyor.

Yoksa dur ve bildir. Varsa dokunma.

### B2. Depoyu ekle

**Add application → GitHub → `yunusemrecelikelll-cloud/asistan`**

- Depo herkese açık, ek yetki gerekmiyor.
- Proje türü sorulursa: **Other** (Flutter değil).
- Codemagic depodaki `codemagic.yaml`ı kendisi bulacak.

### B3. Derlemeyi başlat

**Start new build**

- Branch: `main`
- Workflow: **`NOVA — iPhone + Apple Watch (TestFlight)`** (yaml'da `apple`)

Derleme ~10-15 dakika sürüyor.

### B4. Sonucu bildir

Derleme bittiğinde şunları ilet:

- Derleme URL'si
- Başarılı mı, değilse **hangi adımda** ve **hata metninin tamamı**
- Başarılıysa: IPA artifact'ı üretildi mi, TestFlight'a yüklendi mi

---

## Beklenen sorunlar

**"No matching profiles found"** — Bundle ID kaydı (A1) eksik ya da yanlış
yazılmış. İkisinin de kayıtlı olduğunu doğrula.

**Saat uygulaması için profil bulunamıyor** — `com.asistan.nova.watchkitapp`
kaydı yapılmamış demektir. A1'in ikinci satırı.

**"Cannot create certificate"** ya da sertifika üretme teklifi — **DUR.**
Yukarıdaki uyarıya bak, bildir.

**"App record not found"** — A2 yapılmamış ya da bundle ID eşleşmiyor.

**Xcode/XcodeGen hatası** — kod tarafı, bana ait. Hata metnini olduğu gibi
ilet, düzeltilecek.

---

## Özet — bildirilecekler

1. **Issuer ID** (A3)
2. App Store Connect'te kullanılan **uygulama adı** (A2)
3. Bundle ID'ler kaydedildi mi (A1)
4. Codemagic derleme URL'si ve sonucu (B4)
5. Karşılaşılan her hatanın **tam metni**

Bunlar geldiğinde kalan iş bende.
