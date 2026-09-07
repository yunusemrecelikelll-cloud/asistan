"""Ekran süresi — hangi uygulamada ne kadar vakit geçti.

Windows API'sini doğrudan ctypes ile çağırıyoruz; ek bağımlılık yok. Her
turda yalnızca **öndeki pencerenin** hangi programa ait olduğuna bakılır:
pencere başlığı kaydedilir ama içerik okunmaz, tuş dinlenmez, ekran görüntüsü
alınmaz.

Varsayılan **kapalı** (``ekran_takip = 0``). Bu en müdahaleci parça olduğu
için açmak bilinçli bir seçim olmalı.

Boşta geçen süre sayılmaz: kullanıcı klavye/fareye 3 dakikadır dokunmadıysa
o süre hiçbir uygulamaya yazılmaz — bilgisayarın başında olmadan "5 saat
tarayıcı" yazmasın.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import threading
import time
from datetime import date

import gunluk
import store

ARALIK_SN = 15          # kaç saniyede bir bakılsın
BOSTA_ESIK_SN = 180     # bu kadar dokunulmadıysa "boşta" say

# Görünen adı daha okunur yapalım.
OKUNUR_AD = {
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
    "code.exe": "VS Code", "windowsterminal.exe": "Terminal",
    "explorer.exe": "Dosya Gezgini", "anycubicslicernext.exe": "Anycubic Slicer",
    "orcaslicer.exe": "OrcaSlicer", "blender.exe": "Blender",
    "fusion360.exe": "Fusion 360", "spotify.exe": "Spotify",
    "discord.exe": "Discord", "whatsapp.exe": "WhatsApp",
    "telegram.exe": "Telegram", "steam.exe": "Steam",
    "photoshop.exe": "Photoshop", "notepad.exe": "Not Defteri",
}

_windows = os.name == "nt"

if _windows:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    class SONGIRDI(ctypes.Structure):
        _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def _on_pencere() -> tuple[str, str] | None:
    """(exe adı, pencere başlığı) — bulunamazsa None."""
    if not _windows:
        return None
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None

        uzunluk = _user32.GetWindowTextLengthW(hwnd)
        tampon = ctypes.create_unicode_buffer(uzunluk + 1)
        _user32.GetWindowTextW(hwnd, tampon, uzunluk + 1)
        baslik = tampon.value

        pid = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None

        # PROCESS_QUERY_LIMITED_INFORMATION — yalnızca yolu okumak için
        tutamac = _kernel32.OpenProcess(0x1000, False, pid.value)
        if not tutamac:
            return None
        try:
            yol = ctypes.create_unicode_buffer(1024)
            boyut = wt.DWORD(1024)
            if not _kernel32.QueryFullProcessImageNameW(
                    tutamac, 0, yol, ctypes.byref(boyut)):
                return None
            exe = os.path.basename(yol.value)
        finally:
            _kernel32.CloseHandle(tutamac)
        return exe, baslik
    except (OSError, AttributeError, ValueError):
        return None


def _bosta_sn() -> float:
    """Son klavye/fare hareketinden bu yana geçen saniye."""
    if not _windows:
        return 0.0
    try:
        g = SONGIRDI()
        g.cbSize = ctypes.sizeof(SONGIRDI)
        if not _user32.GetLastInputInfo(ctypes.byref(g)):
            return 0.0
        return (_kernel32.GetTickCount() - g.dwTime) / 1000.0
    except (OSError, AttributeError):
        return 0.0


def okunur(exe: str) -> str:
    return OKUNUR_AD.get(exe.lower(), exe.rsplit(".", 1)[0].title())


# ── döngü ──────────────────────────────────────────────────────────────────

_durdur = threading.Event()
_kilit = threading.Lock()
_calisiyor = False


def _dongu() -> None:
    son = time.time()
    while not _durdur.is_set():
        _durdur.wait(ARALIK_SN)
        if _durdur.is_set():
            break
        simdi = time.time()
        gecen = min(simdi - son, ARALIK_SN * 2)     # uykudan uyanmayı yut
        son = simdi

        if store.ayar("ekran_takip", "0") != "1":
            continue
        if _bosta_sn() > BOSTA_ESIK_SN:
            continue                                # başında değil

        p = _on_pencere()
        if not p:
            continue
        exe, baslik = p
        try:
            store.ekran_ekle(date.today().isoformat(), okunur(exe),
                             int(gecen), baslik[:160] or None)
        except Exception as e:                      # döngü asla ölmesin
            gunluk.hata("ekran", "yazma_hatasi", istisna=e)


def baslat() -> None:
    global _calisiyor
    if not _windows:
        return
    with _kilit:
        if _calisiyor:
            return
        _calisiyor = True
        _durdur.clear()
        threading.Thread(target=_dongu, daemon=True, name="ekran").start()


def durdur() -> None:
    global _calisiyor
    with _kilit:
        _durdur.set()
        _calisiyor = False


# ── raporlama ──────────────────────────────────────────────────────────────


def _sure(saniye: int) -> str:
    dk = saniye // 60
    return f"{dk // 60} sa {dk % 60} dk" if dk >= 60 else f"{dk} dk"


def panel(gun: int = 7) -> dict:
    from datetime import timedelta

    bitis = date.today()
    baslangic = bitis - timedelta(days=max(1, gun) - 1)
    bugun = bitis.isoformat()

    donem = store.ekran_araligi(baslangic.isoformat(), bugun)
    toplam = sum(u["saniye"] for u in donem)
    return {
        "acik": store.ayar("ekran_takip", "0") == "1",
        "destekleniyor": _windows,
        "gun": gun,
        "bugun_saniye": store.ekran_toplam(bugun),
        "bugun_metni": _sure(store.ekran_toplam(bugun)),
        "toplam_saniye": toplam,
        "toplam_metni": _sure(toplam),
        "gunluk_ortalama": _sure(toplam // max(1, gun)),
        "bugun": [{**u, "metin": _sure(u["saniye"])}
                  for u in store.ekran_gunu(bugun, 15)],
        "donem": [{**u, "metin": _sure(u["saniye"]),
                   "yuzde": round(100 * u["saniye"] / toplam) if toplam else 0}
                  for u in donem[:15]],
    }


def koc_ozeti() -> str:
    """Koçun kullanacağı kısa özet. Veri yoksa boş döner."""
    if store.ayar("ekran_takip", "0") != "1":
        return ""
    p = panel(7)
    if not p["toplam_saniye"]:
        return ""
    ust = ", ".join(f"{u['uygulama']} {u['metin']}" for u in p["donem"][:4])
    return (f"EKRAN SÜRESİ (7 gün): toplam {p['toplam_metni']}, "
            f"günlük ortalama {p['gunluk_ortalama']}. En çok: {ust}.")
