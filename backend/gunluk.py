"""İşlem günlüğü — ne olduğunu sonradan okuyabilmek için.

Bu bir geri dönüş noktası değil; hiçbir şeyi geri almaz. Amacı, bir şey ters
gittiğinde "ne oldu, ne zaman oldu, hangi veriyle oldu" sorusunu
cevaplayabilmek.

İki yere birden yazar:

  * **SQLite** (``gunluk`` tablosu) — arayüzden süzülüp aranabilsin diye.
  * **JSONL dosyası** (``data/gunluk/YYYY-MM-DD.jsonl``) — veritabanı bozulsa
    ya da temizlense bile ham kayıt kalsın diye. Satır satır olduğu için
    ``grep`` ile de okunur.

Günlüğün kendisi asla akışı durdurmaz: yazma hatası yutulur, çünkü log
tutamamak yüzünden baskı takibinin çökmesi saçma olur.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import date
from pathlib import Path
from typing import Any

import store

KOK = Path(__file__).resolve().parent.parent / "data" / "gunluk"
_kilit = threading.Lock()

# Dosyaya yazarken bunları maskele — kazara sır sızmasın.
GIZLI_ANAHTARLAR = ("parola", "password", "token", "belirtec", "secret",
                    "api_key", "anahtar", "authorization", "auth")


def _maskele(veri: Any) -> Any:
    """Sözlükteki sır benzeri alanları yıldızla."""
    if isinstance(veri, dict):
        return {k: ("***" if any(g in str(k).lower() for g in GIZLI_ANAHTARLAR)
                    else _maskele(v)) for k, v in veri.items()}
    if isinstance(veri, (list, tuple)):
        return [_maskele(v) for v in veri]
    return veri


def _dosyaya(kayit: dict) -> None:
    try:
        KOK.mkdir(parents=True, exist_ok=True)
        yol = KOK / f"{date.today().isoformat()}.jsonl"
        with _kilit, open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass                                # günlük akışı durdurmasın


def yaz(seviye: str, kaynak: str, olay: str, mesaj: str = "",
        veri: dict | None = None, proje_id: int | None = None,
        gorev_id: int | None = None, sure_ms: int | None = None) -> None:
    """Bir olayı kaydet.

    ``olay`` makine okur kısa etiket (``plan_uretildi``, ``gorev_kacti``),
    ``mesaj`` insan okur açıklama.
    """
    veri = _maskele(veri) if veri else None
    try:
        store.gunluk_yaz(seviye, kaynak, olay, mesaj, veri, proje_id,
                         gorev_id, sure_ms)
    except Exception:                       # veritabanı kilitliyse bile yaz
        pass
    _dosyaya({
        "zaman": time.time(),
        "saat": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seviye": seviye, "kaynak": kaynak, "olay": olay, "mesaj": mesaj,
        "veri": veri, "proje_id": proje_id, "gorev_id": gorev_id,
        "sure_ms": sure_ms,
    })


# İlk üç parametre konumsal-yalnız (``/``): çağıran ``kaynak=...`` ya da
# ``olay=...`` diye ek veri geçtiğinde parametre adıyla çakışmasın. Bu üçü
# günlüğün kendi alanları, gerisi serbest veri.
def bilgi(kaynak: str, olay: str, mesaj: str = "", /, **veri: Any) -> None:
    yaz("bilgi", kaynak, olay, mesaj, veri or None)


def uyari(kaynak: str, olay: str, mesaj: str = "", /, **veri: Any) -> None:
    yaz("uyari", kaynak, olay, mesaj, veri or None)


def hata(kaynak: str, olay: str, mesaj: str = "", /,
         istisna: BaseException | None = None, **veri: Any) -> None:
    d = dict(veri)
    if istisna is not None:
        d["istisna"] = f"{type(istisna).__name__}: {istisna}"
        d["iz"] = "".join(traceback.format_exception(
            type(istisna), istisna, istisna.__traceback__))[-2500:]
    yaz("hata", kaynak, olay, mesaj, d or None)


class olcum:
    """Süre ölçen bağlam yöneticisi.

        with gunluk.olcum("mentor", "plan_uretildi", "haftalık plan"):
            ...

    Blok hata atarsa kayıt ``hata`` seviyesinde düşer ve istisna yeniden
    fırlatılır — günlük hiçbir şeyi yutmaz.
    """

    def __init__(self, kaynak: str, olay: str, mesaj: str = "", /,
                 **veri: Any):
        self.kaynak, self.olay, self.mesaj, self.veri = kaynak, olay, mesaj, veri
        self.baslangic = 0.0

    def __enter__(self) -> "olcum":
        self.baslangic = time.perf_counter()
        return self

    def ekle(self, **veri: Any) -> None:
        """Blok içinde toplanan bilgiyi kayda ekle."""
        self.veri.update(veri)

    def __exit__(self, tur, deger, iz) -> bool:
        sure = int((time.perf_counter() - self.baslangic) * 1000)
        if deger is None:
            yaz("bilgi", self.kaynak, self.olay, self.mesaj,
                self.veri or None, sure_ms=sure)
        else:
            hata(self.kaynak, self.olay, self.mesaj, istisna=deger,
                 **self.veri)
        return False                        # istisnayı yutma


# ── okuma ──────────────────────────────────────────────────────────────────


def oku(**süzgec: Any) -> list[dict]:
    kayitlar = store.gunluk_oku(**süzgec)
    for k in kayitlar:
        if k.get("veri"):
            try:
                k["veri"] = json.loads(k["veri"])
            except json.JSONDecodeError:
                pass
    return kayitlar


def ozet(saat: int = 24) -> dict:
    d = store.gunluk_ozet(saat)
    d["dosyalar"] = sorted(
        (p.name for p in KOK.glob("*.jsonl")), reverse=True)[:14] \
        if KOK.is_dir() else []
    return d


def temizle(gun: int = 60) -> dict:
    """Veritabanındaki eski kayıtları at; JSONL dosyaları kalır."""
    n = store.gunluk_temizle(gun)
    bilgi("gunluk", "temizlendi", f"{n} kayıt silindi", gun=gun)
    return {"silinen": n}
