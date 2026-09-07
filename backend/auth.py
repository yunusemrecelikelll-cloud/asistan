"""Parola koruması — tünel üzerinden dışarı açıldığında gerekli.

Yerel ağdan (127.0.0.1) gelen istekler serbesttir; masaüstünde parola sormak
gereksiz. Tünelden gelen her istek ise geçerli bir belirteç ister.

Parola ilk çalıştırmada rastgele üretilir ve ``data/parola.txt`` dosyasına
yazılır. Belirteç, parolanın tuzlanmış özetidir; parolayı değiştirince eski
belirteçler kendiliğinden geçersiz olur.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path

from fastapi import HTTPException, Request

VERI = Path(__file__).resolve().parent.parent / "data"
PAROLA_DOSYA = VERI / "parola.txt"
TUZ_DOSYA = VERI / "tuz.txt"

# Parola sorulmadan geçilen yollar
SERBEST = {"/api/giris", "/api/giris/durum"}

# Yerel arayüzler — masaüstünde parola sorulmaz
YEREL = {"127.0.0.1", "::1", "localhost"}


def _dosya(yol: Path, uret) -> str:
    VERI.mkdir(parents=True, exist_ok=True)
    if yol.is_file():
        deger = yol.read_text(encoding="utf-8").strip()
        if deger:
            return deger
    deger = uret()
    yol.write_text(deger, encoding="utf-8")
    return deger


def parola() -> str:
    """Mevcut parola; yoksa okunabilir bir tane üretir."""
    return _dosya(PAROLA_DOSYA, lambda: secrets.token_urlsafe(9))


def _tuz() -> str:
    return _dosya(TUZ_DOSYA, lambda: secrets.token_hex(16))


def belirtec() -> str:
    return hashlib.sha256((_tuz() + parola()).encode("utf-8")).hexdigest()


def parola_degistir(yeni: str) -> None:
    yeni = (yeni or "").strip()
    if len(yeni) < 6:
        raise ValueError("parola en az 6 karakter olmalı")
    VERI.mkdir(parents=True, exist_ok=True)
    PAROLA_DOSYA.write_text(yeni, encoding="utf-8")


# Bir vekil/tünel üzerinden geldiğini ele veren başlıklar
_VEKIL_BASLIKLARI = (
    "x-forwarded-for", "x-real-ip", "cf-connecting-ip",
    "cf-ray", "forwarded", "x-forwarded-host", "x-forwarded-proto",
)


def yerel_mi(request: Request) -> bool:
    """İstek gerçekten bu bilgisayardan mı geliyor?

    Tünel (cloudflared) sunucuya 127.0.0.1 üzerinden bağlanır; yalnızca
    ``request.client.host`` bakılırsa tünelden gelen herkes "yerel" sayılır ve
    parola tamamen atlanır. Bu yüzden vekil başlığı taşıyan hiçbir isteği
    yerel kabul etmiyoruz.
    """
    istemci = request.client.host if request.client else ""
    if istemci not in YEREL:
        return False
    return not any(b in request.headers for b in _VEKIL_BASLIKLARI)


def dogrula(request: Request) -> None:
    """Yerel değilse geçerli belirteç şart."""
    if yerel_mi(request):
        return
    yol = request.url.path
    if yol in SERBEST or not yol.startswith("/api/"):
        return
    gelen = (request.headers.get("x-asistan-belirtec")
             or request.query_params.get("belirtec") or "")
    if not hmac.compare_digest(gelen, belirtec()):
        raise HTTPException(401, "parola gerekli")


def belirtec_gecerli(gelen: str) -> bool:
    """WebSocket girişinde kullanılıyor — sabit süreli karşılaştırma."""
    return hmac.compare_digest((gelen or "").strip(), belirtec())


def yerel_mi_ws(ws) -> bool:
    """WebSocket'in yerel olup olmadığı.

    HTTP tarafındaki mantığın aynısı: vekil başlığı taşıyan bağlantı yerel
    sayılmaz, yoksa tünelden bağlanan herkes parolasız girerdi.
    """
    istemci = ws.client.host if ws.client else ""
    if istemci not in YEREL:
        return False
    return not any(b in ws.headers for b in _VEKIL_BASLIKLARI)
