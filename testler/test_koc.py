# -*- coding: utf-8 -*-
"""Yaşam koçu testleri — seriler, örüntüler, odak, bütçe, ritüeller."""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\PC\Desktop\Asistan\backend")

import store

gecici = Path(tempfile.mkdtemp())
store.DB_PATH = gecici / "test.db"

import gunluk

gunluk.KOK = gecici / "gunluk"

import brain
import koc
import mentor

store.kur()

# Modeli çağırmadan test edelim: sahte bir yerel_once koy.
SAHTE_YANIT = {"sonuc": "Dün üç işten ikisini kaçırdın. Bugün ilk işi 09:00'da "
                        "başlat, telefonu başka odaya koy.",
               "metin": "", "kaynak": "yerel", "maliyet": 0.0, "hata": False}
brain.yerel_once = lambda *a, **k: dict(SAHTE_YANIT)

gecti, kaldi = 0, []


def kontrol(ad, kosul, ayrinti=""):
    global gecti
    if kosul:
        gecti += 1
        print(f"  OK   {ad}")
    else:
        kaldi.append(f"{ad} — {ayrinti}")
        print(f"  HATA {ad} — {ayrinti}")


BUGUN = koc._bugun()
G = koc._gun_ekle

print("\n[1] seri hesabı")
kontrol("boş küme sıfır", koc.seri_hesapla(set()) == 0)
kontrol("bugün işaretliyse 1", koc.seri_hesapla({BUGUN}) == 1)
kontrol("bugün boş ama dün varsa 1 (gün bitmedi)",
        koc.seri_hesapla({G(BUGUN, -1)}) == 1)
kontrol("üç günlük seri",
        koc.seri_hesapla({BUGUN, G(BUGUN, -1), G(BUGUN, -2)}) == 3)
kontrol("boşluk seriyi keser",
        koc.seri_hesapla({BUGUN, G(BUGUN, -1), G(BUGUN, -3)}) == 2)
kontrol("çok eski gün sayılmaz", koc.seri_hesapla({G(BUGUN, -10)}) == 0)

kontrol("en uzun seri", koc._en_uzun_seri(
    {G(BUGUN, -9), G(BUGUN, -8), G(BUGUN, -7), G(BUGUN, -5), BUGUN}) == 3)
kontrol("boşta en uzun sıfır", koc._en_uzun_seri(set()) == 0)

print("\n[2] alışkanlıklar")
spor = store.aliskanlik_ekle("Spor", "gunluk", hedef=5, saat="18:00")
kitap = store.aliskanlik_ekle("Kitap", "gunluk", hedef=7)
kontrol("iki alışkanlık", len(store.aliskanliklar()) == 2)
kontrol("aynı ad günceller",
        store.aliskanlik_ekle("Spor", "gunluk", hedef=6) == spor)
kontrol("hedef güncellendi", store.aliskanlik(spor)["hedef"] == 6)

for i in range(4):
    store.aliskanlik_isaretle(spor, G(BUGUN, -i))
p = koc.aliskanlik_paneli(28)
s = next(a for a in p["aliskanliklar"] if a["id"] == spor)
kontrol("seri dört", s["seri"] == 4, s["seri"])
kontrol("bugün işaretli", s["bugun"])
kontrol("bu hafta sayısı", s["bu_hafta"] == 4, s["bu_hafta"])
kontrol("hedef tutmadı", not s["hedef_tuttu"])
kontrol("takvim 28 gün", len(s["takvim"]) == 28)

store.aliskanlik_isaretle(spor, BUGUN, yapildi=False)
p = koc.aliskanlik_paneli(28)
s = next(a for a in p["aliskanliklar"] if a["id"] == spor)
kontrol("geri alınca bugün düşer", not s["bugun"])
kontrol("dünden gelen seri korunur", s["seri"] == 3, s["seri"])

print("\n[3] kırılan seri uyarısı")
kontrol("kitap serisiz, uyarı yok",
        not any(k["id"] == kitap for k in koc.kirilan_seriler()))
for i in range(2, 6):
    store.aliskanlik_isaretle(kitap, G(BUGUN, -i))
kirilan = koc.kirilan_seriler()
kontrol("dün atlanan uzun seri yakalandı",
        any(k["id"] == kitap for k in kirilan), [k["ad"] for k in kirilan])
k = next(k for k in kirilan if k["id"] == kitap)
kontrol("kırılan seri uzunluğu", k["kirilan_seri"] == 4, k["kirilan_seri"])

store.aliskanlik_isaretle(kitap, BUGUN)
kontrol("bugün yapılınca uyarı düşer",
        not any(x["id"] == kitap for x in koc.kirilan_seriler()))

