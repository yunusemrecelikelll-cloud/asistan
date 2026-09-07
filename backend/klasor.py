"""Masaüstündeki "3d Projeler" klasörünü izler ve düzenler.

Yapı:

    Masaüstü/3d Projeler/
        Baskıya Verilecekler/     ← köke attığın her dosya buraya iner
        Baskısı Bitenler/         ← "bitti" dediğinde buraya taşınır

Klasörün köküne bir dosya bıraktığında sıradaki taramada "Baskıya
Verilecekler"e taşınır ve kayda geçer. "Bitti" dediğinde "Baskısı
Bitenler"e taşınır.

Kopyalanmakta olan dosyaya dokunulmaz: boyutu hâlâ değişiyorsa ya da dosya
kilitliyse o tur atlanır, bir sonraki turda tekrar denenir. Yarım kopyalanmış
bir STL'i taşımak sessizce bozuk dosya bırakır.

Elle yapılan taşımalar da algılanır — dosyayı kendin "Baskısı Bitenler"e
sürüklersen kayıt da güncellenir.
"""

from __future__ import annotations

import os
import shutil
import time
import unicodedata
from pathlib import Path

import gunluk
import store

MASAUSTU = Path(os.path.expanduser("~")) / "Desktop"
KOK = MASAUSTU / "3d Projeler"
BEKLEYEN = KOK / "Baskıya Verilecekler"
BITEN = KOK / "Baskısı Bitenler"

# 3D iş akışında anlamlı uzantılar. Diğer dosyalar da kaydedilir ama
# "model" sayılmaz.
MODEL_UZANTILARI = {
    ".stl", ".3mf", ".obj", ".step", ".stp", ".f3d", ".scad", ".ply",
    ".gcode", ".gco", ".g", ".ctb", ".pwmx", ".pwma", ".pm3", ".goo",
}

OKUBENI = """3d Projeler
===========

Bu klasörü Asistan izliyor.

  * Buraya (bu kökün içine) attığın her dosya otomatik olarak
    "Baskıya Verilecekler" klasörüne taşınır ve takibe alınır.

  * Bir işi bitirdiğinde Asistan'a "<dosya adı> bitti" de; dosya
    "Baskısı Bitenler" klasörüne taşınır.

  * Dosyaları elle de taşıyabilirsin, Asistan bunu fark eder.

Bu dosyayı silebilirsin, takip yine çalışır.
"""


def _ad_sadelestir(s: str) -> str:
    """Türkçe karakterleri ve noktalamayı düşürerek eşleştirmeyi kolaylaştır."""
    s = unicodedata.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    cevrim = str.maketrans("ıİğĞüÜşŞöÖçÇ", "iigguussoocc")
    s = s.translate(cevrim)
    return "".join(c if c.isalnum() else " " for c in s).strip()


def kur() -> dict:
    """Klasörleri oluştur. Zaten varsa dokunma."""
    olusan = []
    for k in (KOK, BEKLEYEN, BITEN):
        if not k.exists():
            k.mkdir(parents=True, exist_ok=True)
            olusan.append(str(k))
    okubeni = KOK / "OKUBENI.txt"
    if not okubeni.exists():
        try:
            okubeni.write_text(OKUBENI, encoding="utf-8")
        except OSError:
            pass
    if olusan:
        gunluk.bilgi("klasor", "olusturuldu", "3d Projeler kuruldu",
                     klasorler=olusan)
    return {"kok": str(KOK), "olusan": olusan}


def _yazma_bitti_mi(yol: Path, bekleme: float = 1.5) -> bool:
    """Dosya hâlâ kopyalanıyor mu? Boyutu kısa aralıkla iki kez ölç."""
    try:
        ilk = yol.stat().st_size
        time.sleep(bekleme)
        return yol.stat().st_size == ilk
    except OSError:
        return False


def _benzersiz_hedef(klasor: Path, ad: str) -> Path:
    hedef = klasor / ad
    if not hedef.exists():
        return hedef
    govde, uzanti = os.path.splitext(ad)
    for n in range(2, 500):
        aday = klasor / f"{govde} ({n}){uzanti}"
        if not aday.exists():
            return aday
    return klasor / f"{govde} ({int(time.time())}){uzanti}"


def _kaydet(yol: Path, durum: str) -> int:
    try:
        boyut = yol.stat().st_size
    except OSError:
        boyut = None
    return store.dosya_kaydet(yol.name, str(yol), boyut, durum)


