"""Proje brifingi — programın projeyi "anlaması".

İki katman var:

1. **Yerel brifing** (ücretsiz): README, manifest dosyaları, dosya ağacı, git
   geçmişi ve geçmiş Claude oturumlarının başlıklarından derlenir. Hiçbir model
   çağrılmaz. Taslak yazarken ve otomatik devamda bağlam olarak kullanılır.

2. **Derin brifing** (abonelik kotası): projeyi Claude'a inceletip özet
   çıkartır. Kullanıcı isterse tetiklenir, sonuç veritabanında saklanır.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import store

MANIFESTLER = [
    "package.json", "pyproject.toml", "requirements.txt", "pubspec.yaml",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "composer.json",
    "Gemfile", "CMakeLists.txt", "*.csproj",
]

# Projelerin kökünde tutulan, Asistan'ın ürettiği özet dosyası.
OZET_DOSYA = "ASISTAN-OZET.md"

BELGELER = ["README.md", "README.txt", "readme.md", "BENIOKU.md",
            "CLAUDE.md", "PLAN.md", "TODO.md", "NOTLAR.md"]

_ATLA = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", "build", "dist",
    ".dart_tool", ".gradle", "Pods", ".next", "target", ".idea", ".vscode",
    ".expo", "vendor", "coverage",
}


def _oku(yol: Path, azami: int = 1500) -> str:
    try:
        m = yol.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return m[:azami] + ("…" if len(m) > azami else "")


def _agac(kok: str, azami_derinlik: int = 2, azami_giris: int = 60) -> list[str]:
    """Üst seviye klasör/dosya listesi — projenin şeklini gösterir."""
    kokp = Path(kok)
    satirlar: list[str] = []
    for derinlik in range(azami_derinlik + 1):
        if len(satirlar) >= azami_giris:
            break
        try:
            hedefler = [kokp] if derinlik == 0 else [
                d for d in kokp.rglob("*")
                if d.is_dir()
                and len(d.relative_to(kokp).parts) == derinlik
                and not any(p in _ATLA or p.startswith(".")
                            for p in d.relative_to(kokp).parts)
            ]
        except OSError:
            break
        for h in hedefler[:20]:
            try:
                girisler = sorted(h.iterdir(), key=lambda x: (x.is_file(), x.name))
            except OSError:
                continue
            for g in girisler:
                if g.name.startswith(".") or g.name in _ATLA:
                    continue
                bag = str(g.relative_to(kokp)).replace("\\", "/")
                satirlar.append(bag + ("/" if g.is_dir() else ""))
                if len(satirlar) >= azami_giris:
                    break
            if len(satirlar) >= azami_giris:
                break
    return sorted(set(satirlar))


def _git_gecmis(yol: str, adet: int = 8) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "log", f"-{adet}", "--format=%ad %s", "--date=short"],
            cwd=yol, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
        return r.stdout.strip().splitlines() if r.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return []


def _oturum_basliklari(claude_dizin: str | None, adet: int = 8) -> list[str]:
    """Geçmiş Claude oturumlarının başlıkları — projede ne konuşulduğunu gösterir."""
    if not claude_dizin:
        return []
    kok = Path.home() / ".claude" / "projects" / claude_dizin
    if not kok.is_dir():
        return []
    basliklar: list[str] = []
    dosyalar = sorted(kok.glob("*.jsonl"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    for f in dosyalar[:6]:
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for i, satir in enumerate(fh):
                    if i > 600:
                        break
                    if '"ai-title"' not in satir:
                        continue
                    try:
                        d = json.loads(satir)
                    except json.JSONDecodeError:
                        continue
                    t = d.get("title") or d.get("aiTitle")
                    if t and t not in basliklar:
                        basliklar.append(t)
        except OSError:
            continue
        if len(basliklar) >= adet:
            break
    return basliklar[:adet]


def yerel_brifing(pid: int) -> str:
    """Model çağırmadan, dosyalardan derlenen proje brifingi."""
    p = store.proje(pid)
    if not p:
        return ""
    yol = p["yol"]
    if not Path(yol).is_dir():
        return f"{p['ad']} — klasör diskte yok ({yol})."

    bolumler = [f"PROJE: {p['ad']}", f"YOL: {yol}"]

    # Asistan özeti — varsa en güncel ve en yoğun kaynak, önce o gelir.
    ozet_f = Path(yol, OZET_DOSYA)
    if ozet_f.is_file():
        icerik = _oku(ozet_f, 3000)
        if icerik:
            bolumler.append(f"--- {OZET_DOSYA} (asistan özeti) ---\n" + icerik)

    # Belgeler
    for ad in BELGELER:
        f = Path(yol, ad)
        if f.is_file():
            icerik = _oku(f, 1200)
            if icerik:
                bolumler.append(f"--- {ad} ---\n{icerik}")
            break

    # Manifest
    for kalip in MANIFESTLER:
        for f in Path(yol).glob(kalip):
            if f.is_file():
                bolumler.append(f"--- {f.name} ---\n{_oku(f, 700)}")
                break
        else:
            continue
        break

    # Dosya ağacı
    agac = _agac(yol)
    if agac:
        bolumler.append("--- YAPI ---\n" + "\n".join(agac))

    # Git geçmişi
    gecmis = _git_gecmis(yol)
    if gecmis:
        bolumler.append("--- SON COMMITLER ---\n" + "\n".join(gecmis))

    # Geçmiş oturum başlıkları
    basliklar = _oturum_basliklari(p.get("claude_dizin"))
    if basliklar:
        bolumler.append("--- GEÇMİŞ ÇALIŞMALAR ---\n" +
                        "\n".join("• " + b for b in basliklar))

    if p.get("not_metni"):
        bolumler.append(f"--- SENİN NOTUN ---\n{p['not_metni']}")

    if p.get("ozet"):
        bolumler.append(f"--- DERİN BRİFİNG ---\n{p['ozet']}")

    return "\n\n".join(bolumler)


def kisa_brifing(pid: int, azami: int = 1800) -> str:
    """Taslak yazımı için kısaltılmış brifing."""
    tam = yerel_brifing(pid)
    return tam[:azami] + ("…" if len(tam) > azami else "")


OZET_GOREVI = """Bu projenin kökünde ASISTAN-OZET.md adlı bir dosya tut.

