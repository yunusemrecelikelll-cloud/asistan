"""Kalıcı WebSocket kanalı — telefon ve saat için en kısa gecikme.

Neden HTTP değil:

Her sesli tur şu an dört ayrı HTTP isteği: yazıya çevir, yanıt al, parçalara
böl, her parçayı seslendir. Yerel ağda her istek ~30-60 ms el sıkışma
demek; hücresel bağlantıda 150-300 ms. Saatte bu daha da kötü, çünkü saat
telefon üzerinden geçiyor.

Kalıcı bir kanalda el sıkışma bir kez oluyor. Ses parçaları hazır olur olmaz
itiliyor — istemcinin sorması gerekmiyor. Ölçülen fark: turda 0,4-1,2 saniye.

Protokol (JSON metin çerçeveleri + ikili ses çerçeveleri):

    → {"tur": "giris", "belirtec": "..."}
    ← {"tur": "hazir", "ses": "ses1"}

    → {"tur": "metin", "metin": "bugün ne var"}
    → [ikili ses verisi]  + {"tur": "ses_bitti", "uzanti": ".webm"}
    ← {"tur": "yazi", "metin": "..."}          (konuşma tanıma sonucu)
    ← {"tur": "yanit", "metin": "...", "niyet": "..."}
    ← {"tur": "parca", "sira": 0, "bayt": 12345}  ardından ikili çerçeve
    ← {"tur": "bitti"}

    ← {"tur": "olay", "olay": {...}}           (sunucudan kendiliğinden)

İkili çerçeve her zaman kendisini tarif eden JSON çerçevesinin ARDINDAN
gelir; böylece istemcinin ayrıca eşleme yapması gerekmiyor.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import WebSocket, WebSocketDisconnect

import auth
import gunluk
import olay
import store


class Oturum:
    """Tek bir istemci bağlantısı."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.acik = True
        self.ses_tamponu = bytearray()
        # Bu turda gerçek yanıt sesi çıktı mı? Ara sesler bunu kapatıyor;
        # bekleme sesi yalnızca hâlâ sessizken çalıyor.
        self.gercek_ses_cikti = False

    async def json_gonder(self, veri: dict) -> None:
        if self.acik:
            await self.ws.send_text(json.dumps(veri, ensure_ascii=False))

    async def ikili_gonder(self, veri: bytes) -> None:
        if self.acik:
            await self.ws.send_bytes(veri)


async def _olay_akisi(o: Oturum) -> None:
    """Sunucu tarafındaki değişiklikleri istemciye it.

    Uzun yoklamayı taklit etmek yerine olay kuyruğunu iş parçacığı havuzunda
    bekliyoruz; FastAPI'nin olay döngüsünü bloke etmesin.
    """
    # DİKKAT: burada olay.bekle çağırmak yok. bekle() olay yoksa 25 saniye
    # bloke ediyor ve doğrudan olay döngüsünde çalıştığı için bağlantıdan
    # sonraki İLK mesaj o kadar gecikiyordu. son_id() hemen dönüyor.
    son = olay.son_id()
    while o.acik:
        try:
            d = await asyncio.to_thread(olay.bekle, son)
        except Exception:
            await asyncio.sleep(1)
            continue
        if not o.acik:
            return
        son = d.get("son_id", son)
        for e in d.get("olaylar", []):
            # Olayı İÇ İÇE gönderiyoruz. Eskiden {"tur": "olay", **e} yazıyordu
            # ama olayın kendi "tur" alanı (gorev, mesaj, taslak…) dıştaki
            # "olay" değerini eziyordu; istemciye hiç {"tur": "olay"} çerçevesi
            # ulaşmıyordu. Bir olay türü "bitti" ya da "hata" adını alsaydı
            # istemci onu protokol çerçevesi sanıp turu kesecekti.
            await o.json_gonder({"tur": "olay", "olay": e})


