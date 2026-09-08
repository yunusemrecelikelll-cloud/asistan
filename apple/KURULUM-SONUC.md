# NOVA — kurulum sonucu

[KURULUM.md](KURULUM.md)'deki Görev A ve Görev B tamamlandı. Bu belge ne
yapıldığını, neyin neden bozulduğunu ve geriye ne kaldığını anlatıyor.

**Sonuç: derleme başarılı, imzalı IPA TestFlight'ta.**

---

## Özet — KURULUM.md'nin istediği beş şey

1. **Issuer ID:** `38299892-4b1a-4849-b76f-ae5a06a0916c`
   Anahtar listesinde `4NJXFNWG7L` mevcut (Admin). Yenisi üretilmedi.
2. **Uygulama adı:** `Nova Asistan` — ilk tercih boştu, alternatiflere gerek kalmadı.
   App id `6809634643`.
3. **Bundle ID'ler:** ikisi de kayıtlı, Explicit, hiç capability işaretli değil.
   `com.asistan.nova` (NOVA) ve `com.asistan.nova.watchkitapp` (NOVA Watch).
4. **Derleme:** <https://codemagic.io/app/6a9f5dccb1a7e43f6ca8680d/build/6a9f6a10dcbb14f1c738fea3>
   Başarılı. IPA üretildi ve TestFlight'a yüklendi.
5. **Hatalar:** aşağıda, tam metinleriyle.

Build Metadata: Binary State `Validated`, Device Family `iPhone, iPad, Apple Watch`,
sıkıştırılmış boyut 1.45 MB, Minimum iOS 17.0, `App Uses Non-Exempt Encryption: No`.

Entitlement'lar — saat uygulaması gömülü ve kendi kimliğiyle imzalı:

```
NOVA.app/NOVA                  ->  2YHT6YCHFY.com.asistan.nova
NOVA.app/Watch/NOVA.app/NOVA   ->  2YHT6YCHFY.com.asistan.nova.watchkitapp
```

---

## Bozulmaması gerekenler — durum

| | |
|---|---|
| Yeni dağıtım sertifikası | **Üretilmedi.** Hiçbir ekranda "Create Certificate" teklifi çıkmadı; Codemagic'teki "Generate certificate" düğmesine dokunulmadı. Hesapta hâlâ tek dağıtım sertifikası var (`Yunus emre Çelikel`, Distribution, 19.07.2027). |
| `com.asistan.asistanMobil` | Dokunulmadı. |
| KPSS | Dokunulmadı. Codemagic'e profil çekilirken KPSS'in iki profili işaretlenmedi. |
| App Store incelemesi | Gönderilmedi. Hedef yalnızca TestFlight. |

---

## Asıl sorun: "No matching profiles found"

İlk beş derleme, makineye bile inmeden, log üretmeden, ~0 saniyede şu hatayla düştü:

```
No matching profiles found for bundle identifier "com.asistan.nova" and distribution type "app_store"
```

KURULUM.md bunun sebebini "Bundle ID kaydı eksik ya da yanlış yazılmış" diye
işaretliyordu. Değildi — ikisi de doğru yazımla kayıtlıydı.

Apple portalında `com.asistan.nova` için hiç provisioning profile olmadığı görüldü ve
mevcut sertifikayla iki App Store profili elle üretildi. **Hata değişmedi.**

### Kök sebep

`ios_signing` bloğu Apple portalını **canlı sorgulamıyor.** Codemagic'in kendi deposuna
bakıyor: `Settings > codemagic.yaml settings > Code signing identities`. O depo tamamen
boştu — "No certificates shared with the team", "No profiles shared in a team".
Dokümantasyondaki belirleyici cümle:

> Codemagic will fetch any **uploaded** certificates and profiles matching…

Yani Apple tarafında profil üretmek yetmiyor; Codemagic'e ayrıca **çekilmeleri** gerekiyor.

### Çözüm — panelden, yaml'dan değil

`Code signing identities` altında:

