"""Ses klonlama servisinin istemcisi.

Servis ayrı bir süreçte (``backend/klonses/sunucu.py``, Python 3.12 + CUDA
PyTorch) çalışıyor ve XTTS'i bellekte tutuyor. Buradan HTTP ile konuşuyoruz.

Servis kapalıysa hiçbir şey patlamaz: ``kullanilabilir()`` False döner ve
seslendirme eski edge-tts yoluna düşer. Ses motoru bir iyileştirme, ön koşul
değil.
"""

from __future__ import annotations

import time

import httpx

import gunluk
import store

TABAN = "http://127.0.0.1:8771"
_son_kontrol = 0.0
_son_durum: dict | None = None


def durum(zorla: bool = False) -> dict:
    """Servisin durumu. Sonuç kısa süre önbelleklenir — her seslendirmede
    sağlık yoklaması yapmak gereksiz gecikme."""
    global _son_kontrol, _son_durum
    if not zorla and _son_durum and time.time() - _son_kontrol < 15:
        return _son_durum
    try:
        r = httpx.get(f"{TABAN}/saglik", timeout=3)
        r.raise_for_status()
        _son_durum = {"calisiyor": True, **r.json()}
    except httpx.HTTPError:
        _son_durum = {"calisiyor": False, "referanslar": [], "onbellek": []}
    _son_kontrol = time.time()
    return _son_durum


def kullanilabilir() -> bool:
    return bool(durum().get("calisiyor"))


def referanslar() -> list[str]:
    return list(durum().get("referanslar", []))


def seslendir(metin: str, referans: str | None = None,
              hiz: float = 1.0) -> bytes:
    """Tek bir cümleyi klonlanmış sesle seslendir. WAV döner.

    Hata durumunda boş bayt döner; çağıran edge-tts'e düşer.
    """
    metin = (metin or "").strip()
    if not metin:
        return b""
    referans = referans or store.ayar("klon_referans", "ses1")
    try:
        r = httpx.post(f"{TABAN}/seslendir",
                       json={"metin": metin, "referans": referans,
                             "hiz": hiz, "dil": "tr"},
                       timeout=120)
        if r.status_code != 200:
            gunluk.uyari("ses_klon", "seslendirilemedi",
                         f"HTTP {r.status_code}", referans=referans)
            return b""
        return r.content
    except httpx.HTTPError as e:
        gunluk.uyari("ses_klon", "servise_ulasilamadi", str(e))
        return b""


def isit() -> dict:
    """Modeli ve gömüleri önden yükle."""
    try:
        r = httpx.get(f"{TABAN}/isit", timeout=300)
        r.raise_for_status()
        return {"ok": True, **r.json()}
    except httpx.HTTPError as e:
        return {"ok": False, "hata": str(e)}
