# -*- coding: utf-8 -*-
"""Atölye (yazıcı + baskı) mantığını geçici veritabanında dener."""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\PC\Desktop\Asistan\backend")

import store

store.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"

import baski
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


print("\n[1] yazıcı kaydı")
idler = [store.yazici_ekle(f"Kobra S1 #{i}", "Anycubic Kobra S1",
                           notlar="0.4 nozzle") for i in range(1, 5)]
kontrol("dört yazıcı eklendi", len(set(idler)) == 4, idler)
kontrol("hepsi boş", len(baski.bos_yazicilar()) == 4)

tekrar = store.yazici_ekle("Kobra S1 #1", "Anycubic Kobra S1", ip="192.168.1.50")
kontrol("aynı ad tekrar eklenince günceller", tekrar == idler[0])
kontrol("ip güncellendi", store.yazici(idler[0])["ip"] == "192.168.1.50")
kontrol("yazıcı sayısı artmadı", len(store.yazicilar()) == 4)

print("\n[2] baskı başlatma")
pid = store.harici_proje_ekle("Promosyon Standı", "baski", oncelik=1)
r = baski.baski_basla(idler[0], "anahtarlık v3", 240, pid)
kontrol("baskı başladı", r.get("ok"), r)
bid = r["baski_id"]

kontrol("yazıcı meşgul göründü", len(baski.bos_yazicilar()) == 3)

cakisma = baski.baski_basla(idler[0], "ikinci iş", 60, pid)
kontrol("dolu yazıcıya ikinci baskı reddedilir",
        not cakisma.get("ok") and "baskısında" in cakisma.get("hata", ""),
        cakisma)

r2 = baski.baski_basla(idler[1], "stand gövdesi", 180, pid)
kontrol("başka yazıcıya baskı verilebilir", r2.get("ok"), r2)

print("\n[3] ilerleme")
d = baski.baski_durum(bid)
kontrol("durum okunuyor", d["var"] and d["durum"] == "basiliyor", d)
kontrol("yüzde makul", 0 <= d["yuzde"] <= 2, d["yuzde"])
kontrol("kalan süre makul", 238 <= d["kalan_dk"] <= 240, d["kalan_dk"])
kontrol("henüz bitmedi", not d["bitti"])

store.baski_sure_guncelle(bid, 30)
d = baski.baski_durum(bid)
kontrol("süre düzeltmesi ilerlemeye yansıdı", d["kalan_dk"] <= 30, d)

print("\n[4] denetim: süresi dolan baskı")
# Baskıyı geçmişe çekerek süresini doldur
store._conn().execute("UPDATE baskilar SET baslangic=? WHERE id=?",
                      (time.time() - 3600, bid))
store._conn().commit()
d = baski.baski_durum(bid)
kontrol("süre dolunca bitti işaretlenir", d["bitti"], d)

gorev_once = len(store.gorevler(tarih=mentor.bugun(),
                                bitis=mentor._gun_ekle(mentor.bugun(), 5)))
yapilan = baski.denetle()
kontrol("denetim baskıyı yakaladı", any("baskı bitti" in y for y in yapilan),
        yapilan)
kontrol("baskı kapandı", store.baski(bid)["durum"] == "bitti")
kontrol("yazıcı boşaldı", len(baski.bos_yazicilar()) == 3)

gorev_sonra = store.gorevler(tarih=mentor.bugun(),
                             bitis=mentor._gun_ekle(mentor.bugun(), 5))
yeni = [g for g in gorev_sonra if "anahtarlık v3" in g["baslik"]]
kontrol("sıradaki adım takvime yazıldı", len(yeni) == 1, [g["baslik"] for g in yeni])
if yeni:
    kontrol("sıradaki adım kritik öncelikli", yeni[0]["oncelik"] == 1)
    kontrol("doğru projeye bağlı", yeni[0]["proje_id"] == pid)

kontrol("bitiş bildirimi düştü",
        any(b["baslik"] == "Baskı bitti" for b in store.bildirimler(limit=20)))

print("\n[5] denetim tekrarı")
sayi = len(store.gorevler(tarih=mentor.bugun(),
                          bitis=mentor._gun_ekle(mentor.bugun(), 5)))
baski.denetle()
kontrol("ikinci tur yeni görev üretmez",
        len(store.gorevler(tarih=mentor.bugun(),
                           bitis=mentor._gun_ekle(mentor.bugun(), 5))) == sayi)

print("\n[6] iptal")
bid2 = store.aktif_baskilar()[0]["id"]
r = baski.baski_bitir(bid2, "iptal", sonraki_adim=False)
kontrol("iptal edildi", r.get("ok") and store.baski(bid2)["durum"] == "iptal")
kontrol("iptalde sıradaki adım yazılmaz", r.get("gorev_id") is None)
kontrol("kapanmış baskı tekrar kapatılamaz",
        not baski.baski_bitir(bid2).get("ok"))

print("\n[7] atölye özeti (mentör bağlamı)")
baski.baski_basla(idler[2], "kapak parçası", 120, pid)
ozet = baski.atolye_ozeti()
kontrol("özet dört yazıcıyı sayıyor", ozet.count("Kobra S1 #") == 4, ozet)
kontrol("meşgul yazıcı işaretli", "baskısında" in ozet)
kontrol("boş yazıcı işaretli", "boş" in ozet)

print("\n[8] yazıcı silme")
store.yazici_sil(idler[3])
kontrol("yazıcı silindi", len(store.yazicilar()) == 3)

print("\n[9] ağ keşfi (yazıcı yoksa çökmemeli)")
try:
    bulunan = baski.yazici_ara(derin=False)
    kontrol("SDCP taraması hata vermiyor", isinstance(bulunan, list), bulunan)
except Exception as e:
    kontrol("SDCP taraması hata vermiyor", False, e)

print(f"\n{'='*54}")
print(f"  {gecti} test geçti, {len(kaldi)} kaldı")
for k in kaldi:
    print(f"    - {k}")
print("=" * 54)
sys.exit(1 if kaldi else 0)