- **iOS provisioning profiles → Fetch profiles**
  `nova_ios_app_store` (`com.asistan.nova`) ve
  `nova_watch_ios_app_store` (`com.asistan.nova.watchkitapp`) çekildi.
  KPSS'in iki profili işaretlenmedi.
- **iOS certificates → Fetch certificate**
  `apple_distribution`, production, 19.07.2027. Özel anahtar sormadı: Codemagic zaten
  tutuyor, sertifikayı zamanında o üretmiş
  (portalda "Created by: API Key 62fb5e58-…" yazıyor).

Bunu yapar yapmaz ön kontrol geçti ve Codemagic derlemeye kendi
`Set up code signing identities` adımını ekledi.

---

## codemagic.yaml — neden `ios_signing`e dönüldü

Ara denemede elle `app-store-connect fetch-signing-files` çağıran bir adım yazılmıştı.
Derleme makineye indi ama o adım 1 saniyede öldü:

```
Initialize new keychain to store code signing certificates at /Users/builder/…keychain-db
Create keychain …
Set keychain … timeout to "no timeout"
Set keychain … to system default keychain
Unlock keychain …
Cannot save Signing Certificates without certificate private key

Build failed :|
Step 4 script `İmza dosyalarını çek` exited with status code 1
```

`fetch-signing-files` sertifikayı indirebiliyor ama `.p12` üretip keychain'e yazabilmek
için **özel anahtara** ihtiyaç duyuyor. Onu ya `--certificate-key` ile verirsin, ya
`CERTIFICATE_PRIVATE_KEY` ortam değişkeninden okur, ya `--create` ile kendisi üretir.
Üçü de yoktu. O anahtar Codemagic'in tarafında duruyor ve onu derlemeye taşıyan tek şey
`ios_signing` bloğu.

`bundle_identifier`sız denendi, Codemagic yapılandırmayı doğrulamadan geçirmedi:

```
1 validation error in codemagic.yaml:
apple -> environment -> ios_signing ->
  For fetching signing identities, distribution type and bundle identifier are both required.
```

Saat için ayrıca yazmak gerekmiyor: eşleştirme `--strict-match-identifier` verilmedikçe
öntakı bazlı, `com.asistan.nova` hem telefonun hem saatin profilini kapsıyor.
Build Metadata bunu doğruluyor.

İlgili commit'ler: `9b24c4d`, `e75cd9a`.

---

## App Store doğrulama hataları — üçü de aynı kök sebep

İmzalama çözülünce arşiv ve IPA üretildi, ama `altool` yüklemeyi üst üste reddetti.
Üçünün de sebebi aynı: **hedefler kendi `Info.plist`'ini verdiği için Xcode'un
`INFOPLIST_KEY_*` varsayılanları hiçbir yere yazılmıyor.** `project.yml` içindeki
`INFOPLIST_KEY_UILaunchScreen_Generation: YES` de bu yüzden etkisizdi — o ayarlar
yalnızca Xcode'un *ürettiği* plist'e işliyor.

### `c5cc95b`

```
90713  Missing Info.plist value. A value for the Info.plist key 'CFBundleIconName' is
       missing in the bundle 'com.asistan.nova'. Apps built with iOS 11 or later SDK
       must supply app icons in an asset catalog and must also provide a value for this
       Info.plist key.

90475  Invalid bundle. Apps that support Multitasking on iPad must provide the app's
       launch screen using an Xcode storyboard, or using UILaunchScreen if the app's
       MinimumOSVersion is 14 or higher. Verify that the UILaunchStoryboardName key is
       included in your com.asistan.nova bundle if you're using a storyboard.
```

- **İkon:** projede hiç asset catalog yoktu. İki hedefe de
  `Assets.xcassets/AppIcon.appiconset` eklendi — tek 1024×1024 PNG, Xcode 14 ve sonrası
  kalan boyutları kendisi türetiyor. **Alfa kanalı yok**, App Store saydamlığı reddediyor.
  Görsel uygulamanın kendi küresi: koyu lacivert zemin üstünde parlayan küre.
  Ayrıca `ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon` ve `CFBundleIconName: AppIcon`.
