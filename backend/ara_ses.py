"""Ara sesler — konuşma bittikten sonraki sessizliği doldurur.

Sorun şu: kullanıcı sustuktan sonra ilk sesin duyulmasına 2-3 saniye var
(konuşma tanıma, niyet, üretim, seslendirme). Proje komutlarında bu 15
saniyeye çıkıyor. O aralıkta hiçbir şey duyulmuyor ve karşılıklı konuşma
hissi kopuyor — özellikle saatte, ekrana bakmıyorken.

Araya kısa bir "seni duydum" sesi koyunca boşluk kapanıyor. Bunun işe
yaraması için üç kural var:

1. **Hazır olmalı.** Ara sesi o anda üretirsek doldurmaya çalıştığımız
   gecikmeyi kendimiz üretmiş oluruz. Klipler bir kez üretilip diske
   yazılıyor; sıcak yolda yalnızca dosya okunuyor.

2. **İçerikten bağımsız olmalı.** "Şöyle yapalım o hâlde" gibi bir cümle
   cevabı bilmeden bir plana söz veriyor; yanıt "bugün hiçbir şey yok"
   çıkarsa saçma duruyor. Buradaki cümleler yalnızca *duyduğunu* ve
   *baktığını* söyler, ne yapacağına dair söz vermez.

3. **Kısa olmalı.** Gerçek yanıt ara ses biterken geliyorsa sorun yok
   (çalar sıraya alıyor, boşluk kalmıyor). Ama ara ses gerçek yanıttan
   uzunsa kullanıcıyı biz bekletiyoruz. Bu yüzden hepsi bir saniyenin
   altında.

Çeşitlilik önemli: aynı sesi her turda duymak birkaç turda sırıtıyor ve
"kayıttan çalıyor" hissi veriyor. Son kullanılanlar hatırlanıyor, havuz
tükenmeden tekrar edilmiyor.
"""

from __future__ import annotations

import random
import re
import threading
import unicodedata
from pathlib import Path

import gunluk
import store

KOK = Path(__file__).resolve().parent.parent / "data" / "ara-sesler"

# ── Cümleler ──────────────────────────────────────────────────────────────
#
# Hepsi içerikten bağımsız. Yanıt ne çıkarsa çıksın önlerine konabilir.

ILK = [
    "Hmm.",
    "Tamam.",
    "Anladım.",
    "Bir saniye.",
    "Dur bakayım.",
    "Tamam, bakıyorum.",
    "Peki.",
    "Bakıyorum.",
    "Hmm, tamam.",
    "Anladım, bir saniye.",
]

# Uzun süren işler için. Bunlar da söz vermiyor: "az kaldı" demiyoruz,
# çünkü ne kadar kaldığını bilmiyoruz.
BEKLEME = [
    "Hâlâ bakıyorum.",
    "Devam ediyor.",
    "Biraz sürüyor.",
    "Hâlâ üstünde çalışıyorum.",
    "Bakmaya devam ediyorum.",
]

HAVUZLAR = {"ilk": ILK, "bekleme": BEKLEME}

# Uzun işlerde bekleme sesinin hangi saniyelerde çalınacağı. Aralık gittikçe
# açılıyor: baştaki sessizlik en çok rahatsız eden yer, ama her üç saniyede
# bir konuşan bir asistan da sinir bozucu.
BEKLEME_ANLARI = (3.5, 9.0, 18.0, 32.0)

# Klipler küçük (birkaç on KB) ve sayıları sabit; hepsini bellekte tutmak
# sıcak yoldaki dosya okumasını da kaldırıyor.
_kilit = threading.Lock()
_son_kullanilan: dict[str, list[str]] = {"ilk": [], "bekleme": []}
_onbellek: dict[str, dict[str, tuple[bytes, str, str]]] = {}


def _slug(metin: str) -> str:
    d = unicodedata.normalize("NFKD", metin)
    d = "".join(c for c in d if not unicodedata.combining(c))
    d = re.sub(r"[^a-zA-Z0-9]+", "-", d).strip("-").lower()
    return d or "ses"


def _ses_kimligi() -> str:
    """Kliplerin hangi sese ait olduğu.

    Ses klonu ile edge'in tınısı bambaşka; kullanıcı sesi değiştirdiğinde
    eski klipler yanlış sesle çalar. Klasör adına sesi de koyup her ses
    için ayrı önbellek tutuyoruz.
    """
    import speech

    m = speech.motor()
    if m == "klon":
        return "klon-" + _slug(store.ayar("klon_referans", "ses1"))
    return "edge-" + _slug(store.ayar("ses", "tr-TR-AhmetNeural"))


def _klasor() -> Path:
    return KOK / _ses_kimligi()


