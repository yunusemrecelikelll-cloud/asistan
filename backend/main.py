"""Asistan — FastAPI sunucusu.

Yerelde 127.0.0.1:8770 üzerinde çalışır, arayüzü de kendisi sunar.
"""

from __future__ import annotations

import asyncio
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from fastapi import (FastAPI, File, HTTPException, Request,
                     UploadFile, WebSocket)
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth
import auto
import baski
import brain
import bulk
import brief
import dispatch
import dogal
import duzen
import ekran
import gunluk
import istatistik
import kanal
import klasor
import koc
import mentor
import niyet
import olay
import projects
import speech
import store
import takvim
import yedek
import yasam

ON_YUZ = KOK.parent / "frontend"


@asynccontextmanager
async def omur(_app: FastAPI):
    """Açılış işleri. ``on_event("startup")`` kullanımdan kaldırıldı.

    Kurulum bloke eden bir iş (proje keşfi, disk okuma) olduğu için olay
    döngüsünde değil iş parçacığında çalıştırıyoruz; aksi hâlde sunucu
    ilk isteği kabul etmeden önce donuyor.
    """
    await asyncio.to_thread(baslangic)
    yield


app = FastAPI(title="Asistan", lifespan=omur)


@app.middleware("http")
async def parola_katmani(request: Request, call_next):
    try:
        auth.dogrula(request)
    except HTTPException as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    return await call_next(request)


def baslangic() -> None:
    store.kur()
    bulunan = projects.kesfet()
    print(f"[asistan] {len(bulunan)} proje keşfedildi")
    auto.baslat()
    mentor.baslat()
    if store.ayar('klasor_takip', '1') == '1':
        klasor.kur()
    ekran.baslat()
    threading.Thread(target=_isit, daemon=True).start()
    gunluk.bilgi('sunucu', 'basladi', 'Asistan ayakta')


def _isit() -> None:
    """Modelleri arka planda önceden yükle.

    Yeniden başlatmadan ya da bilgisayarı açtıktan sonraki İLK sesli tur
    27 saniye sürüyordu: dil modeli, Whisper ve XTTS aynı anda yükleniyordu.
    Kullanıcı konuşmadan önce yüklersek o bekleme hiç yaşanmıyor. Sırayla
    yüklüyoruz; üçünü birden yüklemek 8 GB kartta takılmaya yol açıyor.
    """
    import brain

    def tek() -> None:
        brain.yerel_sohbet([{"role": "user", "content": "merhaba"}],
                           azami_token=8, sicaklik=0)

    try:
        # İKİ istek aynı anda: sesli turda niyet ile yanıt paralel gidiyor.
        # Ollama paralel yuvaları ilk eşzamanlı istekte ayırıyor ve bu
        # ayırma modeli yeniden yüklüyordu — ilk tur 28 saniye sürüyordu.
        # Yuvaları burada açtırıyoruz, kullanıcı beklemesin.
        isler = [threading.Thread(target=tek) for _ in range(2)]
        for i in isler:
            i.start()
        for i in isler:
            i.join(timeout=180)
        gunluk.bilgi('sunucu', 'isitma', 'dil modeli hazır')
    except Exception as e:
        gunluk.hata('sunucu', 'isitma_model', istisna=e)
    import speech
    try:
        speech._whisper()
        gunluk.bilgi('sunucu', 'isitma', 'konuşma tanıma hazır')
    except Exception as e:
        gunluk.hata('sunucu', 'isitma_stt', istisna=e)
    try:
        if speech.motor() == 'klon':
            import ses_klon
            ses_klon.seslendir('Hazırım.')
            gunluk.bilgi('sunucu', 'isitma', 'ses klonu hazır')
    except Exception as e:
        gunluk.hata('sunucu', 'isitma_tts', istisna=e)
    try:
        # Ara sesler (konusma bitince calan kisa onay) burada uretiliyor.
        # Sicak yolda uretmek, doldurmaya calistigimiz gecikmeyi kendimizin
        # uretmesi olurdu.
        import ara_ses
        gunluk.bilgi('sunucu', 'isitma', str(ara_ses.hazirla()))
    except Exception as e:
        gunluk.hata('sunucu', 'isitma_ara_ses', istisna=e)


# ── modeller ───────────────────────────────────────────────────────────────


class KomutIstek(BaseModel):
    proje_id: int
    komut: str
    model: str | None = None
    devam: bool = True


class NotIstek(BaseModel):
    not_metni: str | None = None
    etiket: str | None = None


class AyarIstek(BaseModel):
    anahtar: str
    deger: str


class SeslendirIstek(BaseModel):
    metin: str
    ses: str | None = None


class TaslakIstek(BaseModel):
    metin: str
    proje_id: int | None = None
    ses_mi: bool = False


class OnayIstek(BaseModel):
    taslak_id: int
    detayli: str | None = None      # kullanıcı düzenlediyse
    model: str | None = None


class TopluIstek(BaseModel):
    proje_idler: list[int] | None = None      # None = diskte olan tüm projeler
    gorev: str | None = None                  # None = özet görevi


class OtomatikIstek(BaseModel):
    acik: bool
    aralik: int | None = None
    azami: int | None = None


# ── sağlık & ayarlar ───────────────────────────────────────────────────────


class GirisIstek(BaseModel):
    parola: str


class ParolaIstek(BaseModel):
    yeni: str


@app.get("/api/giris/durum")
def giris_durum(request: Request) -> dict:
    """Parola gerekli mi? Yerelden bakınca gerekmez."""
    return {"yerel": auth.yerel_mi(request)}


@app.post("/api/giris")
def giris(istek: GirisIstek) -> dict:
    import hmac as _h

    if not _h.compare_digest(istek.parola.strip(), auth.parola()):
        raise HTTPException(401, "parola yanlış")
    return {"belirtec": auth.belirtec()}


@app.get("/api/parola")
def parola_goster(request: Request) -> dict:
    """Parolayı yalnızca bu bilgisayardan göster."""
    if not auth.yerel_mi(request):
        raise HTTPException(403, "parola yalnızca bu bilgisayardan görülebilir")
    return {"parola": auth.parola()}


@app.post("/api/parola")
def parola_degistir(istek: ParolaIstek, request: Request) -> dict:
    if not auth.yerel_mi(request):
        raise HTTPException(403, "parola yalnızca bu bilgisayardan değiştirilebilir")
    try:
        auth.parola_degistir(istek.yeni)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"tamam": True}


@app.get("/api/olaylar")
def olaylar(since: int = 0) -> dict:
    """Canlı akış. Yeni olay yoksa istek bekletilir (uzun yoklama)."""
    return olay.bekle(since)


@app.get("/api/saglik")
def saglik() -> dict:
    return {
        "durum": "ok",
        "ollama": brain.ollama_var_mi(),
        "ollama_modelleri": brain.ollama_modeller(),
        "claude_bin": dispatch.CLAUDE_BIN,
        "maliyet": store.maliyet_ozeti(),
        "limit": dispatch.limit_durumu(),
        "otomatik": auto.durum(),
        "toplu": bulk.durum(),
        "bekleyen_taslak": len(store.bekleyen_taslaklar()),
    }


@app.get("/api/ayarlar")
def ayarlar_getir() -> dict:
    return {
        "ayarlar": store.tum_ayarlar(),
        "sesler": speech.sesler(),
        "ollama_modelleri": brain.ollama_modeller(),
        "claude_modelleri": ["haiku", "sonnet", "opus"],
        "stt_modelleri": ["small", "medium", "large-v3"],
        "izin_kipleri": ["acceptEdits", "bypassPermissions", "manual"],
        "limit": dispatch.limit_durumu(),
    }


@app.post("/api/ayarlar")
def ayar_yaz(istek: AyarIstek) -> dict:
    store.ayar_yaz(istek.anahtar, istek.deger)
    return {"tamam": True}


# ── projeler ───────────────────────────────────────────────────────────────


@app.get("/api/projeler")
def projeler_getir() -> dict:
    return projects.genel_rapor()


@app.post("/api/projeler/tara")
def projeler_tara() -> dict:
    bulunan = projects.kesfet()
    return {"bulunan": len(bulunan), **projects.genel_rapor()}


@app.get("/api/projeler/{pid}")
def proje_getir(pid: int, derin: bool = False) -> dict:
    d = projects.proje_durumu(pid, derin=derin)
    if "hata" in d:
        raise HTTPException(404, d["hata"])
    return d


@app.post("/api/projeler/{pid}/not")
def proje_not(pid: int, istek: NotIstek) -> dict:
    if not store.proje(pid):
        raise HTTPException(404, "proje bulunamadı")
    store.proje_not_yaz(pid, istek.not_metni, istek.etiket)
    return {"tamam": True}


