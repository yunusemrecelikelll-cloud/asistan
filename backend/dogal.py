"""Doğal konuşma katmanı — yazı dilini konuşma diline çevirir.

Sorun şu: modelin yazdığı metin **okunmak** için yazılmış oluyor. Uzun
cümleler, virgüllü sıralamalar, "ayrıca", "dolayısıyla" gibi bağlaçlar…
Bunu olduğu gibi seslendirince, sesin kendisi ne kadar iyi olursa olsun
robot gibi duyuluyor. Çünkü sorun seste değil, metinde.

Burada iki şey yapıyoruz:

1. **Yeniden yazma** — metni konuşur gibi kısaltıp doğallaştırıyoruz; araya
   duraklama ve düşünme sesleri giriyor.
2. **Bürünsel parçalama** — metni parçalara bölüp her parçayı farklı hız ve
   perdeyle seslendiriyoruz. Tek tonda akan ses, doğru kelimelerle bile
   robotik duyulur; asıl insanlık hissi tempo değişiminden geliyor.

İşaretler metne köşeli parantezle giriyor ve seslendirmede bürünsel ipucuna
çevriliyor:

    [dusun]     düşünme sesi — "ııı", öncesinde kısa duraklama
    [gul]       kısa gülüş
    [dur]       duraklama
    [yavas] …   sonrasını yavaşlat (ciddi/önemli kısım)
    [hizli] …   sonrasını hızlandır (heyecanlı/önemsiz kısım)

Ses klonlama (XTTS) devreye girdiğinde bu katman aynen kalır: iyi bir ses
kötü metni kurtarmıyor, ikisi birlikte çalışıyor.
"""

from __future__ import annotations

import re

import store

# ── işaretler ──────────────────────────────────────────────────────────────

# Düşünme sesleri — hep aynısı olursa o da robotlaşır, sırayla dönüyoruz.
DUSUNME = ("ııı", "hmm", "şey", "yani")
GULUS = ("heh", "haha")

ISARET = re.compile(r"\[(dusun|gul|dur|yavas|hizli|vurgu|normal)\]")


_ORTAK_KURALLAR = """- Rakamları okunduğu gibi bırak, sembol kullanma (% yerine "yüzde").
- Madde işareti, başlık, tırnak, emoji kullanma.
- Anlamı DEĞİŞTİRME. Bilgi ekleme, çıkarma. Sadece söyleyişi değiştir.
- Metin zaten kısa ve konuşma diliyse fazla oynama.

Yalnızca yeniden yazılmış metni ver, başka hiçbir şey yazma."""

SAKIN_TALIMATI = """Bu metni, sesli okunacak biçimde yeniden yaz.

Kurallar:
- Konuşur gibi yaz. Kısa cümleler kur. "Ayrıca", "dolayısıyla", "ilaveten"
  gibi yazı dili bağlaçlarını at.
- Araya doğal duraklamalar koy. En fazla iki kez [dusun] kullanabilirsin;
  düşünmenin gerçekten anlamlı olduğu yerde.
- Gerçekten komikse en fazla bir kez [gul] koy. Zorlama.
- Önemli bir uyarı ya da rakam varsa öncesine [yavas] koy.
""" + _ORTAK_KURALLAR

CANLI_TALIMATI = """Bu metni, HAREKETLİ konuşan biri söylüyormuş gibi yeniden yaz.

Hedef: kitap okuyan bir spiker değil, karşısındakiyle hararetle konuşan biri.

EN ÖNEMLİ KURAL: Hiçbir bilgiyi değiştirme, ekleme, çıkarma. Bütün sayılar,
tarihler, saatler ve isimler AYNEN kalacak. Yeni cümle uydurma. Soru sorma.
Metinde olmayan bir şeyi söyleme. Sadece SÖYLEYİŞİ değiştir.

Kurallar:
- Uzun cümleyi böl, ama parçaların hepsi özgün metindeki bilgiyi taşısın.
- Hafif konuşma ağzı kullanabilirsin ("bi", "yapıcaksın"). Abartma.
- En fazla iki yere "bak", "yani", "hadi" gibi bir bağlaç ekleyebilirsin.
- Vurgulanacak kelimeden önce [vurgu] koy.
- Hızlanacak yerlere [hizli], ağır söylenecek yerlere [yavas] koy.
  Tempo değişimi asıl mesele; bunları rahat kullan.
- En fazla bir [dusun], en fazla bir [gul].
""" + _ORTAK_KURALLAR

SERT_TALIMATI = """Bu metni, sert konuşan bir koç söylüyormuş gibi yeniden yaz.

Kurallar:
- Kısa, tok cümleler. Yumuşatıcı kelime yok ("belki", "sanırım", "olabilir").
- Rakamı öne al, yorumu arkaya.
- Vurgulanacak kelimeden önce [vurgu], ağır söylenecek yerde [yavas] koy.
- Duraklamayı sessizlik olarak kullan: [dur].
- Gülüş kullanma. En fazla bir [dusun].
""" + _ORTAK_KURALLAR

USLUPLAR = {"sakin": SAKIN_TALIMATI, "canli": CANLI_TALIMATI,
            "sert": SERT_TALIMATI}


