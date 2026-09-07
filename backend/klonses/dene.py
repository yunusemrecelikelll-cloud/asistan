# -*- coding: utf-8 -*-
"""XTTS ile ilk klonlama denemesi — model iner, hız ölçülür.

Bu dosya ayrı bir sanal ortamda (.venv-ses) çalışır: XTTS, PyTorch'un CUDA
sürümünü ve Python 3.12'yi istiyor; ana uygulama 3.13 üzerinde ve o ağır
bağımlılıkları taşımasın diye ayrıldı.
"""

import os
import sys
import time
from pathlib import Path

# XTTS lisansı (CPML, ticari olmayan kullanım) için onay.
os.environ.setdefault("COQUI_TOS_AGREED", "1")

KOK = Path(__file__).resolve().parent.parent.parent
REFERANS = KOK / "data" / "ses-klon" / "referans.wav"
CIKTI = KOK / "data" / "ses-klon"

METINLER = [
    "Bugün üç işten sadece birini bitirdin. Anahtarlık tasarımı yine kaldı.",
    "Bak, yarın sabah dokuzda ilk iş o olacak. Başka hiçbir şeye dokunmadan.",
]


def main() -> int:
    if not REFERANS.is_file():
        print(f"Referans yok: {REFERANS}")
        return 1

    import torch
    from TTS.api import TTS

    aygit = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"aygıt: {aygit}")

    t = time.perf_counter()
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(aygit)
    print(f"model yüklendi: {time.perf_counter() - t:.1f} sn")

    for i, metin in enumerate(METINLER, 1):
        hedef = CIKTI / f"klon-{i}.wav"
        t = time.perf_counter()
        tts.tts_to_file(text=metin, speaker_wav=str(REFERANS),
                        language="tr", file_path=str(hedef))
        sure = time.perf_counter() - t
        boyut = hedef.stat().st_size
        # 24 kHz, 16 bit, mono varsayımıyla kaba süre
        ses_sn = boyut / (24000 * 2)
        print(f"{i}. {sure:5.2f} sn üretim | ~{ses_sn:4.1f} sn ses "
              f"| {sure / max(ses_sn, 0.1):.2f}x gerçek zaman | {hedef.name}")

    print(f"\nÇıktılar: {CIKTI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
