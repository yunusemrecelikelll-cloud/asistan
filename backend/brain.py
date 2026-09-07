"""Beyin — hangi işin yerel modele, hangisinin Claude'a gideceğine karar verir.

Yönlendirme ilkesi:
  • Sohbet, tavsiye, projeler hakkında konuşma  → yerel Ollama (ücretsiz, hızlı)
  • Bir projede iş yaptırma                      → claude CLI (dispatch.py)
  • Ağır akıl yürütme                            → claude CLI (opus)
  • Durum/rapor                                  → hiç model yok, yerel hesap
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata

import httpx

import store

OLLAMA = "http://127.0.0.1:11434"
CLAUDE_BIN = shutil.which("claude") or "claude"

SISTEM_TALIMATI = """Sen bir yazılım projesi komuta merkezisin.

Görevin, kullanıcının kısa isteğini Claude Code'a gönderilecek net ve eksiksiz
bir göreve dönüştürmek. Kendin kod yazmazsın, iş yapmazsın; sadece görevi
yazarsın."""


TASLAK_TALIMATI = """Kullanıcının kısa isteğini, bir projede çalışacak Claude
Code'a verilecek ayrıntılı bir göreve dönüştür.

Kurallar:
- Türkçe yaz. Doğrudan göreve başla; "İşte görev" gibi giriş cümlesi kurma.
- Kullanıcının istediğinin ötesine geçme, yeni özellik uydurma. İstediğini
  netleştir ve uygulanabilir hâle getir.
- Brifingdeki gerçek dosya ve klasör adlarını kullan. Brifingde olmayan bir
  dosyayı varmış gibi yazma.
- Görevi şu şekilde kur: ne yapılacak, hangi dosyalarda, nasıl doğrulanacak.
- İstek belirsizse, varsayımını açıkça yaz ("X olduğunu varsayarak…").
- En fazla 150 kelime. Madde işareti kullanabilirsin.
- Sadece görev metnini yaz, başka hiçbir şey yazma."""


DEVAM_TALIMATI = """Projenin durumuna bakarak sıradaki en mantıklı işi belirle
ve Claude Code'a verilecek görev olarak yaz.

Kurallar:
- Türkçe yaz, doğrudan göreve başla.
- Brifingdeki yarım kalmış işlere, TODO'lara ve son commitlere bak.
- Küçük ve tamamlanabilir bir adım seç; tek seferde bitirilebilecek kadar.
- Yıkıcı bir iş seçme: dosya silme, geçmiş yeniden yazma, bağımlılık kaldırma
  gibi işleri önerme.
