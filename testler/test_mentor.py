# -*- coding: utf-8 -*-
"""Mentör ve yaşam katmanının mantık testleri — geçici veritabanında."""

import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, r"C:\Users\PC\Desktop\Asistan\backend")

import store

store.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"

import mentor
import yasam

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


BUGUN = mentor.bugun()
YARIN = mentor._gun_ekle(BUGUN, 1)

print("\n[1] zaman yardımcıları")
kontrol("dakika çevrimi", mentor._dk("09:30") == 570, mentor._dk("09:30"))
kontrol("saat çevrimi", mentor._saat(570) == "09:30", mentor._saat(570))
kontrol("bozuk saat 0 döner", mentor._dk("abc") == 0)
kontrol("saat taşması sınırlanır", mentor._saat(99999) == "23:59")
hb, hs = mentor.hafta_sinirlari(BUGUN)
kontrol("hafta pazartesi başlar",
        date.fromisoformat(hb).weekday() == 0, hb)
kontrol("hafta 7 gün", (date.fromisoformat(hs) - date.fromisoformat(hb)).days == 6)
ab, asn = mentor.ay_sinirlari("2026-02-15")
kontrol("şubat sınırları", (ab, asn) == ("2026-02-01", "2026-02-28"), (ab, asn))
ab2, as2 = mentor.ay_sinirlari("2028-02-10")
kontrol("artık yıl şubatı", as2 == "2028-02-29", as2)

print("\n[2] boş slot bulma")
store.ayar_yaz("gun_baslangic", "09:00")
store.ayar_yaz("gun_bitis", "22:00")
store.ayar_yaz("ara_dk", "20")
store.ayar_yaz("gunluk_azami_blok", "5")

g1 = store.gorev_ekle("Sabah bloğu", YARIN, "09:00", 90)
s = mentor.bos_slot(YARIN, 60, tercih="09:00")
kontrol("dolu saatin üstüne yazmaz", s == "10:50", s)

g2 = store.gorev_ekle("İkinci blok", YARIN, "10:50", 60)
s = mentor.bos_slot(YARIN, 60, tercih="09:00")
kontrol("ikinci boşluğa kayar", s == "12:10", s)

s = mentor.bos_slot(YARIN, 60, tercih="15:00")
kontrol("boş saatte tercihi korur", s == "15:00", s)

s = mentor.bos_slot(YARIN, 700)
kontrol("gün penceresine sığmayan iş None döner", s is None, s)

s = mentor.bos_slot(BUGUN, 30, tercih="00:01")
simdi = mentor._dk(mentor.su_an())
kontrol("bugün geçmiş saate koymaz",
        s is None or mentor._dk(s) >= simdi, s)

print("\n[3] görev yaşam döngüsü")
k = mentor.gunun_karnesi(YARIN)
kontrol("karne toplamı", k["toplam"] == 2, k)
kontrol("karne kalanı", k["kalan"] == 2, k)

mentor.gorev_tamamla(g1)
k = mentor.gunun_karnesi(YARIN)
kontrol("tamamlanan sayılır", k["tamam"] == 1 and k["kalan"] == 1, k)
kontrol("uyum yüzdesi", k["uyum"] == 50, k)

print("\n[4] erteleme kuralları")
store.ayar_yaz("mentor_sertlik", "yuksek")
r = mentor.gorev_ertele(g2, "")
kontrol("sertlik yüksekken gerekçesiz erteleme reddedilir",
        not r.get("ok") and "gerekçe" in r.get("hata", ""), r)

r = mentor.gorev_ertele(g2, "Baskı makinesi doluydu")
kontrol("gerekçeli erteleme kabul edilir", r.get("ok"), r)
kontrol("erteleme sayacı arttı", store.gorev(g2)["erteleme"] == 1,
        store.gorev(g2)["erteleme"])
kontrol("gerekçe kaydedildi",
        store.gorev(g2)["gerekce"] == "Baskı makinesi doluydu")

