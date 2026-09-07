# -*- coding: utf-8 -*-
"""Ara sesler — dolgu kliplerinin kırpılması ve seçimi.

Klipler XTTS ile üretiliyor ama testler model çağırmıyor: sentetik WAV
üretip kırpıcıya veriyoruz. Böylece testler ses servisi kapalıyken de
çalışıyor ve saniyeler değil milisaniyeler sürüyor.
"""
import math
import shutil
import struct
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "backend"))

import ara_ses  # noqa: E402

gecti = kaldi = 0


def ok(kosul, ad):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print(f"  OK   {ad}")
    else:
        kaldi += 1
        print(f"  KALDI {ad}")


ORAN = 24_000


def wav_yap(bolumler) -> bytes:
    """bolumler: [(saniye, genlik), ...] -> 16 bit mono WAV."""
    x = []
    for sure, genlik in bolumler:
        n = int(sure * ORAN)
        for i in range(n):
            # 220 Hz ton; genlik 0 ise sessizlik
            x.append(int(genlik * math.sin(2 * math.pi * 220 * i / ORAN)))
    govde = struct.pack("<%dh" % len(x), *x)
    return (b"RIFF" + struct.pack("<I", 36 + len(govde)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, ORAN, ORAN * 2, 2, 16)
            + b"data" + struct.pack("<I", len(govde)) + govde)


def sure(wav: bytes) -> float:
    i = wav.find(b"data")
    n = struct.unpack("<I", wav[i + 4:i + 8])[0]
    return n / 2 / ORAN


print("[1] baştaki ve sondaki sessizlik atılıyor")

ham = wav_yap([(0.50, 0), (0.40, 8000), (0.60, 0)])
kirpik = _k = ara_ses._sessizligi_kirp(ham)
ok(sure(ham) > 1.4, "ham klip 1,5 saniye")
ok(0.40 <= sure(kirpik) <= 0.75,
   f"kırpık klip söze indi ({sure(kirpik):.2f} sn)")


print("\n[2] XTTS'in sondaki uydurma eki atılıyor")

# Ölçülen gerçek durum: söz, uzun sessizlik, sonra alakasız bir ses.
# Örnek başına bakan bir kırpıcı bunu "cümle sonu" sanıp hepsini tutuyordu.
ham = wav_yap([(0.40, 9000), (0.70, 0), (0.18, 6000)])
kirpik = ara_ses._sessizligi_kirp(ham, "Anladım.")
ok(sure(kirpik) < 0.75, f"uydurma ek atıldı ({sure(kirpik):.2f} sn)")
ok(sure(kirpik) >= 0.40, "söz korundu")


print("\n[3] cümle içi duraklama yutulmuyor")

# "Tamam, bakıyorum." — virgül duraklaması boşluk eşiğinin altında.
ham = wav_yap([(0.32, 9000), (0.22, 0), (0.47, 9000), (0.50, 0)])
kirpik = ara_ses._sessizligi_kirp(ham, "Tamam, bakıyorum.")
ok(sure(kirpik) > 0.95,
   f"iki kelime de duruyor ({sure(kirpik):.2f} sn)")


print("\n[4] makullük denetimi yarım cümleyi kurtarıyor")

# Duraklama eşiği aşarsa boşluk mantığı ikinci kelimeyi keserdi; metin
# uzunluğundan beklenen süre tutmayınca kırpıcı geri adım atıyor.
ham = wav_yap([(0.30, 9000), (0.60, 0), (0.45, 9000), (0.40, 0)])
kirpik = ara_ses._sessizligi_kirp(ham, "Tamam, bakıyorum.")
ok(sure(kirpik) > 1.0,
   f"uzun duraklamaya rağmen tam cümle ({sure(kirpik):.2f} sn)")
# Metin verilmezse geri adım yok: boşluk mantığı çalışır.
kirpik_metinsiz = ara_ses._sessizligi_kirp(ham)
ok(sure(kirpik_metinsiz) < 0.75,
   f"metinsizken boşlukta kesiyor ({sure(kirpik_metinsiz):.2f} sn)")