# ── komut gönderme ─────────────────────────────────────────────────────────


@app.post("/api/komut")
def komut_gonder(istek: KomutIstek) -> dict:
    sonuc = dispatch.gonder(istek.proje_id, istek.komut, istek.model,
                            istek.devam)
    if "hata" in sonuc:
        raise HTTPException(400, sonuc["hata"])
    return sonuc


@app.get("/api/eylem/{eid}")
def eylem_getir(eid: int) -> dict:
    d = dispatch.durum(eid)
    if not d:
        raise HTTPException(404, "eylem bulunamadı")
    return d


@app.post("/api/eylem/{eid}/iptal")
def eylem_iptal(eid: int) -> dict:
    return {"iptal": dispatch.iptal(eid)}


@app.get("/api/eylemler")
def eylemler_getir(limit: int = 40) -> dict:
    return {"eylemler": store.eylemler(limit)}


# ── sohbet ─────────────────────────────────────────────────────────────────


def _rapor_metni(hedef: dict | None) -> str:
    """Rapor metnini modelsiz üret — ücretsiz ve her zaman doğru."""
    r = projects.genel_rapor()
    o = r["ozet"]
    if hedef:
        d = projects.proje_durumu(hedef["id"])
        g = d.get("git_durumu", {})
        parcalar = [f"{d['ad']} projesi."]
        if d.get("son_oturum"):
            gun = (time.time() - d["son_oturum"]) / 86400
            parcalar.append(
                "Son çalışma " +
                ("bugün" if gun < 1 else f"{int(gun)} gün önce") + "."
            )
        parcalar.append(f"{d.get('oturum_sayisi', 0)} oturum kaydı var.")
        if g.get("git"):
            n = g.get("degisiklik_sayisi", 0)
            parcalar.append(
                f"Git dalı {g.get('dal')}, " +
                (f"{n} kaydedilmemiş değişiklik var." if n else "çalışma ağacı temiz.")
            )
            if g.get("son_commit_mesaj"):
                parcalar.append(f"Son commit: {g['son_commit_mesaj']}.")
        else:
            parcalar.append("Bu projede git deposu yok.")
        if d.get("not_metni"):
            parcalar.append(f"Notun: {d['not_metni']}")
        return " ".join(parcalar)

    aktif = [p for p in r["projeler"]
             if p["son_oturum"] and time.time() - p["son_oturum"] < 7 * 86400]
    kirli = [p for p in r["projeler"]
             if p.get("git_durumu", {}).get("degisiklik_sayisi", 0) > 0]
    s = [f"Toplam {o['toplam']} proje takip ediyorum, {o['diskte_var']} tanesi diskte duruyor."]
    if aktif:
        adlar = ", ".join(p["ad"] for p in aktif[:3])
        s.append(f"Son bir haftada {len(aktif)} projede çalışmışsın: {adlar}.")
    if kirli:
        adlar = ", ".join(p["ad"] for p in kirli[:3])
        s.append(f"{len(kirli)} projede kaydedilmemiş değişiklik var: {adlar}.")
    if o["diskte_yok"]:
        s.append(f"{o['diskte_yok']} projenin klasörü artık diskte yok.")
    return " ".join(s)


def _gorev_niyeti(n: dict, metin: str) -> dict:
    """Görevle ilgili niyetleri yerine getir.

    Görevi cümledeki kelimelerden buluyoruz. Birden fazla aday çıkarsa
    seçtirmiyoruz — yanlış görevi tamamlamak, hiç tamamlamamaktan kötü.
    """
    eylem = n.get("eylem")
    aranan = n.get("baslik") or metin

    if eylem == "ekle":
        baslik = (n.get("baslik") or "").strip()
        if not baslik:
            return {"tur": "sohbet", "yanit": "Ne ekleyeyim?"}
        tarih = n.get("tarih") or mentor.bugun()
        sure = int(n.get("sure_dk") or 60)
        saat = n.get("saat") or mentor.bos_slot(tarih, sure)
        if not saat:
            yer = mentor.ilk_uygun_gun(sure, azami_gun=4)
            if not yer:
                return {"tur": "sohbet",
                        "yanit": "Önümüzdeki günlerde boş yer bulamadım."}
            tarih, saat = yer
        gid = store.gorev_ekle(baslik=baslik, tarih=tarih, saat=saat,
                               sure_dk=sure, kaynak="kullanici")
        return {"tur": "gorev_eklendi",
                "yanit": f"Eklendi: {baslik} — {tarih} {saat}.",
                "gorev": store.gorev(gid)}

    adaylar = mentor.gorev_bul(aranan)
    if not adaylar:
        return {"tur": "sohbet",
                "yanit": "Öyle bir görev bulamadım. Adını tam söyler misin?"}
    if len(adaylar) > 1 and len(adaylar[0]["baslik"]) > 0:
        # İlk aday belirgin şekilde öndeyse ona git, değilse sor
        if len(adaylar) > 3:
            return {"tur": "gorev_secim",
                    "yanit": "Hangisi? " + ", ".join(
                        g["baslik"] for g in adaylar[:4]),
                    "adaylar": adaylar[:4]}
    g = adaylar[0]

    if eylem == "tamamla":
        sonuc = mentor.gecmiste_tamamla(
            g["id"], int(n.get("dakika_once") or 0), n.get("saat"))
        if not sonuc.get("ok"):
            return {"tur": "sohbet", "yanit": sonuc.get("hata", "Olmadı.")}
        k = sonuc["karne"]
        return {"tur": "gorev_tamamlandi",
                "yanit": (f"“{g['baslik']}” tamam — {sonuc['gercek_dk']} dakika "
                          f"sürmüş. Bugün {k['tamam']}/{k['toplam']}."),
                **sonuc}

    if eylem == "ertele":
        sonuc = mentor.gorev_ertele(g["id"], n.get("gerekce") or "sesli istek")
        if not sonuc.get("ok"):
            return {"tur": "sohbet", "yanit": sonuc.get("hata", "Olmadı.")}
        return {"tur": "gorev_ertelendi",
                "yanit": (f"“{g['baslik']}” {sonuc['tarih']} {sonuc['saat']}'e "
                          f"alındı."), **sonuc}

    if eylem == "duzenle":
        sonuc = mentor.gorev_duzenle(
            g["id"],
            baslik=n.get("yeni_baslik"), saat=n.get("yeni_saat"),
            tarih=n.get("yeni_tarih"), sure_dk=n.get("yeni_sure_dk"),
            oncelik=n.get("yeni_oncelik"), ayrinti=n.get("yeni_ayrinti"))
        if not sonuc.get("ok"):
            return {"tur": "sohbet", "yanit": sonuc.get("hata", "Olmadı.")}
        y = sonuc["gorev"]
        return {"tur": "gorev_duzenlendi",
                "yanit": (f"“{y['baslik']}” güncellendi: {y['tarih']} "
                          f"{y['saat']}, {y['sure_dk']} dakika."),
                **sonuc}

    return {"tur": "sohbet", "yanit": "Ne yapmamı istiyorsun?"}