print("\n[5] kaçırma ve telafi")
# Dün için, kesin kaçmış bir görev
DUN = mentor._gun_ekle(BUGUN, -1)
g3 = store.gorev_ekle("Kaçacak zorunlu iş", DUN, "10:00", 60, zorunlu=True)
g4 = store.gorev_ekle("Kaçacak esnek iş", DUN, "11:30", 60, zorunlu=False)

oncesi = len(store.gorevler(tarih=BUGUN, bitis=mentor._gun_ekle(BUGUN, 5)))
yapilan = mentor.denetle()
kontrol("kaçırılan görev damgalandı",
        store.gorev(g3)["durum"] == "kacirildi", store.gorev(g3)["durum"])
kontrol("esnek görev de kaçırıldı sayılır",
        store.gorev(g4)["durum"] == "kacirildi")

telafiler = [g for g in store.gorevler(tarih=BUGUN,
                                       bitis=mentor._gun_ekle(BUGUN, 5))
             if g["telafi_eden"]]
kontrol("zorunlu iş için telafi yazıldı", len(telafiler) == 1, telafiler)
if telafiler:
    t = telafiler[0]
    kontrol("telafi başlığı işaretli", t["baslik"].startswith("[TELAFİ]"),
            t["baslik"])
    kontrol("telafi önceliği kritik", t["oncelik"] == 1, t["oncelik"])
    kontrol("telafi doğru göreve bağlı", t["telafi_eden"] == g3)
    kontrol("telafi geleceğe yazıldı", t["tarih"] >= BUGUN, t["tarih"])

kontrol("esnek iş için telafi yazılmadı",
        not any(t["telafi_eden"] == g4 for t in telafiler))

bildirimler = store.bildirimler(limit=50)
kontrol("kaçırma bildirimi düştü",
        any(b["tur"] in ("telafi", "uyari") for b in bildirimler))

print("\n[6] denetim tekrarı bozmuyor")
sayi_once = len(store.gorevler(tarih=BUGUN, bitis=mentor._gun_ekle(BUGUN, 5)))
mentor.denetle()
sayi_sonra = len(store.gorevler(tarih=BUGUN, bitis=mentor._gun_ekle(BUGUN, 5)))
kontrol("ikinci turda yeni telafi üretmez", sayi_once == sayi_sonra,
        (sayi_once, sayi_sonra))

print("\n[7] istatistik")
ist = store.gorev_istatistik(DUN, mentor._gun_ekle(BUGUN, 7))
kontrol("istatistik toplamı tutarlı", ist["toplam"] > 0, ist)
kontrol("kaçırılan sayısı", ist["kacirildi"] == 2, ist)

print("\n[8] yaşam: desen çözümleme")
d = yasam._desenle_coz("dün gece 6.5 saat uyudum")
kontrol("uyku yakalandı", d and d[0]["tur"] == "uyku" and d[0]["deger"] == 6.5, d)
kontrol("dün tarihi çözüldü", d and d[0]["tarih"] == DUN, d)

d = yasam._desenle_coz("kahveye 45 lira verdim")
kontrol("harcama yakalandı",
        any(x["tur"] == "harcama" and x["deger"] == 45 for x in d), d)

d = yasam._desenle_coz("45 dakika koştum")
kontrol("spor yakalandı",
        any(x["tur"] == "spor" and x["deger"] == 45 for x in d), d)

d = yasam._desenle_coz("3 litre su içtim")
kontrol("su yakalandı",
        any(x["tur"] == "su" and x["deger"] == 3 for x in d), d)

d = yasam._desenle_coz("kahvaltıda menemen yedim")
kontrol("öğün yakalandı", any(x["tur"] == "ogun" for x in d), d)

d = yasam._desenle_coz("7 saat uyudum ve markete 250 tl harcadım")
turler = {x["tur"] for x in d}
kontrol("tek cümlede iki kayıt", turler == {"uyku", "harcama"}, turler)

d = yasam._desenle_coz("bugün hava güzel")
kontrol("alakasız cümleden kayıt çıkmaz", d == [], d)

