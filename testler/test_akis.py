# -*- coding: utf-8 -*-
"""Akışlı sesli tur — cümle bölme, spekülatif üretim, işaret kuralları.

Buradaki testler ağ ya da model kullanmıyor; Ollama'ya giden çağrılar
sahteyle değiştiriliyor. Amaç davranışı sabitlemek: sesli turda gecikmeyi
41 saniyeden 3 saniyeye indiren üç mekanizma bozulursa burası patlasın.
"""

import asyncio
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "backend"))

gecti = 0
kaldi = 0


def ok(kosul, ad):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print(f"  OK   {ad}")
    else:
        kaldi += 1
        print(f"  KALDI {ad}")


print("\n[1] cümle sınırı yakalama")
import brain

def bol(metin):
    """yerel_sohbet_akis'in cümle bölme mantığını tek başına dene."""
    cikan, tampon = [], ""
    for harf in metin:
        tampon += harf
        while (m := brain._CUMLE_SONU.search(tampon)):
            cikan.append(tampon[:m.end()].strip())
            tampon = tampon[m.end():]
    if tampon.strip():
        cikan.append(tampon.strip())
    return cikan

ok(bol("Bir. İki! Üç?") == ["Bir.", "İki!", "Üç?"], "üç cümle ayrıldı")
ok(bol("Saat 4. gibi gel") == ["Saat 4. gibi gel"],
   "sayıdan sonraki nokta cümle sonu sayılmaz")
ok(bol("Tek cümle") == ["Tek cümle"], "noktasız kalan da veriliyor")
ok(bol("") == [], "boş metin boş liste")


print("\n[2] akışlı üretim cümle cümle veriyor")
import httpx


class _SahteAkis:
    """httpx.stream yerine geçen bağlam yöneticisi."""

    def __init__(self, parcalar):
        self.parcalar = parcalar

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for p in self.parcalar:
            yield json.dumps({"message": {"content": p}, "done": False})
        yield json.dumps({"message": {"content": ""}, "done": True})


_gercek_stream = httpx.stream
httpx.stream = lambda *a, **k: _SahteAkis(
    ["Birinci cümle", ". ", "İkinci ", "cümle. ", "Son parça"])
try:
    cumleler = list(brain.yerel_sohbet_akis([{"role": "user", "content": "x"}]))
finally:
    httpx.stream = _gercek_stream

ok(cumleler == ["Birinci cümle.", "İkinci cümle.", "Son parça"],
   f"parçalar cümleye toplandı ({cumleler})")


print("\n[3] işaret kuralları sohbet talimatına giriyor")
import dogal
import store

eski_uslup = store.ayar("konusma_uslubu", "canli")
eski_acik = store.ayar("dogal_konusma", "1")

store.ayar_yaz("dogal_konusma", "1")
store.ayar_yaz("konusma_uslubu", "sert")
ek = dogal.sesli_ek()
ok("[vurgu]" in ek and "[dur]" in ek, "sert üslupta işaretler var")
ok("[gul]" in ek, "kullanılmayacak işaret de tanıtılıyor")

store.ayar_yaz("dogal_konusma", "0")
ok(dogal.sesli_ek() == "", "doğal konuşma kapalıyken ek yok")

store.ayar_yaz("dogal_konusma", "1")
store.ayar_yaz("konusma_uslubu", "canli")
ok("[hizli]" in dogal.sesli_ek(), "canlı üslupta tempo işaretleri var")

store.ayar_yaz("konusma_uslubu", eski_uslup)
store.ayar_yaz("dogal_konusma", eski_acik)


print("\n[4] spekülatif üretim iptal edilebiliyor")
import kanal
import main


