"""Niyet çözümleme — kullanıcı ne demek istedi?

Eski hâli düzenli ifadelerle çalışıyordu: "5 saat uyudum" yakalanıyor,
"11'den şimdiye kadar uyudum" yakalanmıyordu. Yakalanmayan her cümle proje
komutu sayılıp "hangi projede çalıştırayım?" sorusuna dönüşüyordu — yani
anlamadığı her şeyi iş emri sanıyordu.

Artık **anlama işini model yapıyor**, kalıp yok. Kod yalnızca iki şeyi
üstleniyor:

* **Aritmetik.** Model "23:00'ten 07:00'a uyudum" cümlesinden saatleri
  çıkarır; kaç saat ettiğini kod hesaplar. Modelin sayı uydurmasına gerek
  bırakmıyoruz.
* **Makullük denetimi.** "40 saat uyudum" gibi çıktılar elenir. Yanlış veri,
  veri olmamasından kötüdür.

En önemli kural: **şüphede kalırsak proje komutu DEĞİL, sohbet sayarız.**
Anlaşılmayan bir cümleyi iş emrine çevirmek, sohbete çevirmekten çok daha
can sıkıcı.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import store

# "şimdiye kadar", "şu ana kadar", "hâlâ" — bitiş saati şu an demek.
_SIMDI = re.compile(r"şimdi|şu ?an|hala|hâlâ", re.IGNORECASE)

GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi",
          "Pazar"]

TALIMAT = """Kullanıcının cümlesini anla ve sınıflandır.

NİYETLER

"yasam"  — Kendi durumunu bildiriyor: uyku, harcama, yemek, spor, su, ruh hâli.
  "dün gece on birde yattım sabah yedide kalktım" → uyku
  "markete uğradım iki yüz lira gitti" → harcama
  "bugün kendimi bitkin hissediyorum" → ruh

"duzen"  — Çalışma düzenini anlatıyor (vardiya, mesai, izin günleri).
  "bir gün yirmi dört saat çalışıyorum iki gün izinliyim"
  "hafta içi dokuz altı çalışıyorum"  (gunler: 1-5, Pazartesi=1)
  "cumartesi pazar izinliyim"        (gunler: 1-5)

"gorev"  — Var olan bir görevle ilgili bir şey söylüyor.
  eylem "tamamla" : "anahtarlığı bitirdim", "şunu iki saat önce tamamladım",
                    "tasarımı saat üçte bitirdim"
  eylem "duzenle" : "anahtarlık görevini ikiye al", "süresini iki saat yap",
                    "başlığını şöyle değiştir", "yarına al"
  eylem "ekle"    : "yarın ona bir görev ekle"
  eylem "ertele"  : "bunu yarına ertele"

"dosya"  — 3D baskı dosyasının bittiğini söylüyor.
  "anahtarlık baskısı bitti"

"proje"  — Bir yazılım projesinde İŞ YAPILMASINI istiyor.
  "mobil uygulamaya karanlık tema ekle", "şu hatayı düzelt"

"planla" — Bugünün programını yeniden düzenlemeni istiyor.
  "saat dörde kadar çalışacağım"        → bugunu_ayarla, bitis "16:00"
  "kaçan görevleri tekrar sıraya al"    → kacanlari_sirala
  "yarınkileri öne alabilirsin"         → ileriden_al, gun 1
  Cümlede BİRDEN FAZLA planlama isteği varsa hepsini "eylemler"
  listesine sırayla koy. Tek istek varsa da liste kullanabilirsin.
  "saat dörde kadar çalışacağım, yarınkileri öne al"
      → eylemler: [{"eylem":"bugunu_ayarla","bitis":"16:00"},
                   {"eylem":"ileriden_al","gun":1}]

"soru"   — Durum soruyor ya da sohbet ediyor.
  "bugün ne var", "nasılsın", "bu hafta nasıl gidiyor"

KURALLAR

- Emin değilsen "soru" de. ASLA tahminle "proje" deme.
- HER kayıtta "deger" alanı ZORUNLUDUR. Boş bırakma, null yazma.
- Uykuda yatma ve kalkma saati verilmişse AYRICA baslangic ve bitis yaz;
  süreyi ben hesaplarım. Saat verilmemişse yalnızca deger yeter.
  "altı saat uyudum"              → deger: 6
  "on birde yattım yedide kalktım" → baslangic: "23:00", bitis: "07:00", deger: 8
  "on birden şimdiye kadar uyudum" → baslangic: "11:00", bitis: ŞU ANKİ SAAT,
                                     deger: aradaki fark
