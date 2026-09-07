# -*- coding: utf-8 -*-
"""Klasör takibi, günlük ve istatistik testleri — geçici disk ve veritabanı."""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\PC\Desktop\Asistan\backend")

import store

gecici = Path(tempfile.mkdtemp())
store.DB_PATH = gecici / "test.db"

import gunluk
import klasor

gunluk.KOK = gecici / "gunluk"

# Klasör kökünü geçiciye al — kullanıcının gerçek masaüstüne dokunma
klasor.KOK = gecici / "3d Projeler"
klasor.BEKLEYEN = klasor.KOK / "Baskıya Verilecekler"
klasor.BITEN = klasor.KOK / "Baskısı Bitenler"

import baski
import istatistik
import mentor

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


def dosya_at(ad, icerik="test"):
    p = klasor.KOK / ad
    p.write_text(icerik, encoding="utf-8")
    return p


# Testte bekleme yapmayalım: yazma bitti kontrolünü kısalt
klasor._yazma_bitti_mi = lambda yol, bekleme=0: yol.exists()

print("\n[1] klasör kurulumu")
r = klasor.kur()
kontrol("kök oluştu", klasor.KOK.is_dir(), klasor.KOK)
kontrol("bekleyen klasörü", klasor.BEKLEYEN.is_dir())
kontrol("biten klasörü", klasor.BITEN.is_dir())
kontrol("okubeni yazıldı", (klasor.KOK / "OKUBENI.txt").exists())
kontrol("ikinci kurulum bozmaz", klasor.kur()["olusan"] == [])

print("\n[2] köke atılan dosya taşınır")
dosya_at("anahtarlik v3.stl", "solid x")
dosya_at("kapak.3mf")
yapilan = klasor.tara()
kontrol("iki dosya alındı", len(yapilan) == 2, yapilan)
kontrol("kökte dosya kalmadı",
        [p.name for p in klasor.KOK.iterdir() if p.is_file()] == ["OKUBENI.txt"],
        [p.name for p in klasor.KOK.iterdir()])
kontrol("bekleyen klasörüne indi",
        len(list(klasor.BEKLEYEN.iterdir())) == 2)
kontrol("kayıtlar oluştu", len(store.dosyalar(durum="bekliyor")) == 2)
kontrol("OKUBENI taşınmadı", (klasor.KOK / "OKUBENI.txt").exists())

print("\n[3] aynı adlı dosya çakışmaz")
dosya_at("anahtarlik v3.stl", "farklı içerik")
klasor.tara()
adlar = sorted(p.name for p in klasor.BEKLEYEN.iterdir())
kontrol("üç dosya var", len(adlar) == 3, adlar)
kontrol("ikinci kopya yeniden adlandırıldı",
        any("(2)" in a for a in adlar), adlar)

print("\n[4] bitti / geri al")
d = next(x for x in store.dosyalar(durum="bekliyor") if x["ad"] == "kapak.3mf")
r = klasor.bitti(d["id"])
kontrol("bitti taşıdı", r.get("ok"), r)
kontrol("biten klasöründe", (klasor.BITEN / "kapak.3mf").exists())
kontrol("bekleyende yok", not (klasor.BEKLEYEN / "kapak.3mf").exists())
kontrol("kayıt bitti", store.dosya(d["id"])["durum"] == "bitti")
kontrol("ikinci kez bitti reddedilir", not klasor.bitti(d["id"]).get("ok"))

r = klasor.geri_al(d["id"])
kontrol("geri alındı", r.get("ok") and
        (klasor.BEKLEYEN / "kapak.3mf").exists())
kontrol("kayıt bekliyor", store.dosya(d["id"])["durum"] == "bekliyor")

print("\n[5] ada göre bulma")
kontrol("tam ad bulur", len(klasor.ada_gore_bul("kapak bitti")) >= 1)
bulunan = klasor.ada_gore_bul("anahtarlik bitti")
kontrol("kısmi ad bulur", len(bulunan) >= 1, [b["ad"] for b in bulunan])
kontrol("Türkçe karakter farkı sorun değil",
        len(klasor.ada_gore_bul("ANAHTARLIK bitti")) >= 1)
kontrol("olmayan ad boş döner", klasor.ada_gore_bul("ejderha heykeli") == [])

print("\n[6] elle taşımayı algılar")
kaynak = klasor.BEKLEYEN / "kapak.3mf"
kaynak.rename(klasor.BITEN / "kapak.3mf")
klasor.tara()
kontrol("elle taşıma yakalandı",
        store.dosya(d["id"])["durum"] == "bitti",
        store.dosya(d["id"])["durum"])

print("\n[7] silinen dosya kayıttan düşer")
(klasor.BITEN / "kapak.3mf").unlink()
klasor.tara()
kontrol("kayıt silindi", store.dosya(d["id"]) is None)

print("\n[8] elle eklenen dosya kayda girer")
(klasor.BEKLEYEN / "elle eklenen.stl").write_text("x", encoding="utf-8")
klasor.tara()
kontrol("kayda alındı",
        any(x["ad"] == "elle eklenen.stl"
            for x in store.dosyalar(durum="bekliyor")))

print("\n[9] günlük")
gunluk.bilgi("test", "deneme", "bilgi kaydı", sayi=1)
gunluk.uyari("test", "dikkat", "uyarı kaydı")
gunluk.hata("test", "patladi", "hata kaydı",
            istisna=ValueError("örnek hata"))
