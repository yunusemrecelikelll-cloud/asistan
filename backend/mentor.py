"""Mentör — planı yapan, günü bloklara bölen ve gevşemeye izin vermeyen katman.

Tasarım ilkesi: **zamansız görev yoktur.** Her işin tarihi, saati ve süresi
olur. "Bir ara yaparım" diyebileceğin bir alan bırakmıyoruz, çünkü kaçışın
büyük kısmı oradan oluyor.

Kaçırma mekaniği:
  görev saati + tolerans geçti ve hâlâ başlanmadıysa
      → görev "kaçırıldı" damgası yer
      → bildirim düşer
      → zorunlu görevse otomatik bir TELAFİ görevi ilk boş slota yazılır
        (öncelik 1) — iş kaybolmaz, sadece ertelenir ve karneye yansır.

Plan üretimi önce yerel modelle denenir (ücretsiz); çıktı doğrulamadan
geçmezse Claude'a yükseltilir. Hangi yolun kullanıldığı günlüğe ve arayüze
yazılır ki maliyetin nereden geldiği görünsün.

Planı kim yazarsa yazsın, takvime oturtmayı, çakışma çözümünü ve denetimi
burası yapar — modele güvenmeyiz, doğrularız.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, datetime, timedelta

import brain
import gunluk
import olay
import store

# ── zaman yardımcıları ─────────────────────────────────────────────────────


def bugun() -> str:
    return date.today().isoformat()


def su_an() -> str:
    return datetime.now().strftime("%H:%M")


def _dk(saat: str) -> int:
    """'09:30' → 570. Bozuk girdi 0 döner."""
    try:
        s, d = str(saat).split(":")[:2]
        return max(0, min(24 * 60 - 1, int(s) * 60 + int(d)))
    except (ValueError, AttributeError):
        return 0


def _saat(dk: int) -> str:
    dk = max(0, min(24 * 60 - 1, int(dk)))
    return f"{dk // 60:02d}:{dk % 60:02d}"


def _gun_ekle(tarih: str, n: int) -> str:
    return (date.fromisoformat(tarih) + timedelta(days=n)).isoformat()


def hafta_sinirlari(tarih: str | None = None) -> tuple[str, str]:
    """Pazartesi–Pazar."""
    g = date.fromisoformat(tarih or bugun())
    pzt = g - timedelta(days=g.weekday())
    return pzt.isoformat(), (pzt + timedelta(days=6)).isoformat()


def ay_sinirlari(tarih: str | None = None) -> tuple[str, str]:
    g = date.fromisoformat(tarih or bugun())
    ilk = g.replace(day=1)
    son = (ilk + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return ilk.isoformat(), son.isoformat()


GUN_ADI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma",
           "Cumartesi", "Pazar"]


def gun_adi(tarih: str) -> str:
    return GUN_ADI[date.fromisoformat(tarih).weekday()]


# ── ritim (kullanıcının günü) ──────────────────────────────────────────────


def ritim() -> dict:
    a = store.tum_ayarlar()

    def sayi(anahtar: str, varsayilan: int) -> int:
        try:
            return int(float(a.get(anahtar, varsayilan)))
        except (TypeError, ValueError):
            return varsayilan

    return {
        "acik": a.get("mentor_acik", "1") == "1",
        "baslangic": a.get("gun_baslangic", "09:00"),
        "bitis": a.get("gun_bitis", "22:00"),
        "blok": sayi("odak_blok_dk", 90),
        "ara": sayi("ara_dk", 20),
        "azami_blok": sayi("gunluk_azami_blok", 5),
        "sertlik": a.get("mentor_sertlik", "yuksek"),
        "tolerans": sayi("gecikme_toleransi_dk", 20),
        "model": a.get("mentor_modeli", "sonnet"),
        "plan_gun": sayi("plan_gun", 1),
        "uyku_hedef": float(a.get("uyku_hedef", "7.5") or 7.5),
    }


# ── takvim yerleştirme ─────────────────────────────────────────────────────


def _dolu_araliklar(tarih: str, haric: int | None = None) -> list[tuple[int, int]]:
    """O günün işgal edilmiş dakika aralıkları — görevler ve randevular."""
    araliklar = []
    for g in store.gorevler(tarih=tarih):
        if g["durum"] in ("iptal", "kacirildi") or g["id"] == haric:
            continue
        bas = _dk(g["saat"])
        araliklar.append((bas, bas + max(5, g["sure_dk"])))

    # Dış takvimdeki randevular da doludur; üstlerine görev yazmıyoruz.
    try:
        import takvim

        araliklar += takvim.dolu_araliklar(tarih)
    except Exception:
        pass
    return sorted(araliklar)


def gun_penceresi(tarih: str) -> tuple[int, int] | None:
    """O günün çalışma penceresi, dakika cinsinden. None = o gün kapalı.

    Vardiyalı düzende nöbet günü tamamen kapalıdır; oraya blok yazmak planı
    daha kurulurken çöpe atmak olur.
    """
    try:
        import duzen

        p = duzen.pencere(tarih)
        if p is None:
            return None
        return _dk(p[0]), _dk(p[1])
    except Exception:
        r = ritim()
        return _dk(r["baslangic"]), _dk(r["bitis"])


def bos_slot(tarih: str, sure_dk: int, tercih: str | None = None,
             haric: int | None = None) -> str | None:
    """Verilen günde ``sure_dk`` dakikalık ilk uygun saati bul.

    ``tercih`` varsa oradan başlar; dolu ise ileri kayar. Gün penceresine
    sığmıyorsa None döner — çağıran bir sonraki güne bakar.
    """
    r = ritim()
    pencere = gun_penceresi(tarih)
    if pencere is None:
        return None                     # nöbet günü
    gun_bas, gun_bit = pencere
    sure_dk = max(5, int(sure_dk))
    dolu = _dolu_araliklar(tarih, haric=haric)

    aday = max(gun_bas, _dk(tercih) if tercih else gun_bas)
    if tarih == bugun():
        # Geçmiş saate görev koyma; 5 dakika nefes payı bırak.
        aday = max(aday, _dk(su_an()) + 5)

    while aday + sure_dk <= gun_bit:
        cakisma = next(((b, s) for b, s in dolu if aday < s and b < aday + sure_dk),
                       None)
        if cakisma is None:
            return _saat(aday)
        aday = cakisma[1] + r["ara"]
    return None


def ilk_uygun_gun(sure_dk: int, baslangic_tarih: str | None = None,
                  azami_gun: int = 7) -> tuple[str, str] | None:
    """Bugünden başlayarak ilk boş (gün, saat) çiftini bul."""
    t = baslangic_tarih or bugun()
    r = ritim()
    for i in range(azami_gun):
        gun = _gun_ekle(t, i)
        if gun_penceresi(gun) is None:
            continue                    # nöbet günü
        if len(_dolu_araliklar(gun)) >= r["azami_blok"]:
            continue
        s = bos_slot(gun, sure_dk)
        if s:
            return gun, s
    return None


# ── plan üretimi ───────────────────────────────────────────────────────────


PLAN_TALIMATI = """Sen kullanıcının kişisel mentörüsün. Arkadaşı değil, koçusun.