print("\n[4] erteleme örüntüsü")
iyi = store.harici_proje_ekle("İyi Giden", "kisisel")
kotu = store.harici_proje_ekle("Sürünen Proje", "kod")
for i in range(4):
    g = store.gorev_ekle(f"iyi {i}", G(BUGUN, -i - 1), "10:00", proje_id=iyi)
    store.gorev_durum(g, "tamam")
for i in range(5):
    g = store.gorev_ekle(f"kotu {i}", G(BUGUN, -i - 1), "11:00", proje_id=kotu)
    store.gorev_durum(g, "kacirildi")

kaliplar = koc.erteleme_kaliplari(21)
adlar = [k["ad"] for k in kaliplar]
kontrol("sürünen proje yakalandı", "Sürünen Proje" in adlar, adlar)
kontrol("iyi giden proje yakalanmadı", "İyi Giden" not in adlar, adlar)
kk = next(k for k in kaliplar if k["ad"] == "Sürünen Proje")
kontrol("kaçan sayısı", kk["kacan"] == 5, kk)
kontrol("yüzde 100", kk["yuzde"] == 100, kk["yuzde"])

print("\n[5] uyku–performans bağlantısı")
u = koc.uyku_performans(30)
kontrol("veri yokken yorum yok", not u["yeterli_veri"], u)

# Az uyunan günler: görevler kaçmış. Bol uyunan: tamam.
for i in range(6, 10):
    t = G(BUGUN, -i)
    store.yasam_ekle("uyku", t, 5.0, "saat")
    g = store.gorev_ekle(f"az {i}", t, "10:00")
    store.gorev_durum(g, "kacirildi")
for i in range(11, 15):
    t = G(BUGUN, -i)
    store.yasam_ekle("uyku", t, 8.0, "saat")
    g = store.gorev_ekle(f"bol {i}", t, "10:00")
    store.gorev_durum(g, "tamam")

u = koc.uyku_performans(30)
kontrol("yeterli veri oldu", u["yeterli_veri"], u)
kontrol("az uyku uyumu düşük", u["az_uyku_uyum"] == 0, u)
kontrol("bol uyku uyumu yüksek", u["bol_uyku_uyum"] == 100, u)
kontrol("fark hesaplandı", u["fark"] == 100, u)

print("\n[6] örüntü özeti mentöre gidiyor")
ozet = koc.kaliplar_ozeti()
kontrol("erteleme örüntüsü özette", "ERTELEME ÖRÜNTÜSÜ" in ozet, ozet[:120])
kontrol("uyku etkisi özette", "UYKU ETKİSİ" in ozet, ozet[:200])
kontrol("sürünen proje adı geçiyor", "Sürünen Proje" in ozet)

print("\n[7] odak oturumu")
g = store.gorev_ekle("Odaklanılacak iş", BUGUN, "23:30", sure_dk=60)
r = koc.odak_basla(g)
kontrol("odak başladı", r.get("ok") and store.gorev(g)["durum"] == "calisiyor")
kontrol("başlangıç zamanı yazıldı", store.gorev(g)["baslatildi"] is not None)

# 90 dakika geçmiş gibi yap
store._conn().execute("UPDATE gorevler SET baslatildi=? WHERE id=?",
                      (time.time() - 90 * 60, g))
store._conn().commit()
r = koc.odak_bitir(g)
kontrol("odak bitti", r.get("ok"))
kontrol("gerçek süre kaydedildi", 89 <= r["gercek_dk"] <= 91, r["gercek_dk"])
kontrol("görev tamam", store.gorev(g)["durum"] == "tamam")
kontrol("tahmin aşımı yorumlandı", "gerçekçi değil" in r["yorum"], r["yorum"])

g2 = store.gorev_ekle("Kısa iş", BUGUN, "23:45", sure_dk=120)
koc.odak_basla(g2)
r2 = koc.odak_bitir(g2)
kontrol("kısa biten iş yorumlandı",
        "fazla yer ayırıyorsun" in r2["yorum"], r2["yorum"])

t = store.tahmin_sapmasi(G(BUGUN, -30), BUGUN)
kontrol("sapma ölçüldü", t["sayi"] == 2, t)
kontrol("oran hesaplandı", t["oran"] is not None, t)

kontrol("olmayan görevde odak reddedilir", not koc.odak_basla(99999).get("ok"))
kontrol("biten görevde odak reddedilir", not koc.odak_basla(g).get("ok"))

print("\n[8] harcama kategorileri")
kontrol("kahve → yeme", koc.kategori_bul("kahveye 45 lira") == "yeme")
kontrol("market → market", koc.kategori_bul("markete 250 tl") == "market")
kontrol("benzin → ulasim", koc.kategori_bul("benzin 900") == "ulasim")
kontrol("filament → atolye", koc.kategori_bul("filament aldım") == "atolye")
kontrol("bilinmeyen → diğer", koc.kategori_bul("şey aldım") == "diğer")

