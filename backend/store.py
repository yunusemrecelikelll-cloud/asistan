"""SQLite deposu — projeler, konuşma geçmişi, denetim günlüğü, notlar."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import olay

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "asistan.db"

_local = threading.local()


def _conn() -> sqlite3.Connection:
    """Thread başına tek bağlantı — FastAPI çalışan iş parçacıkları için."""
    c = getattr(_local, "conn", None)
    if c is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(DB_PATH, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn = c
    return c


SCHEMA = """
CREATE TABLE IF NOT EXISTS projeler (
    id            INTEGER PRIMARY KEY,
    yol           TEXT UNIQUE NOT NULL,      -- diskteki gerçek yol
    ad            TEXT NOT NULL,             -- görünen ad
    claude_dizin  TEXT,                      -- ~/.claude/projects altındaki klasör
    var_mi        INTEGER NOT NULL DEFAULT 1,-- disk üzerinde hâlâ duruyor mu
    son_oturum    REAL,                      -- unix zaman
    oturum_sayisi INTEGER NOT NULL DEFAULT 0,
    son_session_id TEXT,                     -- claude --resume için
    etiket        TEXT,                      -- kullanıcı etiketi
    not_metni     TEXT,                      -- kullanıcının projeye dair notu
    ozet          TEXT,                      -- projenin ne olduğuna dair brifing
    ozet_zaman    REAL,                      -- brifing ne zaman üretildi
    otomatik      INTEGER NOT NULL DEFAULT 0,-- otomatik devam açık mı
    oto_aralik    INTEGER NOT NULL DEFAULT 900,  -- saniye
    oto_son       REAL,                      -- son otomatik tur
    oto_sayac     INTEGER NOT NULL DEFAULT 0,-- arka arkaya kaç tur döndü
    oto_azami     INTEGER NOT NULL DEFAULT 8,-- üst üste en fazla kaç tur
    tur           TEXT NOT NULL DEFAULT 'kod',
                  -- kod | baski (3D) | yayin (App Store/reklam) | kisisel | diger
    harici        INTEGER NOT NULL DEFAULT 0,-- 1 = diskte klasörü yok, elle eklendi
    durum         TEXT NOT NULL DEFAULT 'aktif', -- aktif | beklemede | bitti | arsiv
    hedef_tarih   TEXT,                      -- YYYY-MM-DD
    oncelik       INTEGER NOT NULL DEFAULT 2,-- 1 kritik, 2 normal, 3 düşük
    ayar_json     TEXT,                      -- türe özel ayarlar (yazıcı, mağaza…)
    guncellendi   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS mesajlar (
    id        INTEGER PRIMARY KEY,
    rol       TEXT NOT NULL,                 -- kullanici | asistan | sistem
    metin     TEXT NOT NULL,
    proje_id  INTEGER REFERENCES projeler(id) ON DELETE SET NULL,
    kaynak    TEXT,                          -- ollama | claude | yerel
    ses_mi    INTEGER NOT NULL DEFAULT 0,
    zaman     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS eylemler (
    id         INTEGER PRIMARY KEY,
    proje_id   INTEGER REFERENCES projeler(id) ON DELETE SET NULL,
    proje_yol  TEXT,
    komut      TEXT NOT NULL,
    model      TEXT,
    durum      TEXT NOT NULL,                -- calisiyor | tamam | hata | iptal
    cikti      TEXT,
    hata       TEXT,
    maliyet    REAL,
    sure_ms    INTEGER,
    session_id TEXT,
    checkpoint TEXT,                         -- git stash/commit referansı
    baslangic  REAL NOT NULL,
    bitis      REAL
);

CREATE TABLE IF NOT EXISTS taslaklar (
    id        INTEGER PRIMARY KEY,
    proje_id  INTEGER REFERENCES projeler(id) ON DELETE CASCADE,
    ham       TEXT NOT NULL,                 -- kullanıcının yazdığı
    detayli   TEXT NOT NULL,                 -- detaylandırılmış hâli
    durum     TEXT NOT NULL DEFAULT 'bekliyor', -- bekliyor | gonderildi | iptal
    eylem_id  INTEGER,
    zaman     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ayarlar (
    anahtar TEXT PRIMARY KEY,
    deger   TEXT NOT NULL
);

-- ── mentörlük ──────────────────────────────────────────────────────────────
-- Plan = bir haftanın ya da ayın çerçevesi. Görevler bir plana bağlanır.

CREATE TABLE IF NOT EXISTS planlar (
    id          INTEGER PRIMARY KEY,
    tur         TEXT NOT NULL,             -- haftalik | aylik
    baslangic   TEXT NOT NULL,             -- YYYY-MM-DD (dahil)
    bitis       TEXT NOT NULL,             -- YYYY-MM-DD (dahil)
    metin       TEXT,                      -- mentörün gerekçesi / çerçevesi
    durum       TEXT NOT NULL DEFAULT 'aktif',  -- aktif | kapandi
    olusturuldu REAL NOT NULL,
    UNIQUE(tur, baslangic)
);

-- Görev = takvimde yeri olan tek bir iş. Zamansız görev yok; mentörün
-- "gevşememesi" buna dayanıyor.
CREATE TABLE IF NOT EXISTS gorevler (
    id          INTEGER PRIMARY KEY,
    proje_id    INTEGER REFERENCES projeler(id) ON DELETE CASCADE,
    plan_id     INTEGER REFERENCES planlar(id) ON DELETE SET NULL,
    baslik      TEXT NOT NULL,
    ayrinti     TEXT,
    tarih       TEXT NOT NULL,             -- YYYY-MM-DD
    saat        TEXT NOT NULL,             -- HH:MM (24s)
    sure_dk     INTEGER NOT NULL DEFAULT 60,
    durum       TEXT NOT NULL DEFAULT 'bekliyor',
                -- bekliyor | calisiyor | tamam | kacirildi | ertelendi | iptal
    oncelik     INTEGER NOT NULL DEFAULT 2,-- 1 kritik, 2 normal, 3 esnek
    zorunlu     INTEGER NOT NULL DEFAULT 1,-- 0 ise kaçırmak puan düşürmez
    telafi_eden INTEGER REFERENCES gorevler(id) ON DELETE SET NULL,
                                           -- bu görev hangi kaçırılanı telafi ediyor
    erteleme    INTEGER NOT NULL DEFAULT 0,-- kaç kez ertelendi
    gerekce     TEXT,                      -- erteleme/kaçırma gerekçesi
    baslatildi  REAL,
    tamamlandi  REAL,
    kaynak      TEXT NOT NULL DEFAULT 'ai',-- ai | kullanici
    gercek_dk   INTEGER,                    -- odak oturumunda gecen sure
    olusturuldu REAL NOT NULL
);

-- Yaşam kaydı: uyku, harcama, öğün, spor, ruh hâli, su.
CREATE TABLE IF NOT EXISTS yasam (
    id     INTEGER PRIMARY KEY,
    tur    TEXT NOT NULL,                  -- uyku | harcama | ogun | spor | ruh | su
    tarih  TEXT NOT NULL,                  -- YYYY-MM-DD
    deger  REAL,                           -- saat / TL / porsiyon / 1-10
    birim  TEXT,
    detay  TEXT,
    kategori TEXT,                         -- harcamada: yeme, market, ulasim…
    zaman  REAL NOT NULL
);

-- Mentörün ürettiği dürtmeler. Telefona da buradan gidecek.
CREATE TABLE IF NOT EXISTS bildirimler (
    id        INTEGER PRIMARY KEY,
    baslik    TEXT NOT NULL,
    metin     TEXT NOT NULL,
    tur       TEXT NOT NULL DEFAULT 'bilgi',
              -- gorev | uyari | telafi | kutlama | bilgi
    gorev_id  INTEGER REFERENCES gorevler(id) ON DELETE CASCADE,
    proje_id  INTEGER REFERENCES projeler(id) ON DELETE CASCADE,
    okundu    INTEGER NOT NULL DEFAULT 0,
    iletildi  INTEGER NOT NULL DEFAULT 0,  -- telefona gönderildi mi
    zaman     REAL NOT NULL
);

-- ── atölye: yazıcılar ve baskılar ──────────────────────────────────────────
-- Yazıcı projeye değil atölyeye ait; bir proje hangisi boşsa oraya baskı verir.

CREATE TABLE IF NOT EXISTS yazicilar (
    id             INTEGER PRIMARY KEY,
    ad             TEXT UNIQUE NOT NULL,
    model          TEXT,
    ip             TEXT,                       -- yerel ağdaysa
    tur            TEXT NOT NULL DEFAULT 'elle',  -- elle | mqtt | sdcp
    notlar         TEXT,
    filament       TEXT,                       -- takılı filament (PLA, ABS…)
    filament_renk  TEXT,
    filament_gram  REAL,                       -- makarada kalan tahmini
    nozzle         TEXT DEFAULT '0.4',
    durum          TEXT NOT NULL DEFAULT 'bos',-- bos | basiliyor | bakim | kapali
    toplam_dk      INTEGER NOT NULL DEFAULT 0, -- ömür boyu çalışma süresi
    baski_sayisi   INTEGER NOT NULL DEFAULT 0,
    kamera_url     TEXT,                       -- MJPEG/RTSP akış adresi
    son_gorulme    REAL,                       -- ağda en son ne zaman görüldü
    eklendi        REAL NOT NULL
);

-- Masaüstündeki "3d Projeler" klasöründeki dosyaların takibi.
CREATE TABLE IF NOT EXISTS baski_dosyalari (
    id          INTEGER PRIMARY KEY,
    ad          TEXT NOT NULL,
    yol         TEXT UNIQUE NOT NULL,
    boyut       INTEGER,
    durum       TEXT NOT NULL DEFAULT 'bekliyor',
                                            -- bekliyor | basiliyor | bitti
    proje_id    INTEGER REFERENCES projeler(id) ON DELETE SET NULL,
    baski_id    INTEGER,
    eklendi     REAL NOT NULL,
    guncellendi REAL NOT NULL
);

-- ── yaşam koçluğu ──────────────────────────────────────────────────────────
-- Alışkanlık, proje görevinden farklı: bitmez, tekrar eder. Ölçüsü "yapıldı
-- mı" değil, "zincir sürüyor mu".

CREATE TABLE IF NOT EXISTS aliskanliklar (
    id          INTEGER PRIMARY KEY,
    ad          TEXT UNIQUE NOT NULL,
    aciklama    TEXT,
    tur         TEXT NOT NULL DEFAULT 'gunluk',  -- gunluk | haftalik
    hedef       INTEGER NOT NULL DEFAULT 7,      -- haftada kaç kez
    saat        TEXT,                            -- hatırlatma saati (HH:MM)
    aktif       INTEGER NOT NULL DEFAULT 1,
    olusturuldu REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS aliskanlik_kayit (
    id            INTEGER PRIMARY KEY,
    aliskanlik_id INTEGER REFERENCES aliskanliklar(id) ON DELETE CASCADE,
    tarih         TEXT NOT NULL,                 -- YYYY-MM-DD
    yapildi       INTEGER NOT NULL DEFAULT 1,
    not_metni     TEXT,
    zaman         REAL NOT NULL,
    UNIQUE(aliskanlik_id, tarih)
);

-- Sabah ve akşam ritüelleri: günü açan ve kapatan kısa konuşmalar.
CREATE TABLE IF NOT EXISTS ritueller (
    id          INTEGER PRIMARY KEY,
    tarih       TEXT NOT NULL,                   -- YYYY-MM-DD
    tur         TEXT NOT NULL,                   -- sabah | aksam
    veri        TEXT,                            -- JSON: sorular ve cevaplar
    tamamlandi  REAL,
    olusturuldu REAL NOT NULL,
    UNIQUE(tarih, tur)
);

CREATE INDEX IF NOT EXISTS idx_aliskanlik_kayit
    ON aliskanlik_kayit(aliskanlik_id, tarih DESC);

-- Ekran süresi: hangi uygulamada ne kadar vakit geçti.
CREATE TABLE IF NOT EXISTS ekran_sure (
    id        INTEGER PRIMARY KEY,
    tarih     TEXT NOT NULL,                  -- YYYY-MM-DD
    uygulama  TEXT NOT NULL,                  -- exe adı
    baslik    TEXT,                           -- son görülen pencere başlığı
    saniye    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(tarih, uygulama)
);

-- Dış takvimden çekilen randevular. Mentör bu saatlere görev koymaz.
CREATE TABLE IF NOT EXISTS randevular (
    id        INTEGER PRIMARY KEY,
    uid       TEXT UNIQUE NOT NULL,           -- ICS UID
    baslik    TEXT NOT NULL,
    tarih     TEXT NOT NULL,                  -- YYYY-MM-DD
    saat      TEXT,                           -- HH:MM (tüm gün ise NULL)
    sure_dk   INTEGER,
    yer       TEXT,
    kaynak    TEXT,                           -- takvim adı
    guncellendi REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_randevu_tarih ON randevular(tarih, saat);
CREATE INDEX IF NOT EXISTS idx_ekran_tarih ON ekran_sure(tarih);

-- İşlem günlüğü. Geri dönüş noktası değil — ne olduğunu okumak için.
CREATE TABLE IF NOT EXISTS gunluk (
    id       INTEGER PRIMARY KEY,
    zaman    REAL NOT NULL,
    seviye   TEXT NOT NULL,                 -- bilgi | uyari | hata
    kaynak   TEXT NOT NULL,                 -- modül adı
    olay     TEXT NOT NULL,                 -- kısa etiket (plan_uretildi…)
    mesaj    TEXT,
    veri     TEXT,                          -- JSON ek bilgi
    proje_id INTEGER,
    gorev_id INTEGER,
    sure_ms  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_gunluk_zaman ON gunluk(zaman DESC);
CREATE INDEX IF NOT EXISTS idx_gunluk_seviye ON gunluk(seviye, zaman DESC);
CREATE INDEX IF NOT EXISTS idx_dosya_durum ON baski_dosyalari(durum);

CREATE TABLE IF NOT EXISTS baskilar (
    id          INTEGER PRIMARY KEY,
    yazici_id   INTEGER REFERENCES yazicilar(id) ON DELETE CASCADE,
    proje_id    INTEGER REFERENCES projeler(id) ON DELETE SET NULL,
    ad          TEXT NOT NULL,
    baslangic   REAL NOT NULL,
    tahmini_dk  INTEGER NOT NULL,
    bitis       REAL,                      -- gerçek bitiş
    durum       TEXT NOT NULL DEFAULT 'basiliyor',
                                           -- basiliyor | bitti | iptal | hata
    bildirildi  INTEGER NOT NULL DEFAULT 0,
    gorev_id    INTEGER,
    gram        REAL,                      -- harcanan filament
    maliyet     REAL,                      -- hesaplanan TL maliyet
    satis_fiyati REAL,                     -- satildiysa
    adet        INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_baski_durum ON baskilar(durum, baslangic DESC);
CREATE INDEX IF NOT EXISTS idx_mesaj_zaman ON mesajlar(zaman DESC);
CREATE INDEX IF NOT EXISTS idx_eylem_baslangic ON eylemler(baslangic DESC);
CREATE INDEX IF NOT EXISTS idx_gorev_tarih ON gorevler(tarih, saat);
CREATE INDEX IF NOT EXISTS idx_gorev_durum ON gorevler(durum, tarih);
CREATE INDEX IF NOT EXISTS idx_yasam_tarih ON yasam(tarih DESC, tur);
CREATE INDEX IF NOT EXISTS idx_bildirim_zaman ON bildirimler(zaman DESC);
"""

VARSAYILAN_AYARLAR = {
    "sohbet_modeli": "qwen3.5:4b-tr",        # yerel Ollama
    "komut_modeli": "sonnet",                # claude CLI ile proje komutları
    "akil_modeli": "opus",                   # ağır akıl yürütme
    "ses": "tr-TR-AhmetNeural",
    "stt_modeli": "medium",
    "sesli_yanit": "1",
    "otomatik_checkpoint": "1",
    "gunluk_limit": "25.00",          # USD; asilinca komut gonderilmez
    "komut_azami_tur": "0",          # claude --max-turns (0 = sinirsiz)
    "taslak_modeli": "qwen3.5:9b-tr",# promptu detaylandiran yerel model
    "otomatik_onay": "0",            # 1 = taslagi gostermeden gonder
    "izin_kipi": "bypassPermissions", # bypassPermissions | acceptEdits | manual
    "dinleme_adresi": "127.0.0.1",   # 0.0.0.0 = Tailscale/LAN uzerinden de erisim

    # ── mentörlük ──────────────────────────────────────────────────────────
    "mentor_acik": "1",
    "gun_baslangic": "09:00",        # planlanan ilk is bloğu
    "gun_bitis": "22:00",            # bu saatten sonra gorev yerlestirilmez
    "odak_blok_dk": "90",            # tipik calisma blogu
    "ara_dk": "20",                  # bloklar arasi bosluk
    "gunluk_azami_blok": "5",        # gunde en fazla kac odak blogu
    "mentor_sertlik": "yuksek",      # yuksek | orta | esnek
    "gecikme_toleransi_dk": "20",    # bu sure sonra gorev "kacirildi" sayilir
    "mentor_modeli": "sonnet",       # plan uretiminde kullanilacak claude modeli
    "plan_gun": "1",                 # haftalik plan hangi gun uretilsin (1=Pzt)
    "uyku_hedef": "7.5",             # saat
    "gunluk_harcama_hedef": "0",     # TL; 0 = hedef yok

    # ── agir isler ────────────────────────────────────────────────────
    "agir_is_yerel": "1",            # 1 = once yerel model dener
    "agir_is_modeli": "qwen3.5:9b-tr",
    "gunluk_saklama_gun": "60",      # veritabanindaki log omru
    "klasor_takip": "1",             # 3d Projeler klasorunu izle

    # ── yasam koclugu ─────────────────────────────────────────────────
    "sabah_rituel": "1",
    "aksam_rituel": "1",
    "koc_tonu": "sert",              # sert | dengeli | yumusak
    "haftalik_seans_gun": "7",       # 7 = Pazar
    "butce_aylik": "0",              # TL; 0 = butce yok
    "butce_json": "{}",              # kategori bazli aylik butce

    # ── atolye maliyeti ──────────────────────────────────────────────
    "filament_kg_fiyat": "600",      # TL/kg
    "elektrik_kwh_fiyat": "3.5",     # TL/kWh
    "yazici_watt": "150",            # ortalama cekis
    "iscilik_saat_fiyat": "0",       # 0 = hesaba katma

    # ── yedekleme / takvim / ekran ───────────────────────────────────
    "yedek_acik": "1",
    "yedek_saklama": "14",           # kac yedek tutulsun
    "takvim_ics": "",                # gizli ICS adresi (bos = kapali)
    "ekran_takip": "0",              # 1 = aktif pencereyi olc

    # ── dogal konusma ────────────────────────────────────────────────
    "dogal_konusma": "1",            # metni konusma diline cevir
    "dogal_modeli": "qwen3.5:4b-tr", # dogallastirmayi yapan yerel model
    "konusma_uslubu": "canli",       # sakin | canli | sert
    "akilli_niyet": "1",             # niyeti model cozsun
    "niyet_modeli": "qwen3.5:9b-tr",
    "ses_motoru": "klon",            # klon | edge (edge yalnizca yedek)
    "ses_adlari": '{"ses1": "Kalın", "ses2": "Orta", "ses3": "İnce", "referans": "Hareketli"}',
    "klon_referans": "ses1",         # klon motorunda kullanilacak ses
    # Sohbeti kim yanıtlıyor. Ölçüm: yerel 4B ilk cümleyi 16,8 sn'de ve
    # yanlış veriyor; claude sonnet 6,6 sn'de ve doğru. Yerel yalnızca
    # yedek — claude'a ulaşılamazsa ya da günlük sınır dolarsa.
    "sohbet_saglayici": "claude",       # claude | yerel
    "sohbet_claude_modeli": "sonnet",   # sonnet | opus | haiku
    "hazir_cevap": "1",   # selam/nasilsin gibi cumleler hazir sesle
    "ara_ses": "1",                  # konusma bitince kisa "seni duydum" sesi
}


_EK_SUTUNLAR = [
    ("projeler", "ozet", "TEXT"),
    ("projeler", "ozet_zaman", "REAL"),
    ("projeler", "otomatik", "INTEGER NOT NULL DEFAULT 0"),
    ("projeler", "oto_aralik", "INTEGER NOT NULL DEFAULT 900"),
    ("projeler", "oto_son", "REAL"),
    ("projeler", "oto_sayac", "INTEGER NOT NULL DEFAULT 0"),
    ("projeler", "oto_azami", "INTEGER NOT NULL DEFAULT 8"),
    ("projeler", "tur", "TEXT NOT NULL DEFAULT 'kod'"),
    ("projeler", "harici", "INTEGER NOT NULL DEFAULT 0"),
    ("projeler", "durum", "TEXT NOT NULL DEFAULT 'aktif'"),
    ("projeler", "hedef_tarih", "TEXT"),
    ("projeler", "oncelik", "INTEGER NOT NULL DEFAULT 2"),
    ("projeler", "ayar_json", "TEXT"),
    ("yazicilar", "filament", "TEXT"),
    ("yazicilar", "filament_renk", "TEXT"),
    ("yazicilar", "filament_gram", "REAL"),
    ("yazicilar", "nozzle", "TEXT DEFAULT '0.4'"),
    ("yazicilar", "durum", "TEXT NOT NULL DEFAULT 'bos'"),
    ("yazicilar", "toplam_dk", "INTEGER NOT NULL DEFAULT 0"),
    ("yazicilar", "baski_sayisi", "INTEGER NOT NULL DEFAULT 0"),
    ("yazicilar", "kamera_url", "TEXT"),
    ("yazicilar", "son_gorulme", "REAL"),
    ("gorevler", "gercek_dk", "INTEGER"),
    ("yasam", "kategori", "TEXT"),
    ("baskilar", "gram", "REAL"),
    ("baskilar", "maliyet", "REAL"),
    ("baskilar", "satis_fiyati", "REAL"),
    ("baskilar", "adet", "INTEGER NOT NULL DEFAULT 1"),
]


def _migrasyon(c: sqlite3.Connection) -> None:
    """Eski veritabanlarına eksik sütunları ekle (veri kaybı olmadan)."""
    for tablo, sutun, tip in _EK_SUTUNLAR:
        mevcut = {r["name"] for r in c.execute(f"PRAGMA table_info({tablo})")}
        if sutun not in mevcut:
            c.execute(f"ALTER TABLE {tablo} ADD COLUMN {sutun} {tip}")
    c.commit()


def kur() -> None:
    c = _conn()
    c.executescript(SCHEMA)
    _migrasyon(c)
    for k, v in VARSAYILAN_AYARLAR.items():
        c.execute("INSERT OR IGNORE INTO ayarlar(anahtar, deger) VALUES(?,?)", (k, v))
    c.commit()


# ── ayarlar ────────────────────────────────────────────────────────────────


def ayar(anahtar: str, varsayilan: str | None = None) -> str | None:
    r = _conn().execute(
        "SELECT deger FROM ayarlar WHERE anahtar=?", (anahtar,)
    ).fetchone()
    return r["deger"] if r else varsayilan


def ayar_yaz(anahtar: str, deger: str) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO ayarlar(anahtar,deger) VALUES(?,?) "
        "ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
        (anahtar, str(deger)),
    )
    c.commit()


def tum_ayarlar() -> dict[str, str]:
    return {r["anahtar"]: r["deger"] for r in _conn().execute("SELECT * FROM ayarlar")}


# ── projeler ───────────────────────────────────────────────────────────────


# Projeye bağlı tablolar. gorevler/taslaklar/bildirimler ON DELETE CASCADE
# olduğu için bir proje satırını silmeden ÖNCE çocukları taşınmalı; yoksa
# kullanıcının görevleri de silinir.
_PROJE_COCUKLARI = ("mesajlar", "eylemler", "taslaklar", "gorevler",
                    "bildirimler", "baskilar", "baski_dosyalari")

# Kullanıcının doldurduğu, keşiften gelmeyen alanlar.
_KULLANICI_ALANLARI = ("etiket", "not_metni", "ozet", "ozet_zaman", "tur",
                       "durum", "hedef_tarih", "oncelik", "ayar_json",
                       "otomatik", "oto_aralik", "oto_azami")


def proje_birlestir(kaynak_id: int, hedef_id: int) -> None:
    """``kaynak`` projesini ``hedef``e kat ve kaynağı sil.

    Aynı klasörün iki kaydı oluştuğunda (Windows'ta yol harf büyüklüğüne
    duyarsız ama sütun birincil anahtar) çağrılıyor. Çocuk satırlar önce
    taşınıyor: silme CASCADE olduğu için tersi görev kaybı demek.
    """
    if kaynak_id == hedef_id:
        return
    c = _conn()
    for t in _PROJE_COCUKLARI:
        try:
            c.execute(f"UPDATE {t} SET proje_id=? WHERE proje_id=?",
                      (hedef_id, kaynak_id))
        except sqlite3.OperationalError:
            pass            # tablo yoksa (eski veritabanı) atla
    # Hedefte boş olan kullanıcı alanlarını kaynaktan doldur.
    k = c.execute("SELECT * FROM projeler WHERE id=?", (kaynak_id,)).fetchone()
    h = c.execute("SELECT * FROM projeler WHERE id=?", (hedef_id,)).fetchone()
    if k and h:
        for alan in _KULLANICI_ALANLARI:
            if alan in k.keys() and not h[alan] and k[alan]:
                c.execute(f"UPDATE projeler SET {alan}=? WHERE id=?",
                          (k[alan], hedef_id))
        if not h["son_session_id"] and k["son_session_id"]:
            c.execute("UPDATE projeler SET son_session_id=? WHERE id=?",
                      (k["son_session_id"], hedef_id))
        if (k["oturum_sayisi"] or 0) > (h["oturum_sayisi"] or 0):
            c.execute("UPDATE projeler SET oturum_sayisi=? WHERE id=?",
                      (k["oturum_sayisi"], hedef_id))
    c.execute("DELETE FROM projeler WHERE id=?", (kaynak_id,))
    c.commit()


def proje_yol_yaz(pid: int, yeni_yol: str) -> None:
    c = _conn()
    c.execute("UPDATE projeler SET yol=? WHERE id=?", (yeni_yol, pid))
    c.commit()


def sohbet_maliyeti_yaz(model: str, maliyet: float) -> None:
    """Sohbetin abonelik kotasından tükettiğini eylem günlüğüne yaz.

    Günlük kullanım freni ``eylemler`` tablosuna bakıyor. Sohbet Claude'a
    taşındığında harcama oradan görünmezse fren çalışmaz ve kota sessizce
    tükenir.
    """
    c = _conn()
    simdi = time.time()
    c.execute(
        "INSERT INTO eylemler (proje_id, proje_yol, komut, model, durum, "
        "baslangic, bitis, maliyet) VALUES (NULL, '', ?, ?, 'tamam', ?, ?, ?)",
        ("[sohbet]", model, simdi, simdi, maliyet),
    )
    c.commit()


def proje_kaydet(p: dict[str, Any]) -> int:
    """Yolu anahtar alarak ekle/güncelle. Kullanıcı notu ve etiketi korunur."""
    c = _conn()
    c.execute(
        """
        INSERT INTO projeler (yol, ad, claude_dizin, var_mi, son_oturum,
                              oturum_sayisi, son_session_id, guncellendi)
        VALUES (:yol, :ad, :claude_dizin, :var_mi, :son_oturum,
                :oturum_sayisi, :son_session_id, :guncellendi)
        ON CONFLICT(yol) DO UPDATE SET
            ad             = excluded.ad,
            claude_dizin   = excluded.claude_dizin,
            var_mi         = excluded.var_mi,
            son_oturum     = excluded.son_oturum,
            oturum_sayisi  = excluded.oturum_sayisi,
            son_session_id = COALESCE(excluded.son_session_id, projeler.son_session_id),
            guncellendi    = excluded.guncellendi
        """,
        {**p, "guncellendi": time.time()},
    )
    c.commit()
    r = c.execute("SELECT id FROM projeler WHERE yol=?", (p["yol"],)).fetchone()
    return r["id"]


def projeler(sadece_var: bool = False) -> list[dict]:
    q = "SELECT * FROM projeler"
    if sadece_var:
        q += " WHERE var_mi=1"
    q += " ORDER BY son_oturum DESC NULLS LAST, ad"
    return [dict(r) for r in _conn().execute(q)]


def proje(pid: int) -> dict | None:
    r = _conn().execute("SELECT * FROM projeler WHERE id=?", (pid,)).fetchone()
    return dict(r) if r else None


def proje_yol_ile(yol: str) -> dict | None:
    r = _conn().execute("SELECT * FROM projeler WHERE yol=?", (yol,)).fetchone()
    return dict(r) if r else None


def proje_sil_yol(yol: str) -> None:
    c = _conn()
    c.execute("DELETE FROM projeler WHERE yol=?", (yol,))
    c.commit()


def proje_varlik_guncelle(mevcut_yollar: set[str]) -> None:
    """Taramada görülmeyen kayıtları diske bakarak güncelle.

    Kullanıcının notu olan kayıtları silmeyiz; yalnızca ``var_mi=0`` yaparız ki
    "şu proje nereye gitti" sorusu yanıtlanabilsin.
    """
    c = _conn()
    for r in c.execute("SELECT id, yol, not_metni FROM projeler").fetchall():
        if r["yol"] in mevcut_yollar:
            continue
        from pathlib import Path as _P

        if _P(r["yol"]).is_dir():
            continue
        if r["not_metni"]:
            c.execute("UPDATE projeler SET var_mi=0 WHERE id=?", (r["id"],))
        else:
            c.execute("DELETE FROM projeler WHERE id=?", (r["id"],))
    c.commit()


def proje_not_yaz(pid: int, not_metni: str | None, etiket: str | None) -> None:
    c = _conn()
    c.execute(
        "UPDATE projeler SET not_metni=?, etiket=?, guncellendi=? WHERE id=?",
        (not_metni, etiket, time.time(), pid),
    )
    c.commit()


def proje_session_yaz(pid: int, session_id: str) -> None:
    c = _conn()
    c.execute("UPDATE projeler SET son_session_id=? WHERE id=?", (session_id, pid))
    c.commit()


# ── mesajlar ───────────────────────────────────────────────────────────────


def mesaj_ekle(
    rol: str,
    metin: str,
    proje_id: int | None = None,
    kaynak: str | None = None,
    ses_mi: bool = False,
) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO mesajlar(rol, metin, proje_id, kaynak, ses_mi, zaman) "
        "VALUES(?,?,?,?,?,?)",
        (rol, metin, proje_id, kaynak, 1 if ses_mi else 0, time.time()),
    )
    c.commit()
    olay.yayinla("mesaj", mesaj_id=cur.lastrowid, rol=rol, proje_id=proje_id)
    return cur.lastrowid


def mesajlar(limit: int = 60) -> list[dict]:
    rows = _conn().execute(
        "SELECT * FROM mesajlar ORDER BY zaman DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def sohbet_temizle() -> None:
    c = _conn()
    c.execute("DELETE FROM mesajlar")
    c.commit()
    olay.yayinla("sohbet_temizlendi")


# ── eylem günlüğü ──────────────────────────────────────────────────────────


def eylem_basla(proje_id: int | None, proje_yol: str | None, komut: str,
                model: str | None) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO eylemler(proje_id, proje_yol, komut, model, durum, baslangic) "
        "VALUES(?,?,?,?,'calisiyor',?)",
        (proje_id, proje_yol, komut, model, time.time()),
    )
    c.commit()
    olay.yayinla("eylem", eylem_id=cur.lastrowid, durum="calisiyor",
                 proje_id=proje_id)
    return cur.lastrowid


def eylem_bitir(eid: int, durum: str, cikti: str = "", hata: str = "",
                maliyet: float | None = None, sure_ms: int | None = None,
                session_id: str | None = None, checkpoint: str | None = None) -> None:
    c = _conn()
    c.execute(
        "UPDATE eylemler SET durum=?, cikti=?, hata=?, maliyet=?, sure_ms=?, "
        "session_id=?, checkpoint=?, bitis=? WHERE id=?",
        (durum, cikti, hata, maliyet, sure_ms, session_id, checkpoint,
         time.time(), eid),
    )
    c.commit()
    olay.yayinla("eylem", eylem_id=eid, durum=durum)


def eylemler(limit: int = 50) -> list[dict]:
    return [
        dict(r)
        for r in _conn().execute(
            "SELECT e.*, p.ad AS proje_ad FROM eylemler e "
            "LEFT JOIN projeler p ON p.id = e.proje_id "
            "ORDER BY e.baslangic DESC LIMIT ?",
            (limit,),
        )
    ]


def maliyet_ozeti() -> dict:
    r = _conn().execute(
        "SELECT COUNT(*) n, COALESCE(SUM(maliyet),0) toplam FROM eylemler "
        "WHERE maliyet IS NOT NULL"
    ).fetchone()
    gun = _conn().execute(
        "SELECT COALESCE(SUM(maliyet),0) g FROM eylemler "
        "WHERE maliyet IS NOT NULL AND baslangic > ?",
        (time.time() - 86400,),
    ).fetchone()
    return {"eylem_sayisi": r["n"], "toplam": r["toplam"], "son_24s": gun["g"]}


__all__ = [name for name in dir() if not name.startswith("_")]


# ── proje brifingi ve otomatik devam ───────────────────────────────────────


def proje_ozet_yaz(pid: int, ozet: str) -> None:
    c = _conn()
    c.execute("UPDATE projeler SET ozet=?, ozet_zaman=? WHERE id=?",
              (ozet, time.time(), pid))
    c.commit()


def otomatik_ayarla(pid: int, acik: bool, aralik: int | None = None,
                    azami: int | None = None) -> None:
    c = _conn()
    alanlar = ["otomatik=?", "oto_sayac=0"]
    degerler: list[Any] = [1 if acik else 0]
    if aralik is not None:
        alanlar.append("oto_aralik=?")
        degerler.append(max(60, int(aralik)))
    if azami is not None:
        alanlar.append("oto_azami=?")
        degerler.append(max(1, int(azami)))
    degerler.append(pid)
    c.execute(f"UPDATE projeler SET {', '.join(alanlar)} WHERE id=?", degerler)
    c.commit()
    olay.yayinla("otomatik", proje_id=pid, acik=bool(acik))


def otomatik_tur_kaydet(pid: int, sayac_artir: bool = True) -> None:
    c = _conn()
    if sayac_artir:
        c.execute("UPDATE projeler SET oto_son=?, oto_sayac=oto_sayac+1 WHERE id=?",
                  (time.time(), pid))
    else:
        c.execute("UPDATE projeler SET oto_son=? WHERE id=?", (time.time(), pid))
    c.commit()


def otomatik_projeler() -> list[dict]:
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM projeler WHERE otomatik=1 AND var_mi=1")]


# ── taslaklar ──────────────────────────────────────────────────────────────


def taslak_ekle(proje_id: int, ham: str, detayli: str) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO taslaklar(proje_id, ham, detayli, zaman) VALUES(?,?,?,?)",
        (proje_id, ham, detayli, time.time()),
    )
    c.commit()
    olay.yayinla("taslak", taslak_id=cur.lastrowid, proje_id=proje_id,
                 durum="bekliyor")
    return cur.lastrowid


def taslak(tid: int) -> dict | None:
    r = _conn().execute("SELECT * FROM taslaklar WHERE id=?", (tid,)).fetchone()
    return dict(r) if r else None


def taslak_guncelle(tid: int, detayli: str) -> None:
    c = _conn()
    c.execute("UPDATE taslaklar SET detayli=? WHERE id=?", (detayli, tid))
    c.commit()


def taslak_durum(tid: int, durum: str, eylem_id: int | None = None) -> None:
    c = _conn()
    c.execute("UPDATE taslaklar SET durum=?, eylem_id=? WHERE id=?",
              (durum, eylem_id, tid))
    c.commit()
    olay.yayinla("taslak", taslak_id=tid, durum=durum)


def bekleyen_taslaklar() -> list[dict]:
    return [dict(r) for r in _conn().execute(
        "SELECT t.*, p.ad AS proje_ad FROM taslaklar t "
        "LEFT JOIN projeler p ON p.id=t.proje_id "
        "WHERE t.durum='bekliyor' ORDER BY t.zaman DESC")]


# ── planlar ────────────────────────────────────────────────────────────────


def plan_kaydet(tur: str, baslangic: str, bitis: str, metin: str) -> int:
    """Bir dönemin planını yaz. Aynı dönem tekrar planlanırsa üzerine yazar."""
    c = _conn()
    c.execute(
        "INSERT INTO planlar(tur, baslangic, bitis, metin, olusturuldu) "
        "VALUES(?,?,?,?,?) "
        "ON CONFLICT(tur, baslangic) DO UPDATE SET "
        "  bitis=excluded.bitis, metin=excluded.metin, durum='aktif', "
        "  olusturuldu=excluded.olusturuldu",
        (tur, baslangic, bitis, metin, time.time()),
    )
    c.commit()
    r = c.execute("SELECT id FROM planlar WHERE tur=? AND baslangic=?",
                  (tur, baslangic)).fetchone()
    olay.yayinla("plan", plan_id=r["id"], kategori=tur)
    return r["id"]


def plan_getir(tur: str, baslangic: str) -> dict | None:
    r = _conn().execute("SELECT * FROM planlar WHERE tur=? AND baslangic=?",
                        (tur, baslangic)).fetchone()
    return dict(r) if r else None


def planlar(limit: int = 12) -> list[dict]:
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM planlar ORDER BY baslangic DESC LIMIT ?", (limit,))]


# ── görevler ───────────────────────────────────────────────────────────────


def gorev_ekle(baslik: str, tarih: str, saat: str, sure_dk: int = 60,
               proje_id: int | None = None, plan_id: int | None = None,
               ayrinti: str | None = None, oncelik: int = 2,
               zorunlu: bool = True, kaynak: str = "ai",
               telafi_eden: int | None = None) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO gorevler(proje_id, plan_id, baslik, ayrinti, tarih, saat, "
        "  sure_dk, oncelik, zorunlu, kaynak, telafi_eden, olusturuldu) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (proje_id, plan_id, baslik, ayrinti, tarih, saat, max(5, int(sure_dk)),
         oncelik, 1 if zorunlu else 0, kaynak, telafi_eden, time.time()),
    )
    c.commit()
    olay.yayinla("gorev", gorev_id=cur.lastrowid, durum="bekliyor", tarih=tarih)
    return cur.lastrowid


def gorev(gid: int) -> dict | None:
    r = _conn().execute(
        "SELECT g.*, p.ad AS proje_ad, p.tur AS proje_tur FROM gorevler g "
        "LEFT JOIN projeler p ON p.id=g.proje_id WHERE g.id=?", (gid,)
    ).fetchone()
    return dict(r) if r else None


def gorevler(tarih: str | None = None, bitis: str | None = None,
             durum: str | None = None, proje_id: int | None = None,
             limit: int = 300) -> list[dict]:
    """Görevleri süz. ``tarih`` tek gün, ``tarih``+``bitis`` aralık demek."""
    q = ("SELECT g.*, p.ad AS proje_ad, p.tur AS proje_tur FROM gorevler g "
         "LEFT JOIN projeler p ON p.id=g.proje_id WHERE 1=1")
    d: list[Any] = []
    if tarih and bitis:
        q += " AND g.tarih BETWEEN ? AND ?"
        d += [tarih, bitis]
    elif tarih:
        q += " AND g.tarih=?"
        d.append(tarih)
    if durum:
        q += " AND g.durum=?"
        d.append(durum)
    if proje_id:
        q += " AND g.proje_id=?"
        d.append(proje_id)
    q += " ORDER BY g.tarih, g.saat LIMIT ?"
    d.append(limit)
    return [dict(r) for r in _conn().execute(q, d)]


def gorev_durum(gid: int, durum: str, gerekce: str | None = None) -> None:
    c = _conn()
    alanlar = ["durum=?"]
    d: list[Any] = [durum]
    if gerekce is not None:
        alanlar.append("gerekce=?")
        d.append(gerekce)
    if durum == "calisiyor":
        alanlar.append("baslatildi=?")
        d.append(time.time())
    elif durum == "tamam":
        alanlar.append("tamamlandi=?")
        d.append(time.time())
    d.append(gid)
    c.execute(f"UPDATE gorevler SET {', '.join(alanlar)} WHERE id=?", d)
    c.commit()
    olay.yayinla("gorev", gorev_id=gid, durum=durum)


def gorev_tasi(gid: int, tarih: str, saat: str, gerekce: str | None = None) -> None:
    """Görevi başka bir zamana al ve erteleme sayacını artır."""
    c = _conn()
    c.execute(
        "UPDATE gorevler SET tarih=?, saat=?, durum='bekliyor', "
        "erteleme=erteleme+1, gerekce=COALESCE(?, gerekce) WHERE id=?",
        (tarih, saat, gerekce, gid),
    )
    c.commit()
    olay.yayinla("gorev", gorev_id=gid, durum="ertelendi", tarih=tarih)


def gorev_sil(gid: int) -> None:
    c = _conn()
    c.execute("DELETE FROM gorevler WHERE id=?", (gid,))
    c.commit()
    olay.yayinla("gorev", gorev_id=gid, durum="silindi")


def gecmis_gorevler(simdi_tarih: str, simdi_saat: str) -> list[dict]:
    """Zamanı geçmiş ama hâlâ bekleyen/çalışan görevler."""
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM gorevler WHERE durum IN ('bekliyor','calisiyor') "
        "AND (tarih < ? OR (tarih = ? AND saat <= ?)) ORDER BY tarih, saat",
        (simdi_tarih, simdi_tarih, simdi_saat))]


def gorev_istatistik(baslangic: str, bitis: str) -> dict:
    """Bir aralıktaki uyum karnesi."""
    r = _conn().execute(
        "SELECT "
        "  COUNT(*) toplam, "
        "  SUM(durum='tamam') tamam, "
        "  SUM(durum='kacirildi') kacirildi, "
        "  SUM(erteleme > 0) ertelenen, "
        "  SUM(durum='tamam' AND zorunlu=1) zorunlu_tamam, "
        "  SUM(zorunlu=1) zorunlu_toplam "
        "FROM gorevler WHERE tarih BETWEEN ? AND ? AND durum != 'iptal'",
        (baslangic, bitis),
    ).fetchone()
    d = {k: (r[k] or 0) for k in r.keys()}
    d["uyum"] = round(100 * d["tamam"] / d["toplam"]) if d["toplam"] else None
    return d


# ── yaşam kayıtları ────────────────────────────────────────────────────────


def yasam_ekle(tur: str, tarih: str, deger: float | None,
               birim: str | None = None, detay: str | None = None) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO yasam(tur, tarih, deger, birim, detay, zaman) "
        "VALUES(?,?,?,?,?,?)",
        (tur, tarih, deger, birim, detay, time.time()),
    )
    c.commit()
    olay.yayinla("yasam", kayit_id=cur.lastrowid, kategori=tur, tarih=tarih)
    return cur.lastrowid


def yasam_kayitlari(baslangic: str, bitis: str,
                    tur: str | None = None) -> list[dict]:
    q = "SELECT * FROM yasam WHERE tarih BETWEEN ? AND ?"
    d: list[Any] = [baslangic, bitis]
    if tur:
        q += " AND tur=?"
        d.append(tur)
    q += " ORDER BY tarih DESC, zaman DESC"
    return [dict(r) for r in _conn().execute(q, d)]


def yasam_sil(kid: int) -> None:
    c = _conn()
    c.execute("DELETE FROM yasam WHERE id=?", (kid,))
    c.commit()


def yasam_ozet(baslangic: str, bitis: str) -> dict:
    """Tür başına toplam/ortalama — panelin üst şeridi için."""
    rows = _conn().execute(
        "SELECT tur, COUNT(*) n, COALESCE(SUM(deger),0) toplam, "
        "       AVG(deger) ortalama FROM yasam "
        "WHERE tarih BETWEEN ? AND ? GROUP BY tur",
        (baslangic, bitis),
    ).fetchall()
    return {r["tur"]: {"sayi": r["n"], "toplam": round(r["toplam"], 2),
                       "ortalama": round(r["ortalama"], 2) if r["ortalama"] else None}
            for r in rows}


# ── bildirimler ────────────────────────────────────────────────────────────


def bildirim_ekle(baslik: str, metin: str, tur: str = "bilgi",
                  gorev_id: int | None = None,
                  proje_id: int | None = None) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO bildirimler(baslik, metin, tur, gorev_id, proje_id, zaman) "
        "VALUES(?,?,?,?,?,?)",
        (baslik, metin, tur, gorev_id, proje_id, time.time()),
    )
    c.commit()
    olay.yayinla("bildirim", bildirim_id=cur.lastrowid, kategori=tur,
                 baslik=baslik)
    return cur.lastrowid


def bildirimler(sadece_okunmamis: bool = False, limit: int = 50) -> list[dict]:
    q = "SELECT * FROM bildirimler"
    if sadece_okunmamis:
        q += " WHERE okundu=0"
    q += " ORDER BY zaman DESC LIMIT ?"
    return [dict(r) for r in _conn().execute(q, (limit,))]


def bildirim_okundu(bid: int | None = None) -> None:
    """Tek bildirimi ya da (bid yoksa) hepsini okundu işaretle."""
    c = _conn()
    if bid is None:
        c.execute("UPDATE bildirimler SET okundu=1 WHERE okundu=0")
    else:
        c.execute("UPDATE bildirimler SET okundu=1 WHERE id=?", (bid,))
    c.commit()
    olay.yayinla("bildirim", bildirim_id=bid, durum="okundu")


# ── harici (kodsuz) projeler ───────────────────────────────────────────────


def harici_proje_ekle(ad: str, tur: str, not_metni: str | None = None,
                      hedef_tarih: str | None = None, oncelik: int = 2,
                      ayar: dict | None = None) -> int:
    """Diskte klasörü olmayan proje — 3D baskı, yayın işleri, kişisel hedefler.

    ``yol`` sütunu UNIQUE olduğu için sentetik bir anahtar üretiyoruz;
    disk tarayıcısı bu kayıtlara dokunmuyor (harici=1).
    """
    c = _conn()
    anahtar = f"harici:{tur}:{ad.strip().lower()}"
    c.execute(
        "INSERT INTO projeler(yol, ad, var_mi, harici, tur, durum, not_metni, "
        "  hedef_tarih, oncelik, ayar_json, oturum_sayisi, guncellendi) "
        "VALUES(?,?,1,1,?,'aktif',?,?,?,?,0,?) "
        "ON CONFLICT(yol) DO UPDATE SET "
        "  ad=excluded.ad, not_metni=excluded.not_metni, "
        "  hedef_tarih=excluded.hedef_tarih, oncelik=excluded.oncelik, "
        "  ayar_json=excluded.ayar_json, guncellendi=excluded.guncellendi",
        (anahtar, ad.strip(), tur, not_metni, hedef_tarih, oncelik,
         json.dumps(ayar or {}, ensure_ascii=False), time.time()),
    )
    c.commit()
    r = c.execute("SELECT id FROM projeler WHERE yol=?", (anahtar,)).fetchone()
    olay.yayinla("proje", proje_id=r["id"], kategori=tur)
    return r["id"]


def proje_alan_yaz(pid: int, **alanlar: Any) -> None:
    """Projenin mentörlükle ilgili alanlarını güncelle."""
    izinli = {"tur", "durum", "hedef_tarih", "oncelik", "ayar_json", "ad",
              "not_metni", "etiket"}
    d = {k: v for k, v in alanlar.items() if k in izinli}
    if not d:
        return
    c = _conn()
    set_ifade = ", ".join(f"{k}=?" for k in d)
    c.execute(f"UPDATE projeler SET {set_ifade}, guncellendi=? WHERE id=?",
              [*d.values(), time.time(), pid])
    c.commit()
    olay.yayinla("proje", proje_id=pid)


def aktif_projeler() -> list[dict]:
    """Mentörün plan yaparken bakacağı projeler."""
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM projeler WHERE durum='aktif' AND var_mi=1 "
        "ORDER BY oncelik, son_oturum DESC NULLS LAST, ad")]


# ── yazıcılar ve baskılar ──────────────────────────────────────────────────
#
# Yazıcı projeye değil, atölyeye ait. Dört yazıcı var ve bir proje hangisi
# boşsa oraya baskı verebilir; bu yüzden ayrı varlık olarak tutuluyor.


def yazici_ekle(ad: str, model: str = "", ip: str | None = None,
                tur: str = "elle", notlar: str | None = None) -> int:
    c = _conn()
    c.execute(
        "INSERT INTO yazicilar(ad, model, ip, tur, notlar, eklendi) "
        "VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(ad) DO UPDATE SET model=excluded.model, ip=excluded.ip, "
        "  tur=excluded.tur, notlar=excluded.notlar",
        (ad.strip(), model, ip, tur, notlar, time.time()),
    )
    c.commit()
    r = c.execute("SELECT id FROM yazicilar WHERE ad=?", (ad.strip(),)).fetchone()
    olay.yayinla("yazici", yazici_id=r["id"])
    return r["id"]


def yazici(yid: int) -> dict | None:
    r = _conn().execute("SELECT * FROM yazicilar WHERE id=?", (yid,)).fetchone()
    return dict(r) if r else None


def yazicilar() -> list[dict]:
    """Her yazıcı, üstündeki aktif baskıyla birlikte."""
    liste = [dict(r) for r in _conn().execute(
        "SELECT * FROM yazicilar ORDER BY ad")]
    for y in liste:
        r = _conn().execute(
            "SELECT b.*, p.ad AS proje_ad FROM baskilar b "
            "LEFT JOIN projeler p ON p.id=b.proje_id "
            "WHERE b.yazici_id=? AND b.durum='basiliyor' "
            "ORDER BY b.baslangic DESC LIMIT 1", (y["id"],)).fetchone()
        y["aktif_baski"] = dict(r) if r else None
    return liste


def yazici_sil(yid: int) -> None:
    c = _conn()
    c.execute("DELETE FROM yazicilar WHERE id=?", (yid,))
    c.commit()
    olay.yayinla("yazici", yazici_id=yid, durum="silindi")


def baski_ekle(yazici_id: int, ad: str, tahmini_dk: int,
               proje_id: int | None = None) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO baskilar(yazici_id, proje_id, ad, baslangic, tahmini_dk) "
        "VALUES(?,?,?,?,?)",
        (yazici_id, proje_id, ad, time.time(), max(1, int(tahmini_dk))),
    )
    c.commit()
    olay.yayinla("baski", baski_id=cur.lastrowid, yazici_id=yazici_id,
                 durum="basiliyor")
    return cur.lastrowid


def baski(bid: int) -> dict | None:
    r = _conn().execute(
        "SELECT b.*, y.ad AS yazici_ad, y.model AS yazici_model, "
        "       p.ad AS proje_ad FROM baskilar b "
        "LEFT JOIN yazicilar y ON y.id=b.yazici_id "
        "LEFT JOIN projeler p ON p.id=b.proje_id WHERE b.id=?", (bid,)
    ).fetchone()
    return dict(r) if r else None


def aktif_baskilar() -> list[dict]:
    return [dict(r) for r in _conn().execute(
        "SELECT b.*, y.ad AS yazici_ad, p.ad AS proje_ad FROM baskilar b "
        "LEFT JOIN yazicilar y ON y.id=b.yazici_id "
        "LEFT JOIN projeler p ON p.id=b.proje_id "
        "WHERE b.durum='basiliyor' ORDER BY b.baslangic")]


def baski_gecmisi(limit: int = 30) -> list[dict]:
    return [dict(r) for r in _conn().execute(
        "SELECT b.*, y.ad AS yazici_ad, p.ad AS proje_ad FROM baskilar b "
        "LEFT JOIN yazicilar y ON y.id=b.yazici_id "
        "LEFT JOIN projeler p ON p.id=b.proje_id "
        "ORDER BY b.baslangic DESC LIMIT ?", (limit,))]


def baski_bitir_kayit(bid: int, durum: str = "bitti",
                      gorev_id: int | None = None) -> None:
    c = _conn()
    c.execute(
        "UPDATE baskilar SET durum=?, bitis=?, bildirildi=1, gorev_id=? "
        "WHERE id=?", (durum, time.time(), gorev_id, bid))
    c.commit()
    olay.yayinla("baski", baski_id=bid, durum=durum)


def baski_sure_guncelle(bid: int, tahmini_dk: int) -> None:
    c = _conn()
    c.execute("UPDATE baskilar SET tahmini_dk=? WHERE id=?",
              (max(1, int(tahmini_dk)), bid))
    c.commit()
    olay.yayinla("baski", baski_id=bid, durum="sure_guncellendi")


# ── işlem günlüğü ──────────────────────────────────────────────────────────


def gunluk_yaz(seviye: str, kaynak: str, olay: str, mesaj: str = "",
               veri: dict | None = None, proje_id: int | None = None,
               gorev_id: int | None = None,
               sure_ms: int | None = None) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO gunluk(zaman, seviye, kaynak, olay, mesaj, veri, "
        "  proje_id, gorev_id, sure_ms) VALUES(?,?,?,?,?,?,?,?,?)",
        (time.time(), seviye, kaynak, olay, mesaj,
         json.dumps(veri, ensure_ascii=False, default=str) if veri else None,
         proje_id, gorev_id, sure_ms),
    )
    c.commit()
    return cur.lastrowid


def gunluk_oku(seviye: str | None = None, kaynak: str | None = None,
               olay: str | None = None, ara: str | None = None,
               baslangic: float | None = None, limit: int = 200,
               atla: int = 0) -> list[dict]:
    q = "SELECT * FROM gunluk WHERE 1=1"
    d: list[Any] = []
    if seviye:
        q += " AND seviye=?"
        d.append(seviye)
    if kaynak:
        q += " AND kaynak=?"
        d.append(kaynak)
    if olay:
        q += " AND olay=?"
        d.append(olay)
    if ara:
        q += " AND (mesaj LIKE ? OR olay LIKE ? OR veri LIKE ?)"
        d += [f"%{ara}%"] * 3
    if baslangic:
        q += " AND zaman >= ?"
        d.append(baslangic)
    q += " ORDER BY zaman DESC LIMIT ? OFFSET ?"
    d += [limit, atla]
    return [dict(r) for r in _conn().execute(q, d)]


def gunluk_ozet(saat: int = 24) -> dict:
    """Son N saatte seviye ve kaynak dağılımı."""
    esik = time.time() - saat * 3600
    seviyeler = {r["seviye"]: r["n"] for r in _conn().execute(
        "SELECT seviye, COUNT(*) n FROM gunluk WHERE zaman>=? GROUP BY seviye",
        (esik,))}
    kaynaklar = {r["kaynak"]: r["n"] for r in _conn().execute(
        "SELECT kaynak, COUNT(*) n FROM gunluk WHERE zaman>=? "
        "GROUP BY kaynak ORDER BY n DESC LIMIT 12", (esik,))}
    return {"saat": saat, "seviyeler": seviyeler, "kaynaklar": kaynaklar,
            "toplam": sum(seviyeler.values())}


def gunluk_temizle(gun: int = 60) -> int:
    """Eski kayıtları at. Dosyadaki JSONL kopyası duruyor."""
    c = _conn()
    cur = c.execute("DELETE FROM gunluk WHERE zaman < ?",
                    (time.time() - gun * 86400,))
    c.commit()
    return cur.rowcount


# ── yazıcı alanları ────────────────────────────────────────────────────────


def yazici_alan_yaz(yid: int, **alanlar: Any) -> None:
    izinli = {"ad", "model", "ip", "tur", "notlar", "filament",
              "filament_renk", "filament_gram", "nozzle", "durum",
              "kamera_url", "son_gorulme"}
    d = {k: v for k, v in alanlar.items() if k in izinli}
    if not d:
        return
    c = _conn()
    c.execute(f"UPDATE yazicilar SET {', '.join(f'{k}=?' for k in d)} WHERE id=?",
              [*d.values(), yid])
    c.commit()
    olay.yayinla("yazici", yazici_id=yid)


def yazici_sayac_ekle(yid: int, dakika: int) -> None:
    """Baskı kapanınca ömür boyu sayaçları güncelle."""
    c = _conn()
    c.execute("UPDATE yazicilar SET toplam_dk=toplam_dk+?, "
              "baski_sayisi=baski_sayisi+1 WHERE id=?",
              (max(0, int(dakika)), yid))
    c.commit()


# ── 3d Projeler klasörü ────────────────────────────────────────────────────


def dosya_kaydet(ad: str, yol: str, boyut: int | None,
                 durum: str = "bekliyor") -> int:
    c = _conn()
    c.execute(
        "INSERT INTO baski_dosyalari(ad, yol, boyut, durum, eklendi, guncellendi) "
        "VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(yol) DO UPDATE SET ad=excluded.ad, boyut=excluded.boyut, "
        "  guncellendi=excluded.guncellendi",
        (ad, yol, boyut, durum, time.time(), time.time()),
    )
    c.commit()
    r = c.execute("SELECT id FROM baski_dosyalari WHERE yol=?", (yol,)).fetchone()
    olay.yayinla("dosya", dosya_id=r["id"], durum=durum)
    return r["id"]


def dosya(did: int) -> dict | None:
    r = _conn().execute("SELECT * FROM baski_dosyalari WHERE id=?",
                        (did,)).fetchone()
    return dict(r) if r else None


def dosya_yol_ile(yol: str) -> dict | None:
    r = _conn().execute("SELECT * FROM baski_dosyalari WHERE yol=?",
                        (yol,)).fetchone()
    return dict(r) if r else None


def dosyalar(durum: str | None = None) -> list[dict]:
    q = ("SELECT d.*, p.ad AS proje_ad FROM baski_dosyalari d "
         "LEFT JOIN projeler p ON p.id=d.proje_id")
    d: list[Any] = []
    if durum:
        q += " WHERE d.durum=?"
        d.append(durum)
    q += " ORDER BY d.guncellendi DESC"
    return [dict(r) for r in _conn().execute(q, d)]


def dosya_guncelle(did: int, **alanlar: Any) -> None:
    izinli = {"ad", "yol", "durum", "proje_id", "baski_id", "boyut"}
    d = {k: v for k, v in alanlar.items() if k in izinli}
    if not d:
        return
    c = _conn()
    c.execute(f"UPDATE baski_dosyalari SET {', '.join(f'{k}=?' for k in d)}, "
              "guncellendi=? WHERE id=?", [*d.values(), time.time(), did])
    c.commit()
    olay.yayinla("dosya", dosya_id=did, durum=d.get("durum"))


def dosya_sil(did: int) -> None:
    c = _conn()
    c.execute("DELETE FROM baski_dosyalari WHERE id=?", (did,))
    c.commit()
    olay.yayinla("dosya", dosya_id=did, durum="silindi")


# ── alışkanlıklar ──────────────────────────────────────────────────────────


def aliskanlik_ekle(ad: str, tur: str = "gunluk", hedef: int = 7,
                    saat: str | None = None,
                    aciklama: str | None = None) -> int:
    c = _conn()
    c.execute(
        "INSERT INTO aliskanliklar(ad, aciklama, tur, hedef, saat, olusturuldu) "
        "VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(ad) DO UPDATE SET aciklama=excluded.aciklama, "
        "  tur=excluded.tur, hedef=excluded.hedef, saat=excluded.saat, aktif=1",
        (ad.strip(), aciklama, tur, max(1, min(7, int(hedef))), saat,
         time.time()),
    )
    c.commit()
    r = c.execute("SELECT id FROM aliskanliklar WHERE ad=?",
                  (ad.strip(),)).fetchone()
    olay.yayinla("aliskanlik", aliskanlik_id=r["id"])
    return r["id"]


def aliskanlik(aid: int) -> dict | None:
    r = _conn().execute("SELECT * FROM aliskanliklar WHERE id=?",
                        (aid,)).fetchone()
    return dict(r) if r else None


def aliskanliklar(sadece_aktif: bool = True) -> list[dict]:
    q = "SELECT * FROM aliskanliklar"
    if sadece_aktif:
        q += " WHERE aktif=1"
    q += " ORDER BY ad"
    return [dict(r) for r in _conn().execute(q)]


def aliskanlik_sil(aid: int) -> None:
    c = _conn()
    c.execute("DELETE FROM aliskanliklar WHERE id=?", (aid,))
    c.commit()
    olay.yayinla("aliskanlik", aliskanlik_id=aid, durum="silindi")


def aliskanlik_isaretle(aid: int, tarih: str, yapildi: bool = True,
                        not_metni: str | None = None) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO aliskanlik_kayit(aliskanlik_id, tarih, yapildi, "
        "  not_metni, zaman) VALUES(?,?,?,?,?) "
        "ON CONFLICT(aliskanlik_id, tarih) DO UPDATE SET "
        "  yapildi=excluded.yapildi, not_metni=excluded.not_metni, "
        "  zaman=excluded.zaman",
        (aid, tarih, 1 if yapildi else 0, not_metni, time.time()),
    )
    c.commit()
    olay.yayinla("aliskanlik", aliskanlik_id=aid, tarih=tarih,
                 durum="yapildi" if yapildi else "atlandi")


def aliskanlik_kayitlari(aid: int, baslangic: str, bitis: str) -> list[dict]:
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM aliskanlik_kayit WHERE aliskanlik_id=? "
        "AND tarih BETWEEN ? AND ? ORDER BY tarih", (aid, baslangic, bitis))]


def aliskanlik_gunleri(aid: int, limit: int = 400) -> set[str]:
    """Yapıldı işaretli günler — seri hesabı için."""
    return {r["tarih"] for r in _conn().execute(
        "SELECT tarih FROM aliskanlik_kayit WHERE aliskanlik_id=? AND yapildi=1 "
        "ORDER BY tarih DESC LIMIT ?", (aid, limit))}


# ── ritüeller ──────────────────────────────────────────────────────────────


def rituel_kaydet(tarih: str, tur: str, veri: dict,
                  tamamlandi: bool = False) -> int:
    c = _conn()
    c.execute(
        "INSERT INTO ritueller(tarih, tur, veri, tamamlandi, olusturuldu) "
        "VALUES(?,?,?,?,?) "
        "ON CONFLICT(tarih, tur) DO UPDATE SET veri=excluded.veri, "
        "  tamamlandi=excluded.tamamlandi",
        (tarih, tur, json.dumps(veri, ensure_ascii=False),
         time.time() if tamamlandi else None, time.time()),
    )
    c.commit()
    r = c.execute("SELECT id FROM ritueller WHERE tarih=? AND tur=?",
                  (tarih, tur)).fetchone()
    olay.yayinla("rituel", rituel_id=r["id"], kategori=tur, tarih=tarih)
    return r["id"]


def rituel(tarih: str, tur: str) -> dict | None:
    r = _conn().execute("SELECT * FROM ritueller WHERE tarih=? AND tur=?",
                        (tarih, tur)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["veri"] = json.loads(d["veri"] or "{}")
    except json.JSONDecodeError:
        d["veri"] = {}
    return d


def ritueller(limit: int = 30) -> list[dict]:
    liste = []
    for r in _conn().execute(
            "SELECT * FROM ritueller ORDER BY tarih DESC, tur LIMIT ?",
            (limit,)):
        d = dict(r)
        try:
            d["veri"] = json.loads(d["veri"] or "{}")
        except json.JSONDecodeError:
            d["veri"] = {}
        liste.append(d)
    return liste


# ── odak oturumu ───────────────────────────────────────────────────────────


def gorev_gercek_sure(gid: int, dakika: int) -> None:
    c = _conn()
    c.execute("UPDATE gorevler SET gercek_dk=? WHERE id=?",
              (max(0, int(dakika)), gid))
    c.commit()


def tahmin_sapmasi(baslangic: str, bitis: str) -> dict:
    """Tahmin edilen süre ile gerçekte harcanan süre farkı."""
    r = _conn().execute(
        "SELECT COUNT(*) n, COALESCE(SUM(sure_dk),0) tahmin, "
        "       COALESCE(SUM(gercek_dk),0) gercek FROM gorevler "
        "WHERE gercek_dk IS NOT NULL AND tarih BETWEEN ? AND ?",
        (baslangic, bitis)).fetchone()
    if not r["n"] or not r["tahmin"]:
        return {"sayi": 0, "oran": None, "tahmin_dk": 0, "gercek_dk": 0}
    return {
        "sayi": r["n"],
        "tahmin_dk": round(r["tahmin"]),
        "gercek_dk": round(r["gercek"]),
        "oran": round(r["gercek"] / r["tahmin"], 2),
    }


# ── bütçe ve harcama kategorileri ──────────────────────────────────────────


def harcama_kategorileri(baslangic: str, bitis: str) -> dict[str, float]:
    return {(r["kategori"] or "diğer"): round(r["toplam"], 2)
            for r in _conn().execute(
                "SELECT COALESCE(kategori,'diğer') kategori, "
                "       COALESCE(SUM(deger),0) toplam FROM yasam "
                "WHERE tur='harcama' AND tarih BETWEEN ? AND ? "
                "GROUP BY COALESCE(kategori,'diğer') ORDER BY toplam DESC",
                (baslangic, bitis))}


def yasam_kategori_yaz(kid: int, kategori: str) -> None:
    c = _conn()
    c.execute("UPDATE yasam SET kategori=? WHERE id=?", (kategori, kid))
    c.commit()


# ── ekran süresi ───────────────────────────────────────────────────────────


def ekran_ekle(tarih: str, uygulama: str, saniye: int,
               baslik: str | None = None) -> None:
    """Aynı gün+uygulama için süreyi biriktir."""
    c = _conn()
    c.execute(
        "INSERT INTO ekran_sure(tarih, uygulama, baslik, saniye) "
        "VALUES(?,?,?,?) "
        "ON CONFLICT(tarih, uygulama) DO UPDATE SET "
        "  saniye = saniye + excluded.saniye, "
        "  baslik = COALESCE(excluded.baslik, ekran_sure.baslik)",
        (tarih, uygulama, baslik, max(0, int(saniye))),
    )
    c.commit()


def ekran_gunu(tarih: str, limit: int = 25) -> list[dict]:
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM ekran_sure WHERE tarih=? AND saniye > 0 "
        "ORDER BY saniye DESC LIMIT ?", (tarih, limit))]


def ekran_araligi(baslangic: str, bitis: str, limit: int = 25) -> list[dict]:
    return [dict(r) for r in _conn().execute(
        "SELECT uygulama, SUM(saniye) saniye, MAX(baslik) baslik "
        "FROM ekran_sure WHERE tarih BETWEEN ? AND ? "
        "GROUP BY uygulama ORDER BY saniye DESC LIMIT ?",
        (baslangic, bitis, limit))]


def ekran_toplam(tarih: str) -> int:
    r = _conn().execute(
        "SELECT COALESCE(SUM(saniye),0) t FROM ekran_sure WHERE tarih=?",
        (tarih,)).fetchone()
    return int(r["t"])


# ── randevular (dış takvim) ────────────────────────────────────────────────


def randevu_kaydet(uid: str, baslik: str, tarih: str, saat: str | None,
                   sure_dk: int | None, yer: str | None = None,
                   kaynak: str | None = None) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO randevular(uid, baslik, tarih, saat, sure_dk, yer, "
        "  kaynak, guncellendi) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(uid) DO UPDATE SET baslik=excluded.baslik, "
        "  tarih=excluded.tarih, saat=excluded.saat, sure_dk=excluded.sure_dk, "
        "  yer=excluded.yer, kaynak=excluded.kaynak, "
        "  guncellendi=excluded.guncellendi",
        (uid, baslik, tarih, saat, sure_dk, yer, kaynak, time.time()),
    )
    c.commit()


def randevular(tarih: str | None = None, bitis: str | None = None) -> list[dict]:
    q = "SELECT * FROM randevular WHERE 1=1"
    d: list[Any] = []
    if tarih and bitis:
        q += " AND tarih BETWEEN ? AND ?"
        d += [tarih, bitis]
    elif tarih:
        q += " AND tarih=?"
        d.append(tarih)
    q += " ORDER BY tarih, saat"
    return [dict(r) for r in _conn().execute(q, d)]


def randevu_temizle(eski_gun: int = 30, kaynak: str | None = None) -> int:
    """Geçmiş randevuları at; takvim yeniden çekilirken de kullanılır."""
    c = _conn()
    from datetime import date, timedelta

    esik = (date.today() - timedelta(days=eski_gun)).isoformat()
    if kaynak:
        cur = c.execute("DELETE FROM randevular WHERE kaynak=? OR tarih < ?",
                        (kaynak, esik))
    else:
        cur = c.execute("DELETE FROM randevular WHERE tarih < ?", (esik,))
    c.commit()
    return cur.rowcount


# ── baskı maliyeti ─────────────────────────────────────────────────────────


def baski_maliyet_yaz(bid: int, gram: float | None = None,
                      maliyet: float | None = None,
                      satis_fiyati: float | None = None,
                      adet: int | None = None) -> None:
    alanlar, d = [], []
    for ad, deger in (("gram", gram), ("maliyet", maliyet),
                      ("satis_fiyati", satis_fiyati), ("adet", adet)):
        if deger is not None:
            alanlar.append(f"{ad}=?")
            d.append(deger)
    if not alanlar:
        return
    c = _conn()
    d.append(bid)
    c.execute(f"UPDATE baskilar SET {', '.join(alanlar)} WHERE id=?", d)
    c.commit()
    olay.yayinla("baski", baski_id=bid, durum="maliyet")


def baski_kar_ozeti(baslangic_ts: float) -> dict:
    r = _conn().execute(
        "SELECT COUNT(*) n, "
        "  COALESCE(SUM(gram),0) gram, "
        "  COALESCE(SUM(maliyet),0) maliyet, "
        "  COALESCE(SUM(satis_fiyati),0) satis, "
        "  COALESCE(SUM(adet),0) adet "
        "FROM baskilar WHERE durum='bitti' AND baslangic >= ?",
        (baslangic_ts,)).fetchone()
    maliyet, satis = r["maliyet"] or 0, r["satis"] or 0
    return {
        "baski": r["n"], "adet": r["adet"] or 0,
        "gram": round(r["gram"] or 0, 1),
        "maliyet": round(maliyet, 2),
        "satis": round(satis, 2),
        "kar": round(satis - maliyet, 2),
        "marj": round(100 * (satis - maliyet) / satis) if satis else None,
    }