def _niyeti_uygula(n: dict, metin: str) -> dict | None:
    """Çözülen niyeti yerine getir.

    ``None`` dönerse iş proje komutu akışına devam eder. Yani proje komutu
    varsayılan değil, geriye kalan; anlaşılmayan cümle iş emrine çevrilmiyor.
    """
    tur = n.get("niyet")

    if tur == "yasam":
        yazilan = []
        for k in n["kayitlar"]:
            kid = store.yasam_ekle(k["tur"], k.get("tarih") or yasam.bugun(),
                                   k["deger"], k["birim"], k["detay"])
            if k["tur"] == "harcama":
                store.yasam_kategori_yaz(kid, koc.kategori_bul(k["detay"]))
            yazilan.append({**k, "id": kid})
        ozet = yasam.ozetle(yazilan)
        cevap = f"Yaşam kaydına yazdım: {ozet}."
        store.mesaj_ekle("asistan", cevap, None, "yerel")
        return {"tur": "yasam_kaydedildi", "yanit": cevap,
                "kayitlar": yazilan, "ozet": ozet}

    if tur == "duzen":
        d = duzen.yaz(**{k: v for k, v in n.items()
                         if k in ("tur", "baslangic", "bitis", "calisma_gun",
                                  "izin_gun", "vardiya_saat", "gunler")})
        cevap = (duzen.ozet(d) + " Planları buna göre kuracağım; "
                 "nöbet günlerine iş yazmayacağım.")
        store.mesaj_ekle("asistan", cevap, None, "yerel")
        return {"tur": "duzen_guncellendi", "yanit": cevap, "duzen": d,
                "takvim": duzen.takvim(mentor.bugun(), 14)}

    if tur == "planla":
        # Kullanıcı tek nefeste birden fazla şey isteyebiliyor ("saat dörde
        # kadar çalışacağım, yarınkileri öne al"). Hepsini SIRAYLA
        # uyguluyoruz: pencereyi daraltmak ile işleri öne çekmek birbirine
        # bağlı, sıra değişirse sonuç değişir.
        eylemler = n.get("eylemler") or [n]
        parcalar, son = [], {}
        for e in eylemler:
            son = mentor.yeniden_planla(
                e["eylem"], bitis=e.get("bitis"), gun=e.get("gun", 1))
            parcalar.append(_planlama_ozeti(e, son))
        cevap = " ".join(p for p in parcalar if p)
        store.mesaj_ekle("asistan", cevap, None, "yerel")
        return {"tur": "planlandi", "yanit": cevap, **son}

    if tur == "dosya":
        if n.get("dosya_id"):
            sonuc = klasor.bitti(n["dosya_id"])
            if sonuc.get("ok"):
                cevap = f"“{n['ad']}” Baskısı Bitenler'e taşındı."
                store.mesaj_ekle("asistan", cevap, None, "yerel")
                return {"tur": "dosya_bitti", "yanit": cevap, **sonuc}
        adaylar = n.get("adaylar") or []
        if adaylar:
            cevap = ("Hangisi? " +
                     ", ".join(a["ad"] for a in adaylar[:5]))
            store.mesaj_ekle("asistan", cevap, None, "yerel")
            return {"tur": "dosya_secim", "yanit": cevap, "adaylar": adaylar}
        return None

    if tur == "gorev":
        sonuc = _gorev_niyeti(n, metin)
        store.mesaj_ekle("asistan", sonuc["yanit"], None, "yerel")
        return sonuc

    if tur == "soru":
        cevap = _sohbet_yaniti(metin)
        store.mesaj_ekle("asistan", cevap, None, "ollama")
        return {"tur": "sohbet", "yanit": cevap}

    return None                       # "proje" — komut akışı devam etsin


SOHBET_TALIMATI = """Sen kullanıcının kişisel asistanısın. Onun projelerini,
planını ve alışkanlıklarını takip ediyorsun.

Kurallar:
- Türkçe, kısa ve doğal konuş. EN FAZLA 3 KISA CÜMLE. Uzun cevap yok.
- Elindeki veriye dayan. Bilmediğin şeyi uydurma; bilmiyorsan söyle.
- Madde işareti, başlık, emoji kullanma — bu metin sesli okunacak.
- Girişe, özete, "elbette/tabii" gibi dolgulara girme; doğrudan cevabı ver.
- Sana verilen DURUM metninden BAHSETME. "listede", "dosyada", "verdiğim
  bilgilerde", "kayıtlara göre" deme; bunları zaten biliyormuş gibi konuş.
- Sayı ve saat uydurma. DURUM'da olmayan bir rakamı söyleme."""


def _planlama_ozeti(e: dict, sonuc: dict) -> str:
    """Tek bir planlama eyleminin sonucunu tek cümleye indir."""
    if not sonuc.get("ok"):
        return sonuc.get("hata", "Yapamadım.")

    if e["eylem"] == "bugunu_ayarla":
        t = sonuc.get("tasinan") or []
        return (f"Tamam, bugün {e.get('bitis')}'e kadar. "
                + (f"{len(t)} işi ileri aldım: "
                   + "; ".join(f"{x['baslik']} → {x['yeni']}" for x in t[:4])
                   if t else "Program zaten sığıyor.")
                + (f" {len(sonuc['sigmayan'])} işe yer bulamadım."
                   if sonuc.get("sigmayan") else ""))

    if e["eylem"] == "kacanlari_sirala":
        k = sonuc.get("sirali") or []
        return (f"{len(k)} kaçan işi tekrar sıraya aldım: "
                + "; ".join(f"{x['baslik']} → {x['yeni']}" for x in k[:4])
                if k else "Sıraya alınacak kaçan iş yok.")

    a = sonuc.get("alinan") or []
    return (f"{len(a)} işi öne çektim: "
            + "; ".join(f"{x['baslik']} → {x['yeni']}" for x in a[:4])
            if a else "Bugüne sığacak boş yer kalmadı.")


def _sohbet_baglami(metin: str) -> str:
    """Modele verilecek DURUM metnini kur.

    Yanıtı akışlı da üretebilelim diye bağlam kurma ile model çağrısı
    ayrıldı; ikisi de aynı bağlamı görsün.
    """
    t = mentor.bugun()
    prog = mentor.bugun_programi()
    k = prog["karne"]

    satirlar = [
        f"Bugün {t} {prog['gun']}, saat {prog['saat']}.",
        f"Bugünün karnesi: {k['tamam']}/{k['toplam']} tamam, "
        f"{k['kalan']} kaldı, {k['kacirildi']} kaçtı.",
    ]
    if prog["siradaki"]:
        s = prog["siradaki"]
        satirlar.append(f"Sıradaki iş {s['saat']}: {s['baslik']}"
                        + (f" ({s['proje_ad']})" if s.get("proje_ad") else ""))
    for g in prog["gorevler"][:6]:
        satirlar.append(f"- {g['saat']} {g['baslik']} [{g['durum']}]")

    # ── Yarın ────────────────────────────────────────────────────────
    #
    # Eskiden bağlamda YALNIZCA bugün vardı. "Yarın ne var" diye
    # sorulduğunda model elinde veri olmadığı için ya "bilmiyorum" diyor ya
    # da uyduruyordu. Yarın ayrı bir başlık altında veriliyor ki bugünle
    # karışmasın.
    from datetime import date, timedelta

    try:
        yarin = (date.fromisoformat(t) + timedelta(days=1)).isoformat()
        yg = store.gorevler(tarih=yarin)
        if yg:
            satirlar.append(f"YARIN ({yarin}) {len(yg)} iş var:")
            for g in yg[:8]:
                satirlar.append(
                    f"- {g['saat']} {g['baslik']}"
                    + (f" ({g['proje_ad']})" if g.get("proje_ad") else ""))
        else:
            satirlar.append(f"YARIN ({yarin}) planlanmış iş yok.")
    except Exception:
        pass

    # ── Haftanın kalanı ──────────────────────────────────────────────
    #
    # Gün gün dökmüyoruz; sayı yeter. Bağlam uzadıkça küçük model
    # dağılıyor, önemli olan "önümüzde ne kadar iş var" bilgisi.
    try:
        bas = (date.fromisoformat(t) + timedelta(days=2)).isoformat()
        son = (date.fromisoformat(t) + timedelta(days=7)).isoformat()
        kalan = store.gorevler(tarih=bas, bitis=son)
        if kalan:
            gunler: dict[str, int] = {}
            for g in kalan:
                gunler[g["tarih"]] = gunler.get(g["tarih"], 0) + 1
            satirlar.append(
                "Sonraki günler: "
                + ", ".join(f"{a} {b} iş" for a, b in sorted(gunler.items())))
    except Exception:
        pass

    try:
        satirlar.append(duzen.ozet())
    except Exception:
        pass
    try:
        y = store.yasam_ozet(t, t)
        if y:
            satirlar.append("Bugünkü yaşam kaydı: " + ", ".join(
                f"{a} {b['toplam']}" for a, b in y.items()))
    except Exception:
        pass

    # ── Projeler ─────────────────────────────────────────────────────
    #
    # Yalnızca ad listesi vermek yetmiyordu: "hangi projede ne var"
    # sorusuna model ad listesinden cevap uyduruyordu. Türü ve durumu da
    # veriyoruz; hepsini değil, en çok dokunulan onunu.
    try:
        aktif = store.aktif_projeler()
        if aktif:
            satirlar.append(f"Aktif projeler ({len(aktif)} tane):")
            for p in aktif[:10]:
                parca = [p["ad"]]
                if p.get("tur") and p["tur"] != "kod":
                    parca.append(p["tur"])
                if p.get("not_metni"):
                    parca.append(str(p["not_metni"])[:60])
                satirlar.append("- " + " — ".join(parca))
    except Exception:
        pass

    # ── Atölye ───────────────────────────────────────────────────────
    try:
        bos = [y["ad"] for y in store.yazicilar() if y["durum"] == "bos"]
        if bos:
            satirlar.append(f"Boş yazıcılar: {', '.join(bos)}")
        bekleyen = store.dosyalar(durum="bekliyor")
        if bekleyen:
            satirlar.append(
                f"Baskıya verilecek {len(bekleyen)} dosya var: "
                + ", ".join(d["ad"] for d in bekleyen[:5]))
    except Exception:
        pass

    return "DURUM:\n" + "\n".join(satirlar) + f"\n\nKullanıcı: {metin}"


