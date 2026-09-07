"""Yaşam koçu — ritüeller, alışkanlıklar, örüntü analizi, odak ve bütçe.

Mentör (``mentor.py``) takvimi yönetir: ne zaman ne yapılacak. Burası ise
**yorum** katmanı: veriye bakıp yüzüne söyler.

Ton bilerek sert. Varsayılan ``koc_tonu = sert``:
  * Yumuşatma yok, "ama olsun" yok, teselli yok.
  * Övgü yalnızca sayı varsa ve hak edildiyse.
  * Bahane tekrar ediyorsa bahane olarak adlandırılır.
  * Kişiye değil davranışa yüklenir — hakaret değil, hesap sorma.

Ayarlardan ``dengeli`` ya da ``yumusak`` seçilebilir; talimat ona göre değişir.
"""

from __future__ import annotations

import json
import time
from datetime import date, timedelta

import brain
import gunluk
import mentor
import store

# ── ton ────────────────────────────────────────────────────────────────────

TONLAR = {
    "sert": """Sert bir koç gibi konuş.
- Yumuşatma. "Olabilir", "sorun değil", "kendine yüklenme" deme.
- Rakamı önce söyle, yorumu sonra. Veri yoksa yorum yapma.
- Tekrar eden bahaneyi bahane olarak adlandır.
- Kişiye değil davranışa yüklen. Aşağılama, alay etme, hakaret etme.
- Cümleler kısa. Süsleme yok.
- Sonunda tek bir somut talep bırak — bugün yapılabilir bir şey.""",

    "dengeli": """Dürüst ama dengeli bir koç gibi konuş.
- Önce ne oldu, sonra ne yapılmalı.
- İyi gideni de kötü gideni de aynı netlikte söyle.
- Tek bir somut öneriyle bitir.""",

    "yumusak": """Destekleyici bir koç gibi konuş.
- Önce çabayı gör, sonra eksiği söyle.
- Suçlama, cesaretlendir.
- Tek bir küçük adım öner.""",
}


def ton() -> str:
    return TONLAR.get(store.ayar("koc_tonu", "sert"), TONLAR["sert"])


def _bugun() -> str:
    return date.today().isoformat()


def _gun_ekle(tarih: str, n: int) -> str:
    return (date.fromisoformat(tarih) + timedelta(days=n)).isoformat()


# ── alışkanlıklar ve seriler ───────────────────────────────────────────────


def seri_hesapla(gunler: set[str], bitis: str | None = None) -> int:
    """Bugünden (ya da dünden) geriye kesintisiz kaç gün.

    Bugün henüz işaretlenmediyse seri kırılmış sayılmaz — gün bitmedi.
    """
    bitis = bitis or _bugun()
    seri, imlec = 0, bitis
    if imlec not in gunler:
        imlec = _gun_ekle(imlec, -1)        # bugüne daha vakit var
    while imlec in gunler:
        seri += 1
        imlec = _gun_ekle(imlec, -1)
    return seri


def aliskanlik_paneli(gun: int = 28) -> dict:
    bitis = _bugun()
    baslangic = _gun_ekle(bitis, -(gun - 1))
    liste = []
    for a in store.aliskanliklar():
        gunler = store.aliskanlik_gunleri(a["id"])
        donem = [g for g in gunler if baslangic <= g <= bitis]
        hafta_bas = _gun_ekle(bitis, -6)
        bu_hafta = len([g for g in gunler if hafta_bas <= g <= bitis])
        liste.append({
            **a,
            "seri": seri_hesapla(gunler, bitis),
            "en_uzun_seri": _en_uzun_seri(gunler),
            "bugun": bitis in gunler,
            "donem_sayi": len(donem),
            "donem_yuzde": round(100 * len(donem) / gun),
            "bu_hafta": bu_hafta,
            "hedef_tuttu": bu_hafta >= a["hedef"],
            "takvim": [{"tarih": _gun_ekle(baslangic, i),
                        "yapildi": _gun_ekle(baslangic, i) in gunler}
                       for i in range(gun)],
        })
    return {"gun": gun, "baslangic": baslangic, "bitis": bitis,
            "aliskanliklar": liste}