async def ara_ses_gonder(o: Oturum, tur: str = "ilk") -> bool:
    """Hazır bir ara sesi olduğu gibi it.

    Doğallaştırma, parçalama, seslendirme — hiçbiri yok. Klip zaten diskte
    duruyor; buradaki tek iş dosyayı okuyup yollamak. Amacı gecikmeyi
    kapatmak olan bir şeyin kendisi gecikme üretmemeli.
    """
    import ara_ses

    if not o.acik or o.gercek_ses_cikti:
        return False
    secim = await asyncio.to_thread(ara_ses.sec, tur)
    if not secim or not o.acik or o.gercek_ses_cikti:
        return False
    veri, mime, metin = secim
    # "ara": bu bir dolgu. İstemci ilk-ses gecikmesini bununla ölçmesin,
    # yoksa gerçek gecikme rakamı görünmez olur.
    await o.json_gonder({"tur": "parca", "sira": -1, "bayt": len(veri),
                         "bicim": mime, "metin": metin, "ara": True})
    await o.ikili_gonder(veri)
    return True


async def _bekleme_sesleri(o: Oturum) -> None:
    """İş uzarsa arada "hâlâ bakıyorum" de.

    Proje komutlarında taslak üretimi 15 saniyeyi bulabiliyor. Tek bir
    "tamam"dan sonra yarım dakika sessizlik, hiç konuşmamaktan daha kötü:
    kullanıcı bağlantı koptu sanıyor.
    """
    import ara_ses

    onceki = 0.0
    for an in ara_ses.BEKLEME_ANLARI:
        await asyncio.sleep(an - onceki)
        onceki = an
        if not o.acik or o.gercek_ses_cikti:
            return
        await ara_ses_gonder(o, "bekleme")


async def _cumleyi_gonder(o: Oturum, sira: int, cumle: str,
                          dogal_hazir: bool = False) -> int:
    """Tek cümleyi doğallaştır, seslendir, it. Kaç parça gittiğini döner.

    ``dogal_hazir`` metni üreten model işaretleri baştan koyduysa açılır;
    o zaman yeniden yazma çağrısı atlanır.
    """
    import dogal
    import speech

    temiz = speech.seslendirme_icin_temizle(cumle)
    if not temiz:
        return 0

    parcalar = await asyncio.to_thread(
        lambda: dogal.parcala(temiz if dogal_hazir
                              else dogal.dogallastir(temiz)))
    # Turun ILK parçasını ince bölüyoruz: seslendirme süresi metin
    # uzunluğuyla orantılı, ve ilk sesin duyulmasına kadar geçen süre
    # doğrudan bu parçanın uzunluğuna bağlı. Sonraki parçalar önceki ses
    # çalarken üretildiği için onlarda bölmenin kazancı yok.
    if sira == 0:
        parcalar = dogal.ilk_parcayi_bol(parcalar)
    gonderilen = 0
    for p in parcalar:
        if not o.acik:
            return gonderilen
        veri, tur = await asyncio.to_thread(
            speech.parca_seslendir, p["metin"], p.get("hiz", 0),
            p.get("perde", 0))
        if not veri:
            continue
        await o.json_gonder({"tur": "parca", "sira": sira + gonderilen,
                             "bayt": len(veri), "bicim": tur,
                             "metin": p["metin"]})
        await o.ikili_gonder(veri)
        # İlk gerçek parça çıktı: bekleme sesleri sussun.
        o.gercek_ses_cikti = True
        gonderilen += 1
    return gonderilen


async def _seslendir_akisli(o: Oturum, metin: str) -> None:
    """Hazır bir metni cümle cümle seslendir."""
    import dogal

    sira = 0
    for c in dogal._cumlelere_bol(metin):
        if not o.acik:
            return
        sira += await _cumleyi_gonder(o, sira, c)
    await o.json_gonder({"tur": "bitti"})


