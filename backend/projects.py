"""Claude Code projelerini keşfet ve durumlarını topla.

Klasör adını çözmeye çalışmak yerine oturum dosyalarındaki gerçek ``cwd``
alanını okuruz — klasör adı kodlaması kayıplıdır (boşluk ve tire ayırt
edilemez), ``cwd`` ise kesindir.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import store

CLAUDE_PROJE_KOK = Path.home() / ".claude" / "projects"

# Oturum kaydı olmayan projeler için klasör adından yol çözmede taranacak kökler
ARAMA_KOKLERI = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home(),
]

# Bu yolların altındaki hiçbir şey gerçek proje sayılmaz
DISLANAN_PARCALAR = (
    "\\appdata\\local\\temp\\",
    "\\windows\\system32",
    "\\scratchpad\\",
)


def _dislanan(yol: str) -> bool:
    d = yol.lower().replace("/", "\\")
    return any(p in d for p in DISLANAN_PARCALAR)


def _kodla(yol: str) -> str:
    """Claude Code'un proje klasörü adlandırmasını taklit et.

    Yol ayırıcıları ve harf/rakam olmayan karakterler tireye dönüşür.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", yol)


_aday_dizin: dict[str, str] | None = None


def _adaylari_indeksle() -> dict[str, str]:
    """Diskteki olası proje klasörlerini kodlanmış adlarıyla eşleştir.

    Klasör adı kodlaması kayıplı olduğu için ters çeviremeyiz; onun yerine
    gerçek klasörleri aynı kuralla kodlayıp eşleşme ararız. Bu yüzden sonuç
    her zaman diskte var olan bir yoldur.
    """
    global _aday_dizin
    if _aday_dizin is not None:
        return _aday_dizin

    dizin: dict[str, str] = {}
    for kok in ARAMA_KOKLERI:
        if not kok.is_dir():
            continue
        try:
            for alt in kok.iterdir():
                if not alt.is_dir() or alt.name.startswith("."):
                    continue
                dizin.setdefault(_kodla(str(alt)).lower(), str(alt))
                # bir seviye daha derine bak (örn. KPSS Projesi\Kpss_ios)
                try:
                    for alt2 in alt.iterdir():
                        if alt2.is_dir() and not alt2.name.startswith("."):
                            dizin.setdefault(_kodla(str(alt2)).lower(), str(alt2))
                except OSError:
                    continue
        except OSError:
            continue
    _aday_dizin = dizin
    return dizin


def _klasor_adindan_yol(klasor_adi: str) -> str | None:
    """Oturum kaydı olmayan projeler için yolu diskten eşleştirerek bul."""
    return _adaylari_indeksle().get(klasor_adi.lower())


def _oturum_bilgisi(dizin: Path) -> dict:
    """Bir proje klasöründeki .jsonl oturumlarından özet çıkar."""
    cwd = None
    basliklar: list[str] = []
    son_zaman = 0.0
    sayi = 0
    son_session_id = None
    en_yeni_dosya = None

    dosyalar = sorted(
        dizin.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for f in dosyalar:
        sayi += 1
        mt = f.stat().st_mtime
        if mt > son_zaman:
            son_zaman = mt
            en_yeni_dosya = f

    # cwd ve başlıklar için en yeni birkaç dosyayı tara (hepsi gereksiz).
    for f in dosyalar[:5]:
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for i, satir in enumerate(fh):
                    if i > 400:            # cwd baştaki kayıtlarda bulunur
                        break
                    satir = satir.strip()
                    if not satir:
                        continue
                    try:
                        d = json.loads(satir)
                    except json.JSONDecodeError:
                        continue
                    if cwd is None and d.get("cwd"):
                        cwd = d["cwd"]
                    if d.get("type") == "ai-title":
                        t = d.get("title") or d.get("aiTitle")
                        if t and t not in basliklar:
                            basliklar.append(t)
        except OSError:
            continue

    if en_yeni_dosya is not None:
        son_session_id = en_yeni_dosya.stem

    return {
        "cwd": cwd,
        "basliklar": basliklar[:5],
        "son_zaman": son_zaman or None,
        "oturum_sayisi": sayi,
        "son_session_id": son_session_id,
    }


def kesfet() -> list[dict]:
    """~/.claude/projects tarayıp veritabanını günceller."""
    if not CLAUDE_PROJE_KOK.is_dir():
        return []

    bulunan = []
    for dizin in sorted(CLAUDE_PROJE_KOK.iterdir()):
        if not dizin.is_dir():
            continue
        bilgi = _oturum_bilgisi(dizin)
        yol = bilgi["cwd"]
        if not yol:
            # Oturum kaydı yok: klasör adını diskteki gerçek klasörlerle
            # eşleştirmeyi dene. Eşleşme bulunamazsa projeyi atla.
            yol = _klasor_adindan_yol(dizin.name)
        if not yol or _dislanan(yol):
            continue
        p = Path(yol)
        if p.name.lower() in {"system32", "windows"}:
            continue

        kayit = {
            "yol": str(p),
            "ad": p.name or str(p),
            "claude_dizin": dizin.name,
            "var_mi": 1 if p.is_dir() else 0,
            "son_oturum": bilgi["son_zaman"],
            "oturum_sayisi": bilgi["oturum_sayisi"],
            "son_session_id": bilgi["son_session_id"],
        }
        pid = store.proje_kaydet(kayit)
        kayit["id"] = pid
        kayit["basliklar"] = bilgi["basliklar"]
        bulunan.append(kayit)

    # Artık dışlanan ya da diskten silinmiş kayıtları temizle.
    for p in store.projeler():
        if _dislanan(p["yol"]):
            store.proje_sil_yol(p["yol"])
    store.proje_varlik_guncelle({k["yol"] for k in bulunan})

    return bulunan


# ── proje durumu (LLM kullanmadan, ücretsiz) ───────────────────────────────


def _git(yol: str, *args: str, timeout: int = 10) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=yol,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_durumu(yol: str) -> dict:
    if not Path(yol, ".git").exists():
        return {"git": False}
    dal = _git(yol, "rev-parse", "--abbrev-ref", "HEAD")
    kirli = _git(yol, "status", "--porcelain")
    son = _git(yol, "log", "-1", "--format=%h %s|%ct")
    commit, mesaj, zaman = None, None, None
    if son and "|" in son:
        sol, sag = son.rsplit("|", 1)
        parts = sol.split(" ", 1)
        commit = parts[0]
        mesaj = parts[1] if len(parts) > 1 else ""
        try:
            zaman = float(sag)
        except ValueError:
            pass
    return {
        "git": True,
        "dal": dal,
        "degisiklik_sayisi": len([l for l in (kirli or "").splitlines() if l.strip()]),
        "son_commit": commit,
        "son_commit_mesaj": mesaj,
        "son_commit_zaman": zaman,
    }


_KOD_UZANTILARI = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".dart", ".java", ".kt", ".swift",
    ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css",
}
_ATLA = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", "build", "dist",
    ".dart_tool", ".gradle", "Pods", ".next", "target", ".idea", ".vscode",
}


