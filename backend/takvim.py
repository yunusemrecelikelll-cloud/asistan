"""Dış takvim — mentör gerçek randevuların üstüne blok yazmasın.

Google Takvim, Outlook ve Apple Takvim'in hepsi **gizli ICS adresi** veriyor;
o adresi ayarlara yapıştırmak yeterli. OAuth kurmuyoruz: tek yön okuma için
üç ayrı sağlayıcıyla kimlik doğrulama akışı kurmak, kazandırdığından fazla
bakım getiriyor.

ICS ayrıştırıcı elde yazıldı (``icalendar`` kurulu değil). Biçim basit:
katlanmış ``ANAHTAR;parametre:değer`` satırları. Tekrar eden etkinliklerin
(RRULE) tam açılımını yapmıyoruz — günlük/haftalık basit tekrarları
açıyoruz, karmaşık kuralları ilk oluşumuyla bırakıyoruz. Amaç takvimi
yönetmek değil, çakışmayı görmek.

Gizli ICS adresi takvimin tamamını okutur; ayarlarda parola gibi saklanıyor
ve günlüğe maskelenerek yazılıyor.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import httpx

import gunluk
import store

AZAMI_GUN = 60          # bugünden kaç gün ilerisi alınsın
GERI_GUN = 7


# ── ICS ayrıştırma ─────────────────────────────────────────────────────────


def _satirlari_ac(metin: str) -> list[str]:
    """ICS satır katlamasını aç: boşlukla başlayan satır öncekinin devamıdır."""
    satirlar: list[str] = []
    for ham in metin.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if ham[:1] in (" ", "\t") and satirlar:
            satirlar[-1] += ham[1:]
        else:
            satirlar.append(ham)
    return satirlar


def _deger_coz(satir: str) -> tuple[str, dict, str]:
    """'DTSTART;TZID=Europe/Istanbul:20260907T100000' → (ad, parametreler, değer)"""
    bas = satir.find(":")
    if bas == -1:
        return "", {}, ""
    sol, deger = satir[:bas], satir[bas + 1:]
    parcalar = sol.split(";")
    ad = parcalar[0].upper()
    parametreler = {}
    for p in parcalar[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            parametreler[k.upper()] = v
    return ad, parametreler, deger


def _kacis_coz(s: str) -> str:
    return (s.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\").strip())


def _zaman_coz(deger: str, parametreler: dict) -> tuple[str, str | None] | None:
    """(YYYY-MM-DD, HH:MM ya da None) döndür. Tüm gün etkinliğinde saat yok."""
    deger = deger.strip()
    if parametreler.get("VALUE") == "DATE" or len(deger) == 8:
        try:
            return datetime.strptime(deger[:8], "%Y%m%d").date().isoformat(), None
        except ValueError:
            return None
    m = re.match(r"^(\d{8})T(\d{6})(Z)?$", deger)
    if not m:
        return None
    try:
        g = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    if m.group(3):
        # UTC damgası: yerel saate çevir. Sunucu ve kullanıcı aynı makinede.
        g = g + (datetime.now() - datetime.utcnow())
    return g.date().isoformat(), g.strftime("%H:%M")


def _tekrarlar(bas_tarih: str, kural: str, sinir: str) -> list[str]:
    """Basit RRULE açılımı: GÜNLÜK ve HAFTALIK. Diğerleri tek oluşum."""
    p = dict(x.split("=", 1) for x in kural.split(";") if "=" in x)
    sikligi = p.get("FREQ", "").upper()
    if sikligi not in ("DAILY", "WEEKLY"):
        return [bas_tarih]

    try:
        aralik = max(1, int(p.get("INTERVAL", "1")))
    except ValueError:
        aralik = 1
    adim = timedelta(days=aralik if sikligi == "DAILY" else 7 * aralik)

    son = sinir
    if p.get("UNTIL"):
        u = _zaman_coz(p["UNTIL"], {})
        if u:
            son = min(son, u[0])
    try:
        azami_sayi = int(p.get("COUNT", "0"))
    except ValueError:
        azami_sayi = 0

    tarihler, imlec = [], date.fromisoformat(bas_tarih)
    while imlec.isoformat() <= son and len(tarihler) < 200:
        tarihler.append(imlec.isoformat())
        if azami_sayi and len(tarihler) >= azami_sayi:
            break
        imlec += adim
    return tarihler or [bas_tarih]


def ics_coz(metin: str, kaynak: str = "takvim") -> list[dict]:
    """ICS metnini randevu listesine çevir."""
    bugun = date.today()
    alt_sinir = (bugun - timedelta(days=GERI_GUN)).isoformat()
    ust_sinir = (bugun + timedelta(days=AZAMI_GUN)).isoformat()

    randevular: list[dict] = []
    icinde, e = False, {}

    for satir in _satirlari_ac(metin):
        ust = satir.upper()
        if ust.startswith("BEGIN:VEVENT"):
            icinde, e = True, {}
            continue
        if ust.startswith("END:VEVENT"):
            icinde = False
            r = _etkinlik_cevir(e, kaynak, alt_sinir, ust_sinir)
            randevular += r
            continue
        if not icinde:
            continue

        ad, parametreler, deger = _deger_coz(satir)
        if ad in ("SUMMARY", "LOCATION", "UID", "RRULE", "STATUS"):
            e[ad] = deger
        elif ad in ("DTSTART", "DTEND"):
            e[ad] = (parametreler, deger)
    return randevular


def _etkinlik_cevir(e: dict, kaynak: str, alt: str, ust: str) -> list[dict]:
    if "DTSTART" not in e:
        return []
    if (e.get("STATUS") or "").upper() == "CANCELLED":
        return []

    bas = _zaman_coz(e["DTSTART"][1], e["DTSTART"][0])
    if not bas:
        return []
    bas_tarih, bas_saat = bas

    sure = None
    if "DTEND" in e:
        bit = _zaman_coz(e["DTEND"][1], e["DTEND"][0])
        if bit and bas_saat and bit[1]:
            g1 = datetime.fromisoformat(f"{bas_tarih}T{bas_saat}")
            g2 = datetime.fromisoformat(f"{bit[0]}T{bit[1]}")
            sure = max(0, int((g2 - g1).total_seconds() // 60)) or None

    baslik = _kacis_coz(e.get("SUMMARY", "")) or "(başlıksız)"
    uid = e.get("UID") or f"{kaynak}:{baslik}:{bas_tarih}{bas_saat or ''}"
    yer = _kacis_coz(e.get("LOCATION", "")) or None

    tarihler = (_tekrarlar(bas_tarih, e["RRULE"], ust) if e.get("RRULE")
                else [bas_tarih])

    cikan = []
    for i, t in enumerate(tarihler):
        if not (alt <= t <= ust):
            continue
        cikan.append({
            "uid": uid if len(tarihler) == 1 else f"{uid}#{t}",
            "baslik": baslik, "tarih": t, "saat": bas_saat,
            "sure_dk": sure, "yer": yer, "kaynak": kaynak,
        })
    return cikan


# ── çekme ──────────────────────────────────────────────────────────────────


def cek(adres: str | None = None) -> dict:
    """ICS adresini indir, ayrıştır, kaydet."""
    adres = (adres or store.ayar("takvim_ics", "") or "").strip()
    if not adres:
        return {"ok": False, "hata": "Takvim adresi tanımlı değil."}
    if adres.startswith("webcal://"):
        adres = "https://" + adres[len("webcal://"):]
    if not adres.startswith(("http://", "https://")):
        return {"ok": False, "hata": "Adres http(s) ya da webcal olmalı."}

    try:
        r = httpx.get(adres, timeout=30, follow_redirects=True)
        r.raise_for_status()
        metin = r.text
    except httpx.HTTPError as e:
        gunluk.uyari("takvim", "cekilemedi", type(e).__name__)
        return {"ok": False, "hata": f"Takvim çekilemedi: {e}"}

    if "BEGIN:VCALENDAR" not in metin.upper():
        return {"ok": False,
                "hata": "Gelen içerik takvim değil. Gizli ICS adresini "
                        "kullandığından emin ol."}

    randevular = ics_coz(metin)
    store.randevu_temizle(GERI_GUN, kaynak="takvim")
    for r in randevular:
        store.randevu_kaydet(**r)

    gunluk.bilgi("takvim", "cekildi", f"{len(randevular)} randevu")
    return {"ok": True, "sayi": len(randevular),
            "randevular": store.randevular(
                (date.today() - timedelta(days=GERI_GUN)).isoformat(),
                (date.today() + timedelta(days=AZAMI_GUN)).isoformat())}


def gunun_randevulari(tarih: str) -> list[dict]:
    return [r for r in store.randevular(tarih) if r["saat"]]


def dolu_araliklar(tarih: str) -> list[tuple[int, int]]:
    """Mentörün kaçınacağı dakika aralıkları."""
    araliklar = []
    for r in gunun_randevulari(tarih):
        try:
            s, d = r["saat"].split(":")[:2]
            bas = int(s) * 60 + int(d)
        except (ValueError, AttributeError):
            continue
        araliklar.append((bas, bas + max(15, r["sure_dk"] or 60)))
    return sorted(araliklar)


def ozet(gun: int = 7) -> str:
    """Plan bağlamına eklenecek randevu özeti."""
    bugun = date.today()
    bitis = (bugun + timedelta(days=gun)).isoformat()
    randevular = store.randevular(bugun.isoformat(), bitis)
    if not randevular:
        return ""
    satirlar = ["TAKVİMDEKİ RANDEVULAR (bu saatlere görev koyma):"]
    for r in randevular[:25]:
        saat = f"{r['saat']}" + (f"–{r['sure_dk']}dk" if r["sure_dk"] else "")
        satirlar.append(f"- {r['tarih']} {saat if r['saat'] else 'tüm gün'}: "
                        f"{r['baslik']}")
    return "\n".join(satirlar)


def denetle() -> list[str]:
    """Mentör döngüsünden: saatte bir takvimi tazele."""
    if not (store.ayar("takvim_ics", "") or "").strip():
        return []
    son = 0.0
    r = store._conn().execute(
        "SELECT MAX(guncellendi) g FROM randevular").fetchone()
    if r and r["g"]:
        son = r["g"]
    import time as _t

    if _t.time() - son < 3600:
        return []
    d = cek()
    return [f"takvim güncellendi: {d['sayi']} randevu"] if d.get("ok") else []