def _en_uzun_seri(gunler: set[str]) -> int:
    if not gunler:
        return 0
    sirali = sorted(gunler)
    en_uzun = mevcut = 1
    for onceki, simdi in zip(sirali, sirali[1:]):
        mevcut = mevcut + 1 if _gun_ekle(onceki, 1) == simdi else 1
        en_uzun = max(en_uzun, mevcut)
    return en_uzun


def kirilan_seriler() -> list[dict]:
    """Dün yapılmamış ve serisi kırılmak üzere olan alışkanlıklar."""
    dun = _gun_ekle(_bugun(), -1)
    kirilanlar = []
    for a in store.aliskanliklar():
        gunler = store.aliskanlik_gunleri(a["id"])
        if a["tur"] != "gunluk" or dun in gunler or _bugun() in gunler:
            continue
        seri = seri_hesapla(gunler, _gun_ekle(dun, -1))
        if seri >= 2:
            kirilanlar.append({**a, "kirilan_seri": seri})
    return kirilanlar


# ── örüntü analizi ─────────────────────────────────────────────────────────


def erteleme_kaliplari(gun: int = 21) -> list[dict]:
    """Sürekli ertelenen/kaçırılan projeler — koçun sorgulayacağı yer."""
    bitis = _bugun()
    baslangic = _gun_ekle(bitis, -(gun - 1))
    rows = store._conn().execute(
        "SELECT p.id, p.ad, p.tur, p.durum, "
        "  COUNT(g.id) toplam, "
        "  SUM(g.durum='kacirildi') kacan, "
        "  SUM(g.erteleme) erteleme, "
        "  SUM(g.durum='tamam') tamam "
        "FROM gorevler g JOIN projeler p ON p.id=g.proje_id "
        "WHERE g.tarih BETWEEN ? AND ? AND g.durum!='iptal' "
        "GROUP BY p.id HAVING toplam >= 2",
        (baslangic, bitis)).fetchall()

    kaliplar = []
    for r in rows:
        kacan, erteleme, toplam = r["kacan"] or 0, r["erteleme"] or 0, r["toplam"]
        sorun = kacan + erteleme
        if sorun < 3 or sorun < toplam * 0.5:
            continue
        kaliplar.append({
            "proje_id": r["id"], "ad": r["ad"], "tur": r["tur"],
            "toplam": toplam, "kacan": kacan, "erteleme": erteleme,
            "tamam": r["tamam"] or 0,
            "yuzde": round(100 * sorun / toplam),
        })
    return sorted(kaliplar, key=lambda x: -x["yuzde"])


def uyku_performans(gun: int = 30) -> dict:
    """Az uyunan günlerde uyum düşüyor mu? Veri yetmezse yorum yok."""
    bitis = _bugun()
    baslangic = _gun_ekle(bitis, -(gun - 1))
    esik = float(store.ayar("uyku_hedef", "7.5") or 7.5)

    uyku = {}
    for k in store.yasam_kayitlari(baslangic, bitis, tur="uyku"):
        uyku[k["tarih"]] = uyku.get(k["tarih"], 0) + (k["deger"] or 0)

    az, cok = [], []
    for tarih, saat in uyku.items():
        gorevler = [g for g in store.gorevler(tarih=tarih)
                    if g["durum"] != "iptal"]
        if not gorevler:
            continue
        uyum = 100 * sum(1 for g in gorevler if g["durum"] == "tamam") / len(gorevler)
        (az if saat < esik else cok).append(uyum)

    if len(az) < 3 or len(cok) < 3:
        return {"yeterli_veri": False, "az_gun": len(az), "bol_gun": len(cok),
                "esik": esik}

    az_ort, cok_ort = sum(az) / len(az), sum(cok) / len(cok)
    return {
        "yeterli_veri": True, "esik": esik,
        "az_uyku_uyum": round(az_ort), "bol_uyku_uyum": round(cok_ort),
        "az_gun": len(az), "bol_gun": len(cok),
        "fark": round(cok_ort - az_ort),
    }


