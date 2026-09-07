"""Ses — konuşma tanıma (yerel Whisper) ve seslendirme (edge-tts).

Dinleme tamamen bu makinede yapılır; ses kaydı hiçbir yere gönderilmez.
Seslendirme Microsoft'un ücretsiz neural Türkçe sesini kullanır, bunun için
yalnızca yanıt metni dışarı gider.
"""

from __future__ import annotations

import asyncio
import glob
import os
import re
import tempfile
import threading
from pathlib import Path

import store

# ── CUDA kitaplıklarını göster ─────────────────────────────────────────────
# ctranslate2 cublas/cudnn DLL'lerini PATH üzerinden arar; pip ile gelen
# nvidia paketleri PATH'te olmadığı için elle ekliyoruz.
def _cuda_yolu_ekle() -> None:
    kok = Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages" / "nvidia"
    if not kok.is_dir():
        return
    for d in glob.glob(str(kok / "*" / "bin")):
        d = os.path.abspath(d)
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass


_cuda_yolu_ekle()

_model = None
_model_adi = None
_model_kilit = threading.Lock()


def _cihaz_bilgisi(model: str, cihaz: str, tip: str) -> None:
    """Hangi cihaza yüklendiğini kayda geç.

    Kart doluysa faster-whisper sessizce CPU'ya düşüyor ve tanıma 0,4
    saniyeden 10 saniyeye çıkıyor — sesli turun tamamını yiyor. Bu yüzden
    cihaz seçimi göz önünde olmalı.
    """
    import gunluk
    gunluk.bilgi("ses", "stt_cihaz", f"Whisper '{model}' → {cihaz}",
                 cihaz=cihaz, tip=tip)


def _whisper():
    """Modeli tembel yükle; GPU denenir, olmazsa CPU'ya düşülür."""
    global _model, _model_adi
    istenen = store.ayar("stt_modeli", "medium")
    with _model_kilit:
        if _model is not None and _model_adi == istenen:
            return _model
        from faster_whisper import WhisperModel

        # Kart 8 GB ve üstünde üç model birden duruyor (Ollama, XTTS,
        # Whisper). Sıkışınca tanıma saniyelere çıkıyor, bu yüzden hangi
        # kesinlikle yükleneceği ayarlanabilir: int8_float16 belleği
        # yarıya indiriyor.
        tercih = store.ayar("stt_kesinlik", "float16")
        for cihaz, tip in ((("cuda", tercih), ("cuda", "float16"),
                            ("cpu", "int8"))):
            try:
                _model = WhisperModel(istenen, device=cihaz, compute_type=tip)
                _model_adi = istenen
                _cihaz_bilgisi(istenen, cihaz, tip)
                return _model
            except Exception as e:  # sürücü/kitaplık sorunlarını yut, CPU'ya düş
                import gunluk
                # CPU'ya düşmek tanımayı 0,4 saniyeden 10 saniyeye çıkarıyor;
                # sessizce olmasın, kayda geçsin.
                gunluk.uyari("ses", "stt_cihaz",
                             f"{cihaz} kullanılamadı: {str(e)[:200]}")
        raise RuntimeError("Whisper yüklenemedi")


def yaziya_cevir(ses_baytlari: bytes, uzanti: str = ".webm") -> dict:
    """Ses kaydını Türkçe metne çevir."""
    with tempfile.NamedTemporaryFile(suffix=uzanti, delete=False) as f:
        f.write(ses_baytlari)
        gecici = f.name
    try:
        m = _whisper()
        segmentler, bilgi = m.transcribe(
            gecici,
            language="tr",
            vad_filter=True,                       # sessizlikleri at
            vad_parameters={"min_silence_duration_ms": 400},
            # Işın genişliği 5'ten 1'e: large-v3-turbo'da Türkçe isabet
            # ölçülebilir biçimde değişmiyor ama tanıma belirgin
            # hızlanıyor. Kart üçünü birden (Ollama, XTTS, Whisper)
            # taşıdığı için buradaki her yüz milisaniye sesli tura yansıyor.
            beam_size=int(store.ayar("stt_isin", "1") or 1),
        )
        metin = " ".join(s.text for s in segmentler).strip()
        return {"metin": metin, "sure": getattr(bilgi, "duration", None)}
    finally:
        try:
            os.unlink(gecici)
        except OSError:
            pass


# ── seslendirme ────────────────────────────────────────────────────────────

# Sesli okumada kötü duran işaretleri temizle
_TEMIZLE = [
    (re.compile(r"```.*?```", re.S), " "),        # kod blokları
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"^\s*[-*•]\s*", re.M), ""),      # madde işaretleri
    (re.compile(r"[*_#>]+"), ""),                 # markdown kalıntısı
    (re.compile(r"https?://\S+"), "bağlantı"),
    (re.compile(r"\s{2,}"), " "),
]