def _sohbet_yaniti(metin: str) -> str:
    """Durum sorularını ve sohbeti yerel modelle yanıtla."""
    try:
        istem = _sohbet_baglami(metin)
        return brain.yerel_sohbet([{"role": "user", "content": istem}],
                                  sistem=SOHBET_TALIMATI,
                                  azami_token=350).strip()
    except Exception:
        return "Şu an yanıt üretemedim."


def sohbet_akisi(metin: str):
    """Sohbet yanıtını cümle cümle üret (WebSocket kanalı kullanıyor).

    Kaydı çağıran tarafa bırakıyoruz: cümleler bittiğinde tam metin elde
    oluyor, mesaj geçmişine bir kez yazılıyor.
    """
    import dogal

    # İşaret kuralları BİLEREK eklenmiyor.
    #
    # Cümleyi üretirken bir yandan da bürünsel işaret serpiştirmek 4B'lik
    # bir modele fazla geliyor ve cevabın kendisi bozuluyor. Ölçüldü, aynı
    # soruya iki yanıt:
    #
    #   işaretsiz : "Aktif projelerin Asistan, WhatsApp Mesajları
    #                Uygulaması, CV Oluşturucu…"
    #   işaretli  : "[İlker] Bugün 3 adet kritik [kacirildi] iş var ve
    #                hepsini bitti."
    #
    # İşaretli sürüm olmayan işaretler uyduruyor ([İlker] bir isim, [20],
    # [durun]), iç durum etiketini sese sızdırıyor ve dilbilgisini
    # bozuyor. Doğruluk, büründen önce gelir.
    #
    # Kayıp yok: tempo ve perde değişimini dogal.parcala zaten kendi
    # yapıyor ve modülün kendi notunun dediği gibi "asıl insanlık hissi
    # tempo değişiminden geliyor". İşaretler yalnızca [dusun]/[gul] gibi
    # süslerdi.
    yield from brain.yerel_sohbet_akis(
        [{"role": "user", "content": _sohbet_baglami(metin)}],
        sistem=SOHBET_TALIMATI, azami_token=350)


@app.post("/api/taslak")
def taslak_olustur(istek: TaslakIstek) -> dict:
    """Kullanıcının mesajını ayrıntılı göreve çevir ve ONAYA sun.

    Hiçbir şey gönderilmez; kullanıcı onaylayana kadar bekler.
    """
    return taslak_uret(istek)


def taslak_uret(istek: TaslakIstek, hazir_niyet: dict | None = None) -> dict:
    """Uç noktanın gövdesi. Niyet dışarıda çözüldüyse tekrar çözülmez —
    WebSocket kanalı niyeti kendisi çözüp buraya veriyor, böylece sesli
    turda ikinci bir model çağrısı olmuyor."""
    metin = istek.metin.strip()
    if not metin:
        raise HTTPException(400, "boş mesaj")

    store.mesaj_ekle("kullanici", metin, istek.proje_id, ses_mi=istek.ses_mi)

    proje_listesi = store.projeler(sadece_var=True)

    # Ne demek istediğini modele sorduruyoruz. Eskiden kalıp eşleştirme
    # vardı ve yakalayamadığı her cümleyi proje komutu sanıyordu; "11'den
    # şimdiye kadar uyudum" bile "hangi projede çalıştırayım?" oluyordu.
    # Kullanıcı belirli bir proje seçtiyse niyeti sormaya gerek yok.
    if not istek.proje_id:
        n = hazir_niyet or niyet.coz(metin, proje_listesi)
        gunluk.bilgi("main", "niyet", metin[:120], niyet=n.get("niyet"),
                     kaynak=n.get("kaynak"))
        cevap = _niyeti_uygula(n, metin)
        if cevap is not None:
            return cevap
    hedef = store.proje(istek.proje_id) if istek.proje_id else None
    if hedef is None:
        hedef = brain.proje_bul(metin, proje_listesi)

    if hedef is None:
        yanit = ("Bu komutu hangi projede çalıştırayım? Soldan bir proje seç "
                 "ya da mesajında proje adını geçir.")
        store.mesaj_ekle("asistan", yanit, None, "yerel")
        return {"tur": "proje_secilmedi", "yanit": yanit,
                "projeler": [{"id": p["id"], "ad": p["ad"]} for p in proje_listesi]}

    brifing = brief.kisa_brifing(hedef["id"])
    detayli = brain.promptu_detaylandir(metin, brifing)

    tid = store.taslak_ekle(hedef["id"], metin, detayli)

    # Otomatik onay açıksa beklemeden gönder
    if store.ayar("otomatik_onay", "0") == "1":
        return _taslagi_gonder(tid, detayli, None)

    return {
        "tur": "onay_bekliyor",
        "taslak_id": tid,
        "proje": hedef["ad"],
        "proje_id": hedef["id"],
        "ham": metin,
        "detayli": detayli,
        "yanit": f"{hedef['ad']} için görevi hazırladım. Onaylarsan gönderiyorum.",
    }


def _taslagi_gonder(tid: int, detayli: str, model: str | None) -> dict:
    t = store.taslak(tid)
    if not t:
        raise HTTPException(404, "taslak bulunamadı")
    if t["durum"] != "bekliyor":
        raise HTTPException(400, f"bu taslak zaten {t['durum']}")

    if detayli and detayli.strip() != t["detayli"]:
        store.taslak_guncelle(tid, detayli.strip())
    gorev = (detayli or t["detayli"]).strip()

    sonuc = dispatch.gonder(t["proje_id"], gorev, model)
    if "hata" in sonuc:
        store.taslak_durum(tid, "iptal")
        raise HTTPException(400, sonuc["hata"])

    store.taslak_durum(tid, "gonderildi", sonuc["eylem_id"])
    yanit = (f"{sonuc['proje']} projesine gönderdim, {sonuc['model']} "
             f"modeliyle çalışıyor.")
    store.mesaj_ekle("asistan", yanit, t["proje_id"], "claude")
    return {"tur": "gonderildi", "yanit": yanit,
            "eylem_id": sonuc["eylem_id"], "proje": sonuc["proje"],
            "taslak_id": tid}


@app.post("/api/taslak/onayla")
def taslak_onayla(istek: OnayIstek) -> dict:
    return _taslagi_gonder(istek.taslak_id, istek.detayli or "", istek.model)


@app.post("/api/taslak/{tid}/iptal")
def taslak_iptal(tid: int) -> dict:
    t = store.taslak(tid)
    if not t:
        raise HTTPException(404, "taslak bulunamadı")
    store.taslak_durum(tid, "iptal")
    return {"tamam": True}


@app.get("/api/taslaklar")
def taslaklar_getir() -> dict:
    return {"taslaklar": store.bekleyen_taslaklar()}


# ── proje brifingi ─────────────────────────────────────────────────────────


@app.get("/api/projeler/{pid}/brifing")
def brifing_getir(pid: int) -> dict:
    if not store.proje(pid):
        raise HTTPException(404, "proje bulunamadı")
    return {"brifing": brief.yerel_brifing(pid)}


@app.post("/api/projeler/{pid}/brifing/derin")
def brifing_derin(pid: int) -> dict:
    """Projeyi Claude'a inceletip kalıcı brifing çıkar (abonelik kotası)."""
    p = store.proje(pid)
    if not p:
        raise HTTPException(404, "proje bulunamadı")
    sonuc = dispatch.gonder(pid, brief.DERIN_ISTEM)
    if "hata" in sonuc:
        raise HTTPException(400, sonuc["hata"])
    return {"eylem_id": sonuc["eylem_id"], "proje": p["ad"], "tur": "brifing"}


# ── otomatik devam ─────────────────────────────────────────────────────────


@app.post("/api/projeler/{pid}/otomatik")
def otomatik_ayarla(pid: int, istek: OtomatikIstek) -> dict:
    p = store.proje(pid)
    if not p:
        raise HTTPException(404, "proje bulunamadı")
    if istek.acik and not p["var_mi"]:
        raise HTTPException(400, "proje klasörü diskte yok")
    store.otomatik_ayarla(pid, istek.acik, istek.aralik, istek.azami)
    if istek.acik:
        store.mesaj_ekle(
            "sistem",
            f"{p['ad']} için otomatik devam açıldı. "
            f"Her turda sıradaki adımı belirleyip gönderecek.",
            pid, "yerel")
    return {"tamam": True, **auto.durum()}


@app.post("/api/projeler/{pid}/oturum-sifirla")
def oturum_sifirla(pid: int) -> dict:
    """Projenin Claude oturum bağını kopar; sonraki komut sıfırdan başlar.

    Bir oturumda iş yapılamamışsa (örn. izinler kapalıyken) o bağlam
    sürdürüldüğünde Claude denemeden pes edebiliyor. Bu uç o bağı koparır.
    """
    if not store.proje(pid):
        raise HTTPException(404, "proje bulunamadı")
    c = store._conn()
    c.execute("UPDATE projeler SET son_session_id=NULL WHERE id=?", (pid,))
    c.commit()
    return {"tamam": True}