def dosya_ozeti(yol: str, azami_dosya: int = 8000) -> dict:
    """Kaba kod istatistiği. Büyük ağaçlarda erken durur."""
    kod, toplam, boyut = 0, 0, 0
    diller: dict[str, int] = {}
    try:
        for kok, dizinler, dosyalar in os.walk(yol):
            dizinler[:] = [d for d in dizinler if d not in _ATLA and not d.startswith(".")]
            for d in dosyalar:
                toplam += 1
                if toplam > azami_dosya:
                    return {"dosya": toplam, "kod_dosyasi": kod,
                            "diller": diller, "boyut_mb": round(boyut / 1e6, 1),
                            "kesildi": True}
                uz = Path(d).suffix.lower()
                if uz in _KOD_UZANTILARI:
                    kod += 1
                    diller[uz] = diller.get(uz, 0) + 1
                try:
                    boyut += (Path(kok) / d).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return {"dosya": toplam, "kod_dosyasi": kod, "diller": diller,
            "boyut_mb": round(boyut / 1e6, 1), "kesildi": False}


def proje_durumu(pid: int, derin: bool = False) -> dict:
    p = store.proje(pid)
    if not p:
        return {"hata": "proje bulunamadı"}
    d = dict(p)
    if p["var_mi"]:
        d["git_durumu"] = git_durumu(p["yol"])
        if derin:
            d["dosya_ozeti"] = dosya_ozeti(p["yol"])
    return d


def genel_rapor() -> dict:
    """Tüm projelerin özeti — hiç LLM çağrısı yapmaz, dolayısıyla ücretsizdir."""
    liste = []
    for p in store.projeler():
        kayit = {
            "id": p["id"],
            "ad": p["ad"],
            "yol": p["yol"],
            "var_mi": bool(p["var_mi"]),
            "son_oturum": p["son_oturum"],
            "oturum_sayisi": p["oturum_sayisi"],
            "etiket": p["etiket"],
            "not_metni": p["not_metni"],
        }
        if p["var_mi"]:
            kayit["git_durumu"] = git_durumu(p["yol"])
        liste.append(kayit)

    simdi = time.time()
    aktif = [p for p in liste if p["son_oturum"] and simdi - p["son_oturum"] < 7 * 86400]
    kirli = [p for p in liste
             if p.get("git_durumu", {}).get("degisiklik_sayisi", 0) > 0]
    kayip = [p for p in liste if not p["var_mi"]]

    return {
        "projeler": liste,
        "ozet": {
            "toplam": len(liste),
            "diskte_var": sum(1 for p in liste if p["var_mi"]),
            "son_hafta_aktif": len(aktif),
            "kaydedilmemis_degisiklik": len(kirli),
            "diskte_yok": len(kayip),
        },
    }