def seslendirme_icin_temizle(metin: str, azami: int = 1200) -> str:
    for desen, yerine in _TEMIZLE:
        metin = desen.sub(yerine, metin)
    metin = metin.strip()
    if len(metin) > azami:
        kesme = metin.rfind(".", 0, azami)
        metin = metin[: kesme + 1] if kesme > azami * 0.5 else metin[:azami]
    return metin


async def _seslendir(metin: str, ses: str, hedef: str,
                     hiz: int = 0, perde: int = 0) -> None:
    import edge_tts

    await edge_tts.Communicate(
        metin, ses,
        rate=f"{hiz:+d}%", pitch=f"{perde:+d}Hz",
    ).save(hedef)


# MP3 çerçeveleri kendi kendine yeterli olduğu için parçaları arka arkaya
# eklemek çalışıyor; ayrı bir ses kütüphanesine gerek yok.
#
# 44 baytlık sessiz bir MPEG-1 Layer III çerçevesi (24 kHz, mono, 32 kbps) —
# yaklaşık 24 ms. Duraklamayı bunu tekrarlayarak üretiyoruz.
_SESSIZ_CERCEVE = (b"\xff\xf3\x18\xc4" + b"\x00" * 40)
_CERCEVE_MS = 24


def _sessizlik(ms: int) -> bytes:
    return _SESSIZ_CERCEVE * max(0, int(ms / _CERCEVE_MS))


async def _parcalari_seslendir(parcalar: list[dict], ses: str) -> bytes:
    import edge_tts

    cikti = bytearray()
    for p in parcalar:
        veri = bytearray()
        try:
            iletisim = edge_tts.Communicate(
                p["metin"], ses,
                rate=f"{int(p.get('hiz', 0)):+d}%",
                pitch=f"{int(p.get('perde', 0)):+d}Hz")
            async for olay in iletisim.stream():
                if olay["type"] == "audio":
                    veri += olay["data"]
        except Exception:
            continue                        # bir parça düşerse gerisi okunsun
        cikti += veri
        cikti += _sessizlik(p.get("sonra_ms", 140))
    return bytes(cikti)


def motor() -> str:
    """Hangi seslendirme motoru? Klon servisi kapalıysa edge'e düşülür."""
    secim = store.ayar("ses_motoru", "edge")
    if secim != "klon":
        return "edge"
    import ses_klon

    return "klon" if ses_klon.kullanilabilir() else "edge"


def parca_seslendir(metin: str, hiz: int = 0, perde: int = 0,
                    ses: str | None = None) -> tuple[bytes, str]:
    """Tek bir cümleyi seslendir. (veri, mime) döner.

    Akışlı çalmanın yapı taşı: arayüz cümleleri tek tek isteyip ilki gelir
    gelmez çalmaya başlıyor, gerisi arkadan geliyor.
    """
    metin = (metin or "").strip()
    if not metin:
        return b"", "audio/mpeg"

    if motor() == "klon":
        import ses_klon

        # edge'in yüzdelik hızını XTTS'in çarpanına çevir
        veri = ses_klon.seslendir(metin, hiz=1.0 + hiz / 100)
        if veri:
            return veri, "audio/wav"
        # klon düştüyse sessizce edge'e geç

    ses = ses or store.ayar("ses", "tr-TR-AhmetNeural")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        hedef = f.name
    try:
        asyncio.run(_seslendir(metin, ses, hedef, hiz, perde))
        return Path(hedef).read_bytes(), "audio/mpeg"
    finally:
        try:
            os.unlink(hedef)
        except OSError:
            pass


def seslendir(metin: str, ses: str | None = None,
              dogal: bool | None = None) -> bytes:
    """Metni mp3'e çevir.

    ``dogal`` açıkken metin önce konuşma diline çevrilir, sonra parçalara
    bölünüp her parça kendi hız/perdesiyle seslendirilir. Kapalıyken eski
    tek parça davranışı sürer — hızlıdır, ama düzdür.
    """
    ses = ses or store.ayar("ses", "tr-TR-AhmetNeural")
    temiz = seslendirme_icin_temizle(metin)
    if not temiz:
        return b""

    import dogal as _dogal

    if dogal is None:
        dogal = _dogal.acik_mi()

    if dogal:
        try:
            parcalar = _dogal.parcala(_dogal.dogallastir(temiz))
            if parcalar:
                veri = asyncio.run(_parcalari_seslendir(parcalar, ses))
                if len(veri) > 500:
                    return veri
        except Exception:
            pass                            # doğal katman düşerse düz oku

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        hedef = f.name
    try:
        asyncio.run(_seslendir(_dogal.isaretleri_at(temiz), ses, hedef))
        return Path(hedef).read_bytes()
    finally:
        try:
            os.unlink(hedef)
        except OSError:
            pass


def sesler() -> list[str]:
    return ["tr-TR-AhmetNeural", "tr-TR-EmelNeural"]