print("\n[9] yaşam: kayıt ve panel")
store.yasam_ekle("uyku", BUGUN, 7.0, "saat", "iyi uyudum")
store.yasam_ekle("uyku", DUN, 5.0, "saat", "geç yattım")
store.yasam_ekle("harcama", BUGUN, 120, "TL", "market")
store.yasam_ekle("harcama", BUGUN, 45, "TL", "kahve")

p = yasam.panel(7)
uyku = next(k for k in p["kartlar"] if k["tur"] == "uyku")
kontrol("uyku ortalaması", uyku["ortalama"] == 6.0, uyku)
harcama = next(k for k in p["kartlar"] if k["tur"] == "harcama")
kontrol("bugünkü harcama toplandı", harcama["bugun"] == 165, harcama)
kontrol("veri olmayan tür işaretli",
        next(k for k in p["kartlar"] if k["tur"] == "ruh")["durum"] == "veri_yok")

store.ayar_yaz("uyku_hedef", "7.5")
p = yasam.panel(7)
uyku = next(k for k in p["kartlar"] if k["tur"] == "uyku")
kontrol("hedefin altı işaretlendi", uyku["durum"] == "dusuk", uyku)

seri = yasam.gunluk_seri("harcama", 3)
kontrol("seri gün sayısı", len(seri) == 3, len(seri))
kontrol("serideki bugün toplamı",
        seri[-1]["deger"] == 165 and seri[-1]["tarih"] == BUGUN, seri[-1])

print("\n[10] harici proje")
pid = store.harici_proje_ekle("Promosyon Telefon Standı", "baski",
                              "Anahtarlık tasarımı ve baskı",
                              hedef_tarih=mentor._gun_ekle(BUGUN, 14),
                              oncelik=1)
p = store.proje(pid)
kontrol("harici proje eklendi", p and p["harici"] == 1 and p["tur"] == "baski", p)
kontrol("sentetik yol üretildi", p["yol"].startswith("harici:baski:"), p["yol"])

pid2 = store.harici_proje_ekle("Promosyon Telefon Standı", "baski", "güncellendi")
kontrol("aynı ad tekrar eklenince güncellenir", pid2 == pid, (pid, pid2))
kontrol("not güncellendi", store.proje(pid)["not_metni"] == "güncellendi")

store.proje_alan_yaz(pid, durum="beklemede", oncelik=3)
kontrol("alan güncelleme çalışıyor",
        store.proje(pid)["durum"] == "beklemede", store.proje(pid)["durum"])
kontrol("beklemedeki proje aktif listesinde yok",
        pid not in [x["id"] for x in store.aktif_projeler()])

store.proje_alan_yaz(pid, yol="/hack", durum="aktif")
kontrol("izinsiz alan yazılamaz", store.proje(pid)["yol"].startswith("harici:"))

print("\n[11] JSON ayrıştırma dayanıklılığı")
kontrol("düz json", mentor._json_bul('{"a":1}') == {"a": 1})
kontrol("kod bloğu içinde",
        mentor._json_bul('```json\n{"a":2}\n```') == {"a": 2})
kontrol("metin arasında",
        mentor._json_bul('İşte plan:\n{"a":3}\nUmarım olur.') == {"a": 3})
kontrol("iç içe nesne",
        mentor._json_bul('{"a":{"b":[1,2]}}') == {"a": {"b": [1, 2]}})
kontrol("bozuk json None", mentor._json_bul("{bozuk") is None)
kontrol("boş metin None", mentor._json_bul("") is None)

print("\n[12] plan görev yerleştirme (modelsiz)")
plan_id = store.plan_kaydet("haftalik", hb, hs, "test çerçevesi")
kontrol("plan kaydedildi", plan_id > 0)
kontrol("aynı dönem üzerine yazar",
        store.plan_kaydet("haftalik", hb, hs, "yeni") == plan_id)
kontrol("çerçeve güncellendi",
        store.plan_getir("haftalik", hb)["metin"] == "yeni")

