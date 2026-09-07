"""3D baskı takibi — dört yazıcılı atölye için.

Yazıcı projeye değil atölyeye ait: bir proje hangisi boşsa oraya baskı verir,
mentör de plan yaparken "o saatte hangi yazıcı boş" sorusunu yanıtlayabilir.

Takip iki katmanlı:

  1. **Zamanlayıcı (elle)** — her yazıcıda çalışır, hiçbir ön koşulu yok.
     Baskıyı başlatırken tahmini süreyi verirsin; mentör bitiş anında dürtüp
     sıradaki adımı (yataktan alma, rötuş, montaj, fotoğraf) takvime yazar.

  2. **Ağdan okuma (otomatik)** — yazıcı yerel ağda görünüyorsa ilerleme
     tahmin yerine cihazdan okunur. Kobra S1 MQTT konuşuyor (Chitu SDCP
     değil), o yüzden keşif hem SDCP yayınını hem MQTT portlarını deniyor.

Tasarım kasıtlı olarak "ağ olmasa da çalışır": baskının bitiş anı kaçarsa iş
de kaçar, bu yüzden zamanlayıcı her hâlükârda kurulur.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import socket
import time

import gunluk
import mentor
import store

SDCP_PORT = 3000
SDCP_SORGU = b"M99999"

# Yazıcıların konuştuğu tipik portlar. Kobra S1 MQTT (9883/8883), Chitu
# kartlılar 3000/3030.
YAZICI_PORTLARI = {9883: "mqtt-tls", 8883: "mqtt-tls", 1883: "mqtt",
                   3000: "sdcp", 3030: "sdcp-ws"}

# Baskıdan sonra gelen tipik adımlar. Baskı bitince ilki takvime yazılır.
SONRAKI_ADIMLAR = [
    ("Baskıyı yataktan al ve destekleri temizle", 30),
    ("Rötuş ve zımpara", 45),
    ("Montaj", 45),
    ("Ürün fotoğrafı çek", 60),
]


# ── ağ keşfi ───────────────────────────────────────────────────────────────


def _yerel_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def _sdcp_ara(bekle: float = 3.0) -> list[dict]:
    """Chitu kartlı yazıcılar UDP yayınına kendini tanıtır."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.5)
        s.bind(("", 0))
    except OSError:
        return []

    hedefler = {"255.255.255.255"}
    ip = _yerel_ip()
    if ip:
        hedefler.add(".".join(ip.split(".")[:3]) + ".255")
    for h in hedefler:
        try:
            s.sendto(SDCP_SORGU, (h, SDCP_PORT))
        except OSError:
            continue

    bulunan, gorulen = [], set()
    bitis = time.time() + bekle
    while time.time() < bitis:
        try:
            veri, kaynak = s.recvfrom(8192)
        except socket.timeout:
            continue
        except OSError:
            break
        if kaynak[0] in gorulen:
            continue
        gorulen.add(kaynak[0])
        try:
            d = json.loads(veri.decode("utf-8", "replace")).get("Data", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        bulunan.append({
            "ip": kaynak[0], "tur": "sdcp",
            "model": d.get("MachineName") or d.get("Model") or "",
            "ad": d.get("Name") or d.get("MachineName") or "yazıcı",
        })
    s.close()
    return bulunan


def _port_acik(ip: str, port: int, sure: float = 0.8) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(sure)
            return s.connect_ex((ip, port)) == 0
    except OSError:
        return False


def _mqtt_ara() -> list[dict]:
    """Alt ağı yazıcı portları için tara. ARP'ye güvenmiyoruz — yazıcı
    uykudan yeni uyanmış olabilir."""
    ip = _yerel_ip()
    if not ip:
        return []
    onek = ".".join(ip.split(".")[:3]) + "."
    isler = [(f"{onek}{n}", p) for n in range(1, 255) for p in YAZICI_PORTLARI]

    bulunan: dict[str, list[int]] = {}
    with cf.ThreadPoolExecutor(max_workers=160) as havuz:
        sonuc = {havuz.submit(_port_acik, h, p): (h, p) for h, p in isler}
        for f in cf.as_completed(sonuc):
            h, p = sonuc[f]
            try:
                if f.result():
                    bulunan.setdefault(h, []).append(p)
            except Exception:
                continue

    return [{"ip": h, "tur": "mqtt", "model": "",
             "ad": f"yazıcı? {h}",
             "portlar": [f"{p} ({YAZICI_PORTLARI[p]})" for p in sorted(ps)]}
            for h, ps in bulunan.items()]


def yazici_ara(derin: bool = True) -> list[dict]:
    """Ağdaki olası yazıcıları bul.

    Boş liste "yazıcı yok" demek değildir — cihaz kapalıysa ya da yalnızca
    Anycubic bulutuna bağlıysa yerel ağda hiç görünmez.
    """
    bulunan = _sdcp_ara()
    varolan = {b["ip"] for b in bulunan}
    if derin:
        bulunan += [m for m in _mqtt_ara() if m["ip"] not in varolan]
    return bulunan


# ── baskı yaşam döngüsü ────────────────────────────────────────────────────


def baski_basla(yazici_id: int, ad: str, tahmini_dk: int,
                proje_id: int | None = None) -> dict:
    y = store.yazici(yazici_id)
    if not y:
        return {"ok": False, "hata": "Yazıcı bulunamadı."}

    mevcut = [b for b in store.aktif_baskilar() if b["yazici_id"] == yazici_id]
    if mevcut:
        return {"ok": False,
                "hata": f"{y['ad']} zaten “{mevcut[0]['ad']}” baskısında. "
                        "Önce onu bitir ya da iptal et."}

    bid = store.baski_ekle(yazici_id, ad.strip() or "baskı", tahmini_dk,
                           proje_id)
    store.yazici_alan_yaz(yazici_id, durum="basiliyor")
    gunluk.bilgi("baski", "baski_basladi", f"{y['ad']}: {ad}",
                 baski_id=bid, yazici_id=yazici_id, proje_id=proje_id,
                 tahmini_dk=tahmini_dk, filament=y.get("filament"))
    bitis = time.localtime(time.time() + max(1, int(tahmini_dk)) * 60)
    store.bildirim_ekle(
        "Baskı başladı",
        f"{y['ad']}: “{ad}”. Tahmini bitiş {time.strftime('%H:%M', bitis)}. "
        "Bitince haber vereceğim.",
        tur="bilgi", proje_id=proje_id)
    return {"ok": True, "baski_id": bid,
            "bitis": time.strftime("%Y-%m-%d %H:%M", bitis)}


def baski_durum(bid: int) -> dict:
    b = store.baski(bid)
    if not b:
        return {"var": False}
    if b["durum"] != "basiliyor":
        return {"var": True, "durum": b["durum"], "bitti": True}

    gecen_dk = (time.time() - b["baslangic"]) / 60
    kalan_dk = max(0.0, b["tahmini_dk"] - gecen_dk)
    return {
        "var": True, "durum": "basiliyor", "ad": b["ad"],
        "yazici": b["yazici_ad"], "proje": b["proje_ad"],
        "gecen_dk": round(gecen_dk), "kalan_dk": round(kalan_dk),
        "yuzde": min(100, round(100 * gecen_dk / b["tahmini_dk"])),
        "bitti": kalan_dk <= 0, "kaynak": "sure",
    }


def _sonraki_adimi_yaz(b: dict) -> int | None:
    baslik, sure = SONRAKI_ADIMLAR[0]
    yer = mentor.ilk_uygun_gun(sure, azami_gun=3)
    if not yer:
        return None
    gun, saat = yer
    return store.gorev_ekle(
        baslik=f"{baslik} — {b['ad']}",
        tarih=gun, saat=saat, sure_dk=sure,
        proje_id=b["proje_id"], oncelik=1, zorunlu=True, kaynak="ai",
        ayrinti=f"{b.get('yazici_ad') or 'Yazıcı'} üzerindeki baskı bitti, "
                "parça yatakta bekliyor.")


def baski_bitir(bid: int, durum: str = "bitti",
                sonraki_adim: bool = True) -> dict:
    b = store.baski(bid)
    if not b:
        return {"ok": False, "hata": "Baskı kaydı yok."}
    if b["durum"] != "basiliyor":
        return {"ok": False, "hata": "Bu baskı zaten kapanmış."}

    gorev_id = _sonraki_adimi_yaz(b) if (sonraki_adim and durum == "bitti") else None
    store.baski_bitir_kayit(bid, durum, gorev_id)

    # Ömür boyu sayaçlar: gerçekte ne kadar çalıştıysa o kadar. İptal edilen
    # baskı da yazıcıyı yormuştur, o yüzden süre yine sayılır.
    calisan_dk = round((time.time() - b["baslangic"]) / 60)
    store.yazici_sayac_ekle(b["yazici_id"], calisan_dk)
    store.yazici_alan_yaz(b["yazici_id"], durum="bos")
    gunluk.bilgi("baski", "baski_kapandi", f"{b['yazici_ad']}: {b['ad']}",
                 baski_id=bid, yazici_id=b["yazici_id"], sonuc=durum,
                 calisan_dk=calisan_dk, gorev_id=gorev_id)
    return {"ok": True, "gorev_id": gorev_id, "calisan_dk": calisan_dk}


def bos_yazicilar() -> list[dict]:
    return [y for y in store.yazicilar() if not y["aktif_baski"]]


def denetle() -> list[str]:
    """Mentör döngüsünden çağrılır: süresi dolan baskıları yakala."""
    yapilan = []
    for b in store.aktif_baskilar():
        if b["bildirildi"]:
            continue
        d = baski_durum(b["id"])
        if not d.get("bitti"):
            continue

        sonuc = baski_bitir(b["id"])
        g = store.gorev(sonuc["gorev_id"]) if sonuc.get("gorev_id") else None
        store.bildirim_ekle(
            "Baskı bitti",
            f"{b['yazici_ad']}: “{b['ad']}” tamamlandı." + (
                f" Sıradaki adımı {g['tarih']} {g['saat']}'e yazdım: "
                f"{g['baslik']}." if g else " Sıradaki adımı sen belirle."),
            tur="gorev", proje_id=b["proje_id"],
            gorev_id=sonuc.get("gorev_id"))
        yapilan.append(f"baskı bitti: {b['yazici_ad']} / {b['ad']}")
    return yapilan


def atolye_ozeti() -> str:
    """Mentörün plan yaparken göreceği atölye durumu."""
    yazicilar = store.yazicilar()
    if not yazicilar:
        return ""
    satirlar = ["ATÖLYE (3D yazıcılar):"]
    for y in yazicilar:
        b = y["aktif_baski"]
        fil = f", {y['filament']}" if y.get("filament") else ""
        if b:
            kalan = max(0, round(b["tahmini_dk"]
                                 - (time.time() - b["baslangic"]) / 60))
            satirlar.append(f"- {y['ad']} ({y['model']}{fil}): “{b['ad']}” "
                            f"baskısında, ~{kalan} dk kaldı")
        else:
            satirlar.append(f"- {y['ad']} ({y['model']}{fil}): boş")
    return "\n".join(satirlar)


# ── maliyet ve kâr ─────────────────────────────────────────────────────────


def _sayi_ayar(anahtar: str, varsayilan: float) -> float:
    try:
        return float(store.ayar(anahtar, str(varsayilan)) or varsayilan)
    except (TypeError, ValueError):
        return varsayilan


def maliyet_hesapla(gram: float, sure_dk: float) -> dict:
    """Bir baskının gerçek maliyeti: filament + elektrik + (varsa) işçilik.

    Yazıcı amortismanını katmıyoruz — dürüst bir rakam için makine ömrü ve
    bakım geçmişi gerekir, elimizde yok. Uydurma bir kalem eklemektense
    eksik bırakmak daha doğru.
    """
    kg_fiyat = _sayi_ayar("filament_kg_fiyat", 600)
    kwh_fiyat = _sayi_ayar("elektrik_kwh_fiyat", 3.5)
    watt = _sayi_ayar("yazici_watt", 150)
    iscilik = _sayi_ayar("iscilik_saat_fiyat", 0)

    saat = max(0.0, sure_dk) / 60
    filament = (max(0.0, gram) / 1000) * kg_fiyat
    elektrik = saat * (watt / 1000) * kwh_fiyat
    emek = saat * iscilik
    return {
        "filament": round(filament, 2),
        "elektrik": round(elektrik, 2),
        "iscilik": round(emek, 2),
        "toplam": round(filament + elektrik + emek, 2),
        "gram": gram, "sure_dk": round(sure_dk),
    }


def maliyet_yaz(bid: int, gram: float | None = None,
                satis_fiyati: float | None = None,
                adet: int | None = None) -> dict:
    """Baskıya gram/satış bilgisi gir, maliyeti yeniden hesapla."""
    b = store.baski(bid)
    if not b:
        return {"ok": False, "hata": "Baskı kaydı yok."}

    g = gram if gram is not None else (b["gram"] or 0)
    sure = ((b["bitis"] or time.time()) - b["baslangic"]) / 60
    h = maliyet_hesapla(g, sure)
    store.baski_maliyet_yaz(bid, gram=g, maliyet=h["toplam"],
                            satis_fiyati=satis_fiyati, adet=adet)

    yeni = store.baski(bid)
    kar = ((yeni["satis_fiyati"] or 0) - h["toplam"]) if yeni["satis_fiyati"] else None
    gunluk.bilgi("baski", "maliyet_hesaplandi", f"{b['ad']}: {h['toplam']} TL",
                 baski_id=bid, **h)
    return {"ok": True, "hesap": h, "baski": yeni, "kar": round(kar, 2)
            if kar is not None else None}


def kar_paneli(gun: int = 30) -> dict:
    ozet = store.baski_kar_ozeti(time.time() - gun * 86400)
    ozet["gun"] = gun
    ozet["birim_maliyet"] = (round(ozet["maliyet"] / ozet["adet"], 2)
                             if ozet["adet"] else None)
    ozet["ayarlar"] = {
        "filament_kg_fiyat": _sayi_ayar("filament_kg_fiyat", 600),
        "elektrik_kwh_fiyat": _sayi_ayar("elektrik_kwh_fiyat", 3.5),
        "yazici_watt": _sayi_ayar("yazici_watt", 150),
        "iscilik_saat_fiyat": _sayi_ayar("iscilik_saat_fiyat", 0),
    }
    ozet["baskilar"] = [
        {**b, "kar": (round((b["satis_fiyati"] or 0) - (b["maliyet"] or 0), 2)
                      if b["satis_fiyati"] else None)}
        for b in store.baski_gecmisi(20)
    ]
    return ozet