- Yapılacak bir şey kalmadıysa yalnızca "YAPILACAK_YOK" yaz.
- En fazla 120 kelime. Sadece görev metnini yaz."""


# ── Ollama ─────────────────────────────────────────────────────────────────


def ollama_var_mi() -> bool:
    try:
        return httpx.get(f"{OLLAMA}/api/tags", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def ollama_modeller() -> list[str]:
    try:
        r = httpx.get(f"{OLLAMA}/api/tags", timeout=5)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []))
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def yerel_sohbet(mesajlar: list[dict], model: str | None = None,
                 sistem: str | None = None, azami_token: int = 700,
                 sicaklik: float = 0.7) -> str:
    """Ollama /api/chat. Düşünme kipi kapatılır — sesli asistan için doğrudan
    cevap gerekir, ayrıca düşünme bütçeyi tüketip boş yanıt bırakabiliyor."""
    model = model or store.ayar("sohbet_modeli", "qwen3.5:4b-tr")
    govde = {
        "model": model,
        "messages": [{"role": "system", "content": sistem or SISTEM_TALIMATI},
                     *mesajlar],
        "stream": False,
        "think": False,
        # Modeli bellekte tut. Varsayılan 5 dakika; canlı konuşmada araya
        # birkaç dakika girince model boşaltılıyor ve sonraki tur 10-20
        # saniye yükleme bekliyordu.
        "keep_alive": "30m",
        # Sınıflandırma gibi işlerde düşük sıcaklık şart: 0.7 ile aynı
        # cümle bazen "yasam", bazen "soru" çıkıyordu.
        "options": {"num_predict": azami_token, "temperature": sicaklik},
    }
    try:
        r = httpx.post(f"{OLLAMA}/api/chat", json=govde, timeout=180)
        r.raise_for_status()
        d = r.json()
        icerik = (d.get("message") or {}).get("content", "").strip()
        if icerik:
            return icerik
        # Bazı sürümler "think" alanını yok sayar; düşünme metnine düşme.
        dusunce = (d.get("message") or {}).get("thinking", "").strip()
        return dusunce[:400] if dusunce else "Yanıt üretemedim, tekrar dener misin?"
    except httpx.HTTPError as e:
        return f"Yerel modele ulaşamadım: {e}"


# Cümle sonu: nokta/soru/ünlem + boşluk. Kısaltmalar için sayıdan hemen
# sonraki noktayı saymıyoruz ("saat 4." gibi durumlarda erken kesmesin).
_CUMLE_SONU = re.compile(r"(?<![0-9])[.!?…]+\s")


def yerel_sohbet_akis(mesajlar: list[dict], model: str | None = None,
                      sistem: str | None = None, azami_token: int = 700,
                      sicaklik: float = 0.7):
    """Ollama /api/chat akışlı — CÜMLE cümle verir.

    Sesli turda en pahalı bekleme, modelin bütün yanıtı bitirmesiydi.
    Oysa ilk cümle çıkar çıkmaz seslendirmeye başlanabiliyor; kalan cümleler
    ses çalarken üretiliyor. Ölçülen kazanç: ilk sese kadar ~1,5 saniye.
    """
    model = model or store.ayar("sohbet_modeli", "qwen3.5:4b-tr")
    govde = {
        "model": model,
        "messages": [{"role": "system", "content": sistem or SISTEM_TALIMATI},
                     *mesajlar],
        "stream": True,
        "think": False,
        "keep_alive": "30m",
        "options": {"num_predict": azami_token, "temperature": sicaklik},
    }
    tampon = ""
    try:
        with httpx.stream("POST", f"{OLLAMA}/api/chat", json=govde,
                          timeout=180) as r:
            r.raise_for_status()
            for satir in r.iter_lines():
                if not satir:
                    continue
                try:
                    d = json.loads(satir)
                except ValueError:
                    continue
                tampon += (d.get("message") or {}).get("content", "")
                # Elde tam cümle biriktikçe hemen ver
                while (m := _CUMLE_SONU.search(tampon)):
                    kes = m.end()
                    parca = tampon[:kes].strip()
                    tampon = tampon[kes:]
                    if parca:
                        yield parca
                if d.get("done"):
                    break
    except httpx.HTTPError as e:
        if not tampon:
            yield f"Yerel modele ulaşamadım: {e}"
            return
    if (kalan := tampon.strip()):
        yield kalan


def promptu_detaylandir(ham: str, brifing: str, model: str | None = None) -> str:
    """Kullanıcının kısa isteğini ayrıntılı göreve çevir (yerel model, ücretsiz)."""
    model = model or store.ayar("taslak_modeli", "qwen3.5:9b-tr")
    mesaj = "\n\n".join([
        "PROJE BRİFİNGİ:\n" + brifing,
        "KULLANICININ İSTEĞİ:\n" + ham,
        "Bu isteği yukarıdaki kurallara göre ayrıntılı göreve dönüştür.",
    ])
    sonuc = yerel_sohbet([{"role": "user", "content": mesaj}],
                         model=model, sistem=TASLAK_TALIMATI, azami_token=600)
    sonuc = (sonuc or "").strip()
    # Yerel model tökezlerse ham isteği aynen kullan — akış durmasın.
    if not sonuc or sonuc.startswith("Yerel modele ulaşamadım") or len(sonuc) < 15:
        return ham
    return sonuc


def sonraki_adimi_belirle(brifing: str, son_cikti: str = "",
                          model: str | None = None) -> str:
    """Otomatik devam için sıradaki görevi yaz. 'YAPILACAK_YOK' dönebilir."""
    model = model or store.ayar("taslak_modeli", "qwen3.5:9b-tr")
    mesaj = "PROJE BRİFİNGİ:\n" + brifing
    if son_cikti:
        mesaj += "\n\nEN SON YAPILAN İŞİN ÇIKTISI:\n" + son_cikti[:1200]
    mesaj += "\n\nSıradaki adımı yaz."
    sonuc = yerel_sohbet([{"role": "user", "content": mesaj}],
                         model=model, sistem=DEVAM_TALIMATI, azami_token=400)
    return (sonuc or "").strip()


# ── Claude (akıl yürütme) ──────────────────────────────────────────────────


def claude_akil(prompt: str, model: str | None = None,
                zaman_asimi: int = 600) -> dict:
    """Projeye bağlı olmayan ağır akıl yürütme. Ücretlidir."""
    model = model or store.ayar("akil_modeli", "opus")
    argv = [CLAUDE_BIN, "-p", "--model", model, "--output-format", "json"]
    try:
        import dispatch as _d

        # Prompt stdin'den: Windows .CMD sarmalayıcısı çok satırlı argümanda
        # sonraki bayrakları düşürüyor.
        r = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=zaman_asimi, env=_d.abonelik_ortami())
    except (OSError, subprocess.SubprocessError) as e:
        return {"metin": f"Claude çağrılamadı: {e}", "maliyet": None, "hata": True}
    d = _d._json_coz(r.stdout)
    if d is not None:
        return {"metin": d.get("result", ""), "maliyet": d.get("total_cost_usd"),
                "hata": bool(d.get("is_error"))}
    return {"metin": r.stdout or r.stderr or "boş yanıt", "maliyet": None,
            "hata": r.returncode != 0}


# ── niyet çözümleme ────────────────────────────────────────────────────────

def _sadelestir(s: str) -> str:
    """Türkçe karakterleri ve noktalamayı düşürerek eşleştirmeyi kolaylaştır."""
    s = s.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace("Ş", "s")
    s = s.replace("ğ", "g").replace("Ğ", "g").replace("ü", "u").replace("Ü", "u")
    s = s.replace("ö", "o").replace("Ö", "o").replace("ç", "c").replace("Ç", "c")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


# Bir işin yapılmasını isteyen fiiller
_KOMUT_IPUCLARI = [
    "calistir", "kur", "duzelt", "ekle", "sil", "guncelle", "yaz", "olustur",
    "derle", "test et", "testleri", "commit", "push", "duzenle", "degistir",
    "yapabilir misin", "yap ", "baslat", "durdur", "temizle", "kontrol et",
    "incele", "analiz et", "bak ", "gozden gecir", "refactor", "hata",
]

# Rapor/durum soran kalıplar
_RAPOR_IPUCLARI = [
    "rapor", "durum", "ozet", "ne alemde", "neler var", "hangi projeler",
    "projelerim", "listele", "son ne yaptim", "nerede kalmistim",
    "ne kalmisti", "genel bakis",
]

# Ağır akıl yürütme isteyen kalıplar
_AKIL_IPUCLARI = [
    "akil ver", "ne yapmaliyim", "nasil yapmaliyim", "tavsiye", "onerir misin",
    "hangisi daha iyi", "karsilastir", "strateji", "plan yap", "mimari",
    "derin dusun", "detayli dusun", "iyice dusun",
]


def proje_bul(metin: str, projeler: list[dict]) -> dict | None:
    """Mesajda geçen proje adını bul. En uzun eşleşme kazanır."""
    m = _sadelestir(metin)
    en_iyi, en_uzun = None, 0
    for p in projeler:
        ad = _sadelestir(p["ad"])
        if not ad or len(ad) < 3:
            continue
        # tam kelime sınırında ara
        if re.search(rf"\b{re.escape(ad)}\b", m) and len(ad) > en_uzun:
            en_iyi, en_uzun = p, len(ad)
    if en_iyi:
        return en_iyi
    # Kısmi eşleşme: proje adının ilk kelimesi
    for p in projeler:
        ilk = _sadelestir(p["ad"]).split(" ")[0]
        if len(ilk) >= 4 and re.search(rf"\b{re.escape(ilk)}\b", m):
            return p
    return None


def niyet(metin: str, projeler: list[dict]) -> dict:
    """Mesajı sınıflandır: rapor | komut | akil | sohbet."""
    m = _sadelestir(metin)
    hedef = proje_bul(metin, projeler)

    if any(k in m for k in _RAPOR_IPUCLARI) and not any(
        k in m for k in _KOMUT_IPUCLARI
    ):
        return {"tur": "rapor", "proje": hedef}

    if any(k in m for k in _AKIL_IPUCLARI):
        return {"tur": "akil", "proje": hedef}

    if hedef and any(k in m for k in _KOMUT_IPUCLARI):
        return {"tur": "komut", "proje": hedef}

    return {"tur": "sohbet", "proje": hedef}


# ── yerel önce, gerekirse Claude ───────────────────────────────────────────


def yerel_once(prompt: str, sistem: str, dogrula,
               yerel_model: str | None = None,
               claude_model: str | None = None,
               azami_token: int = 2000,
               zaman_asimi: int = 420) -> dict:
    """Ağır işi önce yerel modele ver; çıktı işe yaramazsa Claude'a yükselt.

    ``dogrula(metin)`` çıktıyı sınayan bir işlev: kabul edilebilirse
    doğruluk-benzeri bir sonuç, değilse yanlış-benzeri bir şey döndürmeli.
    Yerel model ucuz ama tutarsız; doğrulamayı çağıran tanımladığı için
    "yeterince iyi"nin ölçüsü her iş için ayrı olabiliyor.

    Dönen sözlükte ``kaynak`` alanı işi kimin yaptığını söyler — günlüğe ve
    arayüze bunu yazıyoruz ki maliyetin nereden geldiği görünsün.
    """
    import gunluk

    yerel_hata = ""
    if store.ayar("agir_is_yerel", "1") == "1":
        try:
            metin = yerel_sohbet([{"role": "user", "content": prompt}],
                                 model=yerel_model or store.ayar(
                                     "agir_is_modeli", "qwen3.5:9b-tr"),
                                 sistem=sistem, azami_token=azami_token)
            if metin and not metin.startswith("Yerel modele ulaşamadım"):
                sonuc = dogrula(metin)
                if sonuc:
                    gunluk.bilgi("brain", "yerel_yeterli",
                                 "iş yerel modelle bitti",
                                 model=yerel_model or store.ayar(
                                     "agir_is_modeli", "qwen3.5:9b-tr"))
                    return {"metin": metin, "sonuc": sonuc, "kaynak": "yerel",
                            "maliyet": 0.0, "hata": False}
                yerel_hata = "yerel çıktı doğrulamadan geçmedi"
            else:
                yerel_hata = metin or "yerel model yanıt vermedi"
        except Exception as e:                  # yerel taraf asla akışı kesmesin
            yerel_hata = f"{type(e).__name__}: {e}"

        gunluk.uyari("brain", "claude_a_yukseltildi", yerel_hata)

    # Claude tarafında ayrı sistem alanı yok; talimatı prompta katıyoruz.
    d = claude_akil(sistem + "\n\n" + prompt, model=claude_model,
                    zaman_asimi=zaman_asimi)
    return {"metin": d.get("metin", ""), "sonuc": dogrula(d.get("metin", "")),
            "kaynak": "claude", "maliyet": d.get("maliyet"),
            "hata": d.get("hata", False), "yerel_hata": yerel_hata}