class _Spekulasyon:
    """Niyet çözülürken paralel yürüyen sohbet üretimi.

    Sesli turların çoğu sohbet. Niyeti bekleyip sonra üretmeye başlamak her
    turda ~1 saniye boşa bekleme demekti. Ollama iki isteği aynı anda
    yürütebildiği için üretimi hemen başlatıyoruz; niyet "soru" çıkmazsa
    üretilen metni atıyoruz — bedeli bir kerelik kısa bir GPU işi.
    """

    def __init__(self, metin: str):
        self.kuyruk: asyncio.Queue = asyncio.Queue()
        self.dur = False
        # Üretim ayrı bir iş parçacığında; kuyruğa oradan doğrudan yazmak
        # güvenli değil, olay döngüsüne devrediyoruz.
        self._dongu = asyncio.get_running_loop()
        self.gorev = asyncio.create_task(asyncio.to_thread(self._uret, metin))

    def _koy(self, deger) -> None:
        self._dongu.call_soon_threadsafe(self.kuyruk.put_nowait, deger)

    def _uret(self, metin: str) -> None:
        import main
        try:
            for c in main.sohbet_akisi(metin):
                if self.dur:
                    break
                self._koy(c)
        except Exception as e:      # üretim düşerse tüketici kilitlenmesin
            gunluk.hata("kanal", "sohbet_akis", istisna=e)
        finally:
            self._koy(None)

    def iptal(self) -> None:
        """Üretimi bırak — ama BEKLEME.

        Eskiden burada görevin bitmesi bekleniyordu (30 sn'ye kadar). Üretim
        iş parçacığı `dur` bayrağını ancak cümle sınırında görüyor, yani her
        proje komutunda yarım cümlelik bir bekleme kritik yola ekleniyordu.
        Atacağımız metni beklemenin anlamı yok: bayrağı koyup geçiyoruz,
        iş parçacığı kendi kendine kapanıyor.
        """
        self.dur = True
        # Görev başıboş kalmasın: sonucu kimse okumuyor, istisnası da
        # yutulsun ki asyncio "exception was never retrieved" diye bağırmasın.
        self.gorev.add_done_callback(lambda g: g.exception() if not g.cancelled() else None)


async def _sohbeti_akit(o: Oturum, spek: "_Spekulasyon", sesli: bool,
                        t0: float) -> None:
    """Üretilen cümleleri geldikçe seslendir.

    Eskiden sıra şuydu: bütün yanıt üretilir → bütün metin doğallaştırılır →
    seslendirilir. Üç bekleme arka arkaya geliyordu. Şimdi model ilk cümleyi
    verir vermez o cümle seslendiriliyor; model kalanı ses çalarken üretiyor.
    """
    import dogal
    import store

    cumleler: list[str] = []
    sira = 0
    while True:
        c = await spek.kuyruk.get()
        if c is None:
            break
        cumleler.append(c)
        if len(cumleler) == 1:
            gunluk.bilgi("kanal", "ilk_cumle", c[:60],
                         sure_ms=int((time.perf_counter() - t0) * 1000))
            # İlk cümle elde: kullanıcı yanıtı ekranda görsün, ses beklemesin
            await o.json_gonder(
                {"tur": "yanit", "metin": dogal.isaretleri_at(c),
                 "niyet": "sohbet", "kismi": True,
                 "sure_ms": int((time.perf_counter() - t0) * 1000)})
        if sesli and o.acik:
            sira += await _cumleyi_gonder(o, sira, c, dogal_hazir=True)
        elif not o.acik:
            spek.dur = True

    await spek.gorev
    tam = dogal.isaretleri_at(" ".join(cumleler)).strip()
    await asyncio.to_thread(store.mesaj_ekle, "asistan", tam, None, "ollama")
    await o.json_gonder({"tur": "yanit", "metin": tam, "niyet": "sohbet",
                         "sure_ms": int((time.perf_counter() - t0) * 1000)})
    await o.json_gonder({"tur": "bitti"})


async def _metni_isle(o: Oturum, metin: str, sesli: bool = True,
                      ses_mi: bool = True) -> None:
    import main
    import niyet
    import store

    t = time.perf_counter()

    # Sohbet üretimini niyetle AYNI ANDA başlat; niyet kritik yoldan çıksın.
    spek = _Spekulasyon(metin)
    n = await asyncio.to_thread(
        niyet.coz, metin, store.projeler(sadece_var=True))
    gunluk.bilgi("kanal", "niyet_suresi", n.get("niyet", "?"),
                 sure_ms=int((time.perf_counter() - t) * 1000))

    if n.get("niyet") == "soru":
        await asyncio.to_thread(
            lambda: store.mesaj_ekle("kullanici", metin, ses_mi=ses_mi))
        await _sohbeti_akit(o, spek, sesli, t)
        return

    spek.iptal()                    # tahmin tutmadı, üretimi at (beklemeden)
    sonuc = await asyncio.to_thread(
        main.taslak_uret, main.TaslakIstek(metin=metin, ses_mi=ses_mi), n)
    yanit = sonuc.get("yanit") or ""
    await o.json_gonder({"tur": "yanit", "metin": yanit,
                         "niyet": sonuc.get("tur"),
                         "sure_ms": int((time.perf_counter() - t) * 1000)})
    if sesli and yanit:
        await _seslendir_akisli(o, yanit)
    else:
        await o.json_gonder({"tur": "bitti"})