print("\n[5] bozuk veri kırpıcıyı düşürmüyor")

ok(ara_ses._sessizligi_kirp(b"") == b"", "boş veri")
ok(ara_ses._sessizligi_kirp(b"bu WAV degil") == b"bu WAV degil", "WAV değil")
tamamen_sessiz = wav_yap([(0.5, 0)])
ok(ara_ses._sessizligi_kirp(tamamen_sessiz) == tamamen_sessiz,
   "tamamen sessiz klibe dokunmuyor")


print("\n[6] cümleler kısa ve içerikten bağımsız")

# Ara ses gerçek yanıttan uzun olursa gecikmeyi kapatmak yerine biz
# üretiyoruz. Kelime sayısı kaba ama işe yarar bir üst sınır.
ok(all(len(c) <= 24 for c in ara_ses.ILK), "ilk onaylar kısa")
ok(len(ara_ses.ILK) >= 6, "tekrar etmeyecek kadar çeşit var")
ok(len(ara_ses.BEKLEME) >= 3, "bekleme havuzu var")
# Yanıtı bilmeden plana söz veren cümle olmamalı.
yasak = ("yapalım", "yapayım", "az kaldı", "bitti", "hazır",
         "evet", "hayır", "bulundu")
sizan = [c for c in ara_ses.ILK + ara_ses.BEKLEME
         if any(y in c.lower() for y in yasak)]
ok(not sizan, f"söz veren cümle yok ({sizan})")


print("\n[7] seçim çeşitleniyor, üst üste tekrar etmiyor")

gecici = Path(tempfile.mkdtemp(prefix="ara-ses-test-"))
eski_kok = ara_ses.KOK
try:
    ara_ses.KOK = gecici
    klasor = gecici / "sahte-ses"
    klasor.mkdir(parents=True)
    for c in ara_ses.ILK:
        (klasor / f"ilk-{ara_ses._slug(c)}.wav").write_bytes(
            wav_yap([(0.30, 6000)]))

    ara_ses._ses_kimligi = lambda: "sahte-ses"
    ara_ses._onbellek.clear()
    ara_ses._son_kullanilan["ilk"] = []

    secimler = [ara_ses.sec("ilk") for _ in range(8)]
    ok(all(s is not None for s in secimler), "hepsi ses döndü")
    metinler = [s[2] for s in secimler if s]
    ok(all(m for m in metinler), "metinler eşleşti")
    ardisik_tekrar = any(metinler[i] == metinler[i + 1]
                         for i in range(len(metinler) - 1))
    ok(not ardisik_tekrar, "üst üste aynısı gelmedi")
    ok(len(set(metinler)) >= 4, f"çeşitlilik var ({len(set(metinler))} farklı)")

    veri, mime, _ = secimler[0]
    ok(mime == "audio/wav", "biçim bildiriliyor")
    ok(veri.startswith(b"RIFF"), "gerçek WAV döndü")

    print("\n[8] ayar kapalıyken hiç ses dönmüyor")
    import store
    eski = store.ayar("ara_ses", "1")
    store.ayar_yaz("ara_ses", "0")
    try:
        ok(ara_ses.sec("ilk") is None, "kapalıyken None")
    finally:
        store.ayar_yaz("ara_ses", eski)
    ok(ara_ses.sec("ilk") is not None, "tekrar açılınca çalışıyor")

    print("\n[9] klip yoksa sessizce None")
    ara_ses._ses_kimligi = lambda: "olmayan-ses"
    ara_ses._onbellek.clear()
    ok(ara_ses.sec("ilk") is None, "bilinmeyen ses için None")
finally:
    ara_ses.KOK = eski_kok
    shutil.rmtree(gecici, ignore_errors=True)


print("\n" + "=" * 54)
print(f"  {gecti} test geçti, {kaldi} kaldı")
print("=" * 54)
sys.exit(1 if kaldi else 0)
