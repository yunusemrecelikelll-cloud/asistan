"""Yaşam paneli — uyku, harcama, beslenme, spor, su, ruh hâli.

Kayıt iki yoldan girer:
  1. Arayüzdeki hızlı düğmeler (kesin veri).
  2. Konuşarak: "dün 6 saat uyudum, kahveye 45 lira verdim" gibi serbest cümle.

Serbest cümleyi önce düzenli ifadelerle çözüyoruz — bedava, anında ve
öngörülebilir. Yakalanamazsa yerel modele düşüyoruz. Claude'a hiç gitmiyor;
"3 litre su içtim" cümlesi için para harcamanın anlamı yok.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import brain
import store

TURLER = {
    "uyku":    {"ad": "Uyku",     "birim": "saat", "yon": "yuksek_iyi"},
    "harcama": {"ad": "Harcama",  "birim": "TL",   "yon": "dusuk_iyi"},
    "ogun":    {"ad": "Öğün",     "birim": "öğün", "yon": "notr"},
    "spor":    {"ad": "Spor",     "birim": "dk",   "yon": "yuksek_iyi"},
    "su":      {"ad": "Su",       "birim": "litre","yon": "yuksek_iyi"},
    "ruh":     {"ad": "Ruh hâli", "birim": "/10",  "yon": "yuksek_iyi"},
}


def bugun() -> str:
    return date.today().isoformat()


def _gun_ekle(tarih: str, n: int) -> str:
    return (date.fromisoformat(tarih) + timedelta(days=n)).isoformat()


def _sayi(metin: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)", metin)
    return float(m.group(1).replace(",", ".")) if m else None


# ── serbest metin çözümleme ────────────────────────────────────────────────

# Her desen: (tür, regex, birim). Sayı ilk gruptan alınır.
DESENLER: list[tuple[str, str, str]] = [
    ("uyku",    r"(\d+(?:[.,]\d+)?)\s*(?:saat|sa)\b[^.]*?(?:uyu|uyku)", "saat"),
    ("uyku",    r"(?:uyu|uyku)[^.]*?(\d+(?:[.,]\d+)?)\s*(?:saat|sa)\b", "saat"),
    ("harcama", r"(\d+(?:[.,]\d+)?)\s*(?:tl|lira|₺)", "TL"),
    ("harcama", r"(?:harca|ödedi|verdi)[^.]*?(\d+(?:[.,]\d+)?)", "TL"),
    ("spor",    r"(\d+(?:[.,]\d+)?)\s*(?:dakika|dk)[^.]*?"
                r"(?:spor|koş|yürü|antren|salon|bisiklet|yüz)", "dk"),
    ("spor",    r"(?:spor|koş|yürü|antren|salon|bisiklet|yüz)[^.]*?"
                r"(\d+(?:[.,]\d+)?)\s*(?:dakika|dk)", "dk"),
    ("su",      r"(\d+(?:[.,]\d+)?)\s*(?:litre|lt)\b[^.]*?su", "litre"),
    ("su",      r"su[^.]*?(\d+(?:[.,]\d+)?)\s*(?:litre|lt)\b", "litre"),
    ("ruh",     r"(?:moral|ruh|keyif|hissed)[^.]*?(\d+(?:[.,]\d+)?)\s*(?:/\s*10)?",
                "/10"),
]

OGUN_ANAHTARLARI = ("kahvaltı", "öğle", "akşam", "yemek", "yedim", "atıştır",
                    "ara öğün", "tost", "salata", "çorba")

DUN_ANAHTARLARI = ("dün", "dün gece", "dün akşam")


def _tarih_coz(metin: str) -> str:
    d = metin.lower()
    if any(k in d for k in DUN_ANAHTARLARI):
        return _gun_ekle(bugun(), -1)
    if "evvelsi" in d or "önceki gün" in d:
        return _gun_ekle(bugun(), -2)
    return bugun()


def _desenle_coz(metin: str) -> list[dict]:
    """Düzenli ifadelerle yakalanan kayıtlar."""
    d = metin.lower()
    tarih = _tarih_coz(d)
    bulunan: list[dict] = []
    goruldu: set[str] = set()

    for tur, desen, birim in DESENLER:
        if tur in goruldu:
            continue
        m = re.search(desen, d, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            deger = float(m.group(1).replace(",", "."))
        except (ValueError, IndexError):
            continue
        if tur == "ruh" and not 0 < deger <= 10:
            continue
        bulunan.append({"tur": tur, "tarih": tarih, "deger": deger,
                        "birim": birim, "detay": metin.strip()[:200]})
        goruldu.add(tur)

    if "ogun" not in goruldu and any(k in d for k in OGUN_ANAHTARLARI):
        bulunan.append({"tur": "ogun", "tarih": tarih, "deger": 1,
                        "birim": "öğün", "detay": metin.strip()[:200]})
    return bulunan


COZUM_TALIMATI = """Kullanıcının cümlesinden yaşam kayıtlarını çıkar.