@app.post("/api/toplu/ozet")
def toplu_ozet(istek: TopluIstek) -> dict:
    """Tüm projelere ASISTAN-OZET.md yazdır. Sırayla gider, sınıra uyar."""
    sonuc = bulk.ozet_gorevi(istek.proje_idler)
    if "hata" in sonuc:
        raise HTTPException(400, sonuc["hata"])
    store.mesaj_ekle(
        "sistem",
        f"{sonuc['proje_sayisi']} projede özet güncellemesi başladı. "
        f"Sırayla ilerliyor; kullanım sınırı dolarsa kalanlar atlanacak.",
        None, "yerel")
    return sonuc


@app.post("/api/toplu/komut")
def toplu_komut(istek: TopluIstek) -> dict:
    """Aynı komutu birden çok projeye gönder."""
    if not (istek.gorev or "").strip():
        raise HTTPException(400, "görev boş")
    sonuc = bulk.baslat(istek.gorev.strip(), istek.proje_idler, "Toplu komut")
    if "hata" in sonuc:
        raise HTTPException(400, sonuc["hata"])
    return sonuc


@app.get("/api/toplu")
def toplu_durum() -> dict:
    return bulk.durum()


@app.post("/api/toplu/durdur")
def toplu_durdur() -> dict:
    return bulk.durdur()


@app.get("/api/ozetler")
def ozetler() -> dict:
    """Projelerdeki ASISTAN-OZET.md dosyalarını topla — asistanın sürekli
    okuduğu kaynak budur."""
    from pathlib import Path as _P

    liste = []
    for p in store.projeler(sadece_var=True):
        f = _P(p["yol"], brief.OZET_DOSYA)
        if f.is_file():
            try:
                icerik = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            liste.append({
                "id": p["id"], "ad": p["ad"], "yol": str(f),
                "guncellendi": f.stat().st_mtime,
                "boyut": len(icerik),
                "icerik": icerik,
            })
    return {"ozetler": liste, "sayi": len(liste)}


@app.get("/api/otomatik")
def otomatik_durum() -> dict:
    return auto.durum()



@app.get("/api/rapor")
def rapor(proje_id: int | None = None) -> dict:
    """Model kullanmayan durum raporu — kotadan hiçbir şey götürmez."""
    hedef = store.proje(proje_id) if proje_id else None
    return {"metin": _rapor_metni(hedef), "veri": projects.genel_rapor()}


@app.get("/api/mesajlar")
def mesajlar_getir(limit: int = 60) -> dict:
    return {"mesajlar": store.mesajlar(limit)}


@app.post("/api/sohbet/temizle")
def sohbet_temizle() -> dict:
    store.sohbet_temizle()
    return {"tamam": True}


# ── ses ────────────────────────────────────────────────────────────────────


@app.post("/api/stt")
async def stt(ses: UploadFile = File(...)) -> dict:
    veri = await ses.read()
    if not veri:
        raise HTTPException(400, "boş ses")
    uzanti = Path(ses.filename or "kayit.webm").suffix or ".webm"
    try:
        return speech.yaziya_cevir(veri, uzanti)
    except Exception as e:
        raise HTTPException(500, f"konuşma tanıma hatası: {e}")


@app.post("/api/tts")
def tts(istek: SeslendirIstek) -> Response:
    try:
        mp3 = speech.seslendir(istek.metin, istek.ses)
    except Exception as e:
        raise HTTPException(500, f"seslendirme hatası: {e}")
    if not mp3:
        raise HTTPException(400, "seslendirilecek metin yok")
    return Response(content=mp3, media_type="audio/mpeg")


# ── mentörlük: plan ve görevler ────────────────────────────────────────────


class PlanIstek(BaseModel):
    tur: str = "haftalik"                 # haftalik | aylik
    tarih: str | None = None              # dönemin içindeki herhangi bir gün
    ek_istek: str = ""                    # "bu hafta 3D baskıya ağırlık ver"


class GorevIstek(BaseModel):
    baslik: str
    tarih: str
    saat: str
    sure_dk: int = 60
    proje_id: int | None = None
    ayrinti: str | None = None
    oncelik: int = 2
    zorunlu: bool = True


class ErteleIstek(BaseModel):
    gerekce: str = ""


@app.get("/api/mentor/durum")
def mentor_durum() -> dict:
    return mentor.durum()


@app.get("/api/bugun")
def bugun_getir() -> dict:
    return mentor.bugun_programi()


@app.get("/api/hafta")
def hafta_getir(tarih: str | None = None) -> dict:
    return mentor.hafta_programi(tarih)


@app.get("/api/gorevler")
def gorevler_getir(tarih: str | None = None, bitis: str | None = None,
                   durum: str | None = None, proje_id: int | None = None) -> dict:
    return {"gorevler": store.gorevler(tarih=tarih, bitis=bitis, durum=durum,
                                       proje_id=proje_id)}


@app.post("/api/plan/uret")
def plan_uret(istek: PlanIstek) -> dict:
    if istek.tur not in ("haftalik", "aylik"):
        raise HTTPException(400, "tur 'haftalik' ya da 'aylik' olmalı")
    sonuc = mentor.plan_uret(istek.tur, istek.tarih, istek.ek_istek)
    if not sonuc.get("ok"):
        raise HTTPException(502, sonuc.get("hata", "plan üretilemedi"))
    return sonuc


@app.get("/api/planlar")
def planlar_getir() -> dict:
    return {"planlar": store.planlar()}


@app.post("/api/gorev")
def gorev_ekle(istek: GorevIstek) -> dict:
    gid = store.gorev_ekle(
        baslik=istek.baslik, tarih=istek.tarih, saat=istek.saat,
        sure_dk=istek.sure_dk, proje_id=istek.proje_id, ayrinti=istek.ayrinti,
        oncelik=istek.oncelik, zorunlu=istek.zorunlu, kaynak="kullanici")
    return {"gorev": store.gorev(gid)}


@app.post("/api/gorev/{gid}/basla")
def gorev_basla(gid: int) -> dict:
    if not store.gorev(gid):
        raise HTTPException(404, "görev yok")
    store.gorev_durum(gid, "calisiyor")
    return {"gorev": store.gorev(gid)}


@app.post("/api/gorev/{gid}/tamamla")
def gorev_tamamla(gid: int) -> dict:
    sonuc = mentor.gorev_tamamla(gid)
    if not sonuc.get("ok"):
        raise HTTPException(404, sonuc.get("hata", "görev yok"))
    return {**sonuc, "gorev": store.gorev(gid)}


@app.post("/api/gorev/{gid}/ertele")
def gorev_ertele(gid: int, istek: ErteleIstek) -> dict:
    sonuc = mentor.gorev_ertele(gid, istek.gerekce)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "ertelenemedi"))
    return {**sonuc, "gorev": store.gorev(gid)}


@app.delete("/api/gorev/{gid}")
def gorev_sil(gid: int) -> dict:
    if not store.gorev(gid):
        raise HTTPException(404, "görev yok")
    store.gorev_sil(gid)
    return {"ok": True}


# ── bildirimler ────────────────────────────────────────────────────────────


class BildirimIstek(BaseModel):
    id: int | None = None                 # None = hepsini okundu işaretle


@app.get("/api/bildirimler")
def bildirimler_getir(okunmamis: bool = False, limit: int = 50) -> dict:
    return {"bildirimler": store.bildirimler(sadece_okunmamis=okunmamis,
                                             limit=limit)}


@app.post("/api/bildirimler/okundu")
def bildirim_okundu(istek: BildirimIstek) -> dict:
    store.bildirim_okundu(istek.id)
    return {"ok": True}


# ── yaşam paneli ───────────────────────────────────────────────────────────


class YasamIstek(BaseModel):
    tur: str
    deger: float | None = None
    birim: str | None = None
    detay: str | None = None
    tarih: str | None = None


class MetinIstek(BaseModel):
    metin: str


@app.get("/api/yasam")
def yasam_getir(gun: int = 7) -> dict:
    return yasam.panel(gun)


@app.post("/api/yasam")
def yasam_ekle(istek: YasamIstek) -> dict:
    if istek.tur not in yasam.TURLER:
        raise HTTPException(400, f"bilinmeyen tür: {istek.tur}")
    birim = istek.birim or yasam.TURLER[istek.tur]["birim"]
    kid = store.yasam_ekle(istek.tur, istek.tarih or yasam.bugun(),
                           istek.deger, birim, istek.detay)
    return {"ok": True, "id": kid}


