"""Çalışma düzeni — mentör hangi günlerde ne kadar yer bulabilir.

Mentör baştan "her gün 09:00-22:00" varsayıyordu. Vardiyalı çalışan biri için
bu tamamen yanlış: 24 saatlik nöbetin olduğu güne odak bloğu yazmak, o günün
planını daha kurulurken çöpe atmak demek.

Üç düzen var:

* ``sabit``   — her gün aynı pencere (varsayılan).
* ``vardiya`` — N gün çalışma, M gün izin, döngü hâlinde. Nöbet gününde
  kişisel iş için yer açılmaz; izin günlerinde pencere genişler.
* ``serbest`` — pencere yok, mentör istediği saate koyabilir.

Düzen konuşarak değiştirilebiliyor: "bir gün yirmi dört saat çalışıyorum iki
gün izinliyim" cümlesi ``niyet.py`` tarafından anlaşılıp buraya geliyor.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import gunluk
import store

VARSAYILAN = {
    "tur": "sabit",
    "baslangic": "09:00",
    "bitis": "22:00",
    "calisma_gun": 1,
    "izin_gun": 2,
    "vardiya_saat": 24,
    "dongu_basi": None,        # YYYY-MM-DD, döngünün ilk çalışma günü
    "izin_baslangic": "10:00",
    "izin_bitis": "23:00",
    "gunler": None,            # sabit düzende çalışılan günler (1=Pzt)
    "gecici": {},              # {tarih: [baslangic, bitis]} — tek günlük
}


def oku() -> dict:
    try:
        d = json.loads(store.ayar("calisma_duzeni", "{}") or "{}")
    except json.JSONDecodeError:
        d = {}
    return {**VARSAYILAN, **(d if isinstance(d, dict) else {})}


def yaz(**alanlar) -> dict:
    d = {**oku(), **{k: v for k, v in alanlar.items() if v is not None}}
    if d["tur"] == "vardiya" and not d.get("dongu_basi"):
        d["dongu_basi"] = date.today().isoformat()
    store.ayar_yaz("calisma_duzeni", json.dumps(d, ensure_ascii=False))
    gunluk.bilgi("duzen", "guncellendi", ozet(d), **{
        k: d[k] for k in ("tur", "calisma_gun", "izin_gun", "vardiya_saat")})
    return d


def gun_tipi(tarih: str) -> str:
    """'vardiya' | 'izin' | 'normal'"""
    d = oku()
    if d["tur"] != "vardiya":
        return "normal"
    basi = d.get("dongu_basi")
    if not basi:
        return "normal"
    try:
        gecen = (date.fromisoformat(tarih) - date.fromisoformat(basi)).days
    except ValueError:
        return "normal"
    dongu = max(1, int(d["calisma_gun"]) + int(d["izin_gun"]))
    yer = gecen % dongu
    return "vardiya" if yer < int(d["calisma_gun"]) else "izin"


def gecici_pencere_yaz(tarih: str, baslangic: str | None,
                       bitis: str) -> dict:
    """Yalnızca o güne özel pencere. Kalıcı düzeni bozmaz.

    "Bugün dörde kadar çalışacağım" demek yarın da dörde kadar demek değil;
    o yüzden ayrı tutuluyor ve geçmiş günler temizleniyor.
    """
    d = oku()
    gecici = {k: v for k, v in (d.get("gecici") or {}).items()
              if k >= date.today().isoformat()}
    mevcut = gecici.get(tarih)
    gecici[tarih] = [baslangic or (mevcut[0] if mevcut else d["baslangic"]),
                     bitis]
    return yaz(gecici=gecici)["gecici"][tarih]


def pencere(tarih: str) -> tuple[str, str] | None:
    """O günün çalışma penceresi. ``None`` ise o güne iş yazılmaz."""
    d = oku()
    gecici = (d.get("gecici") or {}).get(tarih)
    if gecici:
        return gecici[0], gecici[1]
    if d["tur"] == "serbest":
        return "00:00", "23:59"
    if d["tur"] == "sabit":
        gunler = d.get("gunler")
        if gunler:
            from datetime import date as _d

            try:
                gun_no = _d.fromisoformat(tarih).weekday() + 1
            except ValueError:
                gun_no = None
            if gun_no is not None and gun_no not in gunler:
                # Çalışma günü değil: pencere genişler, iş yasak değil.
                return d["izin_baslangic"], d["izin_bitis"]
        return d["baslangic"], d["bitis"]

    tip = gun_tipi(tarih)
    if tip == "vardiya":
        # 24 saatlik nöbette kişisel işe yer yok. Daha kısa vardiyalarda
        # nöbet sonrası birkaç saat açık kalıyor.
        if float(d["vardiya_saat"]) >= 20:
            return None
        return d["baslangic"], d["bitis"]
    return d["izin_baslangic"], d["izin_bitis"]


def calisilabilir_mi(tarih: str) -> bool:
    return pencere(tarih) is not None


def ozet(d: dict | None = None) -> str:
    d = d or oku()
    if d["tur"] == "serbest":
        return "Serbest — saat kısıtı yok."
    if d["tur"] == "sabit":
        gunler = d.get("gunler")
        if gunler:
            adlar = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
            hangi = ", ".join(adlar[g - 1] for g in gunler)
            return (f"Sabit düzen: {hangi} günleri {d['baslangic']}–"
                    f"{d['bitis']}, diğer günler {d['izin_baslangic']}–"
                    f"{d['izin_bitis']}.")
        return f"Sabit düzen: her gün {d['baslangic']}–{d['bitis']}."
    saat = int(float(d["vardiya_saat"]))
    return (f"Vardiya: {d['calisma_gun']} gün {saat} saat çalışma, "
            f"{d['izin_gun']} gün izin. İzin günlerinde "
            f"{d['izin_baslangic']}–{d['izin_bitis']}.")


def takvim(baslangic: str, gun: int = 14) -> list[dict]:
    """Önümüzdeki günlerin tipi — plan bağlamı ve arayüz için."""
    liste = []
    for i in range(gun):
        t = (date.fromisoformat(baslangic) + timedelta(days=i)).isoformat()
        p = pencere(t)
        liste.append({"tarih": t, "tip": gun_tipi(t),
                      "pencere": f"{p[0]}–{p[1]}" if p else None,
                      "calisilabilir": p is not None})
    return liste


def plan_ozeti(baslangic: str, gun: int = 14) -> str:
    """Mentörün plan yaparken göreceği not."""
    d = oku()
    if d["tur"] == "sabit" and d.get("gunler"):
        return "ÇALIŞMA DÜZENİ: " + ozet(d)
    if d["tur"] != "vardiya":
        return ""
    satirlar = ["ÇALIŞMA DÜZENİ: " + ozet(d),
                "Nöbet günlerine görev YAZMA. Günler:"]
    for g in takvim(baslangic, gun):
        etiket = {"vardiya": "NÖBET — boş bırak",
                  "izin": f"izin, {g['pencere']}",
                  "normal": g["pencere"]}[g["tip"]]
        satirlar.append(f"- {g['tarih']}: {etiket}")
    return "\n".join(satirlar)