# Ara sesin gerçek yanıttan UZUN olmaması gerekiyor, yoksa gecikmeyi
# kapatmak yerine biz üretiyoruz.
#
# XTTS iki şey birden yapıyor: cümlenin sonuna bir saniyeye varan sessizlik
# koyuyor, ve ondan SONRA çoğu zaman uydurma bir ses parçası ekliyor.
# Ölçülen bir örnek ("Anladım."):
#
#     0,00-0,50  söylenen söz
#     0,50-1,20  sessizlik
#     1,22-1,40  uydurma ek        <- örnek başına bakan bir kırpıcı
#                                     burayı "cümle sonu" sanıyor
#
# Bu yüzden kırpma pencere tabanlı: konuşma başladıktan sonraki ilk UZUN
# boşlukta kesiyoruz. Bir-iki kelimelik bu kliplerde yarım saniyelik bir
# iç duraklama olmaz; olan her şey artıktır.

PENCERE = 0.02           # RMS penceresi (saniye)
BOSLUK_ESIGI = 0.45      # bundan uzun sessizlikten sonrası atılıyor
BAS_PAYI = 0.03          # baştan bırakılan pay
SON_PAYI = 0.12          # sonda daha cömert: kelime sonu yutulmasın
AZAMI_SANIYE = 2.5       # akıl sağlığı sınırı; normalde hiç devreye girmez