def uslup() -> str:
    return store.ayar("konusma_uslubu", "canli")


DOGALLASTIR_TALIMATI = SAKIN_TALIMATI       # geriye dönük uyumluluk


def acik_mi() -> bool:
    return store.ayar("dogal_konusma", "1") == "1"


# Yanıtı üreten modele doğrudan verilecek bürünsel kurallar. Metni önce
# üretip sonra ikinci bir modele yeniden yazdırmak sesli turda cümle başına
# bir çağrı daha demekti; işaretleri baştan koydurunca o çağrı tamamen
# kalkıyor ve bilgi kaybı riski de ortadan kalkıyor — çünkü yeniden yazan
# yok.
_ISARET_ORTAK = """
Konuşma işaretleri (köşeli parantezle, metnin içine serpiştir):
[dur] duraklama, [dusun] düşünme sesi, [gul] kısa gülüş,
[yavas] sonrasını ağır söyle, [hizli] sonrasını hızlı söyle,
[vurgu] sonraki kelimeyi vurgula.
Sadece bu altı işareti kullan, başka köşeli parantez açma."""

ISARET_KURALLARI = {
    "sakin": """
Konuşur gibi yaz, kısa cümleler kur. Önemli rakamdan önce [yavas] koy.
En fazla bir [dusun] kullan.""" + _ISARET_ORTAK,
    "canli": """
Hararetle konuşan biri gibi yaz. Tempoyu değiştir: [hizli] ve [yavas]
işaretlerini rahat kullan, vurgulanacak kelimeden önce [vurgu] koy.
En fazla bir [dusun], en fazla bir [gul].""" + _ISARET_ORTAK,
    "sert": """
Sert bir koç gibi yaz. Kısa tok cümleler, yumuşatıcı kelime yok.
Rakamı öne al. [vurgu] ve [dur] kullan, [gul] kullanma.""" + _ISARET_ORTAK,
}


def sesli_ek() -> str:
    """Sohbet talimatına eklenecek işaret kuralları (üsluba göre)."""
    if not acik_mi():
        return ""
    return ISARET_KURALLARI.get(uslup(), ISARET_KURALLARI["sakin"])