def kaliplar_ozeti() -> str:
    """Mentörün plan yaparken göreceği örüntü notu."""
    satirlar = []
    e = erteleme_kaliplari()
    if e:
        satirlar.append("ERTELEME ÖRÜNTÜSÜ:")
        for k in e[:4]:
            satirlar.append(
                f"- {k['ad']}: {k['toplam']} görevin %{k['yuzde']}'i kaçtı ya da "
                f"ertelendi ({k['kacan']} kaçan, {k['erteleme']} erteleme). "
                "Bu projeyi ya erken saate al ya da beklemeye almayı öner.")

    u = uyku_performans()
    if u.get("yeterli_veri") and u["fark"] >= 10:
        satirlar.append(
            f"UYKU ETKİSİ: {u['esik']} saatin altında uyunan günlerde uyum "
            f"%{u['az_uyku_uyum']}, üstünde %{u['bol_uyku_uyum']}. "
            "Az uyunan güne ağır blok koyma.")

    try:
        import ekran

        e = ekran.koc_ozeti()
        if e:
            satirlar.append(e)
    except Exception:
        pass

    t = store.tahmin_sapmasi(_gun_ekle(_bugun(), -30), _bugun())
    if t["sayi"] >= 5 and t["oran"] and t["oran"] > 1.15:
        satirlar.append(
            f"SÜRE TAHMİNİ: gerçekte tahminin {t['oran']}x'i kadar sürüyor "
            f"({t['sayi']} ölçüm). Süreleri buna göre uzat.")

    return "\n".join(satirlar)


# ── odak oturumu ───────────────────────────────────────────────────────────


def odak_basla(gid: int) -> dict:
    g = store.gorev(gid)
    if not g:
        return {"ok": False, "hata": "Görev yok."}
    if g["durum"] == "tamam":
        return {"ok": False, "hata": "Bu görev zaten bitti."}
    store.gorev_durum(gid, "calisiyor")
    gunluk.bilgi("koc", "odak_basladi", g["baslik"], gorev_id=gid,
                 tahmin_dk=g["sure_dk"])
    return {"ok": True, "gorev": store.gorev(gid)}


def odak_bitir(gid: int) -> dict:
    """Görevi kapat ve gerçekte ne kadar sürdüğünü kaydet."""
    g = store.gorev(gid)
    if not g:
        return {"ok": False, "hata": "Görev yok."}

    gercek = None
    if g["baslatildi"]:
        gercek = max(1, round((time.time() - g["baslatildi"]) / 60))
        store.gorev_gercek_sure(gid, gercek)

    sonuc = mentor.gorev_tamamla(gid)
    yorum = ""
    if gercek and g["sure_dk"]:
        oran = gercek / g["sure_dk"]
        # %30 aşım zaten anlamlı bir sapma; 1.5 eşiği tam sınırda kalanı
        # kaçırıyordu.
        if oran >= 1.3:
            yorum = (f"{g['sure_dk']} dk demiştin, {gercek} dk sürdü. "
                     "Tahminin gerçekçi değil.")
        elif oran < 0.6:
            yorum = (f"{g['sure_dk']} dk ayırmıştın, {gercek} dk'da bitti. "
                     "Bu iş için fazla yer ayırıyorsun.")
    gunluk.bilgi("koc", "odak_bitti", g["baslik"], gorev_id=gid,
                 tahmin_dk=g["sure_dk"], gercek_dk=gercek)
    return {**sonuc, "gercek_dk": gercek, "yorum": yorum}


# ── bütçe ──────────────────────────────────────────────────────────────────