@app.post("/api/yasam/metin")
def yasam_metin(istek: MetinIstek) -> dict:
    sonuc = yasam.metinden_kaydet(istek.metin)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "çözümlenemedi"))
    return sonuc


@app.get("/api/yasam/seri")
def yasam_seri(tur: str, gun: int = 14) -> dict:
    if tur not in yasam.TURLER:
        raise HTTPException(400, f"bilinmeyen tür: {tur}")
    return {"tur": tur, "seri": yasam.gunluk_seri(tur, gun)}


@app.get("/api/yasam/analiz")
def yasam_analiz(gun: int = 14) -> dict:
    return yasam.analiz(gun)


@app.delete("/api/yasam/{kid}")
def yasam_sil(kid: int) -> dict:
    store.yasam_sil(kid)
    return {"ok": True}


# ── proje: harici (kodsuz) projeler ve alan güncelleme ─────────────────────


class HariciProjeIstek(BaseModel):
    ad: str
    tur: str = "baski"                    # baski | yayin | kisisel | diger
    not_metni: str | None = None
    hedef_tarih: str | None = None
    oncelik: int = 2
    ayar: dict | None = None


class ProjeGuncelleIstek(BaseModel):
    ad: str | None = None
    tur: str | None = None
    durum: str | None = None
    hedef_tarih: str | None = None
    oncelik: int | None = None
    not_metni: str | None = None
    etiket: str | None = None


PROJE_TURLERI = ("kod", "baski", "yayin", "kisisel", "diger")


@app.post("/api/proje/harici")
def harici_proje_ekle(istek: HariciProjeIstek) -> dict:
    if istek.tur not in PROJE_TURLERI:
        raise HTTPException(400, f"tür şunlardan biri olmalı: "
                                 f"{', '.join(PROJE_TURLERI)}")
    if not istek.ad.strip():
        raise HTTPException(400, "ad boş olamaz")
    pid = store.harici_proje_ekle(
        istek.ad, istek.tur, istek.not_metni, istek.hedef_tarih,
        istek.oncelik, istek.ayar)
    return {"proje": store.proje(pid)}


@app.patch("/api/proje/{pid}")
def proje_guncelle(pid: int, istek: ProjeGuncelleIstek) -> dict:
    if not store.proje(pid):
        raise HTTPException(404, "proje yok")
    alanlar = {k: v for k, v in istek.model_dump().items() if v is not None}
    if istek.tur and istek.tur not in PROJE_TURLERI:
        raise HTTPException(400, f"bilinmeyen tür: {istek.tur}")
    store.proje_alan_yaz(pid, **alanlar)
    return {"proje": store.proje(pid)}


# ── atölye: yazıcılar ve 3D baskı ──────────────────────────────────────────


class YaziciIstek(BaseModel):
    ad: str
    model: str = ""
    ip: str | None = None                 # yerel ağdaysa
    tur: str = "elle"                     # elle | mqtt | sdcp
    notlar: str | None = None


class BaskiIstek(BaseModel):
    yazici_id: int
    ad: str = "baskı"
    tahmini_dk: int = 240
    proje_id: int | None = None


class BaskiKapatIstek(BaseModel):
    baski_id: int
    durum: str = "bitti"                  # bitti | iptal | hata
    sonraki_adim: bool = True


class SureIstek(BaseModel):
    baski_id: int
    tahmini_dk: int


@app.get("/api/atolye")
def atolye_getir() -> dict:
    """Yazıcılar, üstlerindeki baskılar ve son baskı geçmişi."""
    yazicilar = store.yazicilar()
    for y in yazicilar:
        if y["aktif_baski"]:
            y["aktif_baski"]["ilerleme"] = baski.baski_durum(
                y["aktif_baski"]["id"])
    return {"yazicilar": yazicilar, "gecmis": store.baski_gecmisi(20)}


@app.get("/api/atolye/ara")
def yazici_ara(derin: bool = True) -> dict:
    """Ağdaki olası yazıcıları tara.

    Boş liste yazıcı yok demek değil — cihaz kapalıysa ya da yalnızca
    Anycubic bulutuna bağlıysa yerel ağda görünmez.
    """
    return {"bulunan": baski.yazici_ara(derin)}


@app.post("/api/atolye/yazici")
def yazici_ekle(istek: YaziciIstek) -> dict:
    if not istek.ad.strip():
        raise HTTPException(400, "yazıcı adı boş olamaz")
    yid = store.yazici_ekle(istek.ad, istek.model, istek.ip, istek.tur,
                            istek.notlar)
    return {"yazici": store.yazici(yid)}


@app.delete("/api/atolye/yazici/{yid}")
def yazici_sil(yid: int) -> dict:
    if not store.yazici(yid):
        raise HTTPException(404, "yazıcı yok")
    store.yazici_sil(yid)
    return {"ok": True}


@app.post("/api/baski/basla")
def baski_basla(istek: BaskiIstek) -> dict:
    sonuc = baski.baski_basla(istek.yazici_id, istek.ad, istek.tahmini_dk,
                              istek.proje_id)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "başlatılamadı"))
    return sonuc


@app.get("/api/baski/{bid}")
def baski_durum(bid: int) -> dict:
    d = baski.baski_durum(bid)
    if not d.get("var"):
        raise HTTPException(404, "baskı yok")
    return d


@app.post("/api/baski/bitir")
def baski_bitir(istek: BaskiKapatIstek) -> dict:
    sonuc = baski.baski_bitir(istek.baski_id, istek.durum, istek.sonraki_adim)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "kapatılamadı"))
    return sonuc


@app.post("/api/baski/sure")
def baski_sure(istek: SureIstek) -> dict:
    """Tahmini süre yanlışsa düzelt — bitiş dürtmesi buna göre kayar."""
    if not store.baski(istek.baski_id):
        raise HTTPException(404, "baskı yok")
    store.baski_sure_guncelle(istek.baski_id, istek.tahmini_dk)
    return baski.baski_durum(istek.baski_id)


# ── 3d Projeler klasörü ────────────────────────────────────────────────────


class DosyaIstek(BaseModel):
    dosya_id: int


class DosyaMetinIstek(BaseModel):
    metin: str


@app.get("/api/dosyalar")
def dosyalar_getir() -> dict:
    return klasor.panel()


@app.post("/api/dosyalar/tara")
def dosyalar_tara() -> dict:
    return {"yapilan": klasor.tara(), **klasor.panel()}


@app.post("/api/dosya/bitti")
def dosya_bitti(istek: DosyaIstek) -> dict:
    sonuc = klasor.bitti(istek.dosya_id)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "taşınamadı"))
    return sonuc


@app.post("/api/dosya/geri")
def dosya_geri(istek: DosyaIstek) -> dict:
    sonuc = klasor.geri_al(istek.dosya_id)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "taşınamadı"))
    return sonuc


@app.post("/api/dosya/bitti-metin")
def dosya_bitti_metin(istek: DosyaMetinIstek) -> dict:
    """“anahtarlık bitti” gibi bir cümleden dosyayı bulup taşı.

    Birden fazla aday çıkarsa taşımıyoruz — yanlış dosyayı "bitti" diye
    kaldırmak, hiç kaldırmamaktan kötü.
    """
    adaylar = klasor.ada_gore_bul(istek.metin)
    if not adaylar:
        raise HTTPException(404, "Bu isimde bekleyen bir dosya bulamadım.")
    if len(adaylar) > 1:
        return {"ok": False, "secim_gerekli": True, "adaylar": adaylar[:5]}
    sonuc = klasor.bitti(adaylar[0]["id"])
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "taşınamadı"))
    return {**sonuc, "ok": True}


# ── istatistikler ──────────────────────────────────────────────────────────


@app.get("/api/istatistik")
def istatistik_getir(gun: int = 30) -> dict:
    return istatistik.hepsi(max(1, min(gun, 365)))


# ── işlem günlüğü ──────────────────────────────────────────────────────────


@app.get("/api/gunluk")
def gunluk_getir(seviye: str | None = None, kaynak: str | None = None,
                 olay: str | None = None, ara: str | None = None,
                 saat: int | None = None, limit: int = 200,
                 atla: int = 0) -> dict:
    baslangic = (time.time() - saat * 3600) if saat else None
    return {
        "kayitlar": gunluk.oku(seviye=seviye, kaynak=kaynak, olay=olay,
                               ara=ara, baslangic=baslangic,
                               limit=max(1, min(limit, 1000)), atla=atla),
        "ozet": gunluk.ozet(24),
    }


@app.post("/api/gunluk/temizle")
def gunluk_temizle(gun: int = 60) -> dict:
    return gunluk.temizle(max(1, gun))


# ── yazıcı alanları ve kamera ──────────────────────────────────────────────