def _sessizligi_kirp(wav: bytes, metin: str = "") -> bytes:
    """16 bit PCM WAV'ı söylenen sözün sınırlarına kırp.

    Elde ayrıştırıyoruz; ses için ek bir bağımlılık almak istemiyoruz ve
    biçim zaten bizim ürettiğimiz dar bir alt küme.
    """
    import struct

    try:
        if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
            return wav

        k, kanal, oran, bit = 12, 1, 24_000, 16
        bas = boy = 0
        while k + 8 <= len(wav):
            ad = wav[k:k + 4]
            n = struct.unpack("<I", wav[k + 4:k + 8])[0]
            govde = k + 8
            if ad == b"fmt " and govde + 16 <= len(wav):
                kanal, oran = struct.unpack("<HI", wav[govde + 2:govde + 8])
                bit = struct.unpack("<H", wav[govde + 14:govde + 16])[0]
            elif ad == b"data":
                bas, boy = govde, min(n, len(wav) - govde)
                break
            k = govde + n + (n % 2)
        if bit != 16 or kanal != 1 or boy < 4 or oran < 8000:
            return wav

        ham = wav[bas:bas + boy // 2 * 2]
        x = struct.unpack("<%dh" % (len(ham) // 2), ham)
        if len(x) < oran // 10:
            return wav

        # Pencere başına RMS
        pen = max(1, int(PENCERE * oran))
        rms = []
        for i in range(0, len(x) - pen + 1, pen):
            d = x[i:i + pen]
            rms.append((sum(v * v for v in d) / pen) ** 0.5)
        if not rms:
            return wav

        tepe = max(rms) or 1.0
        esik = max(tepe * 0.03, 25.0)
        gurultulu = [r > esik for r in rms]
        if not any(gurultulu):
            return wav

        ilk = gurultulu.index(True)
        bosluk_pencere = max(1, int(BOSLUK_ESIGI / PENCERE))

        # Konuşmanın başından ilerle; uzun bir sessizlik görünce dur.
        son_gurultu = ilk
        sessiz_sayac = 0
        for i in range(ilk, len(gurultulu)):
            if gurultulu[i]:
                son_gurultu = i
                sessiz_sayac = 0
            else:
                sessiz_sayac += 1
                if sessiz_sayac >= bosluk_pencere:
                    break

        basla = max(0, (ilk * pen) - int(BAS_PAYI * oran))
        bitir = min(len(x), ((son_gurultu + 1) * pen) + int(SON_PAYI * oran))

        # Makullük denetimi. XTTS her üretimde biraz farklı konuşuyor; bir
        # seferinde virgül duraklaması boşluk eşiğini aşıp "Tamam, bakıyorum."
        # klibini "Tamam."a indirmişti. Metin uzunluğundan beklenen en kısa
        # süreyi hesaplayıp altına düşersek boşluk mantığını bırakıp yalnızca
        # baş/son sessizliğini atıyoruz. Yarım cümle söyleyen bir ara ses,
        # ara ses olmamasından kötü.
        asgari = max(0.30, 0.042 * len(metin.strip())) if metin else 0.0
        if (bitir - basla) / oran < asgari:
            son_gurultu = len(gurultulu) - 1 - gurultulu[::-1].index(True)
            bitir = min(len(x),
                        ((son_gurultu + 1) * pen) + int(SON_PAYI * oran))

        azami = int(AZAMI_SANIYE * oran)
        if bitir - basla > azami:
            bitir = basla + azami
        if bitir - basla < oran // 20:          # 50 ms'den kısaysa dokunma
            return wav

        kirpik = struct.pack("<%dh" % (bitir - basla), *x[basla:bitir])
        return (b"RIFF" + struct.pack("<I", 36 + len(kirpik)) + b"WAVEfmt "
                + struct.pack("<IHHIIHH", 16, 1, 1, oran,
                              oran * 2, 2, 16)
                + b"data" + struct.pack("<I", len(kirpik)) + kirpik)
    except Exception:
        # Kırpma yalnızca bir iyileştirme; beceremezsek ham klip de çalışır.
        return wav


def hazirla(zorla: bool = False) -> dict:
    """Eksik klipleri üret. Sunucu açılışında çağrılıyor.

    Üretim sırasında ara ses istenirse ``sec()`` sessizce boş dönüyor —
    hazır olmayan bir sesi beklemek, doldurmaya çalıştığımız gecikmeyi
    büyütmekten başka bir işe yaramaz.
    """
    import speech

    kimlik = _ses_kimligi()
    klasor = KOK / kimlik
    klasor.mkdir(parents=True, exist_ok=True)

    uretilen, atlanan, hata = 0, 0, 0
    for tur, cumleler in HAVUZLAR.items():
        for c in cumleler:
            hedef = klasor / f"{tur}-{_slug(c)}.wav"
            if hedef.exists() and hedef.stat().st_size > 128 and not zorla:
                atlanan += 1
                continue
            try:
                veri, mime = speech.parca_seslendir(c)
            except Exception as e:
                gunluk.hata("ara_ses", "uretim", c, istisna=e)
                hata += 1
                continue
            if not veri:
                hata += 1
                continue
            if "mpeg" not in mime:
                veri = _sessizligi_kirp(veri, c)
            # Uzantıyı gerçek biçime göre yazıyoruz: klon WAV, edge mp3.
            gercek = hedef.with_suffix(".mp3" if "mpeg" in mime else ".wav")
            # Atomik yazma: yarım yazılmış bir klibi okumak cızırtı demek.
            # Ses değişiminde üretim arka planda sürerken okunuyor olabilir.
            gecici = gercek.with_suffix(gercek.suffix + ".yeni")
            gecici.write_bytes(veri)
            gecici.replace(gercek)
            uretilen += 1

    with _kilit:
        _onbellek.pop(kimlik, None)     # yeniden üretildi, eskisi geçersiz
    d = {"ses": kimlik, "uretilen": uretilen, "vardi": atlanan, "hata": hata}
    gunluk.bilgi("ara_ses", "hazir", str(d))
    return d


def _yukle(kimlik: str) -> dict[str, tuple[bytes, str, str]]:
    """Bu sesin bütün kliplerini belleğe al: ad -> (veri, mime, metin)."""
    klasor = KOK / kimlik
    d: dict[str, tuple[bytes, str, str]] = {}
    if not klasor.is_dir():
        return d
    for p in sorted(klasor.iterdir()):
        if p.suffix not in (".wav", ".mp3"):
            continue
        try:
            veri = p.read_bytes()
        except OSError:
            continue
        if len(veri) < 128:
            continue
        mime = "audio/mpeg" if p.suffix == ".mp3" else "audio/wav"
        tur = p.stem.split("-", 1)[0]
        metin = next((c for c in HAVUZLAR.get(tur, [])
                      if f"{tur}-{_slug(c)}" == p.stem), "")
        d[p.name] = (veri, mime, metin)
    return d


def sec(tur: str = "ilk") -> tuple[bytes, str, str] | None:
    """Bir ara ses seç. (veri, mime, metin) ya da hazır değilse ``None``.

    Son kullanılanlar atlanıyor; havuzun yarısı tükenene kadar tekrar yok.
    """
    if store.ayar("ara_ses", "1") != "1":
        return None
    kimlik = _ses_kimligi()

    with _kilit:
        klipler = _onbellek.get(kimlik)
    if klipler is None:
        # Diske BİR kez bakıyoruz. Süreç durumuna değil dosyalara
        # güveniyoruz: sunucu yeniden başladığında klipler zaten yerinde,
        # ısıtmanın bitmesini beklemeye gerek yok.
        klipler = _yukle(kimlik)
        with _kilit:
            _onbellek[kimlik] = klipler
    if not klipler:
        return None

    adlar = [a for a in klipler if a.startswith(tur + "-")]
    if not adlar:
        return None

    with _kilit:
        son = _son_kullanilan.setdefault(tur, [])
        aday = [a for a in adlar if a not in son] or adlar
        secilen = random.choice(aday)
        son.append(secilen)
        # Havuzun yarısı kadar geçmiş tutuyoruz: hem tekrar seyrek oluyor
        # hem de seçim tek bir sıraya kilitlenmiyor.
        del son[: max(0, len(son) - max(1, len(adlar) // 2))]

    return klipler[secilen]