KATEGORI_ANAHTARLARI = {
    "yeme": ("kahve", "yemek", "restoran", "lokanta", "cafe", "kafe",
             "starbucks", "börek", "tost", "pizza", "burger", "çay"),
    "market": ("market", "bakkal", "migros", "a101", "bim", "şok", "carrefour"),
    "ulasim": ("benzin", "mazot", "yakıt", "otobüs", "metro", "taksi",
               "uber", "bilet", "otopark", "hgs"),
    "atolye": ("filament", "nozzle", "yazıcı", "pla", "abs", "petg", "reçine"),
    "abonelik": ("abonelik", "netflix", "spotify", "icloud", "domain",
                 "sunucu", "hosting"),
    "saglik": ("eczane", "ilaç", "doktor", "hastane", "diş"),
    "fatura": ("fatura", "elektrik", "su", "doğalgaz", "internet", "kira"),
}


def kategori_bul(metin: str) -> str:
    d = (metin or "").casefold()
    for kategori, anahtarlar in KATEGORI_ANAHTARLARI.items():
        if any(a in d for a in anahtarlar):
            return kategori
    return "diğer"


def _butceler() -> dict:
    try:
        return json.loads(store.ayar("butce_json", "{}") or "{}")
    except json.JSONDecodeError:
        return {}


def butce_paneli() -> dict:
    bugun = _bugun()
    ay_bas = bugun[:8] + "01"
    kategoriler = store.harcama_kategorileri(ay_bas, bugun)
    butceler = _butceler()
    try:
        aylik = float(store.ayar("butce_aylik", "0") or 0)
    except ValueError:
        aylik = 0.0

    toplam = round(sum(kategoriler.values()), 2)
    gun_sayisi = int(bugun[8:10])
    gunluk_ort = round(toplam / gun_sayisi, 2) if gun_sayisi else 0

    satirlar = []
    for k, v in kategoriler.items():
        hedef = butceler.get(k)
        satirlar.append({
            "kategori": k, "harcanan": v, "butce": hedef,
            "yuzde": round(100 * v / hedef) if hedef else None,
            "asildi": bool(hedef and v > hedef),
        })

    return {
        "ay_basi": ay_bas, "bugun": bugun,
        "toplam": toplam, "aylik_butce": aylik,
        "kalan": round(aylik - toplam, 2) if aylik else None,
        "yuzde": round(100 * toplam / aylik) if aylik else None,
        "gunluk_ortalama": gunluk_ort,
        "ay_sonu_tahmini": round(gunluk_ort * 30, 2),
        "kategoriler": satirlar,
    }


def butce_yaz(aylik: float | None = None,
              kategoriler: dict | None = None) -> dict:
    if aylik is not None:
        store.ayar_yaz("butce_aylik", str(max(0, float(aylik))))
    if kategoriler is not None:
        temiz = {k: float(v) for k, v in kategoriler.items()
                 if str(v).strip() not in ("", "0")}
        store.ayar_yaz("butce_json", json.dumps(temiz, ensure_ascii=False))
    return butce_paneli()


# ── ritüeller ──────────────────────────────────────────────────────────────


SABAH_TALIMATI = """Kullanıcının gününü açıyorsun.

Elinde bugünün programı, dünkü karne ve yaşam verisi var. Şunu yaz:
- Bugünün ilk işi ve saati.
- Dün bir şey kaçtıysa tek cümlede hatırlat.
- Uykusu az olduysa günü nasıl kurması gerektiğini söyle.

En fazla 4 cümle. Madde işareti kullanma, konuşur gibi yaz — sesli okunacak."""

AKSAM_TALIMATI = """Kullanıcının gününü kapatıyorsun.

Elinde bugünün karnesi, kaçan işler ve yaşam verisi var. Şunu yaz:
- Bugün ne oldu, rakamla.
- Kaçan iş varsa sebebini sorgula; gerekçe tekrar ediyorsa bunu söyle.
- Yarın için tek bir somut değişiklik iste.

En fazla 5 cümle. Madde işareti kullanma, konuşur gibi yaz."""