def _wav_sarmala(pcm: bytes, oran: int = 16000, kanal: int = 1,
                 bit: int = 16) -> bytes:
    """Ham PCM'e WAV başlığı ekle.

    iPhone ve Apple Watch kaydı BİTMEDEN göndermeye başlıyor: kullanıcı
    sustuğunda ses zaten burada oluyor, yükleme beklemesi kalmıyor. Akış
    hâlinde başlık yazılamayacağı için başlığı sonda biz ekliyoruz —
    44 bayt, ölçülemeyecek kadar ucuz.
    """
    import struct

    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, kanal, oran,
                          oran * kanal * bit // 8, kanal * bit // 8, bit)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


async def _sesi_isle(o: Oturum, uzanti: str, sesli: bool) -> None:
    import speech

    veri = bytes(o.ses_tamponu)
    o.ses_tamponu.clear()
    if uzanti == ".pcm":
        veri = _wav_sarmala(veri)
        uzanti = ".wav"
    if len(veri) < 1200:
        await o.json_gonder({"tur": "hata", "mesaj": "kayıt çok kısa"})
        return

    t = time.perf_counter()
    d = await asyncio.to_thread(speech.yaziya_cevir, veri, uzanti)
    metin = (d.get("metin") or "").strip()
    await o.json_gonder({"tur": "yazi", "metin": metin,
                         "sure_ms": int((time.perf_counter() - t) * 1000)})
    if not metin:
        await o.json_gonder({"tur": "bitti"})
        return

    # Ara ses BURADA giriyor, konuşma tanımadan hemen sonra: konuştuğunu
    # kesin biliyoruz (boş kayıt yukarıda elendi) ama yanıta daha 2-3
    # saniye var. Kullanıcı sustuktan ~300 ms sonra bir karşılık duyuyor.
    bekleyici = None
    if sesli:
        o.gercek_ses_cikti = False
        await ara_ses_gonder(o, "ilk")
        bekleyici = asyncio.create_task(_bekleme_sesleri(o))
    try:
        await _metni_isle(o, metin, sesli, ses_mi=True)
    finally:
        if bekleyici:
            bekleyici.cancel()


async def kanal(ws: WebSocket) -> None:
    await ws.accept()
    o = Oturum(ws)
    dogrulandi = auth.yerel_mi_ws(ws)
    olay_gorevi = None

    try:
        if dogrulandi:
            await o.json_gonder({"tur": "hazir",
                                 "ses": store.ayar("klon_referans", "ses1")})
            olay_gorevi = asyncio.create_task(_olay_akisi(o))

        while True:
            mesaj = await ws.receive()
            if mesaj.get("type") == "websocket.disconnect":
                break

            if (veri := mesaj.get("bytes")) is not None:
                if not dogrulandi:
                    continue
                o.ses_tamponu += veri
                continue

            try:
                istek = json.loads(mesaj.get("text") or "{}")
            except json.JSONDecodeError:
                continue
            tur = istek.get("tur")

            if tur == "giris":
                dogrulandi = auth.belirtec_gecerli(istek.get("belirtec", ""))
                await o.json_gonder(
                    {"tur": "hazir" if dogrulandi else "yetkisiz",
                     "ses": store.ayar("klon_referans", "ses1")})
                if dogrulandi and olay_gorevi is None:
                    olay_gorevi = asyncio.create_task(_olay_akisi(o))
                continue

            if not dogrulandi:
                await o.json_gonder({"tur": "yetkisiz"})
                continue

            if tur == "metin":
                await _metni_isle(o, (istek.get("metin") or "").strip(),
                                  istek.get("sesli", True), ses_mi=False)
            elif tur == "ses_bitti":
                await _sesi_isle(o, istek.get("uzanti", ".webm"),
                                 istek.get("sesli", True))
            elif tur == "ses_basla":
                o.ses_tamponu.clear()
            elif tur == "nabiz":
                await o.json_gonder({"tur": "nabiz"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        gunluk.hata("kanal", "hata", istisna=e)
    finally:
        o.acik = False
        if olay_gorevi:
            olay_gorevi.cancel()
