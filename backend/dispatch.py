"""Projelere komut gönderme — `claude -p` başsız (headless) çağrısı.

Tam yetki modunda çalışır: onay beklemez. Buna karşılık her eylem denetim
günlüğüne yazılır ve git deposu olan projelerde, çalışma ağacı kirliyse
değişiklikten önce kurtarılabilir bir kontrol noktası bırakılır.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import store

# claude CLI Windows'ta .cmd/.ps1 kabuğu üzerinden gelir; tam yolu çözelim.
CLAUDE_BIN = shutil.which("claude") or "claude"


def _agaci_oldur(p: subprocess.Popen) -> None:
    """Süreci ÇOCUKLARIYLA birlikte öldür.

    Windows'ta ``claude`` bir .CMD sarmalayıcısı: cmd.exe -> node. ``p.kill()``
    yalnızca cmd.exe'yi öldürüyor, asıl işi yapan node hayatta kalıyordu —
    dosya yazmaya, kota tüketmeye devam ediyor ve "iptal" hiçbir şeyi
    durdurmuyordu. taskkill /T bütün ağacı alır.
    """
    if p.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(p.pid)],
                capture_output=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            pass
    # taskkill ağacı almadıysa (yetki, yarış) ya da Windows değilsek
    # doğrudan öldür. POSIX'te süreç grubuna DOKUNMUYORUZ: alt süreci ayrı
    # bir oturumda başlatmadığımız için killpg sunucunun kendi grubunu da
    # alırdı — yani asistanı kendi kendine kapatırdı.
    if p.poll() is None:
        try:
            p.kill()
        except OSError:
            pass

_calisanlar: dict[int, subprocess.Popen] = {}
# Kullanıcının iptal ettiği eylemler. İptal sürecin ölmesine yol açıyor,
# süreç ölünce _calistir normal akışında "hata" yazıp iptal damgasını
# eziyordu; burada işaretleyip o yazmayı atlıyoruz.
_iptal_edilenler: set[int] = set()
_kilit = threading.Lock()


def abonelik_ortami() -> dict:
    """claude CLI'ın her zaman Claude aboneliğiyle çalışmasını garanti et.

    Ortamda bir API anahtarı bulunursa CLI onu kullanıp faturalı API'ye
    düşebilir. Kullanıcı ek API ücreti istemediği için bu değişkenleri alt
    süreçten temizliyoruz; CLI böylece ~/.claude içindeki abonelik oturumunu
    kullanır.
    """
    import os

    ortam = os.environ.copy()
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
              "ANTHROPIC_BASE_URL", "CLAUDE_API_KEY"):
        ortam.pop(k, None)
    return ortam


# ── git kontrol noktası ────────────────────────────────────────────────────


def _git(yol: str, *args: str, timeout: int = 15) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args], cwd=yol, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return r.returncode, (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def kontrol_noktasi(yol: str) -> str | None:
    """Değişiklik öncesi kurtarılabilir bir işaret bırak.

    ``git stash create`` çalışma ağacına dokunmadan mevcut durumu içeren bir
    commit nesnesi üretir; bunu ``refs/asistan/<zaman>`` altına bağlarız.
    Böylece bir şey ters giderse ``git stash apply <sha>`` ile geri alınır.
    Temiz ağaçta yapacak bir şey yoktur, sadece HEAD kaydedilir.
    """
    if not Path(yol, ".git").exists():
        return None
    kod, kirli = _git(yol, "status", "--porcelain")
    if kod != 0:
        return None
    if not kirli.strip():
        kod, head = _git(yol, "rev-parse", "HEAD")
        return f"HEAD:{head}" if kod == 0 else None

    kod, sha = _git(yol, "stash", "create")
    if kod != 0 or not sha:
        return None
    etiket = f"refs/asistan/{int(time.time())}"
    _git(yol, "update-ref", etiket, sha)
    return f"stash:{sha}"


# ── komut gönderimi ────────────────────────────────────────────────────────


def _komut_kur(model: str, session_id: str | None, devam: bool) -> list[str]:
    """Komut satırını kur. Prompt argüman olarak GEÇİLMEZ, stdin'den verilir.

    Windows'ta ``claude`` bir .CMD sarmalayıcısıdır; çok satırlı bir metni
    argüman olarak geçtiğimizde satır sonu komut satırını bölüyor ve arkadan
    gelen bayraklar (``--output-format``, ``--permission-mode``) sessizce
    düşüyordu. Bu yüzden prompt stdin'den akıtılıyor.
    """
    argv = [CLAUDE_BIN, "-p", "--output-format", "json"]
    if model:
        argv += ["--model", model]
    if devam and session_id:
        argv += ["--resume", session_id]
    tur = store.ayar("komut_azami_tur", "")
    if tur and tur.isdigit() and int(tur) > 0:
        # Keşif turunu sınırlamak maliyeti doğrudan aşağı çeker.
        argv += ["--max-turns", tur]

    # Başsız kipte Claude izin soramaz; sorarsa istek reddedilir ve iş
    # yapılmadan döner. Bu yüzden izin kipini açıkça veriyoruz.
    kip = store.ayar("izin_kipi", "bypassPermissions")
    if kip and kip != "manual":
        argv += ["--permission-mode", kip]
    return argv


def limit_durumu() -> dict:
    """Günlük kullanım sınırına ne kadar kaldığını döndür.

    Buradaki tutarlar Claude aboneliğinde faturaya dönüşmez; CLI'ın bildirdiği
    liste fiyatı karşılığıdır (``costBasis: list``). Yine de kaçak bir döngünün
    abonelik kotasını tüketmesini engellemek için sınır uygularız.
    """
    try:
        limit = float(store.ayar("gunluk_limit", "25.00") or 0)
    except ValueError:
        limit = 0.0
    harcanan = store.maliyet_ozeti()["son_24s"] or 0.0
    return {
        "limit": limit,
        "harcanan": harcanan,
        "kalan": max(0.0, limit - harcanan),
        "asildi": limit > 0 and harcanan >= limit,
    }


def _json_coz(cikti: str | None) -> dict | None:
    """stdout içindeki JSON nesnesini bul.

    ``claude --output-format json`` bazen JSON'dan önce uyarı/ilerleme satırları
    yazıyor; düz ``json.loads`` bu durumda patlıyor ve maliyet ile oturum
    kimliği kayboluyor. Önce tamamını, sonra satır satır, en son da ilk ``{``
    ile son ``}`` arasını deniyoruz.
    """
    if not cikti:
        return None
    metin = cikti.strip()
    try:
        d = json.loads(metin)
        return d if isinstance(d, dict) else None
    except json.JSONDecodeError:
        pass
    for satir in reversed(metin.splitlines()):
        satir = satir.strip()
        if satir.startswith("{") and satir.endswith("}"):
            try:
                d = json.loads(satir)
                if isinstance(d, dict):
                    return d
            except json.JSONDecodeError:
                continue
    bas, son = metin.find("{"), metin.rfind("}")
    if bas != -1 and son > bas:
        try:
            d = json.loads(metin[bas:son + 1])
            return d if isinstance(d, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _calistir(eid: int, yol: str, prompt: str, model: str,
              session_id: str | None, devam: bool, proje_id: int | None,
              checkpoint: str | None, zaman_asimi: int) -> None:
    t0 = time.time()
    argv = _komut_kur(model, session_id, devam)
    try:
        p = subprocess.Popen(
            argv, cwd=yol, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            env=abonelik_ortami(),
        )
        with _kilit:
            _calisanlar[eid] = p
        try:
            out, err = p.communicate(input=prompt, timeout=zaman_asimi)
        except subprocess.TimeoutExpired:
            _agaci_oldur(p)
            out, err = p.communicate()
            with _kilit:
                iptal_mi = eid in _iptal_edilenler
                _iptal_edilenler.discard(eid)
            if not iptal_mi:
                store.eylem_bitir(eid, "hata", cikti=out or "",
                                  hata=f"{zaman_asimi} sn zaman aşımı",
                                  sure_ms=int((time.time() - t0) * 1000),
                                  checkpoint=checkpoint)
            return
    except OSError as e:
        store.eylem_bitir(eid, "hata", hata=f"claude çalıştırılamadı: {e}",
                          sure_ms=int((time.time() - t0) * 1000),
                          checkpoint=checkpoint)
        return
    finally:
        with _kilit:
            _calisanlar.pop(eid, None)

    with _kilit:
        if eid in _iptal_edilenler:
            # iptal() zaten "iptal" olarak kapattı; üstüne yazmayalım.
            _iptal_edilenler.discard(eid)
            return

    sure_ms = int((time.time() - t0) * 1000)

    metin, maliyet, yeni_sid = out or "", None, None
    d = _json_coz(out)
    if d is not None:
        metin = d.get("result") or ""
        maliyet = d.get("total_cost_usd")
        yeni_sid = d.get("session_id")
        alt = str(d.get("subtype") or "")
        if alt == "error_max_turns":
            # İş yarıda kesildi ama yapılanlar duruyor; ayrı bir durum olarak
            # işaretle ki otomatik kip bunu "hata" sayıp kapanmasın.
            store.eylem_bitir(eid, "kesildi", cikti=metin,
                              hata="tur sınırına takıldı, iş yarım kaldı",
                              maliyet=maliyet, sure_ms=sure_ms,
                              session_id=yeni_sid, checkpoint=checkpoint)
            if yeni_sid and proje_id:
                store.proje_session_yaz(proje_id, yeni_sid)
            return
        if d.get("is_error") or alt.startswith("error"):
            store.eylem_bitir(eid, "hata", cikti=metin,
                              hata=err or f"claude hata döndürdü ({alt or 'bilinmiyor'})",
                              maliyet=maliyet, sure_ms=sure_ms,
                              session_id=yeni_sid, checkpoint=checkpoint)
            return
    elif p.returncode != 0:
        store.eylem_bitir(eid, "hata", cikti=out or "", hata=err or "bilinmeyen hata",
                          sure_ms=sure_ms, checkpoint=checkpoint)
        return

    if yeni_sid and proje_id:
        store.proje_session_yaz(proje_id, yeni_sid)

    store.eylem_bitir(eid, "tamam", cikti=metin, maliyet=maliyet,
                      sure_ms=sure_ms, session_id=yeni_sid,
                      checkpoint=checkpoint)


def gonder(proje_id: int, prompt: str, model: str | None = None,
           devam: bool = True, zaman_asimi: int = 900) -> dict:
    """Komutu arka planda çalıştır, eylem kimliğini hemen döndür."""
    p = store.proje(proje_id)
    if not p:
        return {"hata": "proje bulunamadı"}
    if not p["var_mi"] or not Path(p["yol"]).is_dir():
        return {"hata": f"proje klasörü diskte yok: {p['yol']}"}

    ld = limit_durumu()
    if ld["asildi"]:
        return {"hata": (
            f"Günlük kullanım sınırına ulaşıldı "
            f"({ld['harcanan']:.2f} / {ld['limit']:.2f} birim). "
            f"Bu bir fatura değil, abonelik kotanı korumak için koyduğun sınır. "
            f"Ayarlardan yükseltebilir ya da yarın devam edebilirsin."
        )}

    model = model or store.ayar("komut_modeli", "sonnet")
    cp = None
    if store.ayar("otomatik_checkpoint", "1") == "1":
        cp = kontrol_noktasi(p["yol"])

    eid = store.eylem_basla(proje_id, p["yol"], prompt, model)
    t = threading.Thread(
        target=_calistir,
        args=(eid, p["yol"], prompt, model, p["son_session_id"], devam,
              proje_id, cp, zaman_asimi),
        daemon=True,
    )
    t.start()
    return {"eylem_id": eid, "proje": p["ad"], "model": model,
            "checkpoint": cp}


def iptal(eid: int) -> bool:
    with _kilit:
        p = _calisanlar.get(eid)
        if not p:
            return False
        _iptal_edilenler.add(eid)
    _agaci_oldur(p)
    store.eylem_bitir(eid, "iptal", hata="kullanıcı iptal etti")
    return True


def durum(eid: int) -> dict | None:
    r = store._conn().execute(
        "SELECT e.*, p.ad AS proje_ad FROM eylemler e "
        "LEFT JOIN projeler p ON p.id=e.proje_id WHERE e.id=?", (eid,)
    ).fetchone()
    return dict(r) if r else None