def dogallastir(metin: str) -> str:
    """Metni konuşma diline çevir. Model tökezlerse özgün metin döner."""
    metin = (metin or "").strip()
    if not metin or not acik_mi():
        return metin
    # Kısa ve zaten konuşma dilindeyse modele hiç gitmeye değmez.
    if len(metin) < 60:
        return metin

    import brain

    try:
        yanit = brain.yerel_sohbet(
            [{"role": "user", "content": metin}],
            model=store.ayar("dogal_modeli", "qwen3.5:4b-tr"),
            sistem=USLUPLAR.get(uslup(), SAKIN_TALIMATI),
            azami_token=min(900, len(metin) // 2 + 200), sicaklik=0.4)
    except Exception:
        return metin

    yanit = (yanit or "").strip()
    if not yanit or yanit.startswith("Yerel modele ulaşamadım"):
        return metin
    if not icerik_korundu(metin, yanit):
        return metin
    return yanit


# Modelin kendi görevinden bahsetmeye başladığını ele veren kalıplar.
# Tek tek kelime yerine öbek arıyoruz: "metni" gibi sıradan bir kelimeye
# takılırsak, tanıtım metni yazmakla ilgili gerçek bir görev cümlesi de
# reddedilir ve doğallaştırma boşuna atlanır.
SIZINTI = ("yeniden yazdım", "yeniden yazılmış", "istediğin metni",
           "verilen metni", "bu metni", "yukarıdaki metin", "talimata göre",
           "kurallara göre", "prompt", "asistan olarak", "işte metin")


def icerik_korundu(ozgun: str, yeni: str) -> bool:
    """Doğallaştırma bilgi kaybettirdi mi?

    Yerel model üsluba odaklanırken sayıyı düşürebiliyor, cümle uydurabiliyor
    ya da kendi görevinden bahsetmeye başlayabiliyor. Bir koçun "üç işten
    birini bitirdin"i "birini bitirdin"e çevirmesi, robotik konuşmasından
    daha kötü. O yüzden şüphede kalırsak özgün metne dönüyoruz.
    """
    if not 0.5 * len(ozgun) < len(yeni) < 1.9 * len(ozgun):
        return False

    d = yeni.casefold()
    if any(k in d for k in SIZINTI):
        return False

    # Sayılar birebir korunmalı — saat, adet, yüzde hepsi burada.
    ozgun_sayilar = re.findall(r"\d+(?:[.,]\d+)?", ozgun)
    yeni_sayilar = re.findall(r"\d+(?:[.,]\d+)?", yeni)
    if sorted(ozgun_sayilar) != sorted(yeni_sayilar):
        return False

    # Yazıyla yazılmış sayılar da kaybolmasın ("üç işten" → "işten").
    for kelime in ("bir", "iki", "üç", "dört", "beş", "altı", "yedi",
                   "sekiz", "dokuz", "on", "yüzde"):
        if (f" {kelime}" in f" {ozgun.casefold()}"
                and f" {kelime}" not in f" {d}"):
            return False

    # Metinde olmayan soru uydurulmasın.
    if yeni.count("?") > ozgun.count("?"):
        return False
    return True


# ── bürünsel parçalama ─────────────────────────────────────────────────────


def _cumlelere_bol(metin: str) -> list[str]:
    parcalar = re.split(r"(?<=[.!?…])\s+", metin)
    return [p.strip() for p in parcalar if p.strip()]


# Tanınmayan köşeli parantezler: model zaman zaman "[bi]", "[Bvurgu]" gibi
# bozuk işaretler uyduruyor. Temizlenmezse olduğu gibi sesli okunuyorlar.
_BOZUK_ISARET = re.compile(r"\[(?!(?:dusun|gul|dur|yavas|hizli|vurgu|normal)\])"
                           r"[^\]\n]{0,20}\]")


def temizle_isaretler(metin: str) -> str:
    return _BOZUK_ISARET.sub("", metin or "").replace("  ", " ")


def parcala(metin: str) -> list[dict]:
    """Metni seslendirme parçalarına ayır: her biri kendi hız/perdesiyle.

    Dönen her öğe: ``{"metin", "hiz", "perde", "sonra_ms"}``. ``hiz`` ve
    ``perde`` edge-tts'in beklediği yüzde/Hz biçiminde.
    """
    metin = temizle_isaretler((metin or "").strip())
    if not metin:
        return []

    parcalar: list[dict] = []
    kip = {"hiz": 0, "perde": 0}
    dusunme_sirasi = 0
    gulus_sirasi = 0

    for cumle in _cumlelere_bol(metin):
        # Cümle içindeki işaretleri sırayla işle
        son = 0
        parca_metni = ""
        sonra = 0
        for m in ISARET.finditer(cumle):
            parca_metni += cumle[son:m.start()]
            son = m.end()
            etiket = m.group(1)
            if etiket == "dusun":
                d = DUSUNME[dusunme_sirasi % len(DUSUNME)]
                dusunme_sirasi += 1
                # Düşünme sesi ayrı bir parça: daha yavaş ve alçak perdeden.
                if parca_metni.strip():
                    parcalar.append({"metin": parca_metni.strip(),
                                     **kip, "sonra_ms": 120})
                    parca_metni = ""
                parcalar.append({"metin": d + "...", "hiz": -25,
                                 "perde": -8, "sonra_ms": 260})
            elif etiket == "gul":
                g = GULUS[gulus_sirasi % len(GULUS)]
                gulus_sirasi += 1
                if parca_metni.strip():
                    parcalar.append({"metin": parca_metni.strip(),
                                     **kip, "sonra_ms": 80})
                    parca_metni = ""
                parcalar.append({"metin": g + ".", "hiz": 10, "perde": 12,
                                 "sonra_ms": 200})
            elif etiket == "dur":
                sonra = 350
            elif etiket == "vurgu":
                # Tek kelimelik vurgu: sonraki parça belirgin biçimde yavaş
                # ve alçak perdeden okunur, öncesinde küçük bir boşluk olur.
                if parca_metni.strip():
                    parcalar.append({"metin": parca_metni.strip(),
                                     **kip, "sonra_ms": 220})
                    parca_metni = ""
                kip = {"hiz": -18, "perde": -6}
            elif etiket == "yavas":
                kip = {"hiz": -14, "perde": -4}
            elif etiket == "hizli":
                kip = {"hiz": 18, "perde": 5}
            else:                                   # normal
                kip = {"hiz": 0, "perde": 0}

        parca_metni += cumle[son:]
        parca_metni = parca_metni.strip()
        if parca_metni:
            parcalar.append({"metin": parca_metni, **kip,
                             "sonra_ms": max(sonra, 140)})

    # Tek tonda akmasın: uzun anlatımlarda cümleden cümleye hafif tempo
    # oynatıyoruz. Değerler küçük — abartınca sarhoş gibi duyuluyor.
    # Salınım genişliği üsluba bağlı. Sakin kipte hafif; canlı kipte belirgin
    # — asıl "robot değil" hissi buradan geliyor.
    if uslup() == "canli":
        hizlar, perdeler = (6, 16, -6, 12, -10, 4), (4, 9, -5, 7, -6, 2)
    elif uslup() == "sert":
        hizlar, perdeler = (-4, 2, -8, 0, -6, 3), (-2, 1, -4, 0, -3, 2)
    else:
        hizlar, perdeler = (0, 4, -3, 2, -5, 1), (0, 2, -2, 3, -1, 1)

    normal = [p for p in parcalar if p["hiz"] == 0 and p["perde"] == 0]
    for i, p in enumerate(normal):
        p["hiz"] = hizlar[i % len(hizlar)]
        p["perde"] = perdeler[i % len(perdeler)]

    return parcalar


def isaretleri_at(metin: str) -> str:
    """Ekranda gösterilecek hâli — işaretler görünmesin."""
    return ISARET.sub("", temizle_isaretler(metin)).replace("  ", " ").strip()
