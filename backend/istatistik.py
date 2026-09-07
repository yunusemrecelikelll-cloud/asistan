"""Genel istatistikler — atölye, mentörlük, yaşam ve maliyet.

Hepsi mevcut tablolardan hesaplanır; ayrı bir sayaç tablosu tutmuyoruz.
Veri az olduğunda sayı uydurmak yerine ``None`` dönüyoruz — arayüz "veri yok"
yazsın, yanıltıcı bir yüzde göstermesin.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import store


def _gun_ekle(tarih: str, n: int) -> str:
    return (date.fromisoformat(tarih) + timedelta(days=n)).isoformat()


def _bugun() -> str:
    return date.today().isoformat()


def _sure_metni(dakika: float | int | None) -> str:
    if not dakika:
        return "0 sa"
    dk = int(dakika)
    return f"{dk // 60} sa {dk % 60} dk" if dk >= 60 else f"{dk} dk"


# ── atölye ─────────────────────────────────────────────────────────────────


def atolye(gun: int = 30) -> dict:
    esik = time.time() - gun * 86400
    c = store._conn()

    toplam = c.execute(
        "SELECT COUNT(*) n, "
        "  SUM(durum='bitti') bitti, "
        "  SUM(durum='iptal') iptal, "
        "  SUM(durum='hata') hata, "
        "  SUM(durum='basiliyor') suren, "
        "  COALESCE(SUM(CASE WHEN bitis IS NOT NULL "
        "    THEN (bitis-baslangic)/60.0 ELSE 0 END),0) dakika "
        "FROM baskilar WHERE baslangic >= ?", (esik,)).fetchone()

    kapanan = (toplam["bitti"] or 0) + (toplam["iptal"] or 0) + (toplam["hata"] or 0)
    basari = round(100 * (toplam["bitti"] or 0) / kapanan) if kapanan else None

    yazicilar = []
    for y in store.yazicilar():
        r = c.execute(
            "SELECT COUNT(*) n, SUM(durum='bitti') bitti, "
            "  COALESCE(SUM(CASE WHEN bitis IS NOT NULL "
            "    THEN (bitis-baslangic)/60.0 ELSE 0 END),0) dakika "
            "FROM baskilar WHERE yazici_id=? AND baslangic >= ?",
            (y["id"], esik)).fetchone()
        yazicilar.append({
            "id": y["id"], "ad": y["ad"], "model": y["model"],
            "durum": y["durum"], "filament": y["filament"],
            "filament_renk": y["filament_renk"],
            "nozzle": y["nozzle"],
            "omur_dk": y["toplam_dk"],
            "omur_metni": _sure_metni(y["toplam_dk"]),
            "omur_baski": y["baski_sayisi"],
            "donem_baski": r["n"] or 0,
            "donem_bitti": r["bitti"] or 0,
            "donem_dk": round(r["dakika"] or 0),
            "donem_metni": _sure_metni(r["dakika"]),
            "mesgul_yuzde": (round(100 * (r["dakika"] or 0) / (gun * 24 * 60))
                             if gun else 0),
        })

    filamentler = {}
    for y in store.yazicilar():
        if y["filament"]:
            filamentler[y["filament"]] = filamentler.get(y["filament"], 0) + 1

    return {
        "gun": gun,
        "baski_sayisi": toplam["n"] or 0,
        "bitti": toplam["bitti"] or 0,
        "iptal": toplam["iptal"] or 0,
        "suren": toplam["suren"] or 0,
        "basari_yuzde": basari,
        "toplam_dk": round(toplam["dakika"] or 0),
        "toplam_metni": _sure_metni(toplam["dakika"]),
        "yazicilar": yazicilar,
        "filamentler": filamentler,
    }


# ── mentörlük ──────────────────────────────────────────────────────────────


def mentorluk(gun: int = 30) -> dict:
    bitis = _bugun()
    baslangic = _gun_ekle(bitis, -(gun - 1))
    genel = store.gorev_istatistik(baslangic, bitis)

    # Günlük uyum eğrisi
    seri = []
    for i in range(gun):
        t = _gun_ekle(baslangic, i)
        g = store.gorevler(tarih=t)
        sayilan = [x for x in g if x["durum"] != "iptal"]
        tamam = sum(1 for x in sayilan if x["durum"] == "tamam")
        seri.append({
            "tarih": t, "toplam": len(sayilan), "tamam": tamam,
            "uyum": round(100 * tamam / len(sayilan)) if sayilan else None,
        })

    # Proje başına
    c = store._conn()
    projeler = [dict(r) for r in c.execute(
        "SELECT p.ad, p.tur, COUNT(g.id) toplam, "
        "  SUM(g.durum='tamam') tamam, SUM(g.durum='kacirildi') kacan "
        "FROM gorevler g JOIN projeler p ON p.id=g.proje_id "
        "WHERE g.tarih BETWEEN ? AND ? AND g.durum!='iptal' "
        "GROUP BY p.id ORDER BY toplam DESC LIMIT 12",
        (baslangic, bitis))]

    # En çok kaçırılan işler
    kacanlar = [dict(r) for r in c.execute(
        "SELECT baslik, COUNT(*) n FROM gorevler "
        "WHERE durum='kacirildi' AND tarih BETWEEN ? AND ? "
        "GROUP BY baslik ORDER BY n DESC LIMIT 6", (baslangic, bitis))]

    # Şu anki seri: bugünden geriye kaç gün tam uyum
    seri_gun = 0
    for g in reversed(seri):
        if g["toplam"] and g["uyum"] == 100:
            seri_gun += 1
        elif g["toplam"]:
            break

    return {
        "gun": gun, "baslangic": baslangic, "bitis": bitis,
        **genel, "seri": seri, "projeler": projeler,
        "en_cok_kacan": kacanlar, "temiz_gun_serisi": seri_gun,
    }


# ── yaşam ve maliyet ───────────────────────────────────────────────────────


def yasam_ozeti(gun: int = 30) -> dict:
    bitis = _bugun()
    baslangic = _gun_ekle(bitis, -(gun - 1))
    return {"gun": gun, **store.yasam_ozet(baslangic, bitis)}


def maliyet(gun: int = 30) -> dict:
    c = store._conn()
    esik = time.time() - gun * 86400
    r = c.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(maliyet),0) toplam FROM eylemler "
        "WHERE maliyet IS NOT NULL AND baslangic >= ?", (esik,)).fetchone()
    kaynak = {x["kaynak"]: x["n"] for x in c.execute(
        "SELECT COALESCE(kaynak,'?') kaynak, COUNT(*) n FROM mesajlar "
        "WHERE zaman >= ? GROUP BY kaynak", (esik,))}
    yerel = {x["olay"]: x["n"] for x in c.execute(
        "SELECT olay, COUNT(*) n FROM gunluk "
        "WHERE kaynak='brain' AND zaman >= ? GROUP BY olay", (esik,))}
    yerel_is = yerel.get("yerel_yeterli", 0)
    yukseltme = yerel.get("claude_a_yukseltildi", 0)
    return {
        "gun": gun,
        "eylem_sayisi": r["n"],
        "toplam_birim": round(r["toplam"], 4),
        "mesaj_kaynaklari": kaynak,
        "yerel_biten_is": yerel_is,
        "claude_a_yukselen": yukseltme,
        "yerel_oran": (round(100 * yerel_is / (yerel_is + yukseltme))
                       if (yerel_is + yukseltme) else None),
    }


def dosyalar() -> dict:
    bekleyen = store.dosyalar(durum="bekliyor")
    biten = store.dosyalar(durum="bitti")
    return {"bekleyen": len(bekleyen), "biten": len(biten)}


def hepsi(gun: int = 30) -> dict:
    return {
        "gun": gun,
        "atolye": atolye(gun),
        "mentorluk": mentorluk(gun),
        "yasam": yasam_ozeti(gun),
        "maliyet": maliyet(gun),
        "dosyalar": dosyalar(),
        "gunluk": store.gunluk_ozet(24),
    }