- **Açılış ekranı:** etkisiz `INFOPLIST_KEY_UILaunchScreen_Generation` kaldırıldı, yerine
  gerçek `UILaunchScreen: {}` kondu.

### `9ccd6d2`

```
90474  Invalid bundle. No orientations were specified in the com.asistan.nova bundle.
       To support iPad multitasking, specify the "UIInterfaceOrientationPortrait,
       UIInterfaceOrientationPortraitUpsideDown,UIInterfaceOrientationLandscapeLeft,
       UIInterfaceOrientationLandscapeRight" orientations for the
       UISupportedInterfaceOrientations Info.plist key.
```

- Telefon için bugünkü fiili davranış korundu: dik + iki yan.
- iPad çoklu görev dördünü birden şart koştuğu için `UISupportedInterfaceOrientations~ipad`
  ayrıca verildi.
- Ayrıca `ITSAppUsesNonExemptEncryption: false` eklendi. Kodda özel şifreleme yok —
  `Ayarlar.swift` yalnızca Keychain (`SecItem*`) kullanıyor, gerisi işletim sisteminin
  kendi TLS'i; ikisi de muaf. Bu anahtar olmadan her yükleme TestFlight'ta
  "Missing Compliance" durumunda bekliyor ve elle cevaplanması gerekiyordu.
  **Bu Apple'a yapılan bir beyandır** — yanlış bulunursa App Store Connect'ten değiştirilebilir.

---

## Apple Developer Program License Agreement

App Store Connect'te "sözleşme güncellendi, hesap sahibi kabul etmeli" uyarısı duruyor.
**Kabul edilmedi** — sözleşme onayı hesap sahibinin kararı. Yüklemeyi engellemediği
görüldü: derleme sözleşme kabul edilmeden TestFlight'a çıktı.

---

## TestFlight dağıtımı

- `Ic Test` adında iç test grubu kuruldu, **otomatik dağıtım açık** — bundan sonraki her
  Codemagic derlemesi bu gruba kendiliğinden düşecek.
- Tester: `yunusemrecelikell@hotmail.com` (Account Holder, Admin). Tester listesinde
  eklenebilecek tek kimlik buydu. **Dikkat: bu hotmail**, App Store Connect oturumundaki
  gmail değil; davet e-postası oraya gitti. Davet kabul edildi, uygulama telefonda kullanımda.

Saat uygulaması TestFlight'ta ayrı görünmez; iPhone'a kurulunca Watch'a kendiliğinden
geçiyor (`WKCompanionAppBundleIdentifier` bağlı).

### Yüklenen derlemeler

| Sürüm | Build | Durum |
|---|---|---|
| 1.0.0 | `1` | İlk yükleme. Build numarası TestFlight'a ulaşmıyordu — `ad1a813` düzeltti. |
| 1.0.0 | `1788888982` | `processingState VALID`, `internalBuildState IN_BETA_TESTING` |

İkinci derleme: <https://codemagic.io/app/6a9f5dccb1a7e43f6ca8680d/build/6aa0476363c784534c78ab55>
Hiçbir adım düşmedi, hiç App Store doğrulama hatası çıkmadı. `UPLOAD SUCCEEDED with no errors`.

Build numarası artık `$(CURRENT_PROJECT_VERSION)` üzerinden Unix zaman damgası alıyor;
`1.0.0 (1)` → `1.0.0 (1788888982)`. **TestFlight build numarasını düşüremiyor** — ileride
sabit bir sayıya dönülecekse damganın üstünden devam etmek gerekir.

---

## Bu işte değişen dosyalar

| Commit | Ne |
|---|---|
| `9b24c4d` | Elle `fetch-signing-files` script'i kaldırıldı, `ios_signing` geri geldi |
| `e75cd9a` | `ios_signing` için `bundle_identifier` zorunluymuş, geri kondu |
| `c5cc95b` | İki hedefe app icon (asset catalog) + gerçek `UILaunchScreen` |
| `9ccd6d2` | Yön anahtarları (`~ipad` dahil) + `ITSAppUsesNonExemptEncryption` |