Görevin, verilen projelere ve kullanıcının günlük ritmine bakarak KAÇAMAYACAĞI
somut bir program çıkarmak.

Kurallar:
- Her görevin tarihi, saati ve süresi olacak. "Bir ara yap", "vakit bulunca"
  gibi zamansız görev YAZMA.
- Görev başlığı somut ve bittiği anlaşılır olacak: "anahtarlık tasarımını
  bitirip baskıya ver" gibi. "Projeye bak", "biraz ilerlet", "üzerinde çalış"
  gibi ölçülemeyen görev YAZMA.
- Bir görev tek oturumda bitebilecek büyüklükte olsun.
- Öncelik: 1 kritik (kaçırılamaz), 2 normal, 3 esnek. Her güne en az bir
  öncelik 1 görev koy.
- Kaçırma geçmişine bak: sürekli kaçırılan iş varsa onu günün EN ERKEN saatine
  al ve öncelik 1 yap. Enerji en yüksekken yapılsın, gün içinde erimesin.
- Hedef tarihi yaklaşan projelere ağırlık ver, uzak olanları seyrelt.
- Gerçekçi ol. Günü tıka basa doldurma — tutmayan plan bahane üretir, bahane
  de gevşemenin kapısıdır. Ama boş gün de bırakma.
- Her projeye değil, bu dönemde gerçekten ilerlemesi gerekenlere odaklan.

YALNIZCA şu biçimde JSON döndür, başka hiçbir şey yazma:

