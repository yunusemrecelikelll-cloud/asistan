"""Otomatik devam — açık olan projelerde işi kendi başına sürdürür.

Her turda projeye duran bir "kaldığın yerden devam et" görevi gönderilir.
Sıradaki adımı Claude'un kendisi seçer ve uygular — bu kararı yerel küçük
modele bırakmıyoruz, çünkü orada güvenilir değil. Claude yapacak iş kalmadığını
bildirirse (``YAPILACAK_YOK``) otomatik kip kapanır.

Emniyet frenleri:
  • Kullanım sınırı aşılmışsa hiç tur atılmaz.
  • Üst üste en fazla ``oto_azami`` tur döner, sonra kendini kapatır.
  • Bir tur hata verirse otomatik kip kapatılır — döngüye girmesin.
  • Aynı anda tek bir otomatik tur çalışır.
"""

from __future__ import annotations

import threading
import time

import dispatch
import store

_calisiyor = False
_kilit = threading.Lock()
_durdur = threading.Event()

# Bir turun bitmesi için beklenecek en uzun süre
TUR_ZAMAN_ASIMI = 1800

# Otomatik kipte her turda gönderilen duran görev.
DEVAM_GOREVI = """Bu projede kaldığın yerden devam et.

Şunu yap:
1. Projeye bak: README, TODO, yarım kalmış kod, son commitler, açık uçlar.
2. Tek seferde bitirilebilecek, küçük ve somut bir sonraki adım seç.
3. O adımı uygula ve ne yaptığını iki üç cümleyle özetle.

Kurallar:
- Yıkıcı işler yapma: dosya/klasör silme, git geçmişini değiştirme,
  bağımlılık kaldırma, üretim ayarlarına dokunma.
- Büyük yeniden yapılandırmaya girişme; küçük ve güvenli adım seç.
- Projede yapılacak anlamlı bir iş kalmadıysa hiçbir değişiklik yapma ve
  yanıt olarak yalnızca YAPILACAK_YOK yaz."""


def _son_cikti(proje_id: int) -> str:
    r = store._conn().execute(
        "SELECT cikti FROM eylemler WHERE proje_id=? AND durum='tamam' "
        "ORDER BY baslangic DESC LIMIT 1", (proje_id,)
    ).fetchone()
    return (r["cikti"] or "") if r else ""


def _bir_tur(p: dict) -> str:
    """Tek bir otomatik adım. Ne olduğunu anlatan kısa bir metin döndürür."""
    pid = p["id"]

    if p["oto_sayac"] >= p["oto_azami"]:
        store.otomatik_ayarla(pid, False)
        return (f"{p['ad']}: üst üste {p['oto_azami']} tur tamamlandı, "
                f"otomatik kip kendini kapattı.")

    ld = dispatch.limit_durumu()
    if ld["asildi"]:
        store.otomatik_ayarla(pid, False)
        return (f"{p['ad']}: kullanım sınırı dolduğu için otomatik kip kapatıldı.")

    # Sıradaki adımı yerel modele seçtirmiyoruz: küçük model bu kararda
    # güvenilir değil (kural gereği "YAPILACAK_YOK" yazması gerekirken
    # paragraf yazıyor). Projeyi zaten okuyabilen Claude hem kararı verir
    # hem işi yapar.
    son = _son_cikti(pid)
    gorev = DEVAM_GOREVI
    if son:
        gorev += "\n\nEn son yapılan işin çıktısı:\n" + son[:1200]

    # Temiz oturumda başlat: sürdürülen oturumdaki eski 'izin reddedildi'
    # mesajları Claude'u denemeden pes etmeye ikna edebiliyor. Bağlamı
    # brifing zaten sağlıyor.
    sonuc = dispatch.gonder(pid, gorev, devam=False)
    if "hata" in sonuc:
        store.otomatik_ayarla(pid, False)
        return f"{p['ad']}: otomatik tur başlatılamadı ({sonuc['hata']}). Kip kapatıldı."

    store.otomatik_tur_kaydet(pid)
    store.mesaj_ekle(
        "asistan",
        f"[otomatik] {p['ad']} — sıradaki adımı Claude belirleyip uyguluyor.",
        pid, "claude",
    )

    # Turun bitmesini bekle; hata olursa kipi kapat.
    eid = sonuc["eylem_id"]
    bitis = time.time() + TUR_ZAMAN_ASIMI
    while time.time() < bitis and not _durdur.is_set():
        d = dispatch.durum(eid)
        if not d or d["durum"] != "calisiyor":
            break
        time.sleep(5)

    d = dispatch.durum(eid) or {}
    if d.get("durum") == "kesildi":
        return (f"{p['ad']}: tur sınırına takıldı, iş yarım kaldı. "
                f"Sonraki turda kaldığı yerden devam edecek.")
    if d.get("durum") == "tamam":
        cikti = (d.get("cikti") or "")
        if "YAPILACAK_YOK" in cikti.upper():
            store.otomatik_ayarla(pid, False)
            return (f"{p['ad']}: Claude yapacak iş kalmadığını bildirdi, "
                    f"otomatik kip kapatıldı.")
        ozet = cikti.strip().splitlines()[0][:160] if cikti.strip() else ""
        return f"{p['ad']}: tur tamamlandı. {ozet}"
    store.otomatik_ayarla(pid, False)
    return (f"{p['ad']}: tur {d.get('durum', 'bilinmiyor')} ile bitti, "
            f"otomatik kip kapatıldı.")


def _dongu() -> None:
    while not _durdur.is_set():
        try:
            for p in store.otomatik_projeler():
                if _durdur.is_set():
                    break
                bekleme = p["oto_aralik"] or 900
                son = p["oto_son"] or 0
                if time.time() - son < bekleme:
                    continue
                mesaj = _bir_tur(p)
                store.mesaj_ekle("sistem", mesaj, p["id"], "yerel")
        except Exception as e:                      # döngü asla ölmesin
            print(f"[otomatik] hata: {e}")
        _durdur.wait(20)


def baslat() -> None:
    global _calisiyor
    with _kilit:
        if _calisiyor:
            return
        _calisiyor = True
        _durdur.clear()
        threading.Thread(target=_dongu, daemon=True, name="otomatik").start()
        print("[otomatik] zamanlayıcı çalışıyor")


def durdur() -> None:
    global _calisiyor
    with _kilit:
        _durdur.set()
        _calisiyor = False


def durum() -> dict:
    projeler = store.otomatik_projeler()
    return {
        "calisiyor": _calisiyor,
        "acik_projeler": [
            {
                "id": p["id"],
                "ad": p["ad"],
                "aralik": p["oto_aralik"],
                "sayac": p["oto_sayac"],
                "azami": p["oto_azami"],
                "son": p["oto_son"],
            }
            for p in projeler
        ],
    }
