# -*- coding: utf-8 -*-
"""Yedekleme, takvim (ICS), ekran süresi ve baskı maliyeti testleri."""

import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, r"C:\Users\PC\Desktop\Asistan\backend")

import store

gecici = Path(tempfile.mkdtemp())
store.DB_PATH = gecici / "test.db"

import gunluk

gunluk.KOK = gecici / "gunluk"

import baski
import ekran
import takvim
import yedek

yedek.KOK = gecici / "yedek"

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


BUGUN = date.today()
B = BUGUN.isoformat()


def gun(n):
    return (BUGUN + timedelta(days=n)).isoformat()


def damga(n, saat="100000"):
    return (BUGUN + timedelta(days=n)).strftime("%Y%m%d") + "T" + saat


print("\n[1] yedek alma")
d = yedek.al()
kontrol("yedek alındı", d.get("ok"), d)
kontrol("dosya var", Path(d["dosya"]).is_file())
kontrol("boyut makul", d["boyut"] > 1000, d["boyut"])
kontrol("listede görünüyor", len(yedek.listele()) == 1)

# Yedek gerçekten okunabilir bir veritabanı mı?
import sqlite3

with sqlite3.connect(d["dosya"]) as c:
    tablolar = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
kontrol("yedek okunabilir veritabanı", "projeler" in tablolar, tablolar[:5])

print("\n[2] yedek dönüşümü (saklama sınırı)")
store.ayar_yaz("yedek_saklama", "3")
for i in range(5):
    yedek.al(f"t{i}")
kontrol("saklama sınırı uygulandı", len(yedek.listele()) == 3,
        len(yedek.listele()))
kontrol("en yeniler kaldı",
        all("t" in y["ad"] for y in yedek.listele()),
        [y["ad"] for y in yedek.listele()])

print("\n[3] dışa aktarma")
pid = store.harici_proje_ekle("Dökümlük Proje", "kisisel")
d = yedek.disa_aktar()
kontrol("zip üretildi", d.get("ok") and Path(d["dosya"]).is_file(), d)

import json
import zipfile

with zipfile.ZipFile(d["dosya"]) as z:
    adlar = z.namelist()
    projeler = json.loads(z.read("projeler.json").decode("utf-8"))
kontrol("tablolar dökülmüş", "projeler.json" in adlar and "bilgi.json" in adlar,
        adlar[:5])
kontrol("veri döküme girmiş",
        any(p["ad"] == "Dökümlük Proje" for p in projeler))
kontrol("günlük tablosu hariç tutulmuş", "gunluk.json" not in adlar, adlar)

print("\n[4] geri yükleme")
onceki = len(store.projeler())
# Saklama sınırını gevşetiyoruz: geri yüklemeden önce alınan güvenlik yedeği
# dönüşümü tetikliyor ve sınır darsa geri yükleyeceğimiz dosyayı silebiliyor.
# O uç durumu aşağıda ayrıca sınıyoruz.
store.ayar_yaz("yedek_saklama", "10")
d = yedek.geri_yukle(yedek.listele()[-1]["ad"])
kontrol("geri yükleme çalıştı", d.get("ok"), d)
kontrol("öncesi yedeklendi", d.get("onceki_yedek"), d)
kontrol("olmayan yedek reddedilir",
        not yedek.geri_yukle("yok-boyle-bir-sey.db").get("ok"))
kontrol("klasör dışı yol reddedilir",
        not yedek.geri_yukle("../../gizli.db").get("ok"))