SEANS_TALIMATI = """Haftalık koçluk değerlendirmesi yazıyorsun.

Elinde haftanın karnesi, erteleme örüntüleri, alışkanlık serileri, uyku ve
harcama verisi var. Şunu yaz:
- Haftanın özeti, rakamla. Süslemeden.
- Tekrar eden örüntüyü açıkça adlandır: hangi proje sürekli kaçıyor, hangi
  alışkanlık tutmadı, hangi bahane kaç kez tekrarlandı.
- Bir şey gerçekten yapılmıyorsa "bu projeyi arşive al" demekten çekinme.
- Önümüzdeki hafta için en fazla üç somut değişiklik.

En fazla 12 cümle. Kısa paragraflar."""


def _gun_verisi(tarih: str) -> str:
    k = mentor.gunun_karnesi(tarih)
    gorevler = store.gorevler(tarih=tarih)
    satirlar = [
        f"TARİH: {tarih} {mentor.gun_adi(tarih)}",
        f"KARNE: {k['tamam']}/{k['toplam']} tamam, {k['kacirildi']} kaçtı, "
        f"{k['kalan']} kaldı",
    ]
    if gorevler:
        satirlar.append("GÖREVLER:")
        for g in gorevler:
            satirlar.append(
                f"- {g['saat']} {g['baslik']} [{g['durum']}]"
                + (f" — gerekçe: {g['gerekce']}" if g["gerekce"] else "")
                + (f" ({g['erteleme']}. erteleme)" if g["erteleme"] else ""))

    yasam = store.yasam_ozet(tarih, tarih)
    if yasam:
        satirlar.append("YAŞAM: " + ", ".join(
            f"{t} {d['toplam']}" for t, d in yasam.items()))

    ap = aliskanlik_paneli(7)["aliskanliklar"]
    if ap:
        satirlar.append("ALIŞKANLIKLAR: " + ", ".join(
            f"{a['ad']} {'✓' if a['bugun'] else '✗'} (seri {a['seri']})"
            for a in ap))
    return "\n".join(satirlar)


def rituel_uret(tur: str, tarih: str | None = None) -> dict:
    """Sabah ya da akşam ritüel metnini üret ve kaydet."""
    tarih = tarih or _bugun()
    if tur not in ("sabah", "aksam"):
        return {"ok": False, "hata": "tür 'sabah' ya da 'aksam' olmalı"}

    baglam = _gun_verisi(tarih)
    if tur == "sabah":
        dun = mentor.gunun_karnesi(_gun_ekle(tarih, -1))
        baglam += (f"\nDÜNKÜ KARNE: {dun['tamam']}/{dun['toplam']}, "
                   f"{dun['kacirildi']} kaçtı")
    kalip = kaliplar_ozeti()
    if kalip:
        baglam += "\n\n" + kalip

    talimat = (SABAH_TALIMATI if tur == "sabah" else AKSAM_TALIMATI) \
        + "\n\n" + ton()

    yanit = brain.yerel_once(
        baglam, talimat,
        lambda m: m.strip() if m and 40 < len(m.strip()) < 1400 else None,
        azami_token=500, zaman_asimi=240)

    metin = (yanit.get("sonuc") or yanit.get("metin") or "").strip()
    sorular = (["Bugünün tek kritik işi ne?"] if tur == "sabah"
               else ["Bugün ne iyi gitti?", "Ne kaçtı, neden?",
                     "Yarın neyi değiştiriyorsun?"])
    store.rituel_kaydet(tarih, tur,
                        {"metin": metin, "sorular": sorular, "cevaplar": {},
                         "kaynak": yanit.get("kaynak")})
    gunluk.bilgi("koc", f"{tur}_rituel", tarih, kaynak=yanit.get("kaynak"))
    return {"ok": True, "tarih": tarih, "tur": tur, "metin": metin,
            "sorular": sorular, "kaynak": yanit.get("kaynak")}