Türler: uyku (saat), harcama (TL), ogun (öğün sayısı), spor (dakika),
su (litre), ruh (1-10 arası ruh hâli).

Kurallar:
- Cümlede olmayan şeyi uydurma. Emin değilsen o kaydı yazma.
- Birden fazla kayıt varsa hepsini ayrı ayrı yaz.
- Hiçbir şey çıkmıyorsa boş liste döndür.
- detay alanına cümlenin ilgili kısmını yaz (ne yediği, neye harcadığı).

YALNIZCA JSON dizisi döndür:
[{"tur":"uyku","deger":6.5,"detay":"gece geç yattım"}]"""


def _modelle_coz(metin: str) -> list[dict]:
    yanit = brain.yerel_sohbet(
        [{"role": "user", "content": metin}],
        sistem=COZUM_TALIMATI, azami_token=300)
    ham = re.sub(r"^```(?:json)?|```$", "", (yanit or "").strip(),
                 flags=re.MULTILINE).strip()
    bas, son = ham.find("["), ham.rfind("]")
    if bas == -1 or son <= bas:
        return []
    try:
        veri = json.loads(ham[bas:son + 1])
    except json.JSONDecodeError:
        return []

    tarih = _tarih_coz(metin)
    cikan = []
    for h in veri if isinstance(veri, list) else []:
        if not isinstance(h, dict) or h.get("tur") not in TURLER:
            continue
        try:
            deger = float(str(h.get("deger", 0)).replace(",", "."))
        except (TypeError, ValueError):
            continue
        cikan.append({
            "tur": h["tur"], "tarih": tarih, "deger": deger,
            "birim": TURLER[h["tur"]]["birim"],
            "detay": str(h.get("detay") or metin)[:200],
        })
    return cikan


def metinden_kaydet(metin: str) -> dict:
    """Serbest cümleyi kayda çevir. Önce desen, tutmazsa yerel model."""
    metin = (metin or "").strip()
    if not metin:
        return {"ok": False, "hata": "Boş metin."}

    kayitlar = _desenle_coz(metin)
    kaynak = "desen"
    if not kayitlar:
        kayitlar = _modelle_coz(metin)
        kaynak = "model"
    if not kayitlar:
        return {"ok": False, "hata": "Bu cümleden bir kayıt çıkaramadım. "
                                     "“7 saat uyudum” gibi söyler misin?"}

    import koc                               # döngüsel içe aktarmayı önle

    yazilan = []
    for k in kayitlar:
        kid = store.yasam_ekle(k["tur"], k["tarih"], k["deger"],
                               k["birim"], k["detay"])
        # Harcamayı kategoriye yerleştir — bütçe paneli buna dayanıyor.
        if k["tur"] == "harcama":
            k["kategori"] = koc.kategori_bul(k["detay"] or metin)
            store.yasam_kategori_yaz(kid, k["kategori"])
        yazilan.append({**k, "id": kid})
    return {"ok": True, "kaynak": kaynak, "kayitlar": yazilan,
            "ozet": ozetle(yazilan)}


def ozetle(kayitlar: list[dict]) -> str:
    parcalar = []
    for k in kayitlar:
        ad = TURLER.get(k["tur"], {}).get("ad", k["tur"])
        deger = k["deger"]
        deger = int(deger) if float(deger).is_integer() else deger
        parcalar.append(f"{ad}: {deger} {k['birim']}")
    return ", ".join(parcalar)


# ── panel ──────────────────────────────────────────────────────────────────


def panel(gun: int = 7) -> dict:
    """Panelin üst şeridi: son N gün + bugün + hedeflere göre durum."""
    bitis = bugun()
    baslangic = _gun_ekle(bitis, -(max(1, gun) - 1))
    ozet = store.yasam_ozet(baslangic, bitis)
    bugunku = store.yasam_ozet(bitis, bitis)
    ayarlar = store.tum_ayarlar()

    try:
        uyku_hedef = float(ayarlar.get("uyku_hedef", "7.5") or 7.5)
    except ValueError:
        uyku_hedef = 7.5
    try:
        harcama_hedef = float(ayarlar.get("gunluk_harcama_hedef", "0") or 0)
    except ValueError:
        harcama_hedef = 0.0

    kartlar = []
    for tur, bilgi in TURLER.items():
        d = ozet.get(tur, {})
        b = bugunku.get(tur, {})
        kart = {
            "tur": tur, "ad": bilgi["ad"], "birim": bilgi["birim"],
            "bugun": b.get("toplam"),
            "ortalama": d.get("ortalama"),
            "toplam": d.get("toplam"),
            "sayi": d.get("sayi", 0),
            "durum": "veri_yok" if not d else "normal",
        }
        if tur == "uyku" and d.get("ortalama") is not None:
            kart["hedef"] = uyku_hedef
            kart["durum"] = "iyi" if d["ortalama"] >= uyku_hedef else "dusuk"
        if tur == "harcama" and harcama_hedef and b.get("toplam") is not None:
            kart["hedef"] = harcama_hedef
            kart["durum"] = "iyi" if b["toplam"] <= harcama_hedef else "yuksek"
        kartlar.append(kart)

    return {
        "baslangic": baslangic, "bitis": bitis, "gun": gun,
        "kartlar": kartlar,
        "kayitlar": store.yasam_kayitlari(baslangic, bitis)[:60],
    }


def gunluk_seri(tur: str, gun: int = 14) -> list[dict]:
    """Grafik için günlük toplamlar (boş günler 0 olarak doldurulur)."""
    bitis = bugun()
    baslangic = _gun_ekle(bitis, -(max(1, gun) - 1))
    toplamlar: dict[str, float] = {}
    for k in store.yasam_kayitlari(baslangic, bitis, tur=tur):
        toplamlar[k["tarih"]] = toplamlar.get(k["tarih"], 0) + (k["deger"] or 0)
    return [{"tarih": _gun_ekle(baslangic, i),
             "deger": round(toplamlar.get(_gun_ekle(baslangic, i), 0), 2)}
            for i in range(gun)]


ANALIZ_TALIMATI = """Kullanıcının son günlerdeki yaşam verisine bakıp kısa bir
değerlendirme yaz.

