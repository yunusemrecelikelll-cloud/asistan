"""Toplu iş — aynı görevi tüm projelere sırayla gönderir.

Sırayla gider, paralel değil: 16 Claude örneğini aynı anda çalıştırmak hem
makineyi hem abonelik kotasını gereksiz zorlar. Her projeden sonra kullanım
sınırı yeniden kontrol edilir; sınır dolarsa kalanlar atlanır ve bu durum
rapor edilir.
"""

from __future__ import annotations

import threading
import time

import brief
import dispatch
import olay
import store

_durum: dict = {"calisiyor": False}
_kilit = threading.Lock()
_durdur = threading.Event()

PROJE_ZAMAN_ASIMI = 900


def durum() -> dict:
    with _kilit:
        return dict(_durum)


def _isle(gorev: str, proje_idler: list[int], etiket: str) -> None:
    global _durum
    tamam, atlanan, hata = [], [], []

    for i, pid in enumerate(proje_idler, 1):
        if _durdur.is_set():
            atlanan.append((pid, "kullanıcı durdurdu"))
            continue

        p = store.proje(pid)
        if not p or not p["var_mi"]:
            atlanan.append((pid, "klasör diskte yok"))
            continue

        ld = dispatch.limit_durumu()
        if ld["asildi"]:
            atlanan.append((pid, "kullanım sınırı doldu"))
            continue

        with _kilit:
            _durum.update({"sira": i, "toplam": len(proje_idler),
                           "suanki": p["ad"]})
        olay.yayinla("toplu", sira=i, toplam=len(proje_idler), suanki=p["ad"])

        # Her proje temiz oturumda: bu görev geçmiş bağlama muhtaç değil ve
        # eski oturumlardaki takıntılar sonucu bozabiliyor.
        sonuc = dispatch.gonder(pid, gorev, devam=False,
                                zaman_asimi=PROJE_ZAMAN_ASIMI)
        if "hata" in sonuc:
            hata.append((p["ad"], sonuc["hata"]))
            continue

        eid = sonuc["eylem_id"]
        bitis = time.time() + PROJE_ZAMAN_ASIMI + 60
        while time.time() < bitis and not _durdur.is_set():
            d = dispatch.durum(eid)
            if not d or d["durum"] != "calisiyor":
                break
            time.sleep(4)

        d = dispatch.durum(eid) or {}
        if d.get("durum") in ("tamam", "kesildi"):
            tamam.append((p["ad"], d.get("maliyet") or 0))
        else:
            hata.append((p["ad"], d.get("hata") or d.get("durum") or "bilinmiyor"))

    toplam_tuketim = sum(m for _, m in tamam)
    satirlar = [f"{etiket}: {len(tamam)} proje tamamlandı."]
    if tamam:
        satirlar.append("Tamamlananlar: " + ", ".join(a for a, _ in tamam) + ".")
    if hata:
        satirlar.append(f"{len(hata)} projede hata: " +
                        ", ".join(a for a, _ in hata) + ".")
    if atlanan:
        nedenler = {}
        for _, n in atlanan:
            nedenler[n] = nedenler.get(n, 0) + 1
        satirlar.append("Atlananlar: " +
                        ", ".join(f"{v} proje ({k})" for k, v in nedenler.items()) + ".")
    satirlar.append(f"Toplam tüketim {toplam_tuketim:.2f} birim.")

    store.mesaj_ekle("sistem", " ".join(satirlar), None, "yerel")

    with _kilit:
        _durum = {"calisiyor": False, "bitti": True,
                  "tamam": len(tamam), "hata": len(hata),
                  "atlanan": len(atlanan), "tuketim": round(toplam_tuketim, 2)}
    olay.yayinla("toplu", bitti=True, tamam=len(tamam), hata=len(hata))


def baslat(gorev: str, proje_idler: list[int] | None = None,
           etiket: str = "Toplu iş") -> dict:
    global _durum
    with _kilit:
        if _durum.get("calisiyor"):
            return {"hata": "zaten bir toplu iş çalışıyor"}
        if proje_idler is None:
            proje_idler = [p["id"] for p in store.projeler(sadece_var=True)]
        if not proje_idler:
            return {"hata": "işlenecek proje yok"}
        _durdur.clear()
        _durum = {"calisiyor": True, "sira": 0, "toplam": len(proje_idler),
                  "suanki": None, "etiket": etiket}

    threading.Thread(target=_isle, args=(gorev, proje_idler, etiket),
                     daemon=True, name="toplu").start()
    return {"baslatildi": True, "proje_sayisi": len(proje_idler)}


def durdur() -> dict:
    _durdur.set()
    return {"durduruldu": True}


def ozet_gorevi(proje_idler: list[int] | None = None) -> dict:
    """Her projeye ASISTAN-OZET.md yazdır/güncelle."""
    return baslat(brief.OZET_GOREVI, proje_idler, "Özet güncelleme")