class YaziciGuncelleIstek(BaseModel):
    ad: str | None = None
    model: str | None = None
    ip: str | None = None
    notlar: str | None = None
    filament: str | None = None
    filament_renk: str | None = None
    filament_gram: float | None = None
    nozzle: str | None = None
    durum: str | None = None
    kamera_url: str | None = None


@app.patch("/api/atolye/yazici/{yid}")
def yazici_guncelle(yid: int, istek: YaziciGuncelleIstek) -> dict:
    if not store.yazici(yid):
        raise HTTPException(404, "yazıcı yok")
    alanlar = {k: v for k, v in istek.model_dump().items() if v is not None}
    eski = store.yazici(yid)
    store.yazici_alan_yaz(yid, **alanlar)
    if "filament" in alanlar and alanlar["filament"] != eski["filament"]:
        gunluk.bilgi("atolye", "filament_degisti",
                     f"{eski['ad']}: {eski['filament']} → {alanlar['filament']}",
                     yazici_id=yid)
    return {"yazici": store.yazici(yid)}


@app.get("/api/kamera/{yid}")
def kamera(yid: int):
    """Yazıcı kamerasını sunucu üzerinden geçir.

    Telefon yazıcıya doğrudan ulaşamıyor (yazıcı ev ağında, telefon dışarıda);
    akışı buradan aktarınca Tailscale üzerinden de izlenebiliyor.
    """
    y = store.yazici(yid)
    if not y:
        raise HTTPException(404, "yazıcı yok")
    if not y["kamera_url"]:
        raise HTTPException(400, "bu yazıcıda kamera adresi tanımlı değil")

    import httpx

    def akis():
        try:
            with httpx.stream("GET", y["kamera_url"], timeout=20) as r:
                for parca in r.iter_bytes(chunk_size=8192):
                    yield parca
        except httpx.HTTPError as e:
            gunluk.uyari("kamera", "akis_koptu", str(e), yazici_id=yid)
            return

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        akis(),
        media_type="multipart/x-mixed-replace; boundary=frame")


# ── yaşam koçu ─────────────────────────────────────────────────────────────


class AliskanlikIstek(BaseModel):
    ad: str
    tur: str = "gunluk"                   # gunluk | haftalik
    hedef: int = 7                        # haftada kaç kez
    saat: str | None = None               # hatırlatma saati
    aciklama: str | None = None


class IsaretIstek(BaseModel):
    aliskanlik_id: int
    tarih: str | None = None
    yapildi: bool = True
    not_metni: str | None = None


class RituelIstek(BaseModel):
    tur: str                              # sabah | aksam
    tarih: str | None = None


class RituelCevapIstek(BaseModel):
    tur: str
    cevaplar: dict
    tarih: str | None = None


class ButceIstek(BaseModel):
    aylik: float | None = None
    kategoriler: dict | None = None


@app.get("/api/koc")
def koc_paneli() -> dict:
    return koc.panel()


# ── alışkanlıklar ──────────────────────────────────────────────────────────


@app.get("/api/aliskanliklar")
def aliskanliklar_getir(gun: int = 28) -> dict:
    return koc.aliskanlik_paneli(max(7, min(gun, 180)))


@app.post("/api/aliskanlik")
def aliskanlik_ekle(istek: AliskanlikIstek) -> dict:
    if not istek.ad.strip():
        raise HTTPException(400, "ad boş olamaz")
    if istek.tur not in ("gunluk", "haftalik"):
        raise HTTPException(400, "tür 'gunluk' ya da 'haftalik' olmalı")
    aid = store.aliskanlik_ekle(istek.ad, istek.tur, istek.hedef,
                                istek.saat, istek.aciklama)
    return {"aliskanlik": store.aliskanlik(aid)}


@app.post("/api/aliskanlik/isaret")
def aliskanlik_isaretle(istek: IsaretIstek) -> dict:
    if not store.aliskanlik(istek.aliskanlik_id):
        raise HTTPException(404, "alışkanlık yok")
    store.aliskanlik_isaretle(istek.aliskanlik_id,
                              istek.tarih or koc._bugun(),
                              istek.yapildi, istek.not_metni)
    return koc.aliskanlik_paneli(28)


@app.delete("/api/aliskanlik/{aid}")
def aliskanlik_sil(aid: int) -> dict:
    if not store.aliskanlik(aid):
        raise HTTPException(404, "alışkanlık yok")
    store.aliskanlik_sil(aid)
    return {"ok": True}


# ── ritüeller ve haftalık seans ────────────────────────────────────────────


@app.post("/api/rituel")
def rituel_uret(istek: RituelIstek) -> dict:
    sonuc = koc.rituel_uret(istek.tur, istek.tarih)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "üretilemedi"))
    return sonuc


@app.post("/api/rituel/cevap")
def rituel_cevapla(istek: RituelCevapIstek) -> dict:
    sonuc = koc.rituel_cevapla(istek.tur, istek.cevaplar, istek.tarih)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "kaydedilemedi"))
    return sonuc


@app.get("/api/ritueller")
def ritueller_getir(limit: int = 30) -> dict:
    return {"ritueller": store.ritueller(max(1, min(limit, 200)))}


@app.post("/api/seans")
def haftalik_seans(tarih: str | None = None) -> dict:
    return koc.haftalik_seans(tarih)


# ── odak oturumu ───────────────────────────────────────────────────────────


@app.post("/api/odak/{gid}/basla")
def odak_basla(gid: int) -> dict:
    sonuc = koc.odak_basla(gid)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "başlatılamadı"))
    return sonuc


@app.post("/api/odak/{gid}/bitir")
def odak_bitir(gid: int) -> dict:
    sonuc = koc.odak_bitir(gid)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "bitirilemedi"))
    return sonuc


# ── bütçe ve örüntüler ─────────────────────────────────────────────────────


@app.get("/api/butce")
def butce_getir() -> dict:
    return koc.butce_paneli()


@app.post("/api/butce")
def butce_yaz(istek: ButceIstek) -> dict:
    return koc.butce_yaz(istek.aylik, istek.kategoriler)


@app.get("/api/kaliplar")
def kaliplar_getir() -> dict:
    return {
        "erteleme": koc.erteleme_kaliplari(),
        "uyku": koc.uyku_performans(),
        "tahmin": store.tahmin_sapmasi(
            koc._gun_ekle(koc._bugun(), -30), koc._bugun()),
        "kirilan_seriler": koc.kirilan_seriler(),
        "ozet": koc.kaliplar_ozeti(),
    }


# ── yedekleme ──────────────────────────────────────────────────────────────


class GeriYukleIstek(BaseModel):
    ad: str


@app.get("/api/yedek")
def yedek_durum() -> dict:
    return yedek.durum()


@app.post("/api/yedek/al")
def yedek_al() -> dict:
    sonuc = yedek.al()
    if not sonuc.get("ok"):
        raise HTTPException(500, sonuc.get("hata", "yedek alınamadı"))
    return sonuc


@app.post("/api/yedek/disa-aktar")
def yedek_disa_aktar() -> dict:
    sonuc = yedek.disa_aktar()
    if not sonuc.get("ok"):
        raise HTTPException(500, sonuc.get("hata", "döküm alınamadı"))
    return sonuc


@app.post("/api/yedek/geri-yukle")
def yedek_geri_yukle(istek: GeriYukleIstek) -> dict:
    sonuc = yedek.geri_yukle(istek.ad)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "geri yüklenemedi"))
    return sonuc


@app.get("/api/yedek/indir/{ad}")
def yedek_indir(ad: str) -> FileResponse:
    """Yedeği bilgisayarın dışına almak için indir."""
    yol = yedek.KOK / ad
    if not yol.is_file() or yol.parent != yedek.KOK:
        raise HTTPException(404, "yedek yok")
    return FileResponse(yol, filename=ad,
                        media_type="application/octet-stream")


# ── takvim ─────────────────────────────────────────────────────────────────


class TakvimIstek(BaseModel):
    adres: str | None = None


@app.get("/api/takvim")
def takvim_getir(gun: int = 14) -> dict:
    from datetime import date, timedelta

    bugun = date.today()
    bitis = (bugun + timedelta(days=max(1, gun))).isoformat()
    return {
        "tanimli": bool((store.ayar("takvim_ics", "") or "").strip()),
        "randevular": store.randevular(bugun.isoformat(), bitis),
    }


@app.post("/api/takvim/cek")
def takvim_cek(istek: TakvimIstek) -> dict:
    """Adres verilirse önce kaydedilir, sonra çekilir."""
    if istek.adres is not None:
        store.ayar_yaz("takvim_ics", istek.adres.strip())
    sonuc = takvim.cek()
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "çekilemedi"))
    return sonuc


