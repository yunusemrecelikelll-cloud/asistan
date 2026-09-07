"""Yedekleme — her şey tek bir SQLite dosyasında, sigortası olsun.

Günde bir kez ``data/yedek/asistan-YYYY-MM-DD-HHMM.db`` yazar ve eskileri
siler. Yedek, dosyayı kopyalayarak değil SQLite'ın kendi ``backup`` API'siyle
alınır: WAL kipinde çalışan bir veritabanını kopyalamak yarım işlem yakalayıp
bozuk yedek üretebilir; backup API tutarlı bir anlık görüntü verir.

Ayrıca ``disa_aktar()`` her tabloyu JSON'a döker — veritabanı sürümü değişse
ya da başka bir yere taşımak istesen bile okunabilir kalsın diye.
"""

from __future__ import annotations

import json

import sqlite3
import time
import zipfile
from datetime import datetime
from pathlib import Path

import gunluk
import store

KOK = Path(__file__).resolve().parent.parent / "data" / "yedek"

# Dökümde atlanacak tablolar — büyük ve yeniden üretilebilir.
DOKUM_HARIC = {"gunluk"}


def _saklama() -> int:
    try:
        return max(1, int(store.ayar("yedek_saklama", "14")))
    except (TypeError, ValueError):
        return 14


def al(etiket: str = "") -> dict:
    """Tutarlı bir yedek al ve eskileri temizle."""
    KOK.mkdir(parents=True, exist_ok=True)
    # Saniye dahil: aynı dakikada iki yedek alınırsa adları da sıraları da
    # karışmasın.
    damga = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    ad = f"asistan-{damga}{('-' + etiket) if etiket else ''}.db"
    hedef = KOK / ad

    # Bağlantıyı açıkça kapatıyoruz: ``with sqlite3.connect(...)`` işlemi
    # tamamlar ama bağlantıyı KAPATMAZ. Windows'ta açık kalan tutamaç
    # yüzünden eski yedekler sonradan silinemiyordu.
    yeni = None
    try:
        yeni = sqlite3.connect(hedef)
        store._conn().backup(yeni)
        yeni.commit()
    except (sqlite3.Error, OSError) as e:
        gunluk.hata("yedek", "alinamadi", str(hedef), istisna=e)
        return {"ok": False, "hata": str(e)}
    finally:
        if yeni is not None:
            yeni.close()

    silinen = _temizle(hedef)
    boyut = hedef.stat().st_size
    gunluk.bilgi("yedek", "alindi", ad, boyut=boyut, silinen=silinen)
    return {"ok": True, "dosya": str(hedef), "ad": ad, "boyut": boyut,
            "silinen": silinen}


def _sirali() -> list:
    """Yeniden eskiye. Ada göre sıralıyoruz: ad zaman damgası taşıyor ve
    dosya sistemi zaman damgaları aynı saniyede eşitlenip sırayı belirsiz
    bırakabiliyor."""
    return sorted(KOK.glob("asistan-*.db"), key=lambda p: p.name, reverse=True)


def _temizle(koru: Path | None = None) -> int:
    """Saklama sayısını aşan en eski yedekleri sil.

    ``koru`` az önce alınan yedektir ve asla silinmez. Ada göre sıralama aynı
    saniyede alınan etiketli/etiketsiz yedeklerde sırayı bozabiliyor; yeni
    yedeğin kendi temizliğine kurban gitmesi bu yüzden mümkün.
    """
    dosyalar = [p for p in _sirali() if koru is None or p != koru]
    if koru is not None:
        dosyalar.insert(0, koru)
    silinen = 0
    for p in dosyalar[_saklama():]:
        try:
            p.unlink()
            silinen += 1
        except OSError:
            continue
    return silinen


def listele() -> list[dict]:
    if not KOK.is_dir():
        return []
    liste = []
    for p in _sirali():
        st = p.stat()
        liste.append({
            "ad": p.name, "boyut": st.st_size, "zaman": st.st_mtime,
            "tarih": datetime.fromtimestamp(st.st_mtime)
                             .strftime("%Y-%m-%d %H:%M"),
        })
    return liste