Kurallar:
- Türkçe, en fazla 5 cümle. Madde işareti kullanma, konuşur gibi yaz.
- Veriye dayan. Veri yoksa "yeterli veri yok" de, tahmin yürütme.
- Bir tane somut ve bugün uygulanabilir öneri ver.
- Sağlık teşhisi koyma, ilaç ya da diyet önerme.
- Nazik ol ama yumuşatma; gerçeği söyle."""


def analiz(gun: int = 14) -> dict:
    p = panel(gun)
    veri_var = any(k["sayi"] for k in p["kartlar"])
    if not veri_var:
        return {"ok": False, "metin": "Henüz yeterli veri yok. Birkaç gün "
                                      "uyku ve harcama kaydı girersen "
                                      "değerlendirebilirim."}
    satirlar = [f"Son {gun} gün:"]
    for k in p["kartlar"]:
        if not k["sayi"]:
            continue
        satirlar.append(
            f"- {k['ad']}: toplam {k['toplam']} {k['birim']}, "
            f"ortalama {k['ortalama']}, {k['sayi']} kayıt")
    metin = brain.yerel_sohbet(
        [{"role": "user", "content": "\n".join(satirlar)}],
        sistem=ANALIZ_TALIMATI, azami_token=400)
    return {"ok": True, "metin": (metin or "").strip(), "panel": p}
