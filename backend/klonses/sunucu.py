# -*- coding: utf-8 -*-
"""Ses klonlama servisi — XTTS'i bellekte tutar.

Neden ayrı bir süreç:
  * XTTS, PyTorch'un CUDA sürümünü ve Python 3.12'yi istiyor; ana uygulama
    3.13 üzerinde. Ağır bağımlılıklar oraya bulaşmasın.
  * Model yüklemesi 12 saniye sürüyor. Her istekte yeniden yüklemek konuşmayı
    kullanılamaz hâle getirirdi, o yüzden süreç ayakta kalıyor.

Hız için iki şey yapılıyor:
  1. **Konuşmacı gömüsü önbelleği.** XTTS her çağrıda referans sesten
     konuşmacı temsilini yeniden çıkarıyor; bu tek başına saniyeler alıyor.
     Referans başına bir kez hesaplayıp saklıyoruz.
  2. **Cümle cümle üretim.** Uzun metni tek seferde beklemek yerine çağıran
     taraf cümleleri ayrı ayrı istiyor; ilki gelir gelmez çalmaya başlıyor.

Yalnızca 127.0.0.1 dinler; dışarı açılmaz.

    .venv-ses\\Scripts\\python.exe backend\\klonses\\sunucu.py
"""

import io
import json
import os
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")

KOK = Path(__file__).resolve().parent.parent.parent
REFERANS_KLASOR = KOK / "data" / "ses-klon"
ADRES, PORT = "127.0.0.1", 8771
ORNEKLEME = 24000               # XTTS çıkışı

_model = None
_kilit = threading.Lock()
_gomu: dict[str, tuple] = {}    # referans adı -> (gpt_latent, konusmaci)


def model_yukle():
    global _model
    if _model is not None:
        return _model
    with _kilit:
        if _model is not None:
            return _model
        import torch
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
        from TTS.utils.manage import ModelManager

        t = time.perf_counter()
        yonetici = ModelManager()
        yol, _, _ = yonetici.download_model(
            "tts_models/multilingual/multi-dataset/xtts_v2")

        yapilandirma = XttsConfig()
        yapilandirma.load_json(str(Path(yol) / "config.json"))
        m = Xtts.init_from_config(yapilandirma)
        m.load_checkpoint(yapilandirma, checkpoint_dir=yol, eval=True)
        if torch.cuda.is_available():
            m.cuda()
        _model = m
        print(f"[klonses] model yüklendi: {time.perf_counter() - t:.1f} sn",
              flush=True)
        return _model


def gomu_al(referans: str):
    """Konuşmacı gömüsünü önbellekten ver, yoksa hesapla."""
    if referans in _gomu:
        return _gomu[referans]
    # Aynı sesin bütün klipleri: ses1.wav, ses1-2.wav, ses1-3.wav …
    # Tek klip konuşmacının bütün aralığını taşımıyor; birkaç klip verince
    # tını gözle görülür biçimde daha iyi oturuyor.
    yollar = [REFERANS_KLASOR / f"{referans}.wav"]
    yollar += sorted(REFERANS_KLASOR.glob(f"{referans}-[0-9].wav"))
    yollar = [y for y in yollar if y.is_file()]
    if not yollar:
        raise FileNotFoundError(f"referans yok: {referans}")
    m = model_yukle()
    t = time.perf_counter()
    with _kilit:
        gpt, konusmaci = m.get_conditioning_latents(
            audio_path=[str(y) for y in yollar],
            # Daha uzun koşullama penceresi: tınıyı ve konuşma temposunu
            # daha iyi yakalıyor, karşılığında yalnızca bir kerelik maliyet.
            gpt_cond_len=30, gpt_cond_chunk_len=6, max_ref_length=60)
    _gomu[referans] = (gpt, konusmaci)
    print(f"[klonses] '{referans}' gömüsü çıkarıldı ({len(yollar)} klip): "
          f"{time.perf_counter() - t:.1f} sn", flush=True)
    return _gomu[referans]