print("\n[9] bütçe paneli")
ay_bas = BUGUN[:8] + "01"
for tutar, kat in ((120, "yeme"), (45, "yeme"), (300, "market"), (200, "atolye")):
    kid = store.yasam_ekle("harcama", BUGUN, tutar, "TL", kat)
    store.yasam_kategori_yaz(kid, kat)

b = koc.butce_paneli()
kontrol("toplam doğru", b["toplam"] == 665, b["toplam"])
kontrol("bütçe yokken kalan None", b["kalan"] is None, b)
yeme = next(k for k in b["kategoriler"] if k["kategori"] == "yeme")
kontrol("yeme kategorisi toplandı", yeme["harcanan"] == 165, yeme)
kontrol("kategoriler büyükten küçüğe",
        [k["harcanan"] for k in b["kategoriler"]]
        == sorted([k["harcanan"] for k in b["kategoriler"]], reverse=True))

b = koc.butce_yaz(aylik=2000, kategoriler={"yeme": 400, "market": 200})
kontrol("aylık bütçe yazıldı", b["aylik_butce"] == 2000)
kontrol("kalan hesaplandı", b["kalan"] == 1335, b["kalan"])
kontrol("yüzde hesaplandı", b["yuzde"] == 33, b["yuzde"])
market = next(k for k in b["kategoriler"] if k["kategori"] == "market")
kontrol("kategori bütçesi aşıldı", market["asildi"], market)
yeme = next(k for k in b["kategoriler"] if k["kategori"] == "yeme")
kontrol("aşılmayan kategori işaretsiz", not yeme["asildi"], yeme)
kontrol("ay sonu tahmini var", b["ay_sonu_tahmini"] > 0, b["ay_sonu_tahmini"])

print("\n[10] ritüeller")
r = koc.rituel_uret("sabah", BUGUN)
kontrol("sabah ritüeli üretildi", r.get("ok") and r["metin"], r)
kontrol("soru eklendi", len(r["sorular"]) == 1, r["sorular"])
kayit = store.rituel(BUGUN, "sabah")
kontrol("kaydedildi", kayit and kayit["veri"]["metin"] == r["metin"])
kontrol("henüz tamamlanmadı", kayit["tamamlandi"] is None)

r = koc.rituel_cevapla("sabah", {"Bugünün tek kritik işi ne?": "Anahtarlık"})
kontrol("cevap kaydedildi", r.get("ok"))
kayit = store.rituel(BUGUN, "sabah")
kontrol("tamamlandı damgası", kayit["tamamlandi"] is not None)
kontrol("cevap duruyor",
        kayit["veri"]["cevaplar"]["Bugünün tek kritik işi ne?"] == "Anahtarlık")

r = koc.rituel_uret("aksam", BUGUN)
kontrol("akşam ritüeli üç soru", len(r["sorular"]) == 3, r["sorular"])
kontrol("geçersiz tür reddedilir", not koc.rituel_uret("oglen").get("ok"))
kontrol("üretilmemiş ritüele cevap reddedilir",
        not koc.rituel_cevapla("aksam", {}, G(BUGUN, -5)).get("ok"))

print("\n[11] haftalık seans")
r = koc.haftalik_seans()
kontrol("seans üretildi", r.get("ok") and r["metin"], r)
kontrol("veri toplandı", any("KARNE" in x for x in r["veri"]), r["veri"][:3])
kontrol("erteleme örüntüsü seansta",
        any("ERTELENEN" in x for x in r["veri"]))
kontrol("alışkanlıklar seansta",
        any("ALIŞKANLIK" in x for x in r["veri"]))
kontrol("harcama seansta", any("HARCAMA" in x for x in r["veri"]))
_, hafta_son = mentor.hafta_sinirlari()
kontrol("seans kaydedildi", store.rituel(hafta_son, "seans") is not None)

print("\n[12] ton ayarı")
kontrol("varsayılan sert", "Sert bir koç" in koc.ton())
store.ayar_yaz("koc_tonu", "yumusak")
kontrol("yumuşak seçilebiliyor", "Destekleyici" in koc.ton())
store.ayar_yaz("koc_tonu", "bilinmeyen")
kontrol("bilinmeyen ton serte düşer", "Sert bir koç" in koc.ton())
store.ayar_yaz("koc_tonu", "sert")

print("\n[13] koç paneli")
p = koc.panel()
kontrol("panel bölümleri",
        {"sabah", "aksam", "aliskanliklar", "butce", "kaliplar", "son_seans"}
        <= set(p), set(p))
kontrol("son seans bulundu", p["son_seans"] is not None)
kontrol("kalıplar dolu", p["kaliplar"]["erteleme"], p["kaliplar"])

print(f"\n{'='*54}")
print(f"  {gecti} test geçti, {len(kaldi)} kaldı")
for k in kaldi:
    print(f"    - {k}")
print("=" * 54)
sys.exit(1 if kaldi else 0)
