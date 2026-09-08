# -*- coding: utf-8 -*-
"""Doğal konuşma katmanı testleri — içerik koruma, işaretler, parçalama."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"C:\Users\PC\Desktop\Asistan\backend")

import store

gecici = Path(tempfile.mkdtemp())
store.DB_PATH = gecici / "test.db"

import gunluk

gunluk.KOK = gecici / "gunluk"

import dogal
import speech

store.kur()

gecti, kaldi = 0, []


def kontrol(ad, kosul, ayrinti=""):
    global gecti
    if kosul:
        gecti += 1
        print(f"  OK   {ad}")
    else:
        kaldi.append(f"{ad} — {ayrinti}")
        print(f"  HATA {ad} — {ayrinti}")


print("\n[1] içerik koruma — kabul edilmesi gerekenler")
kabul = [
    ("bağlaç eklenmiş",
     "Bugün üç işten birini bitirdin.",
     "Bak, bugün üç işten sadece birini bitirdin."),
    ("işaret eklenmiş",
     "Yarın sabah dokuzda başla. Anahtarlık kaldı.",
     "[vurgu] Yarın sabah dokuzda başla. [hizli] Anahtarlık kaldı."),
    ("cümle bölünmüş",
     "Bugün iki iş var ve ikisi de kritik.",
     "Bugün iki iş var. İkisi de kritik."),
    ("saat korunmuş",
     "Saat 09:00 da baslayacaksin.",
     "Hadi, saat 09:00 da baslayacaksin."),
]
for ad, a, b in kabul:
    kontrol(ad, dogal.icerik_korundu(a, b), (a, b))

print("\n[2] içerik koruma — reddedilmesi gerekenler")
ret = [
    ("yazıyla sayı düşmüş",
     "Bugün üç işten birini bitirdin.",
     "Bugün işten birini bitirdin."),
    ("rakam değişmiş",
     "Saat 9 da basla, 3 isin var.",
     "Saat 10 da basla, 3 isin var."),
    ("rakam düşmüş",
     "Saat 9 da basla, 3 isin var.",
     "Saat 9 da basla, isin var."),
    ("soru uydurulmuş",
     "Yarin dokuzda baslayacaksin kesinlikle.",
     "Yarin dokuzda baslayacaksin. Ne oldu peki?"),
    ("talimat sızmış",
     "Bugun bir is var ve onemli bir istir.",
     "Istediğin metni yeniden yazdım: bugun bir is var."),
    ("aşırı kısalmış",
     "Bugun uc isten birini bitirdin ve anahtarlik kaldi.",
     "Bitti."),
    ("aşırı uzamış",
     "Bugun bir is var.",
     "Bugun bir is var ve bu is cok onemli, ayrica yarin da baska isler "
     "olacak, hepsini planlamak lazim, unutma sakin."),
]
for ad, a, b in ret:
    kontrol(ad, not dogal.icerik_korundu(a, b), (a, b))

print("\n[3] sızıntı kalıbı sıradan cümleyi yakalamamalı")
kontrol("tanıtım metni yazma görevi reddedilmiyor",
        dogal.icerik_korundu(
            "Yarin tanitim metnini yazacaksin ve gorseli hazirlayacaksin.",
            "Bak, yarin tanitim metnini yazacaksin. Gorseli de hazirlayacaksin."))

print("\n[4] bozuk işaret temizliği")
kontrol("bilinmeyen işaret atılır",
        "[bi]" not in dogal.temizle_isaretler("Bugün [bi] üç iş var."))
kontrol("bozuk vurgu atılır",
        "[Bvurgu]" not in dogal.temizle_isaretler("[Bvurgu] Bugün üç iş var."))
kontrol("geçerli işaret korunur",
        "[vurgu]" in dogal.temizle_isaretler("[vurgu] Bugün üç iş var."))
kontrol("uzun parantez metni bozmaz",
        dogal.temizle_isaretler("Bir [çok uzun bir metin parçası buraya] var")
        == "Bir [çok uzun bir metin parçası buraya] var")

print("\n[5] parçalama")
p = dogal.parcala("Bugün üç iş var. [dusun] İlki dokuzda. "
                  "[yavas] Bu son uyarım. [gul] Hadi bakalım.")
kontrol("parça üretildi", len(p) >= 5, len(p))
metinler = [x["metin"] for x in p]
kontrol("düşünme sesi eklendi", any(m.startswith("ııı") for m in metinler),
        metinler)
kontrol("gülüş eklendi", any(m.startswith(("heh", "haha")) for m in metinler),
        metinler)
# Klon motorunda hız kısılıyor: XTTS'te hız bir SENTEZ parametresi, 1.0'dan
# uzaklaştıkça tını da kayıyor ve kullanıcı bunu "her cümlede farklı ses"
# olarak duyuyor. İşaret hâlâ işini görüyor — parça yavaşlıyor — ama
# sesin kimliğini bozacak kadar değil.
yavas_esik = -4 if speech.motor() == "klon" else -10
kontrol("yavaş kipi uygulandı",
        any(x["hiz"] <= yavas_esik and "son uyarım" in x["metin"] for x in p),
        [(x["hiz"], x["metin"]) for x in p])
kontrol("hiçbir parçada işaret kalmadı",
        not any("[" in m for m in metinler), metinler)
kontrol("her parçada duraklama var", all(x["sonra_ms"] > 0 for x in p))

print("\n[6] vurgu işareti")
p = dogal.parcala("Bugün üç iş var. [vurgu] Hiçbirini kaçırma.")
vurgulu = [x for x in p if "Hiçbirini" in x["metin"]]
kontrol("vurgulu parça yavaşladı",
        vurgulu and vurgulu[0]["hiz"] <= yavas_esik,
        vurgulu)

print("\n[7] üsluba göre tempo salınımı")
store.ayar_yaz("konusma_uslubu", "sakin")
sakin = dogal.parcala("Bir. İki. Üç. Dört. Beş. Altı.")
store.ayar_yaz("konusma_uslubu", "canli")
canli = dogal.parcala("Bir. İki. Üç. Dört. Beş. Altı.")
sakin_genislik = max(x["hiz"] for x in sakin) - min(x["hiz"] for x in sakin)
canli_genislik = max(x["hiz"] for x in canli) - min(x["hiz"] for x in canli)
kontrol("canlı üslupta salınım daha geniş",
        canli_genislik > sakin_genislik, (sakin_genislik, canli_genislik))

print("\n[8] ekran metni")
kontrol("işaretler ekranda görünmez",
        dogal.isaretleri_at("[vurgu] Bugün [bi] üç iş var.")
        == "Bugün üç iş var.",
        dogal.isaretleri_at("[vurgu] Bugün [bi] üç iş var."))

print("\n[9] sınır durumlar")
kontrol("boş metin", dogal.parcala("") == [])
kontrol("yalnız işaret", dogal.parcala("[dur]") == [])
kontrol("kısa metin modele gitmez",
        dogal.dogallastir("Tamam.") == "Tamam.")
store.ayar_yaz("dogal_konusma", "0")
kontrol("kapalıyken dokunmaz",
        dogal.dogallastir("Bu uzun bir metin, en az altmış karakter olsun "
                          "diye yazıldı.")
        == "Bu uzun bir metin, en az altmış karakter olsun diye yazıldı.")
store.ayar_yaz("dogal_konusma", "1")

print("\n[10] turun ilk parcasi ince bolunuyor")

# Seslendirme suresi metin uzunluguyla orantili (~85 ms/karakter). Ilk sesin
# duyulma ani dogrudan ilk parcanin uzunluguna bagli, o yuzden yalnizca onu
# boluyoruz; sonrakiler zaten onceki ses calarken uretiliyor.


def _bol(metin):
    return [p["metin"] for p in dogal.ilk_parcayi_bol(dogal.parcala(metin))]


p = _bol("Bugun bes isin var ve biri de telafi gorevi.")
kontrol("baglactan bolundu", len(p) == 2)
kontrol("baglac ikinci parcada", p[1].startswith("ve"))
kontrol("ilk parca kisaldi", len(p[0]) <= dogal.ILK_PARCA_HEDEF)

p = _bol("Tamam, bakiyorum ama bu biraz surebilir.")
kontrol("virgulden sonra bolundu", p[0].rstrip().endswith("bakiyorum"))

p = _bol("Vardigin saatte su an sadece bir sey yapabilirsin.")
kontrol("noktalama yoksa kelime sinirindan", len(p) == 2)
kontrol("kelime ortasindan bolmuyor", all(x.strip() == x for x in p))
kontrol("bolunen metin korunuyor",
        " ".join(p) == "Vardigin saatte su an sadece bir sey yapabilirsin.")

kontrol("kisa cumleye dokunmuyor",
        _bol("Bugun hicbir sey yok.") == ["Bugun hicbir sey yok."])
kontrol("tek kelimeye dokunmuyor", _bol("Tamam.") == ["Tamam."])
kontrol("bos liste sorun degil", dogal.ilk_parcayi_bol([]) == [])

# Kalinti cok kisa kalacaksa bolmuyoruz.
uzun = dogal.ilk_parcayi_bol([{"metin": "A" * 40 + ", b", "hiz": 0,
                               "perde": 0, "sonra_ms": 0}])
kontrol("cok kisa kalinti icin bolmuyor", len(uzun) == 1)


print(f"\n{'='*54}")
print(f"  {gecti} test geçti, {len(kaldi)} kaldı")
for k in kaldi:
    print(f"    - {k}")
print("=" * 54)
sys.exit(1 if kaldi else 0)