def _tablolar() -> list[str]:
    return [r[0] for r in store._conn().execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def disa_aktar() -> dict:
    """Tüm tabloları JSON'a dök, zip'le.

    Yedek dosyası SQLite sürümüne bağlı; bu döküm bağlı değil. İkisini birden
    tutuyoruz çünkü geri yükleme kolaylığı ile taşınabilirlik farklı şeyler.
    """
    KOK.mkdir(parents=True, exist_ok=True)
    damga = datetime.now().strftime("%Y-%m-%d-%H%M")
    hedef = KOK / f"asistan-dokum-{damga}.zip"
    c = store._conn()

    try:
        with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED) as z:
            for tablo in _tablolar():
                if tablo in DOKUM_HARIC:
                    continue
                satirlar = [dict(r) for r in c.execute(f"SELECT * FROM {tablo}")]
                z.writestr(f"{tablo}.json",
                           json.dumps(satirlar, ensure_ascii=False, indent=1,
                                      default=str))
            z.writestr("bilgi.json", json.dumps({
                "olusturuldu": datetime.now().isoformat(timespec="seconds"),
                "tablolar": _tablolar(),
            }, ensure_ascii=False, indent=1))
    except (OSError, sqlite3.Error) as e:
        gunluk.hata("yedek", "dokum_hatasi", str(hedef), istisna=e)
        return {"ok": False, "hata": str(e)}

    gunluk.bilgi("yedek", "dokum", hedef.name, boyut=hedef.stat().st_size)
    return {"ok": True, "dosya": str(hedef), "ad": hedef.name,
            "boyut": hedef.stat().st_size}


def geri_yukle(ad: str) -> dict:
    """Bir yedeği geri yükle.

    Mevcut veritabanı önce ``-geri-yukleme-oncesi`` etiketiyle yedeklenir;
    yanlış yedeği seçmek geri dönülemez olmasın.

    Dosyayı kopyalamıyoruz: canlı veritabanının üstüne yazmak Windows'ta açık
    tutamaçlara takılıyor, üstelik geride kalan bir WAL dosyası yeni veriyi
    bozabiliyor. Onun yerine SQLite'ın kendi ``backup`` API'sini ters yönde
    kullanıyoruz — yedek kaynak, canlı veritabanı hedef. İşlem SQLite'ın
    kilitleriyle yürüdüğü için diğer bağlantılar tutarlı kalıyor ve yeni
    veriyi anında görüyor.
    """
    kaynak = KOK / ad
    try:
        if kaynak.resolve().parent != KOK.resolve() or not kaynak.is_file():
            return {"ok": False, "hata": "Yedek bulunamadı."}
    except OSError:
        return {"ok": False, "hata": "Yedek bulunamadı."}

    # Güvenlik yedeği alırken dönüşüm devreye girip geri yükleyeceğimiz
    # dosyayı silebilir. Bu yüzden önce onu koruyoruz.
    onceki = al("geri-yukleme-oncesi")
    if not kaynak.is_file():
        return {"ok": False,
                "hata": "Yedek, güvenlik yedeği alınırken dönüşüme takılıp "
                        "silindi. Saklama sayısını artır."}

    eski = None
    try:
        # Salt okunur URI: dosya yoksa SQLite BOŞ bir veritabanı yaratır ve
        # onu canlıya kopyalamak her şeyi silerdi. mode=ro bunu hataya çevirir.
        eski = sqlite3.connect(f"file:{kaynak.as_posix()}?mode=ro", uri=True)
        tablolar = {r[0] for r in eski.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "projeler" not in tablolar:
            return {"ok": False,
                    "hata": "Bu dosya geçerli bir Asistan yedeği değil."}
        eski.backup(store._conn())
        store._conn().commit()
    except (sqlite3.Error, OSError) as e:
        gunluk.hata("yedek", "geri_yukleme_hatasi", ad, istisna=e)
        return {"ok": False, "hata": str(e)}
    finally:
        if eski is not None:
            eski.close()

    gunluk.uyari("yedek", "geri_yuklendi", ad, onceki_yedek=onceki.get("ad"))
    return {"ok": True, "yuklenen": ad, "onceki_yedek": onceki.get("ad"),
            "not": "Veri değişti. Açık arayüzleri yenile."}


def son_yedek_zamani() -> float:
    liste = listele()
    return liste[0]["zaman"] if liste else 0.0


def denetle() -> list[str]:
    """Mentör döngüsünden: günde bir yedek al."""
    if store.ayar("yedek_acik", "1") != "1":
        return []
    if time.time() - son_yedek_zamani() < 86400:
        return []
    d = al()
    return [f"yedek alındı: {d['ad']}"] if d.get("ok") else []


def durum() -> dict:
    liste = listele()
    return {
        "acik": store.ayar("yedek_acik", "1") == "1",
        "saklama": _saklama(),
        "klasor": str(KOK),
        "sayi": len(liste),
        "son": liste[0] if liste else None,
        "yedekler": liste,
    }