async def _spekulasyon_denemesi():
    uretilen = []

    def sahte_akis(metin):
        for i in range(50):
            uretilen.append(i)
            yield f"Cümle {i}."

    eski = main.sohbet_akisi
    main.sohbet_akisi = sahte_akis
    try:
        spek = kanal._Spekulasyon("merhaba")
        ilk = await spek.kuyruk.get()
        spek.iptal()
        # iptal() artık BEKLEMİYOR — üretim iş parçacığı bayrağı cümle
        # sınırında görüp kapanıyor. Üretimin gerçekten durduğunu ölçmek
        # için burada, testte bekliyoruz; üretimde beklemenin anlamı yok
        # çünkü çıkan metni zaten atıyoruz.
        await spek.gorev
        return ilk, len(uretilen)
    finally:
        main.sohbet_akisi = eski


ilk, sayi = asyncio.run(_spekulasyon_denemesi())
ok(ilk == "Cümle 0.", "ilk cümle kuyruktan alındı")
ok(sayi < 50, f"iptal üretimi kesti ({sayi}/50)")


print("\n[5] olay akışı bağlantıyı bloke etmiyor")
import inspect

import olay

kaynak = inspect.getsource(kanal._olay_akisi)
ok("olay.son_id()" in kaynak, "başlangıç kimliği bloke etmeden alınıyor")
ok("son = olay.bekle(" not in kaynak,
   "bloke eden bekle() doğrudan olay döngüsünde çağrılmıyor")
ok(isinstance(olay.son_id(), int), "son_id sayı döndürüyor")


print("\n[6] hazır doğallaştırılmış metin ikinci kez yazılmıyor")
imza = inspect.signature(kanal._cumleyi_gonder)
ok("dogal_hazir" in imza.parameters, "dogal_hazir parametresi var")
gvd = inspect.getsource(kanal._sohbeti_akit)
ok("dogal_hazir=True" in gvd, "sohbet akışı doğallaştırmayı atlıyor")


print("\n[7] niyet hazır verilince tekrar çözülmüyor")
imza = inspect.signature(main.taslak_uret)
ok("hazir_niyet" in imza.parameters, "taslak_uret hazır niyet alıyor")
gvd = inspect.getsource(main.taslak_uret)
ok("hazir_niyet or niyet.coz" in gvd, "hazır niyet varsa model çağrılmıyor")


print("\n[8] tek cümlede birden fazla planlama isteği")
import niyet


def sahte_niyet(cikti):
    """Modeli sahteyle değiştirip niyet.coz'un doğrulamasını sına."""
    import brain
    eski = brain.yerel_sohbet
    brain.yerel_sohbet = lambda *a, **k: json.dumps(cikti, ensure_ascii=False)
    try:
        return niyet.coz("herhangi bir cümle", [])
    finally:
        brain.yerel_sohbet = eski


n = sahte_niyet({"niyet": "planla", "eylemler": [
    {"eylem": "bugunu_ayarla", "bitis": "16:00"},
    {"eylem": "ileriden_al", "gun": 1}]})
ok(n["niyet"] == "planla", "çoklu eylem planla olarak kalıyor")
ok(len(n.get("eylemler", [])) == 2, "iki eylem de korundu")
ok(n["eylemler"][0]["eylem"] == "bugunu_ayarla",
   "sıra korunuyor — pencere daralt, sonra öne çek")
ok(n.get("eylem") == "bugunu_ayarla",
   "eski tek-eylem biçimi de doldurulmuş (geriye uyum)")

n = sahte_niyet({"niyet": "planla", "eylem": "ileriden_al", "gun": 2})
ok(n.get("eylemler") and len(n["eylemler"]) == 1,
   "tek eylem de listeye sarılıyor")

n = sahte_niyet({"niyet": "planla", "eylemler": [
    {"eylem": "bugunu_ayarla", "bitis": "16:00"},
    {"eylem": "uydurma_eylem"}]})
ok(len(n.get("eylemler", [])) == 1, "geçersiz eylem atılıyor, geçerli kalıyor")

n = sahte_niyet({"niyet": "planla", "eylem": "bugunu_ayarla", "bitis": None})
ok(n["niyet"] == "soru", "saatsiz bugunu_ayarla uygulanmıyor")