def rituel_cevapla(tur: str, cevaplar: dict, tarih: str | None = None) -> dict:
    tarih = tarih or _bugun()
    r = store.rituel(tarih, tur)
    if not r:
        return {"ok": False, "hata": "Bu ritüel henüz üretilmedi."}
    veri = r["veri"]
    veri["cevaplar"] = {**veri.get("cevaplar", {}), **cevaplar}
    store.rituel_kaydet(tarih, tur, veri, tamamlandi=True)
    gunluk.bilgi("koc", f"{tur}_cevaplandi", tarih)
    return {"ok": True, "rituel": store.rituel(tarih, tur)}


# ── haftalık seans ─────────────────────────────────────────────────────────


def haftalik_seans(tarih: str | None = None) -> dict:
    baslangic, bitis = mentor.hafta_sinirlari(tarih)
    ist = store.gorev_istatistik(baslangic, bitis)

    satirlar = [
        f"HAFTA: {baslangic} – {bitis}",
        f"KARNE: {ist['tamam']}/{ist['toplam']} tamam "
        f"(uyum %{ist['uyum'] if ist['uyum'] is not None else '—'}), "
        f"{ist['kacirildi']} kaçtı, {ist['ertelenen']} ertelendi",
    ]

    e = erteleme_kaliplari()
    if e:
        satirlar.append("ERTELENEN PROJELER:")
        for k in e[:5]:
            satirlar.append(f"- {k['ad']}: %{k['yuzde']} kaçtı/ertelendi "
                            f"({k['tamam']}/{k['toplam']} tamam)")

    ap = aliskanlik_paneli(28)["aliskanliklar"]
    if ap:
        satirlar.append("ALIŞKANLIKLAR:")
        for a in ap:
            satirlar.append(
                f"- {a['ad']}: bu hafta {a['bu_hafta']}/{a['hedef']}, "
                f"seri {a['seri']}, en uzun {a['en_uzun_seri']}")

    u = uyku_performans()
    if u.get("yeterli_veri"):
        satirlar.append(
            f"UYKU: {u['esik']} saat altında uyum %{u['az_uyku_uyum']} "
            f"({u['az_gun']} gün), üstünde %{u['bol_uyku_uyum']} "
            f"({u['bol_gun']} gün)")

    b = butce_paneli()
    if b["toplam"]:
        ust = ", ".join(f"{k['kategori']} {k['harcanan']}"
                        for k in b["kategoriler"][:4])
        satirlar.append(f"HARCAMA (bu ay): {b['toplam']} TL — {ust}"
                        + (f"; aylık bütçe {b['aylik_butce']}, "
                           f"%{b['yuzde']} kullanıldı" if b["aylik_butce"] else ""))

    t = store.tahmin_sapmasi(baslangic, bitis)
    if t["sayi"]:
        satirlar.append(f"SÜRE: {t['sayi']} ölçümde tahminin {t['oran']}x'i")

    yanit = brain.yerel_once(
        "\n".join(satirlar), SEANS_TALIMATI + "\n\n" + ton(),
        lambda m: m.strip() if m and 120 < len(m.strip()) < 3000 else None,
        azami_token=900, zaman_asimi=300)

    metin = (yanit.get("sonuc") or yanit.get("metin") or "").strip()
    store.rituel_kaydet(bitis, "seans",
                        {"metin": metin, "veri": satirlar,
                         "kaynak": yanit.get("kaynak")}, tamamlandi=True)
    store.bildirim_ekle("Haftalık değerlendirme hazır",
                        metin.split("\n")[0][:200], tur="bilgi")
    gunluk.bilgi("koc", "haftalik_seans", f"{baslangic} – {bitis}",
                 kaynak=yanit.get("kaynak"))
    return {"ok": True, "baslangic": baslangic, "bitis": bitis,
            "metin": metin, "veri": satirlar, "kaynak": yanit.get("kaynak")}