def _wav_paketle(ses) -> bytes:
    """Model çıkışını (float dizisi) 16 bit mono WAV'a çevir."""
    import numpy as np
    import torch

    if isinstance(ses, torch.Tensor):
        ses = ses.detach().cpu().numpy()
    ses = np.asarray(ses, dtype=np.float32).squeeze()
    # Tepe normalizasyonu: cümleden cümleye seviye oynaması kulakta
    # "yapıştırılmış" duyuluyor. Hepsini aynı tepeye çekiyoruz.
    tepe = float(np.max(np.abs(ses))) if ses.size else 0.0
    if tepe > 0.001:
        ses = ses * (0.94 / tepe)
    pcm = (ses * 32767).astype(np.int16)

    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ORNEKLEME)
        w.writeframes(pcm.tobytes())
    return tampon.getvalue()


def seslendir(metin: str, referans: str, hiz: float = 1.0,
              dil: str = "tr") -> bytes:
    m = model_yukle()
    gpt, konusmaci = gomu_al(referans)
    with _kilit:
        sonuc = m.inference(
            text=metin, language=dil,
            gpt_cond_latent=gpt, speaker_embedding=konusmaci,
            speed=max(0.6, min(1.4, hiz)),
            # Akıcılık ayarları. Yüksek sıcaklık tonlamayı zenginleştiriyor
            # ama sözcük yutmaya başlıyor; 0.65 tutarlı kalırken düz de
            # duyulmuyor.
            # 0.75: tonlama zenginliği ile tutarlılık arasındaki tatlı
            # nokta. 0.65 düz, 0.9 sözcük yutuyor.
            temperature=0.75,
            length_penalty=1.0,
            # 5.0 fazla sertti: tekrar eden hecelerde ses kesiliyordu.
            repetition_penalty=2.5,
            top_k=50,
            top_p=0.87,
            enable_text_splitting=False,   # bölmeyi çağıran yapıyor
        )
    return _wav_paketle(sonuc["wav"])


def referanslar() -> list[str]:
    if not REFERANS_KLASOR.is_dir():
        return []
    # "ses1-2.wav" aynı sesin ikinci klibi, ayrı bir ses değil — listeye
    # girmemeli.
    import re as _re

    return sorted({p.stem for p in REFERANS_KLASOR.glob("*.wav")
                   if not p.stem.startswith(("_", "klon-"))
                   and not _re.search(r"-\d$", p.stem)})


class Islemci(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, bicim, *args):       # sessiz kal
        pass

    def _yanit(self, kod: int, govde: bytes, tur: str) -> None:
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def _json(self, kod: int, veri: dict) -> None:
        self._yanit(kod, json.dumps(veri, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path == "/saglik":
            self._json(200, {"durum": "ok", "model_yuklu": _model is not None,
                             "referanslar": referanslar(),
                             "onbellek": sorted(_gomu)})
        elif self.path == "/isit":
            # Modeli ve gömüleri önden yükle ki ilk konuşma beklemesin.
            model_yukle()
            for r in referanslar():
                try:
                    gomu_al(r)
                except Exception as e:
                    print(f"[klonses] {r}: {e}", flush=True)
            self._json(200, {"durum": "hazır", "onbellek": sorted(_gomu)})
        else:
            self._json(404, {"hata": "yok"})

    def do_POST(self) -> None:
        if self.path != "/seslendir":
            self._json(404, {"hata": "yok"})
            return
        try:
            uzunluk = int(self.headers.get("Content-Length", 0))
            istek = json.loads(self.rfile.read(uzunluk) or b"{}")
            metin = (istek.get("metin") or "").strip()
            if not metin:
                self._json(400, {"hata": "metin boş"})
                return
            t = time.perf_counter()
            veri = seslendir(metin, istek.get("referans") or "ses1",
                             float(istek.get("hiz", 1.0)),
                             istek.get("dil", "tr"))
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(veri)))
            self.send_header("X-Sure-Ms",
                             str(int((time.perf_counter() - t) * 1000)))
            self.end_headers()
            self.wfile.write(veri)
        except FileNotFoundError as e:
            self._json(404, {"hata": str(e)})
        except Exception as e:
            print(f"[klonses] hata: {e}", flush=True)
            self._json(500, {"hata": str(e)})


def main() -> int:
    print(f"[klonses] dinleniyor: {ADRES}:{PORT}", flush=True)
    if "--isit" in sys.argv:
        model_yukle()
        for r in referanslar():
            try:
                gomu_al(r)
            except Exception as e:
                print(f"[klonses] {r}: {e}", flush=True)
    ThreadingHTTPServer((ADRES, PORT), Islemci).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
