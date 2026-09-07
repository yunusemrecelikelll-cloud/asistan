# -*- coding: utf-8 -*-
"""Referans ses dosyalarını klonlamaya uygun hâle getirir.

XTTS'in istediği: tek konuşmacı, gürültüsüz, 10-30 saniye, mono. Uzun bir
kayıttan gelişigüzel bir parça almak yerine **en yüksek enerjili kesintisiz
konuşma aralığını** seçiyoruz — araya giren sessizlikler ve müzik girişleri
klon kalitesini düşürüyor.

Kullanım:
    python referans_hazirla.py "C:\\...\\1.mp3" [ad]
"""

import subprocess
import sys
import wave
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent.parent
KLASOR = KOK / "data" / "ses-klon"
FFMPEG = ("C:/Users/PC/AppData/Local/Microsoft/WinGet/Packages/"
          "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/"
          "ffmpeg-8.1.2-full_build/bin/ffmpeg.exe")

PENCERE_SN = 16.0       # her klibin uzunluğu
KLIP_SAYISI = 3         # kaç ayrı temiz pencere alınsın
ADIM_SN = 1.0           # tarama adımı


def _ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
                   check=True)


def _gecici_wav(kaynak: Path, hedef: Path) -> None:
    """Tarama için 16 kHz mono — enerji ölçmeye bu yeter."""
    _ffmpeg("-i", str(kaynak), "-ac", "1", "-ar", "16000", str(hedef))


def _enerji_profili(yol: Path, adim_sn: float) -> tuple[list[float], int]:
    with wave.open(str(yol), "rb") as w:
        oran = w.getframerate()
        toplam = w.getnframes()
        adim = int(oran * adim_sn)
        profil = []
        for _ in range(toplam // adim):
            ham = w.readframes(adim)
            if len(ham) < 2:
                break
            # 16 bit işaretli örnekler; mutlak ortalama kaba bir şiddet ölçüsü
            toplam_mutlak = 0
            for i in range(0, len(ham) - 1, 2):
                ornek = int.from_bytes(ham[i:i + 2], "little", signed=True)
                toplam_mutlak += ornek if ornek >= 0 else -ornek
            profil.append(toplam_mutlak / (len(ham) / 2))
        return profil, oran


def en_iyi_aralik(profil: list[float], pencere_adim: int) -> int:
    """Kayan pencereyle en yüksek ortalama enerjili başlangıcı bul."""
    if len(profil) <= pencere_adim:
        return 0
    toplam = sum(profil[:pencere_adim])
    en_iyi_toplam, en_iyi_bas = toplam, 0
    for i in range(1, len(profil) - pencere_adim + 1):
        toplam += profil[i + pencere_adim - 1] - profil[i - 1]
        if toplam > en_iyi_toplam:
            en_iyi_toplam, en_iyi_bas = toplam, i
    return en_iyi_bas


def ust_araliklar(profil: list[float], pencere_adim: int,
                  kac: int = 3) -> list[int]:
    """En yüksek enerjili, ÇAKIŞMAYAN N pencereyi bul.

    XTTS tek klip yerine birkaç klip verilince tınıyı belirgin biçimde daha
    iyi yakalıyor — tek pencerede konuşmacının bütün ses aralığı olmuyor.
    """
    secilen: list[int] = []
    kalan = list(profil)
    for _ in range(kac):
        if len(kalan) <= pencere_adim:
            break
        bas = en_iyi_aralik(kalan, pencere_adim)
        if kalan[bas] <= 0:
            break
        secilen.append(bas)
        # Seçilen bölgeyi sıfırla ki bir sonraki tur başka yeri bulsun
        for i in range(max(0, bas - pencere_adim // 2),
                       min(len(kalan), bas + pencere_adim + pencere_adim // 2)):
            kalan[i] = 0.0
    return sorted(secilen)


def hazirla(kaynak: Path, ad: str) -> dict:
    KLASOR.mkdir(parents=True, exist_ok=True)
    gecici = KLASOR / f"_tarama-{ad}.wav"
    hedef = KLASOR / f"{ad}.wav"

    _gecici_wav(kaynak, gecici)
    profil, _ = _enerji_profili(gecici, ADIM_SN)
    gecici.unlink(missing_ok=True)

    if not profil:
        return {"ok": False, "hata": "Ses okunamadı."}

    toplam_sn = len(profil) * ADIM_SN
    pencere = min(int(PENCERE_SN / ADIM_SN), len(profil))
    baslar = ust_araliklar(profil, pencere, KLIP_SAYISI) or [0]

    # highpass/lowpass: telefon bandı dışındaki uğultu ve tizi at.
    # dynaudnorm: seviyeyi dengele; XTTS sabit seviyeli referansı sever.
    # loudnorm yerine dynaudnorm: kısa kliplerde loudnorm aşırı pompalıyor.
    SUZGEC = "highpass=f=70,lowpass=f=9000,dynaudnorm=p=0.9:s=5"

    dosyalar = []
    for i, b in enumerate(baslar):
        bas = b * ADIM_SN
        sure = min(PENCERE_SN, toplam_sn - bas)
        if sure < 4:
            continue
        cikti = KLASOR / (f"{ad}.wav" if i == 0 else f"{ad}-{i + 1}.wav")
        _ffmpeg("-ss", str(bas), "-t", str(sure), "-i", str(kaynak),
                "-ac", "1", "-ar", "22050", "-af", SUZGEC, str(cikti))
        dosyalar.append({"dosya": str(cikti), "baslangic_sn": round(bas, 1),
                         "sure_sn": round(sure, 1)})

    return {"ok": True, "ad": ad, "kaynak_sn": round(toplam_sn, 1),
            "klipler": dosyalar}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    kaynak = Path(sys.argv[1])
    ad = sys.argv[2] if len(sys.argv) > 2 else kaynak.stem
    print(hazirla(kaynak, ad))