# ── denetim (mentör döngüsünden çağrılır) ──────────────────────────────────


def denetle() -> list[str]:
    yapilan: list[str] = []
    a = store.tum_ayarlar()
    t, s = _bugun(), mentor.su_an()
    s_dk = mentor._dk(s)
    r = mentor.ritim()

    # Sabah ritüeli
    if (a.get("sabah_rituel", "1") == "1"
            and mentor._dk(r["baslangic"]) <= s_dk < mentor._dk(r["baslangic"]) + 30
            and not store.rituel(t, "sabah")):
        d = rituel_uret("sabah", t)
        if d.get("ok") and d["metin"]:
            store.bildirim_ekle("Günaydın", d["metin"][:400], tur="gun_basi")
            yapilan.append("sabah ritüeli")

    # Akşam ritüeli
    if (a.get("aksam_rituel", "1") == "1" and s_dk >= mentor._dk(r["bitis"])
            and not store.rituel(t, "aksam")):
        d = rituel_uret("aksam", t)
        if d.get("ok") and d["metin"]:
            store.bildirim_ekle("Günün değerlendirmesi", d["metin"][:400],
                                tur="gun_sonu")
            yapilan.append("akşam ritüeli")

    # Alışkanlık hatırlatmaları
    for al in store.aliskanliklar():
        if not al["saat"] or al["tur"] != "gunluk":
            continue
        fark = mentor._dk(al["saat"]) - s_dk
        if 0 < fark <= 10 and t not in store.aliskanlik_gunleri(al["id"]):
            if not _bildirim_var(f"aliskanlik:{al['id']}", t):
                store.bildirim_ekle(f"Alışkanlık: {al['ad']}",
                                    f"{al['saat']} — sıra bunda.",
                                    tur=f"aliskanlik:{al['id']}")
                yapilan.append(f"alışkanlık hatırlatma: {al['ad']}")

    # Kırılan seriler
    for k in kirilan_seriler():
        if not _bildirim_var(f"seri:{k['id']}", t):
            store.bildirim_ekle(
                f"Zincir kırıldı: {k['ad']}",
                f"{k['kirilan_seri']} günlük seriyi dün kırdın. "
                "Bugün yaparsan yeniden başlar, yapmazsan alışkanlık değil "
                "niyet olarak kalır.", tur=f"seri:{k['id']}")
            yapilan.append(f"seri uyarısı: {k['ad']}")

    # Haftalık seans
    try:
        seans_gun = int(a.get("haftalik_seans_gun", "7"))
    except ValueError:
        seans_gun = 7
    _, hafta_son = mentor.hafta_sinirlari(t)
    if (date.fromisoformat(t).weekday() + 1 == seans_gun
            and s_dk >= mentor._dk(r["bitis"])
            and not store.rituel(hafta_son, "seans")):
        haftalik_seans(t)
        yapilan.append("haftalık seans")

    return yapilan


def _bildirim_var(tur: str, tarih: str) -> bool:
    gun_basi = time.mktime(date.fromisoformat(tarih).timetuple())
    return any(b["tur"] == tur and b["zaman"] >= gun_basi
               for b in store.bildirimler(limit=200))


def panel() -> dict:
    t = _bugun()
    return {
        "tarih": t,
        "sabah": store.rituel(t, "sabah"),
        "aksam": store.rituel(t, "aksam"),
        "aliskanliklar": aliskanlik_paneli(28),
        "butce": butce_paneli(),
        "kaliplar": {
            "erteleme": erteleme_kaliplari(),
            "uyku": uyku_performans(),
            "tahmin": store.tahmin_sapmasi(_gun_ekle(t, -30), t),
        },
        "son_seans": next((r for r in store.ritueller(20)
                           if r["tur"] == "seans"), None),
    }