n = sahte_niyet({"niyet": "planla", "eylemler": []})
ok(n["niyet"] == "soru", "boş eylem listesi soruya düşüyor")

ok(niyet._planlama_gecerli({"eylem": "kacanlari_sirala"}),
   "kacanlari_sirala ek alan istemiyor")
ok(not niyet._planlama_gecerli("metin"), "sözlük olmayan reddediliyor")


print("\n[9] ham PCM sunucuda WAV'a sarılıyor")
import kanal

pcm = bytes(range(256)) * 4
sarili = kanal._wav_sarmala(pcm)
ok(sarili[:4] == b"RIFF" and sarili[8:12] == b"WAVE", "WAV başlığı doğru")
ok(len(sarili) == len(pcm) + 44, "başlık 44 bayt, gövde bozulmamış")
ok(sarili[44:] == pcm, "ses verisi aynen korunuyor")
ok(int.from_bytes(sarili[24:28], "little") == 16000, "16 kHz yazılmış")
ok(int.from_bytes(sarili[22:24], "little") == 1, "mono yazılmış")


print("\n[10] olay çerçevesi protokol çerçevesini ezmiyor")


class SahteWS:
    """json_gonder çağrılarını toplayan sahte soket."""

    def __init__(self):
        self.gonderilen = []

    async def send_text(self, metin):
        self.gonderilen.append(json.loads(metin))

    async def send_bytes(self, veri):
        pass


async def _olay_denemesi():
    import olay

    ws = SahteWS()
    o = kanal.Oturum(ws)
    turlar = [
        {"olaylar": [{"id": 1, "tur": "gorev", "zaman": 0.0, "gorev_id": 3}],
         "son_id": 1},
    ]

    def sahte_bekle(since, bekleme=0):
        if turlar:
            return turlar.pop(0)
        o.acik = False
        return {"olaylar": [], "son_id": 1}

    eski_bekle = olay.bekle
    olay.bekle = sahte_bekle
    try:
        await kanal._olay_akisi(o)
    finally:
        olay.bekle = eski_bekle
    return ws.gonderilen


gonderilen = asyncio.run(_olay_denemesi())
ok(len(gonderilen) == 1, "bir olay çerçevesi gitti")
cerceve = gonderilen[0] if gonderilen else {}
# Eskiden {"tur": "olay", **e} yazılıyordu; olayın kendi "tur" alanı
# dıştakini eziyor ve istemciye hiç {"tur": "olay"} ulaşmıyordu. Bir olay
# "bitti" adını alsaydı istemci turu erkenden kapatırdı.
ok(cerceve.get("tur") == "olay", "dış tür 'olay' olarak kaldı")
ok(cerceve.get("olay", {}).get("tur") == "gorev", "olay türü iç içe duruyor")
ok(cerceve.get("olay", {}).get("gorev_id") == 3, "olay alanları korunuyor")


print("\n[11] spekülasyon iptali beklemiyor")
import inspect

ok(not inspect.iscoroutinefunction(kanal._Spekulasyon.iptal),
   "iptal() eşzamanlı — kritik yolda beklemiyor")


print("\n[12] süreç ağacı öldürme")
import dispatch

ok(hasattr(dispatch, "_agaci_oldur"), "_agaci_oldur var")
kaynak = inspect.getsource(dispatch._agaci_oldur)
# claude bir .CMD sarmalayıcısı: cmd.exe -> node. p.kill() yalnızca cmd'yi
# öldürüyor, asıl işi yapan node hayatta kalıyordu.
ok("taskkill" in kaynak, "Windows'ta taskkill /T kullanılıyor")
ok("os.killpg(" not in kaynak, "POSIX'te süreç grubuna dokunulmuyor")
ok("_iptal_edilenler" in inspect.getsource(dispatch.iptal),
   "iptal işaretleniyor — sonuç 'hata' ile ezilmiyor")


print("\n" + "=" * 54)
print(f"  {gecti} test geçti, {kaldi} kaldı")
print("=" * 54)
sys.exit(1 if kaldi else 0)