- Diğer türlerde deger alanını KENDİ BİRİMİNDE ver:
    uyku    → saat    (7.5)
    spor    → DAKİKA  ("bir saat yürüdüm" → 60)
    harcama → TL      (200)
    su      → litre   (2)
    ogun    → adet    (1)
    ruh     → 1-10 arası (yorgun/kötü ≈ 3, iyi ≈ 8)
- Kendini nasıl hissettiğini söylüyorsa bu "ruh" kaydıdır: "yorgunum",
  "bugün çok iyiyim", "moralim bozuk".
- "gorev" niyetinde eylem alanı ZORUNLU: tamamla / duzenle / ekle / ertele.
  "iki saat önce" gibi ifadeleri dakika_once olarak ver (120).
  Saat söylenmişse saat alanına yaz.
- Cümlede olmayan şeyi uydurma.

YALNIZCA JSON döndür. Biçimler:

{"niyet":"yasam","kayitlar":[{"tur":"uyku","deger":8,"baslangic":"23:00","bitis":"07:00"}]}
{"niyet":"yasam","kayitlar":[{"tur":"harcama","deger":200,"detay":"market"}]}
{"niyet":"duzen","tur":"vardiya","calisma_gun":1,"izin_gun":2,"vardiya_saat":24}
{"niyet":"duzen","tur":"sabit","baslangic":"09:00","bitis":"18:00","gunler":[1,2,3,4,5]}
{"niyet":"gorev","eylem":"tamamla","baslik":"anahtarlık tasarımı",
 "dakika_once":120}
{"niyet":"gorev","eylem":"tamamla","baslik":"tasarım","saat":"15:00"}
{"niyet":"gorev","eylem":"duzenle","baslik":"anahtarlık",
 "yeni_saat":"14:00","yeni_sure_dk":120,"yeni_baslik":null,"yeni_tarih":null}
{"niyet":"gorev","eylem":"ekle","baslik":"faturaları öde","saat":"10:00",
 "tarih":"2026-09-08","sure_dk":30}
{"niyet":"gorev","eylem":"ertele","baslik":"anahtarlık"}
{"niyet":"dosya","ad":"anahtarlık"}
{"niyet":"proje","proje":"Mobil","is":"karanlık tema ekle"}
{"niyet":"planla","eylem":"bugunu_ayarla","bitis":"16:00"}
{"niyet":"planla","eylem":"kacanlari_sirala"}
{"niyet":"planla","eylem":"ileriden_al","gun":1}
{"niyet":"planla","eylemler":[{"eylem":"bugunu_ayarla","bitis":"16:00"},
 {"eylem":"ileriden_al","gun":1}]}
{"niyet":"soru"}"""


# Model bazen saçma değer üretiyor. Sınırların dışını almıyoruz.
SINIRLAR = {"uyku": (0.5, 16), "harcama": (1, 500000), "ogun": (1, 10),
            "spor": (1, 600), "su": (0.1, 10), "ruh": (1, 10)}


PLANLAMA_EYLEMLERI = ("bugunu_ayarla", "kacanlari_sirala", "ileriden_al")


def _planlama_gecerli(e) -> bool:
    """Tek bir planlama eylemi uygulanabilir mi?"""
    if not isinstance(e, dict):
        return False
    if e.get("eylem") not in PLANLAMA_EYLEMLERI:
        return False
    if e["eylem"] == "bugunu_ayarla" and _saat_dk(e.get("bitis")) is None:
        return False
    return True


def _makul(tur: str, deger: float) -> bool:
    alt, ust = SINIRLAR.get(tur, (0, 1e9))
    return alt <= deger <= ust


def _saat_dk(deger) -> int | None:
    """'23:00' ya da '23' → dakika. Bozuksa None."""
    if deger is None:
        return None
    m = re.match(r"^\s*(\d{1,2})(?:[:.](\d{1,2}))?\s*$", str(deger))
    if not m:
        return None
    s = int(m.group(1))
    d = int(m.group(2) or 0)
    if not (0 <= s <= 23 and 0 <= d <= 59):
        return None
    return s * 60 + d


def sure_hesapla(baslangic, bitis) -> float | None:
    """İki saat arasındaki süreyi saat cinsinden hesapla.

    Gece yarısını geçen aralıklar için bitiş başlangıçtan küçükse 24 saat
    ekleniyor — "23'ten 7'ye" sekiz saat eder, eksi on altı değil.
    """
    bas, bit = _saat_dk(baslangic), _saat_dk(bitis)
    if bas is None or bit is None:
        return None
    return round(((bit - bas) % (24 * 60)) / 60, 2)


def _json_bul(metin: str) -> dict | None:
    if not metin:
        return None
    metin = re.sub(r"^```(?:json)?|```$", "", metin.strip(),
                   flags=re.MULTILINE).strip()
    bas, son = metin.find("{"), metin.rfind("}")
    if bas == -1 or son <= bas:
        return None
    try:
        d = json.loads(metin[bas:son + 1])
        return d if isinstance(d, dict) else None
    except json.JSONDecodeError:
        return None


YAZIYLA = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6,
           "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10, "yarım": 0.5,
           "onbir": 11, "on bir": 11, "oniki": 12, "on iki": 12}


def _metinden_sayi(metin: str, tur: str) -> float | None:
    """Son çare: cümledeki ilk makul sayıyı al.

    Model ``deger`` alanını boş bırakırsa kaydı tamamen kaybetmek yerine
    cümleden okumayı deniyoruz. Makullük denetimi zaten arkadan geliyor.
    """
    m = re.search(r"(\d+(?:[.,]\d+)?)", metin)
    if m:
        try:
            d = float(m.group(1).replace(",", "."))
            if _makul(tur, d):
                return d
        except ValueError:
            pass
    kucuk = metin.casefold()
    for kelime, sayi in YAZIYLA.items():
        if kelime in kucuk and _makul(tur, sayi):
            return float(sayi)
    return None


def _yasam_temizle(d: dict, metin: str) -> dict:
    """Model çıktısındaki yaşam kayıtlarını doğrula ve süreleri hesapla."""
    import yasam

    temiz = []
    for k in d.get("kayitlar") or []:
        if not isinstance(k, dict) or k.get("tur") not in yasam.TURLER:
            continue
        tur = k["tur"]

        deger = None
        # Saat aralığını yalnızca uykuda kabul ediyoruz. Modele spor için de
        # aralık verme serbestisi tanıyınca "bir saat yürüdüm" cümlesinden
        # altı saatlik aralık uydurup 360 dakika yazabiliyor.
        if tur == "uyku":
            bas, bit = k.get("baslangic"), k.get("bitis")
            # "şimdiye kadar" — modelin şu anki saati doğru yazması güvenilir
            # değil, bitişi kendimiz koyuyoruz. Saat hesabı zaten kodun işi.
            if bas is not None and (bit is None or _SIMDI.search(metin)):
                bit = datetime.now().strftime("%H:%M")
            if bas is not None and bit is not None:
                deger = sure_hesapla(bas, bit)
        if deger is None:
            try:
                deger = float(str(k.get("deger", "")).replace(",", "."))
            except (TypeError, ValueError):
                # Model deger alanını boş bıraktıysa cümledeki sayıya bak.
                # Sık görülen bir tökezleme; kaydı komple düşürmek yerine
                # kurtarmayı deniyoruz.
                deger = _metinden_sayi(metin, tur)
                if deger is None:
                    continue

        if not _makul(tur, deger):
            continue
        temiz.append({
            "tur": tur, "deger": deger,
            "birim": yasam.TURLER[tur]["birim"],
            "detay": str(k.get("detay") or metin)[:200],
            "tarih": yasam._tarih_coz(metin),
        })

    if not temiz:
        import gunluk

        gunluk.uyari("niyet", "yasam_reddedildi", metin[:120],
                     ham_kayitlar=d.get("kayitlar"))
        return {"niyet": "soru"}                # yaşam dedi ama kayıt çıkmadı
    return {"niyet": "yasam", "kayitlar": temiz}


def _duzen_temizle(d: dict) -> dict:
    """Çalışma düzeni bildirimini doğrula."""
    tur = d.get("tur")
    if tur == "vardiya":
        try:
            calisma = int(d.get("calisma_gun", 0))
            izin = int(d.get("izin_gun", 0))
            saat = float(d.get("vardiya_saat", 24))
        except (TypeError, ValueError):
            return {"niyet": "soru"}
        if not (1 <= calisma <= 14 and 0 <= izin <= 14 and 1 <= saat <= 24):
            return {"niyet": "soru"}
        return {"niyet": "duzen", "tur": "vardiya", "calisma_gun": calisma,
                "izin_gun": izin, "vardiya_saat": saat}

    if tur == "sabit":
        if _saat_dk(d.get("baslangic")) is None or _saat_dk(d.get("bitis")) is None:
            return {"niyet": "soru"}
        gunler = d.get("gunler")
        if isinstance(gunler, list):
            gunler = sorted({int(g) for g in gunler
                             if str(g).isdigit() and 1 <= int(g) <= 7})
        return {"niyet": "duzen", "tur": "sabit",
                "baslangic": str(d["baslangic"]), "bitis": str(d["bitis"]),
                "gunler": gunler or None}

    return {"niyet": "soru"}


def coz(metin: str, projeler: list[dict] | None = None) -> dict:
    """Cümlenin niyetini çöz.

    Anlama tamamen modelde. Kod yalnızca aritmetiği ve makullüğü denetler.
    """
    metin = (metin or "").strip()
    if not metin:
        return {"niyet": "soru"}
    if store.ayar("akilli_niyet", "1") != "1":
        return {"niyet": "proje", "kaynak": "kapali"}

    import brain

    simdi = datetime.now()
    projeler = projeler or []
    baglam = (
        f"Şu an: {simdi.strftime('%d.%m.%Y %H:%M')}, "
        f"{GUNLER[simdi.weekday()]}\n"
        f"Projeler: {', '.join(p['ad'] for p in projeler[:25]) or 'yok'}\n\n"
        f"Cümle: {metin}"
    )

    try:
        yanit = brain.yerel_sohbet(
            [{"role": "user", "content": baglam}],
            model=store.ayar("niyet_modeli", "qwen3.5:9b-tr"),
            sistem=TALIMAT, azami_token=400, sicaklik=0.1)
    except Exception:
        return {"niyet": "soru", "kaynak": "hata"}

    d = _json_bul(yanit or "")
    if not d or d.get("niyet") not in ("yasam", "duzen", "gorev", "dosya",
                                       "proje", "planla", "soru"):
        import gunluk

        gunluk.uyari("niyet", "cozulemedi", metin[:120],
                     ham=(yanit or "")[:400])
        return {"niyet": "soru", "kaynak": "cozulemedi"}

    if d["niyet"] == "yasam":
        return {**_yasam_temizle(d, metin), "kaynak": "model"}
    if d["niyet"] == "duzen":
        return {**_duzen_temizle(d), "kaynak": "model"}
    if d["niyet"] == "gorev":
        if d.get("eylem") not in ("tamamla", "duzenle", "ekle", "ertele"):
            return {"niyet": "soru", "kaynak": "model"}
        return {**d, "kaynak": "model"}

    if d["niyet"] == "planla":
        # Tek eylem de liste olarak taşınıyor: "saat dörde kadar
        # çalışacağım, yarınkileri öne al" gibi cümlelerde kullanıcı tek
        # nefeste iki şey istiyor ve yarısını yapmak yapmamaktan kötü.
        ham = d.get("eylemler")
        if not isinstance(ham, list):
            ham = [d]
        eylemler = [e for e in ham if _planlama_gecerli(e)]
        if not eylemler:
            return {"niyet": "soru", "kaynak": "model"}
        return {"niyet": "planla", "eylemler": eylemler,
                # Tek eylemli eski biçimi de koruyoruz; çağıranların hepsini
                # değiştirmek gerekmesin.
                **eylemler[0], "kaynak": "model"}

    if d["niyet"] == "dosya":
        import klasor

        adaylar = klasor.ada_gore_bul(str(d.get("ad") or metin))
        if len(adaylar) == 1:
            return {"niyet": "dosya", "dosya_id": adaylar[0]["id"],
                    "ad": adaylar[0]["ad"], "kaynak": "model"}
        return {"niyet": "dosya", "adaylar": adaylar[:5], "kaynak": "model"}

    return {**d, "kaynak": "model"}