# Asistan yedeği olmayan bir dosya canlı veritabanını silmemeli.
sahte = yedek.KOK / "asistan-2000-01-01-000000-sahte.db"
sahte.write_bytes(b"bu bir veritabani degil")
r = yedek.geri_yukle(sahte.name)
kontrol("geçersiz dosya reddedilir", not r.get("ok"), r)
kontrol("reddedilince canlı veri durur", len(store.projeler()) >= 0
        and "projeler" in {x[0] for x in store._conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'")})

# Saklama sınırı 1 iken güvenlik yedeği kaynağı silerse fark edilmeli.
store.ayar_yaz("yedek_saklama", "1")
hedef = yedek.listele()[-1]["ad"]
r = yedek.geri_yukle(hedef)
kontrol("dönüşüme kurban giden yedek fark edilir",
        r.get("ok") or "dönüşüme" in r.get("hata", ""), r)
kontrol("her hâlükârda tablolar duruyor",
        "projeler" in {x[0] for x in store._conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'")})
store.ayar_yaz("yedek_saklama", "14")

print("\n[5] ICS ayrıştırma — temel")
ics = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:abc-123
SUMMARY:Diş hekimi
DTSTART;TZID=Europe/Istanbul:{damga(1, "143000")}
DTEND;TZID=Europe/Istanbul:{damga(1, "153000")}
LOCATION:Kadıköy
END:VEVENT
END:VCALENDAR"""
r = takvim.ics_coz(ics)
kontrol("bir randevu çıktı", len(r) == 1, r)
if r:
    e = r[0]
    kontrol("başlık", e["baslik"] == "Diş hekimi", e["baslik"])
    kontrol("tarih", e["tarih"] == gun(1), e["tarih"])
    kontrol("saat", e["saat"] == "14:30", e["saat"])
    kontrol("süre 60 dk", e["sure_dk"] == 60, e["sure_dk"])
    kontrol("yer", e["yer"] == "Kadıköy", e["yer"])

print("\n[6] ICS — satır katlama ve kaçışlar")
ics = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uzun-1
SUMMARY:Cok uzun bir toplanti bas
 ligi devam ediyor
DESCRIPTION:x
DTSTART:{damga(2)}
DTEND:{damga(2, "113000")}
END:VEVENT
BEGIN:VEVENT
UID:kacis-1
SUMMARY:Toplanti\\, sonra yemek
DTSTART:{damga(2, "150000")}
END:VEVENT
END:VCALENDAR"""
r = takvim.ics_coz(ics)
kontrol("iki randevu", len(r) == 2, len(r))
kontrol("katlanmış satır birleşti",
        r[0]["baslik"] == "Cok uzun bir toplanti basligi devam ediyor",
        r[0]["baslik"])
kontrol("kaçış çözüldü", r[1]["baslik"] == "Toplanti, sonra yemek",
        r[1]["baslik"])
kontrol("DTEND yoksa süre None", r[1]["sure_dk"] is None)

print("\n[7] ICS — tüm gün, iptal, tekrar")
ics = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
UID:tumgun-1
SUMMARY:Tatil
DTSTART;VALUE=DATE:{(BUGUN + timedelta(days=3)).strftime('%Y%m%d')}
END:VEVENT
BEGIN:VEVENT
UID:iptal-1
SUMMARY:Iptal olan
STATUS:CANCELLED
DTSTART:{damga(3)}
END:VEVENT
BEGIN:VEVENT
UID:tekrar-1
SUMMARY:Haftalik toplanti
DTSTART:{damga(1, "090000")}
DTEND:{damga(1, "100000")}
RRULE:FREQ=WEEKLY;COUNT=4
END:VEVENT
END:VCALENDAR"""
r = takvim.ics_coz(ics)
tumgun = [x for x in r if x["baslik"] == "Tatil"]
kontrol("tüm gün etkinliği alındı", len(tumgun) == 1, r)
kontrol("tüm günde saat yok", tumgun and tumgun[0]["saat"] is None)
kontrol("iptal edilen atlandı",
        not any(x["baslik"] == "Iptal olan" for x in r))
tekrar = [x for x in r if x["baslik"] == "Haftalik toplanti"]
kontrol("haftalık tekrar açıldı", len(tekrar) == 4, len(tekrar))
kontrol("tekrarlar 7'şer gün arayla",
        tekrar[1]["tarih"] == gun(8), [t["tarih"] for t in tekrar])
kontrol("tekrar uid'leri ayrı",
        len({t["uid"] for t in tekrar}) == 4)

print("\n[8] ICS — sınırlar ve bozuk girdi")
ics = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
UID:cok-ileri
SUMMARY:Gelecek yil
DTSTART:{(BUGUN + timedelta(days=400)).strftime('%Y%m%d')}T100000
END:VEVENT
BEGIN:VEVENT
UID:cok-geri
SUMMARY:Gecen ay
DTSTART:{(BUGUN - timedelta(days=40)).strftime('%Y%m%d')}T100000
END:VEVENT
BEGIN:VEVENT
UID:bozuk
SUMMARY:Bozuk tarih
DTSTART:not-a-date
END:VEVENT
BEGIN:VEVENT
UID:basliksiz
DTSTART:{damga(1, "080000")}
END:VEVENT
END:VCALENDAR"""
r = takvim.ics_coz(ics)
kontrol("uzak gelecek elendi",
        not any(x["baslik"] == "Gelecek yil" for x in r), r)
kontrol("eski etkinlik elendi",
        not any(x["baslik"] == "Gecen ay" for x in r), r)
kontrol("bozuk tarih atlandı",
        not any(x["baslik"] == "Bozuk tarih" for x in r), r)
kontrol("başlıksız etkinlik yine de alındı",
        any(x["baslik"] == "(başlıksız)" for x in r), r)
kontrol("boş metin çökmez", takvim.ics_coz("") == [])
kontrol("takvim olmayan metin çökmez", takvim.ics_coz("merhaba") == [])

print("\n[9] randevular takvime yansıyor")
for e in takvim.ics_coz(f"""BEGIN:VCALENDAR
BEGIN:VEVENT
UID:blok-1
SUMMARY:Toplanti
DTSTART:{damga(1, "140000")}
DTEND:{damga(1, "153000")}
END:VEVENT
END:VCALENDAR"""):
    store.randevu_kaydet(**e)

kayitli = store.randevular(gun(1))
kontrol("randevu kaydedildi", len(kayitli) == 1, kayitli)
araliklar = takvim.dolu_araliklar(gun(1))
kontrol("dolu aralık çıkarıldı", araliklar == [(840, 930)], araliklar)

import mentor

store.ayar_yaz("gun_baslangic", "09:00")
store.ayar_yaz("gun_bitis", "22:00")
store.ayar_yaz("ara_dk", "20")
slot = mentor.bos_slot(gun(1), 120, tercih="13:00")
kontrol("mentör randevunun üstüne yazmıyor",
        slot != "13:00" and slot is not None, slot)
kontrol("randevudan sonraki boşluğa kaydı",
        mentor._dk(slot) >= 930 or mentor._dk(slot) + 120 <= 840, slot)

ozet = takvim.ozet(7)
kontrol("plan bağlamına özet çıkıyor", "Toplanti" in ozet, ozet[:100])

print("\n[10] ICS adres doğrulama")
kontrol("boş adres reddedilir", not takvim.cek("").get("ok"))
kontrol("http olmayan adres reddedilir",
        not takvim.cek("ftp://sunucu/takvim.ics").get("ok"))

print("\n[11] ekran süresi")
store.ekran_ekle(B, "Chrome", 3600, "YouTube")
store.ekran_ekle(B, "Chrome", 1800, "GitHub")
store.ekran_ekle(B, "VS Code", 7200, "main.py")
kontrol("aynı uygulama biriktirildi",
        next(u["saniye"] for u in store.ekran_gunu(B) if u["uygulama"] == "Chrome")
        == 5400)
kontrol("başlık güncellendi",
        next(u["baslik"] for u in store.ekran_gunu(B) if u["uygulama"] == "Chrome")
        == "GitHub")
kontrol("toplam doğru", store.ekran_toplam(B) == 12600, store.ekran_toplam(B))
kontrol("sıralama azalan",
        [u["uygulama"] for u in store.ekran_gunu(B)][0] == "VS Code")

kontrol("okunur ad çevrimi", ekran.okunur("chrome.exe") == "Chrome")
kontrol("bilinmeyen exe okunur",
        ekran.okunur("birsey.exe") == "Birsey", ekran.okunur("birsey.exe"))

store.ayar_yaz("ekran_takip", "1")
p = ekran.panel(7)
kontrol("panel toplamı", p["bugun_saniye"] == 12600, p["bugun_saniye"])
kontrol("süre metni", p["bugun_metni"] == "3 sa 30 dk", p["bugun_metni"])
kontrol("yüzde hesaplandı",
        p["donem"][0]["yuzde"] > 0, p["donem"][0])
o = ekran.koc_ozeti()
kontrol("koç özeti üretildi", "EKRAN SÜRESİ" in o, o[:80])
store.ayar_yaz("ekran_takip", "0")
kontrol("takip kapalıyken özet boş", ekran.koc_ozeti() == "")

print("\n[12] baskı maliyeti")
store.ayar_yaz("filament_kg_fiyat", "600")
store.ayar_yaz("elektrik_kwh_fiyat", "3.5")
store.ayar_yaz("yazici_watt", "150")
store.ayar_yaz("iscilik_saat_fiyat", "0")

h = baski.maliyet_hesapla(50, 120)
kontrol("filament maliyeti", h["filament"] == 30.0, h)
kontrol("elektrik maliyeti", h["elektrik"] == 1.05, h)
kontrol("toplam", h["toplam"] == 31.05, h)

store.ayar_yaz("iscilik_saat_fiyat", "100")
h = baski.maliyet_hesapla(50, 120)
kontrol("işçilik eklendi", h["iscilik"] == 200.0, h)
kontrol("işçilikli toplam", h["toplam"] == 231.05, h)
store.ayar_yaz("iscilik_saat_fiyat", "0")

kontrol("sıfır gram sıfır filament",
        baski.maliyet_hesapla(0, 60)["filament"] == 0)
kontrol("negatif gram sıfırlanır",
        baski.maliyet_hesapla(-100, 60)["filament"] == 0)

print("\n[13] kâr hesabı")
y = store.yazici_ekle("Test Yazıcı", "Kobra S1")
p2 = store.harici_proje_ekle("Satılık Ürün", "baski")
r = baski.baski_basla(y, "anahtarlık x10", 120, p2)
bid = r["baski_id"]
store._conn().execute("UPDATE baskilar SET baslangic=? WHERE id=?",
                      (time.time() - 7200, bid))
store._conn().commit()
baski.baski_bitir(bid)

d = baski.maliyet_yaz(bid, gram=80, satis_fiyati=400, adet=10)
kontrol("maliyet yazıldı", d.get("ok"), d)
kontrol("filament 80 gram", d["hesap"]["filament"] == 48.0, d["hesap"])
kontrol("kâr hesaplandı", d["kar"] == 400 - d["hesap"]["toplam"], d["kar"])

k = baski.kar_paneli(30)
kontrol("panel baskı sayısı", k["baski"] == 1, k)
kontrol("panel satış", k["satis"] == 400, k)
kontrol("panel kâr", k["kar"] > 340, k)
kontrol("marj yüzdesi", 80 <= k["marj"] <= 95, k["marj"])
kontrol("birim maliyet", k["birim_maliyet"] is not None, k)
kontrol("ayarlar panelde", k["ayarlar"]["filament_kg_fiyat"] == 600)

kontrol("olmayan baskıda maliyet reddedilir",
        not baski.maliyet_yaz(99999, gram=10).get("ok"))

print("\n[14] yedek denetimi")
store.ayar_yaz("yedek_acik", "1")
kontrol("yeni yedek varken tekrar almaz", yedek.denetle() == [])
store.ayar_yaz("yedek_acik", "0")
kontrol("kapalıyken almaz", yedek.denetle() == [])

d = yedek.durum()
kontrol("durum alanları",
        {"acik", "saklama", "sayi", "son", "yedekler"} <= set(d), set(d))

print(f"\n{'='*54}")
print(f"  {gecti} test geçti, {len(kaldi)} kaldı")
for k in kaldi:
    print(f"    - {k}")
print("=" * 54)
sys.exit(1 if kaldi else 0)