{
  "cerceve": "Bu dönemin ana teması ve neden böyle kurgulandığı — 2-3 cümle.",
  "gorevler": [
    {
      "proje": "projenin tam adı ya da null",
      "baslik": "somut görev",
      "ayrinti": "nasıl yapılacak, neyle bitmiş sayılır",
      "tarih": "YYYY-MM-DD",
      "saat": "HH:MM",
      "sure_dk": 90,
      "oncelik": 1,
      "zorunlu": true
    }
  ]
}"""


def _baglam(baslangic: str, bitis: str) -> str:
    """Modele verilecek durum özeti."""
    r = ritim()
    satirlar = [
        f"DÖNEM: {baslangic} – {bitis} "
        f"({gun_adi(baslangic)}'den {gun_adi(bitis)}'e)",
        f"BUGÜN: {bugun()} {gun_adi(bugun())}, saat {su_an()}",
        "",
        "KULLANICININ RİTMİ:",
        f"- Çalışma penceresi: {r['baslangic']} – {r['bitis']}",
        f"- Tipik odak bloğu: {r['blok']} dk, bloklar arası {r['ara']} dk ara",
        f"- Günde en fazla {r['azami_blok']} odak bloğu",
        f"- Sertlik: {r['sertlik']}",
        "",
        "PROJELER:",
    ]

    for p in store.aktif_projeler():
        parcalar = [f"- [{p['tur']}] {p['ad']} (öncelik {p['oncelik']})"]
        if p["hedef_tarih"]:
            parcalar.append(f"hedef {p['hedef_tarih']}")
        satirlar.append("  ".join(parcalar))
        if p["not_metni"]:
            satirlar.append(f"    not: {p['not_metni'][:300]}")
        if p["ozet"]:
            satirlar.append(f"    durum: {p['ozet'][:400]}")

    # Geçen dönemin karnesi — mentörün sıkılaştırma yapabilmesi için.
    onceki_bas = _gun_ekle(baslangic, -(date.fromisoformat(bitis)
                                        - date.fromisoformat(baslangic)).days - 1)
    ist = store.gorev_istatistik(onceki_bas, _gun_ekle(baslangic, -1))
    if ist["toplam"]:
        satirlar += [
            "",
            "GEÇEN DÖNEMİN KARNESİ:",
            f"- {ist['tamam']}/{ist['toplam']} görev tamamlandı "
            f"(uyum %{ist['uyum']})",
            f"- {ist['kacirildi']} görev kaçırıldı, "
            f"{ist['ertelenen']} görev ertelendi",
        ]
        kacan = [g["baslik"] for g in store.gorevler(
            tarih=onceki_bas, bitis=_gun_ekle(baslangic, -1), durum="kacirildi")]
        if kacan:
            satirlar.append("- Kaçırılanlar: " + "; ".join(kacan[:8]))

    # Atölye durumu — hangi yazıcı boş, hangisi ne zaman boşalıyor.
    try:
        import baski

        atolye = baski.atolye_ozeti()
        if atolye:
            satirlar += ["", atolye]
    except Exception:                       # atölye yoksa plan yine çıksın
        pass

    # Çalışma düzeni — nöbet günlerine iş yazılmasın.
    try:
        import duzen

        dz = duzen.plan_ozeti(
            baslangic,
            (date.fromisoformat(bitis) - date.fromisoformat(baslangic)).days + 1)
        if dz:
            satirlar += ["", dz]
    except Exception:
        pass

    # Takvimdeki gerçek randevular — plan bunların üstüne yazılmasın.
    try:
        import takvim

        t = takvim.ozet(
            (date.fromisoformat(bitis) - date.fromisoformat(bugun())).days + 1)
        if t:
            satirlar += ["", t]
    except Exception:
        pass

    # Koçun bulduğu örüntüler — plan bunlara göre sıkılaşsın.
    try:
        import koc

        kalip = koc.kaliplar_ozeti()
        if kalip:
            satirlar += ["", kalip]
    except Exception:
        pass

    # Yaşam verisi — uykusuz haftaya ağır plan yazmasın.
    yasam = store.yasam_ozet(_gun_ekle(bugun(), -7), bugun())
    if yasam:
        satirlar.append("")
        satirlar.append("SON 7 GÜN (yaşam):")
        if "uyku" in yasam:
            satirlar.append(f"- Ortalama uyku: {yasam['uyku']['ortalama']} saat "
                            f"(hedef {r['uyku_hedef']})")
        if "harcama" in yasam:
            satirlar.append(f"- Toplam harcama: {yasam['harcama']['toplam']} TL")
        if "spor" in yasam:
            satirlar.append(f"- Spor: {yasam['spor']['sayi']} kez")

    return "\n".join(satirlar)


def _json_bul(metin: str) -> dict | None:
    """Modelin yanıtından ilk JSON nesnesini çıkar."""
    if not metin:
        return None
    metin = re.sub(r"^```(?:json)?|```$", "", metin.strip(),
                   flags=re.MULTILINE).strip()
    try:
        return json.loads(metin)
    except json.JSONDecodeError:
        pass
    bas = metin.find("{")
    while bas != -1:
        derinlik = 0
        for i in range(bas, len(metin)):
            if metin[i] == "{":
                derinlik += 1
            elif metin[i] == "}":
                derinlik -= 1
                if derinlik == 0:
                    try:
                        return json.loads(metin[bas:i + 1])
                    except json.JSONDecodeError:
                        break
        bas = metin.find("{", bas + 1)
    return None


def _proje_bul(ad: str | None, projeler: list[dict]) -> int | None:
    if not ad:
        return None
    ad_k = str(ad).strip().lower()
    for p in projeler:
        if p["ad"].strip().lower() == ad_k:
            return p["id"]
    for p in projeler:
        if ad_k in p["ad"].lower() or p["ad"].lower() in ad_k:
            return p["id"]
    return None


def _gorevleri_yerlestir(ham: list[dict], plan_id: int,
                         baslangic: str, bitis: str) -> tuple[int, list[str]]:
    """Modelin verdiği görevleri doğrula ve takvime oturt.

    Modele güvenmiyoruz: tarihi dönem dışına taşan, gün penceresine sığmayan
    ya da çakışan görevleri buradan düzeltiyoruz.
    """
    projeler = store.aktif_projeler()
    r = ritim()
    yazilan, uyarilar = 0, []
    gun_sayaci: dict[str, int] = {}

    for h in ham:
        if not isinstance(h, dict):
            continue
        baslik = str(h.get("baslik") or "").strip()
        if not baslik:
            continue

        tarih = str(h.get("tarih") or "").strip()
        try:
            date.fromisoformat(tarih)
        except ValueError:
            tarih = max(baslangic, bugun())
        if tarih < baslangic:
            tarih = baslangic
        if tarih > bitis:
            uyarilar.append(f"“{baslik}” dönem dışına düşmüştü, son güne alındı.")
            tarih = bitis
        if tarih < bugun():
            tarih = bugun()

        sure = h.get("sure_dk") or 60
        try:
            sure = max(15, min(int(sure), r["blok"] * 2))
        except (TypeError, ValueError):
            sure = 60
        # Geçmişte benzer iş ne kadar sürdüyse tahmini ona yaklaştır.
        sure = sure_oner(baslik, sure, _proje_bul(h.get("proje"), projeler))

        # Günlük blok sınırını aşma; aşarsa sonraki uygun güne taşı.
        hedef_gun, hedef_saat = tarih, str(h.get("saat") or r["baslangic"])
        for _ in range(14):
            if (gun_sayaci.get(hedef_gun, 0) >= r["azami_blok"]
                    or gun_penceresi(hedef_gun) is None):
                hedef_gun, hedef_saat = _gun_ekle(hedef_gun, 1), r["baslangic"]
                continue
            slot = bos_slot(hedef_gun, sure, tercih=hedef_saat)
            if slot:
                hedef_saat = slot
                break
            hedef_gun, hedef_saat = _gun_ekle(hedef_gun, 1), r["baslangic"]
        else:
            uyarilar.append(f"“{baslik}” için yer bulunamadı, atlandı.")
            continue

        if hedef_gun != tarih:
            uyarilar.append(f"“{baslik}” {tarih} dolu olduğu için "
                            f"{hedef_gun} gününe alındı.")

        try:
            oncelik = max(1, min(3, int(h.get("oncelik") or 2)))
        except (TypeError, ValueError):
            oncelik = 2

        store.gorev_ekle(
            baslik=baslik,
            tarih=hedef_gun,
            saat=hedef_saat,
            sure_dk=sure,
            proje_id=_proje_bul(h.get("proje"), projeler),
            plan_id=plan_id,
            ayrinti=(h.get("ayrinti") or None),
            oncelik=oncelik,
            zorunlu=bool(h.get("zorunlu", True)),
            kaynak="ai",
        )
        gun_sayaci[hedef_gun] = gun_sayaci.get(hedef_gun, 0) + 1
        yazilan += 1

    return yazilan, uyarilar


def plan_uret(tur: str = "haftalik", tarih: str | None = None,
              ek_istek: str = "") -> dict:
    """Dönem planını üret ve görevleri takvime yaz.

    Aynı dönem tekrar planlanırsa o döneme ait AI görevlerinden henüz
    başlanmamış olanlar silinir; tamamlanan ve kaçırılan geçmiş korunur.
    """
    baslangic, bitis = (hafta_sinirlari(tarih) if tur == "haftalik"
                        else ay_sinirlari(tarih))
    if not store.aktif_projeler():
        return {"ok": False, "hata": "Aktif proje yok. Önce proje ekle."}

    istem = _baglam(baslangic, bitis)
    if ek_istek.strip():
        istem += "\n\nKULLANICININ BU DÖNEM İÇİN ÖZEL İSTEĞİ:\n" + ek_istek.strip()
    istem += ("\n\nYukarıdaki duruma göre "
              f"{'bu haftanın' if tur == 'haftalik' else 'bu ayın'} planını çıkar.")

    def _dogrula(metin: str):
        """Plan işe yarar mı?

        Yerel model bu kapıdan geçemezse iş Claude'a yükseltiliyor. Ölçüt
        bilerek düşük tutuldu: JSON geçerli olsun, görevlerin başlığı, tarihi
        ve saati bulunsun, üç görevden az olmasın — bir haftayı taşımayan
        plan zaten plan değil.
        """
        d = _json_bul(metin or "")
        if not d or not isinstance(d.get("gorevler"), list):
            return None
        gecerli = [g for g in d["gorevler"]
                   if isinstance(g, dict)
                   and str(g.get("baslik") or "").strip()
                   and str(g.get("tarih") or "").strip()
                   and str(g.get("saat") or "").strip()]
        if len(gecerli) < 3:
            return None
        d["gorevler"] = gecerli
        return d

    yanit = brain.yerel_once(istem, PLAN_TALIMATI, _dogrula,
                             claude_model=ritim()["model"],
                             azami_token=3000, zaman_asimi=420)
    veri = yanit.get("sonuc")
    if not veri:
        gunluk.uyari("mentor", "plan_uretilemedi",
                     "model geçerli plan vermedi",
                     kaynak=yanit.get("kaynak"))
        return {"ok": False, "hata": "Plan üretilemedi, model geçerli JSON vermedi.",
                "ham": (yanit.get("metin") or "")[:600]}

    plan_id = store.plan_kaydet(tur, baslangic, bitis,
                                str(veri.get("cerceve") or "").strip())

    # Bu döneme ait, henüz başlanmamış AI görevlerini temizle (yeniden planlama).
    for g in store.gorevler(tarih=baslangic, bitis=bitis, durum="bekliyor"):
        if g["kaynak"] == "ai" and not g["telafi_eden"]:
            store.gorev_sil(g["id"])

    yazilan, uyarilar = _gorevleri_yerlestir(veri["gorevler"], plan_id,
                                             baslangic, bitis)
    gunluk.bilgi("mentor", "plan_uretildi",
                 f"{tur}: {baslangic} – {bitis}", plan_id=plan_id,
                 gorev_sayisi=yazilan, uyarilar=uyarilar,
                 maliyet=yanit.get("maliyet"), kaynak=yanit.get("kaynak"),
                 yerel_hata=yanit.get("yerel_hata"))
    store.bildirim_ekle(
        f"{'Haftalık' if tur == 'haftalik' else 'Aylık'} plan hazır",
        f"{baslangic} – {bitis} arası {yazilan} görev planlandı.",
        tur="bilgi")
    return {"ok": True, "plan_id": plan_id, "tur": tur, "baslangic": baslangic,
            "bitis": bitis, "gorev_sayisi": yazilan, "uyarilar": uyarilar,
            "cerceve": veri.get("cerceve", ""), "maliyet": yanit.get("maliyet"),
            "kaynak": yanit.get("kaynak")}


# ── kaçırma ve telafi ──────────────────────────────────────────────────────


def _telafi_olustur(g: dict) -> int | None:
    """Kaçırılan zorunlu görevi ilk boş slota yeniden yaz."""
    if not g["zorunlu"]:
        return None
    yer = ilk_uygun_gun(g["sure_dk"], azami_gun=4)
    if not yer:
        return None
    gun, saat = yer
    # Telafinin telafisi de yazılabiliyor; önek üst üste binmesin.
    baslik = g["baslik"]
    if not baslik.startswith("[TELAFİ]"):
        baslik = f"[TELAFİ] {baslik}"
    return store.gorev_ekle(
        baslik=baslik,
        tarih=gun, saat=saat, sure_dk=g["sure_dk"],
        proje_id=g["proje_id"], plan_id=g["plan_id"], ayrinti=g["ayrinti"],
        oncelik=1, zorunlu=True, kaynak="ai", telafi_eden=g["id"],
    )


def gorev_tamamla(gid: int) -> dict:
    g = store.gorev(gid)
    if not g:
        return {"ok": False, "hata": "Görev bulunamadı."}
    store.gorev_durum(gid, "tamam")
    ist = gunun_karnesi(g["tarih"])
    if ist["kalan"] == 0 and ist["toplam"] > 0:
        store.bildirim_ekle("Gün temiz",
                            f"{g['tarih']} günündeki {ist['toplam']} görevin "
                            "hepsi bitti.", tur="kutlama")
    return {"ok": True, "karne": ist}


def gorev_ertele(gid: int, gerekce: str = "") -> dict:
    """Erteleme gerekçe ister ve karneye yazılır — bedava değildir."""
    g = store.gorev(gid)
    if not g:
        return {"ok": False, "hata": "Görev bulunamadı."}
    r = ritim()
    if r["sertlik"] == "yuksek" and not gerekce.strip():
        return {"ok": False, "hata": "Erteleme için gerekçe yazman gerekiyor."}
    yer = ilk_uygun_gun(g["sure_dk"], azami_gun=4)
    if not yer:
        return {"ok": False, "hata": "Önümüzdeki 4 günde boş yer yok. "
                                     "Ya bugün yap ya bir şeyi iptal et."}
    gun, saat = yer
    store.gorev_tasi(gid, gun, saat, gerekce.strip() or None)
    if g["erteleme"] >= 1:
        store.bildirim_ekle(
            "Bu görevi tekrar erteledin",
            f"“{g['baslik']}” {g['erteleme'] + 1}. kez ertelendi. "
            "Ya bugün bitir ya da projeyi beklemeye al — arada kalması "
            "hepsini yavaşlatıyor.", tur="uyari", gorev_id=gid)
    return {"ok": True, "tarih": gun, "saat": saat,
            "erteleme": g["erteleme"] + 1}


# ── günlük görünüm ve karne ────────────────────────────────────────────────


def gunun_karnesi(tarih: str | None = None) -> dict:
    tarih = tarih or bugun()
    gorevler = store.gorevler(tarih=tarih)
    sayilar = {"toplam": 0, "tamam": 0, "kacirildi": 0, "kalan": 0}
    for g in gorevler:
        if g["durum"] == "iptal":
            continue
        sayilar["toplam"] += 1
        if g["durum"] == "tamam":
            sayilar["tamam"] += 1
        elif g["durum"] == "kacirildi":
            sayilar["kacirildi"] += 1
        else:
            sayilar["kalan"] += 1
    sayilar["uyum"] = (round(100 * sayilar["tamam"] / sayilar["toplam"])
                       if sayilar["toplam"] else None)
    return sayilar


def bugun_programi() -> dict:
    t = bugun()
    gorevler = store.gorevler(tarih=t)
    s = _dk(su_an())
    siradaki = next((g for g in gorevler
                     if g["durum"] in ("bekliyor", "calisiyor")
                     and _dk(g["saat"]) + g["sure_dk"] > s), None)
    return {
        "tarih": t,
        "gun": gun_adi(t),
        "saat": su_an(),
        "gorevler": gorevler,
        "siradaki": siradaki,
        "karne": gunun_karnesi(t),
        "hafta": dict(zip(("baslangic", "bitis"), hafta_sinirlari(t))),
    }


def hafta_programi(tarih: str | None = None) -> dict:
    baslangic, bitis = hafta_sinirlari(tarih)
    gorevler = store.gorevler(tarih=baslangic, bitis=bitis)
    gunler = []
    for i in range(7):
        g = _gun_ekle(baslangic, i)
        gunler.append({
            "tarih": g,
            "gun": gun_adi(g),
            "bugun": g == bugun(),
            "gorevler": [x for x in gorevler if x["tarih"] == g],
        })
    return {
        "baslangic": baslangic, "bitis": bitis, "gunler": gunler,
        "plan": store.plan_getir("haftalik", baslangic),
        "karne": store.gorev_istatistik(baslangic, bitis),
    }


# ── denetim döngüsü ────────────────────────────────────────────────────────


def _bildirim_atildi_mi(tur: str, gorev_id: int | None, gun_basi: float) -> bool:
    for b in store.bildirimler(limit=200):
        if b["zaman"] < gun_basi:
            return False
        if b["tur"] == tur and b["gorev_id"] == gorev_id:
            return True
    return False


def denetle() -> list[str]:
    """Zamanlayıcının bir turu. Yapılan işlerin listesini döndürür."""
    r = ritim()
    if not r["acik"]:
        return []

    yapilan: list[str] = []
    t, s = bugun(), su_an()
    s_dk = _dk(s)
    gun_basi = datetime.now().replace(hour=0, minute=0, second=0,
                                      microsecond=0).timestamp()

    # 1) Zamanı geçmiş görevler → kaçırıldı + telafi
    esik = _saat(max(0, s_dk - r["tolerans"]))
    for g in store.gecmis_gorevler(t, esik):
        store.gorev_durum(g["id"], "kacirildi")
        telafi_id = _telafi_olustur(g)
        gunluk.uyari("mentor", "gorev_kacti", g["baslik"],
                     gorev_id=g["id"], planlanan=f"{g['tarih']} {g['saat']}",
                     telafi_id=telafi_id, zorunlu=bool(g["zorunlu"]))
        if telafi_id:
            tg = store.gorev(telafi_id)
            store.bildirim_ekle(
                "Görev kaçtı, telafisi yazıldı",
                f"“{g['baslik']}” {g['saat']} için planlanmıştı, başlamadın. "
                f"{tg['tarih']} {tg['saat']}'e telafi olarak yazdım. "
                "Bu sefer kaçmayacak.", tur="telafi", gorev_id=telafi_id,
                proje_id=g["proje_id"])
        else:
            store.bildirim_ekle(
                "Görev kaçtı",
                f"“{g['baslik']}” yapılmadı ve takvimde telafi için yer yok. "
                "Bir işi iptal etmen ya da günü uzatman gerekiyor.",
                tur="uyari", gorev_id=g["id"], proje_id=g["proje_id"])
        yapilan.append(f"kaçırıldı: {g['baslik']}")

    # 2) Yaklaşan görev (10 dk kala) ve başlama anı
    for g in store.gorevler(tarih=t, durum="bekliyor"):
        fark = _dk(g["saat"]) - s_dk
        if 0 < fark <= 10 and not _bildirim_atildi_mi("gorev", g["id"], gun_basi):
            store.bildirim_ekle(
                f"{fark} dakika sonra: {g['baslik']}",
                (g["ayrinti"] or "Hazırlan, başlıyoruz.")[:300],
                tur="gorev", gorev_id=g["id"], proje_id=g["proje_id"])
            yapilan.append(f"hatırlatma: {g['baslik']}")

    # 3) Sabah brifingi
    if (_dk(r["baslangic"]) <= s_dk < _dk(r["baslangic"]) + 20
            and not _bildirim_atildi_mi("gun_basi", None, gun_basi)):
        prog = bugun_programi()
        if prog["gorevler"]:
            ilk = prog["gorevler"][0]
            store.bildirim_ekle(
                f"Bugün {len(prog['gorevler'])} iş var",
                f"İlk iş {ilk['saat']}: {ilk['baslik']}. "
                "Günü buradan takip edelim.", tur="gun_basi")
            yapilan.append("sabah brifingi")

    # 4) Akşam karnesi
    if (s_dk >= _dk(r["bitis"])
            and not _bildirim_atildi_mi("gun_sonu", None, gun_basi)):
        k = gunun_karnesi(t)
        if k["toplam"]:
            store.bildirim_ekle(
                f"Günün karnesi: {k['tamam']}/{k['toplam']}",
                (f"%{k['uyum']} uyum. {k['kacirildi']} kaçan iş var, "
                 "telafileri yarına yazıldı."
                 if k["kacirildi"] else f"%{k['uyum']} uyum. Temiz gün."),
                tur="gun_sonu")
            yapilan.append("akşam karnesi")

    # 5) Haftalık planı zamanı gelince kendisi üret
    hafta_bas, _ = hafta_sinirlari(t)
    if (date.fromisoformat(t).weekday() + 1 == r["plan_gun"]
            and s_dk >= _dk(r["baslangic"])
            and not store.plan_getir("haftalik", hafta_bas)):
        sonuc = plan_uret("haftalik")
        yapilan.append("haftalık plan üretildi"
                       if sonuc.get("ok") else f"plan hatası: {sonuc.get('hata')}")

    # 6) Biten 3D baskılar. İçe aktarma burada: baski.py mentor'ü kullanıyor,
    #    üstte aktarsak döngü olurdu.
    try:
        import baski

        yapilan += baski.denetle()
    except Exception as e:                      # baskı takibi mentörü düşürmesin
        gunluk.hata("mentor", "baski_denetim_hatasi", istisna=e)

    # 7) "3d Projeler" klasörü — köke atılan dosyaları yerleştir.
    try:
        import klasor

        yapilan += klasor.tara()
    except Exception as e:
        gunluk.hata("mentor", "klasor_tarama_hatasi", istisna=e)

    # 8) Yaşam koçu: ritüeller, alışkanlıklar, haftalık seans.
    try:
        import koc

        yapilan += koc.denetle()
    except Exception as e:
        gunluk.hata("mentor", "koc_denetim_hatasi", istisna=e)

    # 9) Dış takvim, yedekleme. Biri patlarsa diğerleri yürüsün.
    for modul_adi in ("takvim", "yedek"):
        try:
            modul = __import__(modul_adi)
            yapilan += modul.denetle()
        except Exception as e:
            gunluk.hata("mentor", f"{modul_adi}_denetim_hatasi", istisna=e)

    return yapilan


_durdur = threading.Event()
_kilit = threading.Lock()
_calisiyor = False


def _dongu() -> None:
    while not _durdur.is_set():
        try:
            for is_ in denetle():
                print(f"[mentör] {is_}")
        except Exception as e:                      # döngü asla ölmesin
            gunluk.hata("mentor", "dongu_hatasi", istisna=e)
        _durdur.wait(60)


def baslat() -> None:
    global _calisiyor
    with _kilit:
        if _calisiyor:
            return
        _calisiyor = True
        _durdur.clear()
        threading.Thread(target=_dongu, daemon=True, name="mentor").start()
        print("[mentör] denetim döngüsü çalışıyor")


def durdur() -> None:
    global _calisiyor
    with _kilit:
        _durdur.set()
        _calisiyor = False


def durum() -> dict:
    r = ritim()
    return {
        "calisiyor": _calisiyor,
        "acik": r["acik"],
        "sertlik": r["sertlik"],
        "pencere": f"{r['baslangic']}–{r['bitis']}",
        "bugun": gunun_karnesi(),
        "okunmamis_bildirim": len(store.bildirimler(sadece_okunmamis=True,
                                                    limit=100)),
    }


# ── konuşarak yeniden planlama ─────────────────────────────────────────────
#
# "Saat dörde kadar çalışacağım", "kaçanları tekrar sıraya al", "yarınkileri
# öne çek" — bunlar plan üretmek değil, var olan planı bugüne oturtmak.
# Yeni plan istemek Claude'a gitmek demek ve saniyeler sürüyor; bu işler
# saniyenin altında bitmeli, o yüzden tamamen yerel.


def gunun_penceresini_ayarla(bitis: str, baslangic: str | None = None,
                             tarih: str | None = None) -> dict:
    """Yalnızca bugüne özel çalışma penceresi.

    Kalıcı düzeni bozmuyoruz: "bugün dörde kadar" demek yarın da dörde kadar
    demek değil. Geçici pencere yalnızca o günü etkiliyor.
    """
    import duzen

    tarih = tarih or bugun()
    d = duzen.gecici_pencere_yaz(tarih, baslangic, bitis)

    tasinan, sigmayan = [], []
    bit = _dk(bitis)
    for g in store.gorevler(tarih=tarih, durum="bekliyor"):
        if _dk(g["saat"]) + g["sure_dk"] <= bit:
            continue                        # pencereye sığıyor, dursun
        yer = ilk_uygun_gun(g["sure_dk"], azami_gun=4)
        if yer:
            store.gorev_tasi(g["id"], yer[0], yer[1],
                             f"gün {bitis}'te bitiyor")
            tasinan.append({**g, "yeni": f"{yer[0]} {yer[1]}"})
        else:
            sigmayan.append(g)

    gunluk.bilgi("mentor", "pencere_ayarlandi", f"{tarih} → {bitis}",
                 tasinan=len(tasinan), sigmayan=len(sigmayan))
    return {"ok": True, "tarih": tarih, "pencere": d, "tasinan": tasinan,
            "sigmayan": sigmayan}


def kacanlari_geri_al(gun: int = 7, tarih: str | None = None) -> dict:
    """Kaçırılmış görevleri yeniden sıraya al.

    Telafisi zaten yazılmış olanları atlıyoruz — aynı iş iki kez takvime
    girmesin.
    """
    tarih = tarih or bugun()
    baslangic = _gun_ekle(tarih, -gun)
    telafi_edilen = {g["telafi_eden"] for g in
                     store.gorevler(tarih=baslangic,
                                    bitis=_gun_ekle(tarih, 14))
                     if g["telafi_eden"]}

    sirali, sigmayan = [], []
    kacanlar = store.gorevler(tarih=baslangic, bitis=tarih,
                              durum="kacirildi")
    # Öncelik sırasına göre: kritik işler günün başına
    for g in sorted(kacanlar, key=lambda x: (x["oncelik"], x["tarih"])):
        if g["id"] in telafi_edilen:
            continue
        yer = ilk_uygun_gun(g["sure_dk"], azami_gun=4)
        if not yer:
            sigmayan.append(g)
            continue
        store.gorev_tasi(g["id"], yer[0], yer[1], "yeniden sıraya alındı")
        sirali.append({**g, "yeni": f"{yer[0]} {yer[1]}"})

    gunluk.bilgi("mentor", "kacanlar_sirlandi", f"{len(sirali)} görev",
                 sigmayan=len(sigmayan))
    return {"ok": True, "sirali": sirali, "sigmayan": sigmayan}


def ileriden_al(gun: int = 1, tarih: str | None = None,
                azami: int = 6) -> dict:
    """Sonraki günlerin işlerini bugüne çek — boş yer kaldığı sürece."""
    tarih = tarih or bugun()
    alinan = []
    for i in range(1, gun + 1):
        kaynak = _gun_ekle(tarih, i)
        for g in sorted(store.gorevler(tarih=kaynak, durum="bekliyor"),
                        key=lambda x: (x["oncelik"], x["saat"])):
            if len(alinan) >= azami:
                break
            saat = bos_slot(tarih, g["sure_dk"])
            if not saat:
                break                       # bugün doldu
            store.gorev_tasi(g["id"], tarih, saat, "öne alındı")
            alinan.append({**g, "yeni": f"{tarih} {saat}"})
    gunluk.bilgi("mentor", "ileriden_alindi", f"{len(alinan)} görev")
    return {"ok": True, "alinan": alinan}


def yeniden_planla(eylem: str, **secenek) -> dict:
    """Konuşmadan gelen yeniden planlama isteklerinin tek kapısı."""
    if eylem == "bugunu_ayarla":
        bitis = secenek.get("bitis")
        if not bitis:
            return {"ok": False, "hata": "Bitiş saati gerekiyor."}
        return gunun_penceresini_ayarla(bitis, secenek.get("baslangic"))
    if eylem == "kacanlari_sirala":
        return kacanlari_geri_al(int(secenek.get("gun", 7)))
    if eylem == "ileriden_al":
        return ileriden_al(int(secenek.get("gun", 1)))
    return {"ok": False, "hata": f"bilinmeyen eylem: {eylem}"}


# ── süre öğrenme ───────────────────────────────────────────────────────────
#
# Bir işi kaç dakikada bitirdiğin, o işin gerçek süresidir. Plan hep aynı
# tahminle çalışırsa aynı hatayı tekrarlar. Burada geçmiş ölçümlerden
# öğreniyoruz: benzer işler için tahmini gerçeğe yaklaştırıyoruz.


def _anahtar_kelimeler(baslik: str) -> set[str]:
    """Başlıktan ayırt edici kelimeler — benzer işleri eşleştirmek için."""
    d = re.sub(r"\[.*?\]", " ", (baslik or "").casefold())
    d = re.sub(r"[^\wçğıöşü ]", " ", d)
    return {k for k in d.split() if len(k) > 3}


def benzer_sure(baslik: str, proje_id: int | None = None,
                azami: int = 40) -> dict | None:
    """Geçmişte benzer işler ne kadar sürmüş?

    Önce aynı projedeki, sonra başlığı örtüşen işlere bakıyoruz. İki ölçümden
    az varsa öğrenilecek bir şey yok — tek örnekten kural çıkarmak, tahmini
    iyileştirmek yerine rastgeleleştirir.
    """
    kelimeler = _anahtar_kelimeler(baslik)
    if not kelimeler:
        return None

    q = ("SELECT baslik, sure_dk, gercek_dk, proje_id FROM gorevler "
         "WHERE gercek_dk IS NOT NULL AND gercek_dk > 0 "
         "ORDER BY tamamlandi DESC LIMIT 300")
    eslesen = []
    for r in store._conn().execute(q):
        ortak = kelimeler & _anahtar_kelimeler(r["baslik"])
        if not ortak:
            continue
        puan = len(ortak) / max(1, len(kelimeler))
        if proje_id and r["proje_id"] == proje_id:
            puan += 0.5
        if puan >= 0.34:
            eslesen.append((puan, r))

    if len(eslesen) < 2:
        return None
    eslesen.sort(key=lambda x: -x[0])
    secilen = [r for _, r in eslesen[:azami]]
    gercek = sum(r["gercek_dk"] for r in secilen) / len(secilen)
    tahmin = sum(r["sure_dk"] for r in secilen) / len(secilen)
    return {
        "sayi": len(secilen),
        "ortalama_gercek": round(gercek),
        "ortalama_tahmin": round(tahmin),
        "oran": round(gercek / tahmin, 2) if tahmin else None,
    }


def sure_oner(baslik: str, tahmin: int, proje_id: int | None = None) -> int:
    """Geçmişe bakarak süreyi düzelt.

    Tamamen geçmişe uymuyoruz: yeni tahminle öğrenilen süreyi harmanlıyoruz.
    Tek bir uzun günün bütün gelecek planı bozmasını istemiyoruz.
    """
    b = benzer_sure(baslik, proje_id)
    if not b or not b["ortalama_gercek"]:
        return tahmin
    harman = round(tahmin * 0.4 + b["ortalama_gercek"] * 0.6)
    # Uçlara kaçmasın: yarısından az, iki katından çok olmasın
    return max(15, min(harman, tahmin * 2, 240))


# ── geriye dönük tamamlama ─────────────────────────────────────────────────


def gecmiste_tamamla(gid: int, dakika_once: int = 0,
                     saat: str | None = None) -> dict:
    """“Bunu iki saat önce bitirdim” — tamamlanma anını geçmişe yaz.

    Gerçek süreyi de buradan çıkarıyoruz: başlangıç işaretlenmişse aradaki
    fark, değilse görevin planlanan saatinden bitişe kadar geçen süre.
    """
    g = store.gorev(gid)
    if not g:
        return {"ok": False, "hata": "Görev bulunamadı."}
    if g["durum"] == "tamam":
        return {"ok": False, "hata": "Bu görev zaten tamam."}

    simdi = time.time()
    if saat:
        try:
            bitis_dk = _dk(saat)
            bugun_baslangic = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0).timestamp()
            bitis = bugun_baslangic + bitis_dk * 60
            if bitis > simdi:               # gelecekteyse dünü kastetmiştir
                bitis -= 86400
        except (ValueError, TypeError):
            bitis = simdi
    else:
        bitis = simdi - max(0, dakika_once) * 60

    baslangic = g["baslatildi"]
    if not baslangic:
        # Başlat denmemiş: planlanan saatten bitişe kadarını çalışma say,
        # ama görevin planlanan süresini aşmasına izin verme.
        try:
            gun = datetime.fromisoformat(g["tarih"]).timestamp()
            baslangic = gun + _dk(g["saat"]) * 60
        except (ValueError, TypeError):
            baslangic = bitis - g["sure_dk"] * 60
    gercek = max(1, min(round((bitis - baslangic) / 60), g["sure_dk"] * 3))

    c = store._conn()
    c.execute("UPDATE gorevler SET durum='tamam', tamamlandi=?, gercek_dk=? "
              "WHERE id=?", (bitis, gercek, gid))
    c.commit()
    gunluk.bilgi("mentor", "gecmiste_tamamlandi", g["baslik"],
                 gorev_id=gid, gercek_dk=gercek,
                 dakika_once=round((simdi - bitis) / 60))
    return {"ok": True, "gorev": store.gorev(gid), "gercek_dk": gercek,
            "karne": gunun_karnesi(g["tarih"])}


# ── konuşarak görev düzenleme ──────────────────────────────────────────────


def gorev_bul(metin: str, tarih: str | None = None,
              gun: int = 3) -> list[dict]:
    """Cümlede geçen kelimelerden görevi bul."""
    kelimeler = _anahtar_kelimeler(metin)
    if not kelimeler:
        return []
    t = tarih or bugun()
    adaylar = store.gorevler(tarih=_gun_ekle(t, -gun),
                             bitis=_gun_ekle(t, gun))
    puanli = []
    for g in adaylar:
        if g["durum"] in ("iptal",):
            continue
        ortak = kelimeler & _anahtar_kelimeler(g["baslik"])
        if not ortak:
            continue
        puan = len(ortak)
        if g["tarih"] == t:
            puan += 1                      # bugünküler öncelikli
        if g["durum"] in ("bekliyor", "calisiyor"):
            puan += 1
        puanli.append((puan, g))
    puanli.sort(key=lambda x: -x[0])
    return [g for _, g in puanli]


def gorev_duzenle(gid: int, baslik: str | None = None,
                  saat: str | None = None, tarih: str | None = None,
                  sure_dk: int | None = None, oncelik: int | None = None,
                  ayrinti: str | None = None) -> dict:
    """Görevin içeriğini değiştir. Saat/tarih değişince çakışma denetlenir."""
    g = store.gorev(gid)
    if not g:
        return {"ok": False, "hata": "Görev bulunamadı."}

    yeni_tarih = tarih or g["tarih"]
    yeni_saat = saat or g["saat"]
    yeni_sure = max(5, int(sure_dk)) if sure_dk else g["sure_dk"]

    if saat or tarih or sure_dk:
        uygun = bos_slot(yeni_tarih, yeni_sure, tercih=yeni_saat, haric=gid)
        if uygun is None:
            return {"ok": False,
                    "hata": f"{yeni_tarih} günü {yeni_sure} dakikalık işe yer yok."}
        if saat and uygun != yeni_saat:
            # İstenen saat dolu; en yakın boşluğa alıp haber veriyoruz.
            yeni_saat = uygun
        elif not saat:
            yeni_saat = uygun

    alanlar, d = [], []
    for ad, deger in (("baslik", baslik), ("ayrinti", ayrinti),
                      ("tarih", yeni_tarih), ("saat", yeni_saat),
                      ("sure_dk", yeni_sure),
                      ("oncelik", max(1, min(3, oncelik)) if oncelik else None)):
        if deger is not None:
            alanlar.append(f"{ad}=?")
            d.append(deger)
    if not alanlar:
        return {"ok": False, "hata": "Değiştirilecek bir şey yok."}

    c = store._conn()
    d.append(gid)
    c.execute(f"UPDATE gorevler SET {', '.join(alanlar)} WHERE id=?", d)
    c.commit()
    olay.yayinla("gorev", gorev_id=gid, durum="duzenlendi")
    gunluk.bilgi("mentor", "gorev_duzenlendi", g["baslik"], gorev_id=gid,
                 yeni_saat=yeni_saat, yeni_tarih=yeni_tarih,
                 yeni_sure=yeni_sure)
    return {"ok": True, "gorev": store.gorev(gid), "eski": g}
