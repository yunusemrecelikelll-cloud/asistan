# -*- coding: utf-8 -*-
"""NOVA simgelerini üretir — harici bağımlılık yok, saf Python.

Aynı yıldız biçimi hem arayüzdeki SVG'de hem burada tanımlı. SVG vektörel
olduğu için ekranda; PNG'ler ise PWA ve ana ekran kısayolu için gerekiyor
(tarayıcılar manifest simgesi olarak SVG'yi her yerde kabul etmiyor).

Kenar yumuşatma süper örnekleme ile: her piksel 3x3 alt noktadan ortalanıyor.
Küçük boyutlarda tırtıklı kenar, logoyu ucuz gösteriyor.

    python simge_uret.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

KOK = Path(__file__).resolve().parent

ZEMIN = (0x0E, 0x11, 0x16)
PARLAK = (0x9C, 0xC4, 0xFF)
ORTA = (0x6E, 0xA8, 0xFE)
KOYU = (0x3D, 0x7E, 0xE0)
CEKIRDEK = (0xEA, 0xF2, 0xFF)

ORNEK = 3           # piksel başına alt nokta (3x3)


def _karistir(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _yildiz_icinde(x: float, y: float, olcek: float, kalinlik: float) -> bool:
    """Dört uçlu, içbükey kenarlı yıldız.

    |x|^k + |y|^k <= r^k biçiminde bir süper elips; k < 1 olduğunda kenarlar
    içe çöküyor ve yıldız ucu çıkıyor.
    """
    ax, ay = abs(x) / olcek, abs(y) / olcek
    if ax > 1.2 or ay > 1.2:
        return False
    return ax ** kalinlik + ay ** kalinlik <= 1.0


def _renk(px: float, py: float, boyut: int):
    """Merkez (0,0), köşeler ±1 olacak biçimde normalize edilmiş koordinat."""
    x = (px / boyut) * 2 - 1
    y = (py / boyut) * 2 - 1

    # Ana yıldız
    # 0.50 üsteli: uçlar hâlâ sivri ama gövde taşıyor. Daha düşük değerde
    # uçlar saç teline dönüp küçük boyutlarda kayboluyor.
    if _yildiz_icinde(x, y, 0.88, 0.50):
        # Sol üstten sağ alta doğru degrade
        t = (x + y + 2) / 4
        renk = _karistir(PARLAK, KOYU, t)
        # Çekirdek parlaklığı
        d = (x * x + y * y) ** 0.5
        if d < 0.06:
            return CEKIRDEK
        if d < 0.15:
            return _karistir(CEKIRDEK, renk, (d - 0.06) / 0.09)
        return renk

    # İkincil küçük yıldız (sağ üst)
    ix, iy = (x - 0.58) / 0.30, (y + 0.46) / 0.30
    if _yildiz_icinde(ix, iy, 1.0, 0.52):
        return _karistir(ZEMIN, ORTA, 0.55)

    return ZEMIN


def png_yaz(boyut: int, hedef: Path) -> int:
    satirlar = []
    adim = 1.0 / ORNEK
    for py in range(boyut):
        satir = bytearray([0])                      # filtre baytı
        for px in range(boyut):
            toplam = [0, 0, 0]
            for sy in range(ORNEK):
                for sx in range(ORNEK):
                    r = _renk(px + (sx + 0.5) * adim,
                              py + (sy + 0.5) * adim, boyut)
                    toplam[0] += r[0]
                    toplam[1] += r[1]
                    toplam[2] += r[2]
            n = ORNEK * ORNEK
            satir += bytes(v // n for v in toplam)
        satirlar.append(bytes(satir))

    ham = b"".join(satirlar)

    def parca(tip: bytes, veri: bytes) -> bytes:
        return (struct.pack(">I", len(veri)) + tip + veri +
                struct.pack(">I", zlib.crc32(tip + veri) & 0xFFFFFFFF))

    icerik = b"\x89PNG\r\n\x1a\n"
    icerik += parca(b"IHDR", struct.pack(">IIBBBBB", boyut, boyut, 8, 2, 0, 0, 0))
    icerik += parca(b"IDAT", zlib.compress(ham, 9))
    icerik += parca(b"IEND", b"")

    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_bytes(icerik)
    return len(icerik)


def main() -> None:
    for boyut in (192, 512):
        hedef = KOK / f"simge-{boyut}.png"
        n = png_yaz(boyut, hedef)
        print(f"{hedef.name}: {n} bayt")


if __name__ == "__main__":
    main()