kayitlar = gunluk.oku(kaynak="test")
kontrol("üç kayıt", len(kayitlar) == 3, len(kayitlar))
kontrol("seviyeler doğru",
        {k["seviye"] for k in kayitlar} == {"bilgi", "uyari", "hata"})
h = next(k for k in kayitlar if k["seviye"] == "hata")
kontrol("istisna kaydedildi", "ValueError" in str(h["veri"]), h["veri"])
kontrol("yığın izi var", "iz" in h["veri"])

kontrol("seviyeye göre süzme",
        len(gunluk.oku(seviye="hata", kaynak="test")) == 1)
kontrol("metinde arama",
        len(gunluk.oku(ara="uyarı kaydı")) == 1)

gunluk.yaz("bilgi", "test", "sirli", "parola sizmasin",
           {"parola": "cok gizli", "token": "abc", "normal": "gorunur"})
son = gunluk.oku(olay="sirli")[0]
kontrol("parola maskelendi", son["veri"]["parola"] == "***", son["veri"])
kontrol("token maskelendi", son["veri"]["token"] == "***")
kontrol("normal alan duruyor", son["veri"]["normal"] == "gorunur")

print("\n[10] günlük dosyaya da yazıldı")
dosyalar = list(gunluk.KOK.glob("*.jsonl")) if gunluk.KOK.is_dir() else []
kontrol("jsonl dosyası oluştu", len(dosyalar) == 1, dosyalar)
if dosyalar:
    satirlar = dosyalar[0].read_text(encoding="utf-8").strip().splitlines()
    kontrol("dosyada da kayıt var", len(satirlar) >= 4, len(satirlar))
    import json as _j
    kontrol("satırlar geçerli JSON",
            all(_j.loads(s) for s in satirlar))
    kontrol("dosyada da maskeli",
            all('"cok gizli"' not in s for s in satirlar))

print("\n[11] süre ölçümü")
with gunluk.olcum("test", "olculdu", "kısa iş") as o:
    o.ekle(adim=3)
k = gunluk.oku(olay="olculdu")[0]
kontrol("süre kaydedildi", k["sure_ms"] is not None, k["sure_ms"])
kontrol("ek veri kaydedildi", k["veri"].get("adim") == 3, k["veri"])

try:
    with gunluk.olcum("test", "patlayan", "hata atan iş"):
        raise RuntimeError("bilerek")
except RuntimeError:
    pass
k = gunluk.oku(olay="patlayan")[0]
kontrol("hata seviyesi", k["seviye"] == "hata")
kontrol("istisna yutulmadı", "RuntimeError" in str(k["veri"]))

print("\n[12] günlük özeti ve temizlik")
o = gunluk.ozet(24)
kontrol("özet seviyeleri sayıyor", o["toplam"] > 0, o)
kontrol("özet kaynakları sayıyor", "test" in o["kaynaklar"], o["kaynaklar"])
store._conn().execute("UPDATE gunluk SET zaman=? WHERE kaynak='test'",
                      (time.time() - 100 * 86400,))
store._conn().commit()
n = gunluk.temizle(60)["silinen"]
kontrol("eski kayıtlar silindi", n > 0, n)
kontrol("jsonl dosyası duruyor", dosyalar and dosyalar[0].exists())

print("\n[13] istatistik")
pid = store.harici_proje_ekle("Test Baskı", "baski", oncelik=1)
y1 = store.yazici_ekle("Y1", "Kobra S1")
store.yazici_alan_yaz(y1, filament="PLA", filament_renk="siyah")
r = baski.baski_basla(y1, "parça", 60, pid)
store._conn().execute("UPDATE baskilar SET baslangic=? WHERE id=?",
                      (time.time() - 7200, r["baski_id"]))
store._conn().commit()
baski.baski_bitir(r["baski_id"])

a = istatistik.atolye(30)
kontrol("baskı sayıldı", a["baski_sayisi"] == 1, a["baski_sayisi"])
kontrol("başarı yüzdesi", a["basari_yuzde"] == 100, a["basari_yuzde"])
kontrol("süre hesaplandı", a["toplam_dk"] >= 118, a["toplam_dk"])
kontrol("filament görünüyor", a["filamentler"].get("PLA") == 1, a["filamentler"])
yz = next(x for x in a["yazicilar"] if x["id"] == y1)
kontrol("ömür sayacı işledi", yz["omur_dk"] >= 118, yz["omur_dk"])
kontrol("ömür baskı sayısı", yz["omur_baski"] == 1)
kontrol("yazıcı boşaldı", store.yazici(y1)["durum"] == "bos")

m = istatistik.mentorluk(7)
kontrol("mentörlük serisi 7 gün", len(m["seri"]) == 7, len(m["seri"]))
kontrol("mentörlük alanları",
        {"uyum", "temiz_gun_serisi", "en_cok_kacan"} <= set(m))

h = istatistik.hepsi(30)
kontrol("toplu rapor bütün bölümleri içeriyor",
        {"atolye", "mentorluk", "yasam", "maliyet", "dosyalar", "gunluk"}
        <= set(h))

print("\n[14] veri yokken çökmez")
store._conn().execute("DELETE FROM baskilar")
store._conn().commit()
a = istatistik.atolye(30)
kontrol("boş atölyede başarı None", a["basari_yuzde"] is None, a["basari_yuzde"])
kontrol("boş atölyede sayı sıfır", a["baski_sayisi"] == 0)

print(f"\n{'='*54}")
print(f"  {gecti} test geçti, {len(kaldi)} kaldı")
for k in kaldi:
    print(f"    - {k}")
print("=" * 54)
sys.exit(1 if kaldi else 0)