# ── ekran süresi ───────────────────────────────────────────────────────────


@app.get("/api/ekran")
def ekran_getir(gun: int = 7) -> dict:
    return ekran.panel(max(1, min(gun, 90)))


# ── baskı maliyeti ve kâr ──────────────────────────────────────────────────


class MaliyetIstek(BaseModel):
    baski_id: int
    gram: float | None = None
    satis_fiyati: float | None = None
    adet: int | None = None


@app.get("/api/kar")
def kar_getir(gun: int = 30) -> dict:
    return baski.kar_paneli(max(1, min(gun, 365)))


@app.post("/api/baski/maliyet")
def baski_maliyet(istek: MaliyetIstek) -> dict:
    sonuc = baski.maliyet_yaz(istek.baski_id, istek.gram,
                              istek.satis_fiyati, istek.adet)
    if not sonuc.get("ok"):
        raise HTTPException(400, sonuc.get("hata", "hesaplanamadı"))
    return sonuc


# ── akışlı seslendirme ─────────────────────────────────────────────────────
#
# Tek parça seslendirmede kullanıcı bütün metnin bitmesini bekliyor. Burada
# metni cümlelere bölüp ayrı ayrı sunuyoruz: arayüz ilk cümleyi alır almaz
# çalmaya başlıyor, gerisini arkadan indiriyor. Toplam işlem süresi aynı ama
# beklenen süre ilk cümleye iniyor.


class KonusIstek(BaseModel):
    metin: str
    dogal: bool | None = None             # None = ayardaki değer


class ParcaIstek(BaseModel):
    metin: str
    hiz: int = 0
    perde: int = 0
    ses: str | None = None


@app.post("/api/konus")
def konus_parcala(istek: KonusIstek) -> dict:
    """Metni seslendirmeye hazır parçalara böl.

    Doğallaştırma burada bir kez yapılır; arayüz sonra her parçayı
    /api/tts/parca ile ister.
    """
    temiz = speech.seslendirme_icin_temizle(istek.metin)
    if not temiz:
        return {"parcalar": [], "motor": speech.motor()}

    kullan = dogal.acik_mi() if istek.dogal is None else istek.dogal
    hazir = dogal.dogallastir(temiz) if kullan else temiz
    parcalar = dogal.parcala(hazir)
    return {
        "parcalar": [{"sira": i, **p} for i, p in enumerate(parcalar)],
        "motor": speech.motor(),
        "uslup": dogal.uslup(),
        "metin": dogal.isaretleri_at(hazir),
    }


@app.post("/api/tts/parca")
def tts_parca(istek: ParcaIstek) -> Response:
    """Tek cümlelik ses. Akışlı çalmanın yapı taşı."""
    try:
        veri, tur = speech.parca_seslendir(istek.metin, istek.hiz,
                                           istek.perde, istek.ses)
    except Exception as e:
        raise HTTPException(500, f"seslendirme hatası: {e}")
    if not veri:
        raise HTTPException(400, "seslendirilecek metin yok")
    return Response(content=veri, media_type=tur)


# ── ses motoru ve klonlanmış sesler ────────────────────────────────────────


class KlonIstek(BaseModel):
    referans: str


def _ses_adlari() -> dict:
    import json as _j

    try:
        return _j.loads(store.ayar("ses_adlari", "{}") or "{}")
    except _j.JSONDecodeError:
        return {}


@app.get("/api/ses/durum")
def ses_durum() -> dict:
    """Seçilebilir sesler. Tek liste — hazır/klon ayrımı kullanıcıya
    gösterilmiyor, klon servisi kapalıysa arka planda hazır sese düşülüyor."""
    import ses_klon

    d = ses_klon.durum(zorla=True)
    adlar = _ses_adlari()
    sesler = [{"anahtar": r, "ad": adlar.get(r, r),
               "hazir": r in d.get("onbellek", [])}
              for r in d.get("referanslar", [])]
    return {
        "sesler": sesler,
        "secili": store.ayar("klon_referans", "ses1"),
        "servis": d.get("calisiyor", False),
        "motor": speech.motor(),
    }


class SesAdIstek(BaseModel):
    anahtar: str
    ad: str


@app.post("/api/ses/ad")
def ses_ad_yaz(istek: SesAdIstek) -> dict:
    import json as _j

    ad = istek.ad.strip()[:40]
    if not ad:
        raise HTTPException(400, "ad boş olamaz")
    adlar = _ses_adlari()
    adlar[istek.anahtar] = ad
    store.ayar_yaz("ses_adlari", _j.dumps(adlar, ensure_ascii=False))
    return {"ok": True, "adlar": adlar}


class SesSecIstek(BaseModel):
    anahtar: str


@app.post("/api/ses/sec")
def ses_sec(istek: SesSecIstek) -> dict:
    store.ayar_yaz("klon_referans", istek.anahtar)
    store.ayar_yaz("ses_motoru", "klon")
    # Ara sesler ses basina onbelleklenlyor. Yeni sesin klipleri arka planda
    # uretilsin; hazir olana kadar sec() sessizce bos donuyor, yani tur
    # ara ses olmadan ama sorunsuz calisiyor.
    threading.Thread(target=_ara_ses_yenile, daemon=True).start()
    return {"ok": True, "secili": istek.anahtar}


def _ara_ses_yenile() -> None:
    try:
        import ara_ses
        ara_ses.hazirla()
    except Exception as e:
        gunluk.hata("sunucu", "ara_ses_yenile", istisna=e)


@app.post("/api/ara-ses/yenile")
def ara_ses_yenile(zorla: bool = False) -> dict:
    """Ara ses kliplerini yeniden uret. Ses degisince kendiliginden olur."""
    import ara_ses

    return ara_ses.hazirla(zorla=zorla)


@app.post("/api/ses/dene")
def ses_dene(istek: KlonIstek) -> Response:
    """Bir klon sesini örnek cümleyle dinlet — seçmeden önce."""
    import ses_klon

    veri = ses_klon.seslendir(
        "Merhaba. Bugünün programını birlikte gözden geçirelim.",
        referans=istek.referans)
    if not veri:
        raise HTTPException(503, "Ses servisi yanıt vermedi. Çalışıyor mu?")
    return Response(content=veri, media_type="audio/wav")


@app.post("/api/ses/isit")
def ses_isit() -> dict:
    """Modeli ve gömüleri önden yükle — ilk konuşma beklemesin."""
    import ses_klon

    return ses_klon.isit()


@app.websocket("/ws")
async def websocket_kanali(ws: WebSocket) -> None:
    """Telefon ve saat için kalıcı kanal — bkz. kanal.py."""
    await kanal.kanal(ws)


# ── arayüz ─────────────────────────────────────────────────────────────────

if ON_YUZ.is_dir():
    app.mount("/statik", StaticFiles(directory=ON_YUZ), name="statik")

    @app.get("/")
    def anasayfa() -> Response:
        """Arayüzü sun; varlık adreslerine sürüm damgası ekle.

        Tarayıcı, dosya değişse bile eski CSS/JS'i önbellekten sunabiliyordu.
        Adrese dosyanın değişme zamanını iliştirince değişen dosya yeni bir
        adres oluyor ve önbellek kendiliğinden bypass ediliyor.
        """
        html = (ON_YUZ / "index.html").read_text(encoding="utf-8")
        for varlik in ("style.css", "app.js", "panel.js"):
            yol = ON_YUZ / varlik
            if yol.exists():
                html = html.replace(f"/statik/{varlik}",
                                    f"/statik/{varlik}?v={int(yol.stat().st_mtime)}")
        return Response(content=html, media_type="text/html; charset=utf-8")

    @app.get("/sw.js")
    def servis_calisani() -> FileResponse:
        """Servis çalışanı kökten sunulmalı.

        /statik/sw.js altından sunulursa kapsamı /statik/ ile sınırlanır ve
        kök sayfayı yönetemez; uygulama "ana ekrana eklenebilir" sayılmaz.
        """
        return FileResponse(ON_YUZ / "sw.js", media_type="application/javascript")

    @app.get("/manifest.json")
    def manifest() -> FileResponse:
        return FileResponse(ON_YUZ / "manifest.json",
                            media_type="application/manifest+json")


if __name__ == "__main__":
    import uvicorn

    store.kur()
    # Varsayılan yalnızca bu bilgisayar. Telefondan Tailscale üzerinden düz
    # HTTP ile bağlanmak istersen 0.0.0.0 yap — yerel olmayan her istek zaten
    # parola ister, LAN'dan gelen de dahil.
    adres = store.ayar("dinleme_adresi", "127.0.0.1") or "127.0.0.1"
    print(f"[asistan] dinleniyor: {adres}:8770")
    uvicorn.run(app, host=adres, port=8770, log_level="warning")