ham = [
    {"proje": "Promosyon Telefon Standı", "baslik": "Anahtarlık tasarımı",
     "tarih": YARIN, "saat": "10:00", "sure_dk": 90, "oncelik": 1,
     "zorunlu": True},
    {"proje": "Yok Böyle Bir Proje", "baslik": "Çakışan iş",
     "tarih": YARIN, "saat": "10:00", "sure_dk": 60, "oncelik": 2},
    {"baslik": "Dönem dışına taşan", "tarih": "2030-01-01", "saat": "10:00",
     "sure_dk": 60},
    {"baslik": "", "tarih": YARIN, "saat": "10:00"},
    {"baslik": "Bozuk süre", "tarih": YARIN, "saat": "bozuk",
     "sure_dk": "abc", "oncelik": 99},
]
n, uyarilar = mentor._gorevleri_yerlestir(ham, plan_id, hb, hs)
kontrol("boş başlıklı görev atlandı", n == 4, n)

yeni = [g for g in store.gorevler(tarih=hb, bitis=hs) if g["plan_id"] == plan_id]
saatler = [(g["tarih"], g["saat"]) for g in yeni]
kontrol("çakışma yok", len(set(saatler)) == len(saatler), saatler)
kontrol("bilinen proje eşleşti",
        any(g["proje_id"] == pid for g in yeni), [g["proje_id"] for g in yeni])
kontrol("bilinmeyen proje null bırakıldı",
        any(g["proje_id"] is None for g in yeni))
kontrol("dönem dışı tarih sınıra çekildi",
        all(hb <= g["tarih"] <= hs for g in yeni), [g["tarih"] for g in yeni])
kontrol("bozuk öncelik sınırlandı",
        all(1 <= g["oncelik"] <= 3 for g in yeni), [g["oncelik"] for g in yeni])
kontrol("bozuk süre makul değere çekildi",
        all(15 <= g["sure_dk"] <= 180 for g in yeni), [g["sure_dk"] for g in yeni])

print("\n[13] günlük blok sınırı")
store.ayar_yaz("gunluk_azami_blok", "2")
OBUR = mentor._gun_ekle(BUGUN, 3)
cok = [{"baslik": f"İş {i}", "tarih": OBUR, "saat": "09:00", "sure_dk": 60}
       for i in range(5)]
mentor._gorevleri_yerlestir(cok, plan_id, hb, mentor._gun_ekle(OBUR, 6))
o_gun = [g for g in store.gorevler(tarih=OBUR) if g["baslik"].startswith("İş ")]
kontrol("günlük blok sınırı aşılmadı", len(o_gun) <= 2, len(o_gun))
tasan = [g for g in store.gorevler(tarih=OBUR, bitis=mentor._gun_ekle(OBUR, 6))
         if g["baslik"].startswith("İş ")]
kontrol("taşan işler sonraki günlere dağıldı", len(tasan) == 5, len(tasan))

print("\n[14] bildirimler")
store.ayar_yaz("gunluk_azami_blok", "5")
bid = store.bildirim_ekle("Test", "gövde", tur="uyari")
kontrol("okunmamış listede", any(b["id"] == bid for b in
                                 store.bildirimler(sadece_okunmamis=True)))
store.bildirim_okundu(bid)
kontrol("okundu işaretlendi",
        not any(b["id"] == bid for b in
                store.bildirimler(sadece_okunmamis=True)))
store.bildirim_ekle("Test2", "gövde", tur="uyari")
store.bildirim_okundu()
kontrol("hepsi okundu", store.bildirimler(sadece_okunmamis=True) == [])

print("\n[15] mentör durumu")
d = mentor.durum()
kontrol("durum alanları", {"acik", "sertlik", "pencere", "bugun"} <= set(d), d)

print(f"\n{'='*54}")
print(f"  {gecti} test geçti, {len(kaldi)} kaldı")
if kaldi:
    for k in kaldi:
        print(f"    - {k}")
print("=" * 54)
sys.exit(1 if kaldi else 0)