def tara() -> list[str]:
    """Bir tur: kökteki yeni dosyaları taşı, elle taşınanları eşitle."""
    if not KOK.is_dir():
        return []

    yapilan: list[str] = []

    # 1) Kökteki yeni dosyalar → Baskıya Verilecekler
    try:
        girdiler = list(KOK.iterdir())
    except OSError as e:
        gunluk.hata("klasor", "kok_okunamadi", str(KOK), istisna=e)
        return []

    for p in girdiler:
        if p.is_dir() or p.name == "OKUBENI.txt" or p.name.startswith("~$"):
            continue
        if not _yazma_bitti_mi(p):
            continue                        # hâlâ kopyalanıyor, sonraki turda
        hedef = _benzersiz_hedef(BEKLEYEN, p.name)
        try:
            shutil.move(str(p), str(hedef))
        except (OSError, shutil.Error) as e:
            gunluk.uyari("klasor", "tasinamadi", p.name, hata=str(e))
            continue
        did = _kaydet(hedef, "bekliyor")
        model = hedef.suffix.lower() in MODEL_UZANTILARI
        store.bildirim_ekle(
            "Yeni baskı dosyası",
            f"“{hedef.name}” Baskıya Verilecekler'e alındı."
            + ("" if model else " (3D model dosyası değil gibi duruyor.)"),
            tur="bilgi")
        gunluk.bilgi("klasor", "dosya_alindi", hedef.name,
                     dosya_id=did, model=model)
        yapilan.append(f"alındı: {hedef.name}")

    # 2) Diskteki gerçek durumla kayıtları eşitle
    for kayit in store.dosyalar():
        yol = Path(kayit["yol"])
        if yol.exists():
            continue
        # Dosya yerinde değil: elle taşınmış ya da silinmiş olabilir.
        yeni = None
        for klasor, durum in ((BITEN, "bitti"), (BEKLEYEN, "bekliyor")):
            aday = klasor / kayit["ad"]
            if aday.exists():
                yeni = (aday, durum)
                break
        if yeni:
            if kayit["durum"] != yeni[1] or kayit["yol"] != str(yeni[0]):
                store.dosya_guncelle(kayit["id"], yol=str(yeni[0]),
                                     durum=yeni[1])
                gunluk.bilgi("klasor", "elle_tasindi", kayit["ad"],
                             dosya_id=kayit["id"], durum=yeni[1])
                yapilan.append(f"elle taşındı: {kayit['ad']} → {yeni[1]}")
        else:
            store.dosya_sil(kayit["id"])
            gunluk.uyari("klasor", "dosya_kayboldu", kayit["ad"],
                         dosya_id=kayit["id"])
            yapilan.append(f"kayboldu: {kayit['ad']}")

    # 3) Elle "Baskısı Bitenler"e atılmış, hiç kaydı olmayan dosyalar
    for klasor, durum in ((BEKLEYEN, "bekliyor"), (BITEN, "bitti")):
        if not klasor.is_dir():
            continue
        try:
            for p in klasor.iterdir():
                if p.is_dir() or store.dosya_yol_ile(str(p)):
                    continue
                _kaydet(p, durum)
                yapilan.append(f"kayda alındı: {p.name}")
        except OSError:
            continue

    return yapilan


# ── durum değiştirme ───────────────────────────────────────────────────────


def _tasi(kayit: dict, hedef_klasor: Path, durum: str) -> dict:
    kaynak = Path(kayit["yol"])
    if not kaynak.exists():
        store.dosya_guncelle(kayit["id"], durum=durum)
        return {"ok": True, "uyari": "Dosya diskte bulunamadı, "
                                     "yalnızca kayıt güncellendi."}
    hedef = _benzersiz_hedef(hedef_klasor, kaynak.name)
    try:
        shutil.move(str(kaynak), str(hedef))
    except (OSError, shutil.Error) as e:
        gunluk.hata("klasor", "tasima_hatasi", kayit["ad"], istisna=e)
        return {"ok": False, "hata": f"Taşınamadı: {e}"}
    store.dosya_guncelle(kayit["id"], yol=str(hedef), ad=hedef.name,
                         durum=durum)
    gunluk.bilgi("klasor", "durum_degisti", hedef.name,
                 dosya_id=kayit["id"], durum=durum)
    return {"ok": True, "yol": str(hedef)}


def bitti(dosya_id: int) -> dict:
    kayit = store.dosya(dosya_id)
    if not kayit:
        return {"ok": False, "hata": "Dosya kaydı yok."}
    if kayit["durum"] == "bitti":
        return {"ok": False, "hata": "Bu dosya zaten bitmiş."}
    sonuc = _tasi(kayit, BITEN, "bitti")
    if sonuc.get("ok"):
        store.bildirim_ekle(
            "Baskı tamamlandı",
            f"“{kayit['ad']}” Baskısı Bitenler'e taşındı.", tur="kutlama")
    return {**sonuc, "dosya": store.dosya(dosya_id)}


def geri_al(dosya_id: int) -> dict:
    """Yanlışlıkla bitti denen dosyayı geri getir."""
    kayit = store.dosya(dosya_id)
    if not kayit:
        return {"ok": False, "hata": "Dosya kaydı yok."}
    return {**_tasi(kayit, BEKLEYEN, "bekliyor"),
            "dosya": store.dosya(dosya_id)}


def ada_gore_bul(metin: str) -> list[dict]:
    """“anahtarlık bitti” gibi bir cümleden dosyayı bul.

    Konuşma tanıma uzantıyı ve noktalamayı düşürdüğü için karşılaştırma
    sadeleştirilmiş adlar üzerinden yapılıyor.
    """
    aranan = _ad_sadelestir(metin)
    if not aranan:
        return []
    kelimeler = [k for k in aranan.split() if len(k) > 2]
    eslesen = []
    for d in store.dosyalar(durum="bekliyor"):
        ad = _ad_sadelestir(Path(d["ad"]).stem)
        if not ad:
            continue
        if ad in aranan or aranan in ad:
            eslesen.append((100, d))
            continue
        ortak = sum(1 for k in kelimeler if k in ad)
        if ortak:
            eslesen.append((ortak, d))
    eslesen.sort(key=lambda x: -x[0])
    return [d for _, d in eslesen]


def panel() -> dict:
    bekleyen = store.dosyalar(durum="bekliyor")
    biten = store.dosyalar(durum="bitti")
    return {
        "kok": str(KOK),
        "var_mi": KOK.is_dir(),
        "bekleyen": bekleyen,
        "biten": biten[:40],
        "sayilar": {"bekleyen": len(bekleyen), "biten": len(biten)},
    }