Dosya yoksa oluştur, varsa güncelle. İçeriği şu başlıklarla, Türkçe, düz
markdown olsun:

# <proje adı>

## Ne işe yarıyor
Bir iki cümle. Kime hitap ediyor, ne çözüyor.

## Teknoloji
Diller, çatılar, önemli bağımlılıklar.

## Yapı
Ana klasörler ve her birinin işi. En fazla 10 satır.

## Şu anki durum
Nerede kalınmış, ne çalışıyor, ne yarım. Testler varsa son durumu.

## Yapılan değişiklikler
Tarihli liste, en yeni üstte. Bu bölümü ASLA silme, sadece üstüne ekle.
Her satır: `- YYYY-AA-GG — ne değişti`
Bu turda bir şey değiştirdiysen onu da ekle. Değiştirmediysen ekleme.
Git geçmişi varsa son commitlerden geriye dönük doldur.

## Sıradaki adımlar
Yapılması mantıklı 3 madde.

Kurallar:
- Yalnızca ASISTAN-OZET.md dosyasını oluştur/güncelle. Başka hiçbir dosyaya
  dokunma, kod değiştirme, komut çalıştırma gereği yoksa çalıştırma.
- Bilmediğini uydurma; emin olmadığın yeri "belirsiz" diye yaz.
- Dosyayı yazdıktan sonra bana bir cümlelik özet ver."""


DERIN_ISTEM = """Bu projeyi incele ve kısa bir brifing çıkar. Şunları yaz:

1. Proje ne işe yarıyor, kime hitap ediyor (1-2 cümle)
2. Hangi teknolojilerle yazılmış
3. Kod nasıl örgütlenmiş, ana parçalar neler
4. Şu an hangi noktada, yarım kalan ya da eksik ne var
5. Mantıklı bir sonraki adım ne olurdu

Türkçe yaz, en fazla 250 kelime, düz metin. Hiçbir dosyayı değiştirme."""
