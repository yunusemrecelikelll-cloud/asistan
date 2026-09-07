'use strict';

/* Mentörlük panelleri — Bugün, Plan, Projeler, Yaşam.
 *
 * app.js'ten sonra yüklenir ve oradaki `api`, `bildir`, `durum`, `gonder`
 * bağlarını kullanır. Klasik betik olduğu için üst düzey tanımlar ortaktır.
 */

const PROJE_TURU = {
  kod: 'Kod', baski: '3D baskı', yayin: 'Yayın', kisisel: 'Kişisel',
  diger: 'Diğer',
};

const ONCELIK_ADI = { 1: 'kritik', 2: 'normal', 3: 'esnek' };

const DURUM_ADI = {
  bekliyor: 'bekliyor', calisiyor: 'çalışıyor', tamam: 'bitti',
  kacirildi: 'kaçtı', ertelendi: 'ertelendi', iptal: 'iptal',
};

let aktifSekme = 'nova';
let yasamAralik = 7;

// ── küçük yardımcılar ──────────────────────────────────────

/** Metni HTML'e gömerken kaçır. */
function gv(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function ogun(t) {
  return new Date(t + 'T00:00:00').toLocaleDateString('tr-TR',
    { day: 'numeric', month: 'long' });
}

function bugunISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${
    String(d.getDate()).padStart(2, '0')}`;
}

/** "10:00" + 90dk → "11:30" */
function bitisSaati(saat, sure) {
  const [s, d] = saat.split(':').map(Number);
  const t = s * 60 + d + (sure || 0);
  return `${String(Math.floor(t / 60) % 24).padStart(2, '0')}:${
    String(t % 60).padStart(2, '0')}`;
}

// ── sekmeler ───────────────────────────────────────────────

const SEKME_ALT = {
  nova: 'Konuş, dinle, gör.',
  bugun: 'Bugünün programı. Mentör takipte.',
  plan: 'Dönem planı ve haftanın dağılımı.',
  projeler: 'Tüm projeler — kod, baskı, yayın, kişisel.',
  atolye: 'Yazıcılar, süren baskılar ve 3d Projeler klasörü.',
  rapor: 'İstatistikler ve işlem günlüğü.',
  yasam: 'Uyku, harcama, beslenme, spor.',
  koc: 'Ritüeller, alışkanlıklar ve koçun tespitleri.',
  sohbet: 'Konuş, sor, komut ver.',
};

async function sekmeSec(ad) {
  aktifSekme = ad;
  document.querySelectorAll('.sekme').forEach((d) =>
    d.classList.toggle('etkin', d.dataset.sekme === ad));
  document.querySelectorAll('.sekme-govde').forEach((s) =>
    s.classList.toggle('gizli', s.id !== `sekme-${ad}`));

  $('#alt-baslik').textContent = SEKME_ALT[ad] || '';
  const sohbetDugmeleri = ['#ozetle', '#rapor', '#temizle'];
  sohbetDugmeleri.forEach((s) =>
    $(s)?.classList.toggle('gizli', ad !== 'sohbet'));

  $('#mesaj').placeholder = ad === 'yasam'
    ? 'Örn. “dün 6 saat uyudum, kahveye 45 lira verdim”'
    : 'Mesaj yaz ya da mikrofona bas…';

  try {
    if (ad === 'nova') { kureKur(); }
    else if (ad === 'bugun') await bugunYukle();
    else if (ad === 'plan') await haftaYukle();
    else if (ad === 'projeler') await projePanelYukle();
    else if (ad === 'atolye') { await projeleriYukle(); await atolyeYukle(); }
    else if (ad === 'rapor') await raporYukle();
    else if (ad === 'koc') await kocYukle();
    else if (ad === 'yasam') await yasamYukle();
  } catch (e) {
    if (e.message !== 'parola gerekli') bildir(e.message, true);
  }
}

// ── Bugün ──────────────────────────────────────────────────

function gorevKarti(g, gunGoster = false) {
  const kalanSinif = g.durum === 'tamam' ? 'bitti'
    : g.durum === 'kacirildi' ? 'kacti'
    : g.durum === 'calisiyor' ? 'calisiyor' : '';
  const telafi = g.telafi_eden ? '<span class="etiket telafi">telafi</span>' : '';
  const zorunlu = g.zorunlu ? '' : '<span class="etiket esnek">esnek</span>';
  const proje = g.proje_ad
    ? `<span class="gorev-proje">${gv(g.proje_ad)}</span>` : '';
  const erteleme = g.erteleme > 0
    ? `<span class="etiket uyari">${g.erteleme}. erteleme</span>` : '';

  const aksiyon = ['tamam', 'iptal'].includes(g.durum) ? '' : `
      <div class="gorev-aksiyon">
        ${g.durum === 'calisiyor' ? ''
          : `<button class="mini" data-is="basla" data-id="${g.id}">Başla</button>`}
        <button class="mini birincil" data-is="tamamla" data-id="${g.id}">Bitti</button>
        <button class="mini" data-is="ertele" data-id="${g.id}">Ertele</button>
        <button class="mini sil" data-is="sil" data-id="${g.id}" title="Sil">✕</button>
      </div>`;

  return `
    <article class="gorev ${kalanSinif} onc-${g.oncelik}" data-id="${g.id}">
      <div class="gorev-saat">
        <strong>${gv(g.saat)}</strong>
        <span>${gv(bitisSaati(g.saat, g.sure_dk))}</span>
        ${gunGoster ? `<em>${gv(ogun(g.tarih))}</em>` : ''}
      </div>
      <div class="gorev-govde">
        <div class="gorev-baslik">${gv(g.baslik)}</div>
        <div class="gorev-alt">
          ${proje}
          <span class="etiket onc">${ONCELIK_ADI[g.oncelik] || ''}</span>
          ${zorunlu}${telafi}${erteleme}
          <span class="etiket durum">${DURUM_ADI[g.durum] || g.durum}</span>
        </div>
        ${g.ayrinti ? `<p class="gorev-ayrinti">${gv(g.ayrinti)}</p>` : ''}
        ${g.gerekce ? `<p class="gorev-gerekce">Gerekçe: ${gv(g.gerekce)}</p>` : ''}
        ${aksiyon}
      </div>
    </article>`;
}

async function bugunYukle() {
  const d = await api('/api/bugun');
  $('#bugun-tarih').textContent = `${ogun(d.tarih)} · ${d.gun}`;

  const k = d.karne;
  $('#bugun-karne').innerHTML = k.toplam
    ? `<span class="buyuk">${k.tamam}/${k.toplam}</span>
       <span class="alt">${k.uyum ?? 0}% uyum${
         k.kacirildi ? ` · ${k.kacirildi} kaçtı` : ''}</span>`
    : '<span class="alt">bugüne görev yok</span>';

  $('#bugun-alt').textContent = k.toplam
    ? `${k.kalan} iş kaldı.`
    : 'Plan yapılmamış. Plan sekmesinden haftalık plan çıkarabilirsin.';

  const s = d.siradaki;
  const sk = $('#siradaki');
  if (s) {
    sk.classList.remove('gizli');
    sk.innerHTML = `
      <div class="siradaki-etiket">Sıradaki</div>
      <div class="siradaki-baslik">${gv(s.baslik)}</div>
      <div class="siradaki-alt">${gv(s.saat)} · ${s.sure_dk} dk${
        s.proje_ad ? ` · ${gv(s.proje_ad)}` : ''}</div>
      <div class="gorev-aksiyon">
        <button class="mini birincil" data-is="tamamla" data-id="${s.id}">Bitti</button>
        <button class="mini" data-is="ertele" data-id="${s.id}">Ertele</button>
      </div>`;
  } else {
    sk.classList.add('gizli');
  }

  $('#bugun-liste').innerHTML = d.gorevler.length
    ? d.gorevler.map((g) => gorevKarti(g)).join('')
    : '<p class="bos">Bugün için planlanmış iş yok.</p>';
}

// ── Plan ───────────────────────────────────────────────────

async function haftaYukle(tarih) {
  const d = await api('/api/hafta' + (tarih ? `?tarih=${tarih}` : ''));
  $('#plan-baslik').textContent =
    `${ogun(d.baslangic)} – ${ogun(d.bitis)}`;

  const k = d.karne;
  $('#plan-karne').innerHTML = k.toplam
    ? `<span class="buyuk">${k.tamam}/${k.toplam}</span>
       <span class="alt">${k.uyum ?? 0}% uyum</span>`
    : '<span class="alt">plan yok</span>';
  $('#plan-alt').textContent = k.toplam
    ? `${k.kacirildi} kaçırıldı · ${k.ertelenen} ertelendi`
    : 'Bu hafta için henüz plan çıkarılmadı.';

  const c = $('#plan-cerceve');
  if (d.plan?.metin) {
    c.classList.remove('gizli');
    c.textContent = d.plan.metin;
  } else {
    c.classList.add('gizli');
  }

  $('#hafta-izgara').innerHTML = d.gunler.map((g) => `
    <div class="hafta-gun${g.bugun ? ' bugun' : ''}">
      <header>
        <strong>${gv(g.gun)}</strong>
        <span>${gv(ogun(g.tarih))}</span>
      </header>
      ${g.gorevler.length
        ? g.gorevler.map((x) => `
          <div class="mini-gorev onc-${x.oncelik} ${
            x.durum === 'tamam' ? 'bitti' : x.durum === 'kacirildi' ? 'kacti' : ''}"
               data-id="${x.id}" title="${gv(x.ayrinti || '')}">
            <span class="mg-saat">${gv(x.saat)}</span>
            <span class="mg-baslik">${gv(x.baslik)}</span>
          </div>`).join('')
        : '<p class="bos kucuk">—</p>'}
    </div>`).join('');
}

async function planUret(tur) {
  const dugme = tur === 'haftalik' ? $('#plan-hafta') : $('#plan-ay');
  const eski = dugme.textContent;
  dugme.disabled = true;
  dugme.textContent = 'Mentör düşünüyor…';
  try {
    const d = await api('/api/plan/uret', {
      method: 'POST',
      body: JSON.stringify({ tur, ek_istek: $('#plan-istek').value.trim() }),
    });
    bildir(`${d.gorev_sayisi} görev planlandı.`);
    (d.uyarilar || []).forEach((u) => bildir(u));
    $('#plan-istek').value = '';
    await haftaYukle();
    if (aktifSekme === 'bugun') await bugunYukle();
  } catch (e) {
    bildir('Plan üretilemedi: ' + e.message, true);
  } finally {
    dugme.disabled = false;
    dugme.textContent = eski;
  }
}

// ── görev eylemleri ────────────────────────────────────────

async function gorevEylem(is_, id) {
  try {
    if (is_ === 'basla') {
      // Odak oturumu: sayaç işlemeye başlar, bitişte gerçek süre yazılır.
      await api(`/api/odak/${id}/basla`, { method: 'POST' });
      bildir('Sayaç başladı. Bitirince gerçek süre kaydedilecek.');
    } else if (is_ === 'tamamla') {
      const r = await api(`/api/odak/${id}/bitir`, { method: 'POST' });
      bildir(r.yorum || (r.gercek_dk
        ? `Bitti — ${r.gercek_dk} dk sürdü.` : 'Bitti olarak işaretlendi.'));
    } else if (is_ === 'ertele') {
      const gerekce = prompt('Neden erteliyorsun? Mentör gerekçe istiyor.');
      if (gerekce === null) return;
      const d = await api(`/api/gorev/${id}/ertele`, {
        method: 'POST', body: JSON.stringify({ gerekce }),
      });
      bildir(`${ogun(d.tarih)} ${d.saat}'e taşındı.`);
    } else if (is_ === 'sil') {
      if (!confirm('Bu görev silinsin mi?')) return;
      await api(`/api/gorev/${id}`, { method: 'DELETE' });
    }
    await panelleriYenile();
  } catch (e) {
    bildir(e.message, true);
  }
}

document.addEventListener('click', (e) => {
  const d = e.target.closest('[data-is]');
  if (d && d.dataset.id) gorevEylem(d.dataset.is, Number(d.dataset.id));
});

// ── görev ekleme kutusu ────────────────────────────────────

function gorevFormAc() {
  $('#yg-tarih').value = bugunISO();
  $('#yg-saat').value = new Date(Date.now() + 30 * 60000)
    .toTimeString().slice(0, 5);
  $('#yg-baslik').value = '';
  $('#yg-ayrinti').value = '';
  $('#yg-sure').value = 60;
  $('#yg-zorunlu').checked = true;

  const sec = $('#yg-proje');
  sec.innerHTML = '<option value="">Proje seçilmedi</option>' +
    (durum.projeler || []).map((p) =>
      `<option value="${p.id}">${gv(p.ad)}</option>`).join('');

  $('#gorev-katman').classList.remove('gizli');
  $('#yg-baslik').focus();
}

async function gorevKaydet() {
  const baslik = $('#yg-baslik').value.trim();
  if (!baslik) { bildir('Başlık gerekli.', true); return; }
  try {
    await api('/api/gorev', {
      method: 'POST',
      body: JSON.stringify({
        baslik,
        tarih: $('#yg-tarih').value || bugunISO(),
        saat: $('#yg-saat').value || '09:00',
        sure_dk: Number($('#yg-sure').value) || 60,
        proje_id: Number($('#yg-proje').value) || null,
        ayrinti: $('#yg-ayrinti').value.trim() || null,
        oncelik: Number($('#yg-oncelik').value) || 2,
        zorunlu: $('#yg-zorunlu').checked,
      }),
    });
    $('#gorev-katman').classList.add('gizli');
    bildir('Görev eklendi.');
    await panelleriYenile();
  } catch (e) {
    bildir(e.message, true);
  }
}

// ── Projeler ───────────────────────────────────────────────

async function projePanelYukle() {
  const { projeler } = await api('/api/projeler');
  durum.projeler = projeler;
  $('#proje-kartlar').innerHTML = projeler.map((p) => `
    <article class="proje-kart onc-${p.oncelik}" data-pid="${p.id}">
      <header>
        <strong>${gv(p.ad)}</strong>
        <span class="etiket tur">${gv(PROJE_TURU[p.tur] || p.tur)}</span>
      </header>
      ${p.not_metni ? `<p class="kart-not">${gv(p.not_metni)}</p>` : ''}
      <div class="kart-alan">
        <label>Tür
          <select data-alan="tur">
            ${Object.entries(PROJE_TURU).map(([k, v]) =>
              `<option value="${k}"${k === p.tur ? ' selected' : ''}>${v}</option>`).join('')}
          </select>
        </label>
        <label>Durum
          <select data-alan="durum">
            ${['aktif', 'beklemede', 'bitti', 'arsiv'].map((k) =>
              `<option value="${k}"${k === p.durum ? ' selected' : ''}>${k}</option>`).join('')}
          </select>
        </label>
        <label>Öncelik
          <select data-alan="oncelik">
            ${[1, 2, 3].map((k) =>
              `<option value="${k}"${k === p.oncelik ? ' selected' : ''}>${ONCELIK_ADI[k]}</option>`).join('')}
          </select>
        </label>
        <label>Hedef
          <input type="date" data-alan="hedef_tarih" value="${gv(p.hedef_tarih || '')}" />
        </label>
      </div>
    </article>`).join('');
}

$('#proje-kartlar')?.addEventListener('change', async (e) => {
  const alan = e.target.dataset.alan;
  if (!alan) return;
  const pid = e.target.closest('[data-pid]')?.dataset.pid;
  if (!pid) return;
  const deger = alan === 'oncelik' ? Number(e.target.value) : e.target.value;
  try {
    await api(`/api/proje/${pid}`, {
      method: 'PATCH', body: JSON.stringify({ [alan]: deger || null }),
    });
    bildir('Kaydedildi.');
    await projePanelYukle();
  } catch (err) {
    bildir(err.message, true);
  }
});

async function hariciProjeKaydet() {
  const ad = $('#yp-ad').value.trim();
  if (!ad) { bildir('Proje adı gerekli.', true); return; }
  try {
    await api('/api/proje/harici', {
      method: 'POST',
      body: JSON.stringify({
        ad,
        tur: $('#yp-tur').value,
        not_metni: $('#yp-not').value.trim() || null,
        hedef_tarih: $('#yp-hedef').value || null,
        oncelik: Number($('#yp-oncelik').value) || 2,
      }),
    });
    ['#yp-ad', '#yp-not', '#yp-hedef'].forEach((s) => { $(s).value = ''; });
    $('#proje-ekle-form').classList.add('gizli');
    bildir('Proje eklendi.');
    await projePanelYukle();
    await projeleriYukle();
  } catch (e) {
    bildir(e.message, true);
  }
}

// ── Baskı (atölye) ─────────────────────────────────────────

let baskiYaziciId = null;

function sureMetni(dk) {
  dk = Math.max(0, Math.round(dk));
  const s = Math.floor(dk / 60);
  return s ? `${s} sa ${dk % 60} dk` : `${dk} dk`;
}

let sonYazicilar = [];

async function atolyeYukle() {
  const d = await api('/api/atolye');
  sonYazicilar = d.yazicilar;

  $('#yazici-kartlar').innerHTML = d.yazicilar.length
    ? d.yazicilar.map((y) => {
      const b = y.aktif_baski;
      const i = b?.ilerleme;
      return `
      <article class="proje-kart ${b ? 'basiyor' : ''}" data-yid="${y.id}">
        <header>
          <strong>${gv(y.ad)}</strong>
          <span class="etiket ${b ? 'uyari' : 'tur'}">${b ? 'baskıda' : 'boş'}</span>
        </header>
        <p class="kart-not">${gv(y.model || '')}${
          y.filament ? ` · ${gv(y.filament)}${
            y.filament_renk ? ` (${gv(y.filament_renk)})` : ''}` : ' · filament yok'}${
          y.nozzle ? ` · ${gv(y.nozzle)} nozzle` : ''}</p>
        <p class="kart-not">Ömür: ${sureMetni(y.toplam_dk)} · ${
          y.baski_sayisi} baskı${y.ip ? ` · ${gv(y.ip)}` : ''}</p>
        ${b ? `
          <div class="baski-bilgi">
            <div class="baski-ad">${gv(b.ad)}${
              b.proje_ad ? ` <span class="gorev-proje">${gv(b.proje_ad)}</span>` : ''}</div>
            <div class="cubuk"><span style="width:${i?.yuzde ?? 0}%"></span></div>
            <div class="baski-alt">%${i?.yuzde ?? 0} · ${
              sureMetni(i?.kalan_dk ?? 0)} kaldı</div>
          </div>
          <div class="gorev-aksiyon">
            <button class="mini birincil" data-baski="bitir" data-id="${b.id}">Bitti</button>
            <button class="mini" data-baski="sure" data-id="${b.id}">Süreyi düzelt</button>
            <button class="mini" data-baski="kamera" data-id="${y.id}">Kamera</button>
            <button class="mini sil" data-baski="iptal" data-id="${b.id}">İptal</button>
          </div>`
        : `
          <div class="gorev-aksiyon">
            <button class="mini birincil" data-baski="basla" data-id="${y.id}">Baskı ver</button>
            <button class="mini" data-baski="duzenle" data-id="${y.id}">Ayarlar</button>
            <button class="mini" data-baski="kamera" data-id="${y.id}">Kamera</button>
            <button class="mini sil" data-baski="yazici-sil" data-id="${y.id}" title="Yazıcıyı sil">✕</button>
          </div>`}
      </article>`;
    }).join('')
    : '<p class="bos">Henüz yazıcı eklenmedi. “+ Yazıcı” ile ekle ya da “Ağda ara”yı dene.</p>';

  await dosyalariYukle();

  $('#baski-gecmis').innerHTML = d.gecmis.length
    ? d.gecmis.map((b) => `
      <div class="kayit">
        <span class="k-tarih">${new Date(b.baslangic * 1000)
          .toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })}</span>
        <span class="k-tur">${gv(b.yazici_ad || '')}</span>
        <span class="k-deger">${gv(DURUM_BASKI[b.durum] || b.durum)}</span>
        <span class="k-detay">${gv(b.ad)}${
          b.proje_ad ? ` · ${gv(b.proje_ad)}` : ''}${
          b.maliyet ? ` · ${b.maliyet} TL` : ''}${
          b.satis_fiyati ? ` → ${b.satis_fiyati} TL` : ''}</span>
        <button class="mini" data-maliyet="${b.id}">${
          b.maliyet ? 'Düzelt' : 'Maliyet'}</button>
      </div>`).join('')
    : '<p class="bos">Baskı geçmişi yok.</p>';
}

const DURUM_BASKI = {
  basiliyor: 'sürüyor', bitti: 'bitti', iptal: 'iptal', hata: 'hata',
};

function baskiFormAc(yaziciId) {
  baskiYaziciId = yaziciId;
  $('#yb-ad').value = '';
  $('#yb-saat').value = 4;
  $('#yb-dakika').value = 0;
  $('#yb-proje').innerHTML = '<option value="">Proje seçilmedi</option>' +
    (durum.projeler || []).filter((p) => p.tur === 'baski' || p.harici)
      .map((p) => `<option value="${p.id}">${gv(p.ad)}</option>`).join('');
  $('#baski-katman').classList.remove('gizli');
  $('#yb-ad').focus();
}

async function baskiBaslat() {
  const ad = $('#yb-ad').value.trim();
  const dk = (Number($('#yb-saat').value) || 0) * 60 +
             (Number($('#yb-dakika').value) || 0);
  if (!ad) { bildir('Ne basıldığını yaz.', true); return; }
  if (dk < 1) { bildir('Süre en az 1 dakika olmalı.', true); return; }
  try {
    const d = await api('/api/baski/basla', {
      method: 'POST',
      body: JSON.stringify({
        yazici_id: baskiYaziciId, ad, tahmini_dk: dk,
        proje_id: Number($('#yb-proje').value) || null,
      }),
    });
    $('#baski-katman').classList.add('gizli');
    bildir(`Baskı başladı. Tahmini bitiş ${d.bitis.slice(11)}.`);
    await atolyeYukle();
  } catch (e) { bildir(e.message, true); }
}

async function baskiEylem(is_, id) {
  try {
    if (is_ === 'basla') { baskiFormAc(id); return; }
    if (is_ === 'duzenle') {
      const y = sonYazicilar.find((x) => x.id === id);
      if (y) yaziciDuzenle(y);
      return;
    }
    if (is_ === 'kamera') {
      const y = sonYazicilar.find((x) => x.id === id);
      if (y) kameraAc(y);
      return;
    }
    if (is_ === 'yazici-sil') {
      if (!confirm('Bu yazıcı silinsin mi?')) return;
      await api(`/api/atolye/yazici/${id}`, { method: 'DELETE' });
    } else if (is_ === 'bitir') {
      await api('/api/baski/bitir', {
        method: 'POST', body: JSON.stringify({ baski_id: id, durum: 'bitti' }),
      });
      bildir('Baskı kapandı, sıradaki adım takvime yazıldı.');
    } else if (is_ === 'iptal') {
      if (!confirm('Baskı iptal olarak kapatılsın mı?')) return;
      await api('/api/baski/bitir', {
        method: 'POST',
        body: JSON.stringify({ baski_id: id, durum: 'iptal', sonraki_adim: false }),
      });
    } else if (is_ === 'sure') {
      const s = prompt('Kalan süre yerine toplam tahmini süre (dakika):');
      if (s === null) return;
      await api('/api/baski/sure', {
        method: 'POST',
        body: JSON.stringify({ baski_id: id, tahmini_dk: Number(s) || 60 }),
      });
    }
    await atolyeYukle();
  } catch (e) { bildir(e.message, true); }
}

document.addEventListener('click', (e) => {
  const d = e.target.closest('[data-baski]');
  if (d && d.dataset.id) baskiEylem(d.dataset.baski, Number(d.dataset.id));
});

async function yaziciEkle() {
  const ad = $('#yz-ad').value.trim();
  if (!ad) { bildir('Yazıcı adı gerekli.', true); return; }
  const ip = $('#yz-ip').value.trim();
  try {
    await api('/api/atolye/yazici', {
      method: 'POST',
      body: JSON.stringify({
        ad, model: $('#yz-model').value.trim(),
        ip: ip || null, tur: ip ? 'mqtt' : 'elle',
        notlar: $('#yz-not').value.trim() || null,
      }),
    });
    ['#yz-ad', '#yz-ip', '#yz-not'].forEach((s) => { $(s).value = ''; });
    $('#yazici-ekle-form').classList.add('gizli');
    bildir('Yazıcı eklendi.');
    await atolyeYukle();
  } catch (e) { bildir(e.message, true); }
}

async function agdaAra() {
  const d = $('#yazici-bulunan');
  const dugme = $('#yazici-ara');
  dugme.disabled = true;
  d.classList.remove('gizli');
  d.textContent = 'Ağ taranıyor…';
  try {
    const r = await api('/api/atolye/ara');
    d.textContent = r.bulunan.length
      ? 'Bulunanlar: ' + r.bulunan.map((b) =>
          `${b.ip}${b.model ? ` (${b.model})` : ''}`).join(', ') +
        ' — IP alanına yazıp ekleyebilirsin.'
      : 'Ağda yazıcı görünmedi. Yazıcı kapalıysa ya da yalnızca Anycubic '
        + 'bulutuna bağlıysa burada çıkmaz; zamanlayıcı kipi yine çalışır.';
  } catch (e) {
    d.textContent = 'Tarama başarısız: ' + e.message;
  } finally {
    dugme.disabled = false;
  }
}

// ── 3d Projeler klasörü ────────────────────────────────────

function dosyaSatiri(d, bitti) {
  const kb = d.boyut ? `${Math.round(d.boyut / 1024)} KB` : '';
  return `
    <div class="kayit">
      <span class="k-tarih">${new Date(d.guncellendi * 1000)
        .toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })}</span>
      <span class="k-detay" title="${gv(d.yol)}">${gv(d.ad)}</span>
      <span class="k-deger">${kb}</span>
      <button class="mini" data-dosya="${bitti ? 'geri' : 'bitti'}"
              data-id="${d.id}">${bitti ? 'Geri al' : 'Bitti'}</button>
    </div>`;
}

async function dosyalariYukle() {
  const d = await api('/api/dosyalar');
  $('#klasor-yol').textContent = d.var_mi
    ? d.kok
    : `${d.kok} — klasör bulunamadı, sunucu yeniden başlayınca oluşturulur.`;
  $('#sayi-bekleyen').textContent = d.sayilar.bekleyen;
  $('#sayi-biten').textContent = d.sayilar.biten;
  $('#dosya-bekleyen').innerHTML = d.bekleyen.length
    ? d.bekleyen.map((x) => dosyaSatiri(x, false)).join('')
    : '<p class="bos kucuk">Klasörün köküne dosya at, buraya düşsün.</p>';
  $('#dosya-biten').innerHTML = d.biten.length
    ? d.biten.map((x) => dosyaSatiri(x, true)).join('')
    : '<p class="bos kucuk">Henüz biten yok.</p>';
}

document.addEventListener('click', async (e) => {
  const t = e.target.closest('[data-dosya]');
  if (!t) return;
  try {
    await api(`/api/dosya/${t.dataset.dosya}`, {
      method: 'POST', body: JSON.stringify({ dosya_id: Number(t.dataset.id) }),
    });
    await dosyalariYukle();
  } catch (err) { bildir(err.message, true); }
});

// ── yazıcı ayarları ve kamera ──────────────────────────────

let duzenlenenYazici = null;

function yaziciDuzenle(y) {
  duzenlenenYazici = y.id;
  const at = (s, v) => { $(s).value = v ?? ''; };
  at('#yd-ad', y.ad); at('#yd-model', y.model); at('#yd-filament', y.filament);
  at('#yd-renk', y.filament_renk); at('#yd-nozzle', y.nozzle);
  at('#yd-gram', y.filament_gram); at('#yd-ip', y.ip);
  at('#yd-kamera', y.kamera_url); at('#yd-not', y.notlar);
  $('#yd-durum').value = y.durum || 'bos';
  $('#yazici-katman').classList.remove('gizli');
}

async function yaziciKaydet() {
  if (!duzenlenenYazici) return;
  const al = (s) => $(s).value.trim() || null;
  try {
    await api(`/api/atolye/yazici/${duzenlenenYazici}`, {
      method: 'PATCH',
      body: JSON.stringify({
        ad: al('#yd-ad'), model: al('#yd-model'), filament: al('#yd-filament'),
        filament_renk: al('#yd-renk'), nozzle: al('#yd-nozzle'),
        filament_gram: Number($('#yd-gram').value) || null,
        ip: al('#yd-ip'), kamera_url: al('#yd-kamera'), notlar: al('#yd-not'),
        durum: $('#yd-durum').value,
      }),
    });
    $('#yazici-katman').classList.add('gizli');
    bildir('Yazıcı güncellendi.');
    await atolyeYukle();
  } catch (e) { bildir(e.message, true); }
}

function kameraAc(y) {
  $('#kamera-baslik').textContent = `${y.ad} — kamera`;
  $('#kamera-govde').innerHTML = y.kamera_url
    ? `<img src="/api/kamera/${y.id}" alt="${gv(y.ad)} kamera görüntüsü" />`
    : '<p class="bos">Bu yazıcı için kamera adresi tanımlı değil. '
      + 'Yazıcı ayarlarından MJPEG akış adresini gir.</p>';
  $('#kamera-katman').classList.remove('gizli');
}

// Akış açık kalmasın: kutu kapanınca <img> kaynağını bırak.
function kameraKapat() {
  $('#kamera-govde').innerHTML = '';
  $('#kamera-katman').classList.add('gizli');
}

// ── Koç ────────────────────────────────────────────────────

let sonRituel = null;

async function kocYukle() {
  const d = await api('/api/koc');

  // Bugünün ritüeli — akşam varsa o, yoksa sabah.
  const r = d.aksam || d.sabah;
  const kutu = $('#rituel-kutu');
  if (r?.veri?.metin) {
    sonRituel = { tur: d.aksam ? 'aksam' : 'sabah', ...r };
    kutu.classList.remove('gizli');
    kutu.textContent = r.veri.metin;
    rituelSorulariCiz(sonRituel);
  } else {
    kutu.classList.add('gizli');
    $('#rituel-sorular').classList.add('gizli');
  }

  aliskanliklariCiz(d.aliskanliklar);
  kaliplariCiz(d.kaliplar);
  butceCiz(d.butce);
}

function rituelSorulariCiz(r) {
  const kutu = $('#rituel-sorular');
  const sorular = r.veri?.sorular || [];
  const cevaplar = r.veri?.cevaplar || {};
  if (!sorular.length || r.tamamlandi) {
    kutu.classList.add('gizli');
    return;
  }
  kutu.classList.remove('gizli');
  kutu.innerHTML = sorular.map((s, i) => `
    <label class="soru">
      <span>${gv(s)}</span>
      <input type="text" data-soru="${gv(s)}" value="${gv(cevaplar[s] || '')}"
             placeholder="Cevabın" autocomplete="off" />
    </label>`).join('')
    + `<div class="form-satir sag">
         <button id="rituel-kaydet" class="birincil">Cevapları kaydet</button>
       </div>`;
  $('#rituel-kaydet').onclick = rituelCevapKaydet;
}

async function rituelCevapKaydet() {
  if (!sonRituel) return;
  const cevaplar = {};
  document.querySelectorAll('#rituel-sorular [data-soru]').forEach((g) => {
    if (g.value.trim()) cevaplar[g.dataset.soru] = g.value.trim();
  });
  try {
    await api('/api/rituel/cevap', {
      method: 'POST',
      body: JSON.stringify({ tur: sonRituel.tur, cevaplar }),
    });
    bildir('Kaydedildi.');
    await kocYukle();
  } catch (e) { bildir(e.message, true); }
}

async function rituelUret(tur) {
  const dugme = $(tur === 'sabah' ? '#rituel-sabah' : '#rituel-aksam');
  const eski = dugme.textContent;
  dugme.disabled = true;
  dugme.textContent = 'Yazıyor…';
  try {
    await api('/api/rituel', { method: 'POST', body: JSON.stringify({ tur }) });
    await kocYukle();
  } catch (e) {
    bildir(e.message, true);
  } finally {
    dugme.disabled = false;
    dugme.textContent = eski;
  }
}

function aliskanliklariCiz(p) {
  const liste = p?.aliskanliklar || [];
  $('#aliskanlik-liste').innerHTML = liste.length
    ? liste.map((a) => `
      <article class="aliskanlik${a.bugun ? ' yapildi' : ''}">
        <div class="al-bas">
          <button class="al-kutu" data-aliskanlik="isaret" data-id="${a.id}"
                  title="${a.bugun ? 'Geri al' : 'Bugün yaptım'}">${
            a.bugun ? '✓' : ''}</button>
          <div>
            <strong>${gv(a.ad)}</strong>
            <div class="al-alt">
              seri <b>${a.seri}</b> gün · en uzun ${a.en_uzun_seri} ·
              bu hafta ${a.bu_hafta}/${a.hedef}
              ${a.hedef_tuttu ? '<span class="etiket">hedef tamam</span>'
                : '<span class="etiket uyari">hedefin altında</span>'}
            </div>
          </div>
          <button class="mini sil" data-aliskanlik="sil" data-id="${a.id}"
                  title="Sil">✕</button>
        </div>
        <div class="al-takvim">${a.takvim.map((g) =>
          `<span class="${g.yapildi ? 'dolu' : ''}" title="${g.tarih}"></span>`
        ).join('')}</div>
      </article>`).join('')
    : '<p class="bos">Alışkanlık eklenmedi. Spor, kitap, erken kalkma…</p>';
}

document.addEventListener('click', async (e) => {
  const t = e.target.closest('[data-aliskanlik]');
  if (!t) return;
  const id = Number(t.dataset.id);
  try {
    if (t.dataset.aliskanlik === 'sil') {
      if (!confirm('Bu alışkanlık silinsin mi? Geçmişi de gider.')) return;
      await api(`/api/aliskanlik/${id}`, { method: 'DELETE' });
    } else {
      const kart = t.closest('.aliskanlik');
      await api('/api/aliskanlik/isaret', {
        method: 'POST',
        body: JSON.stringify({
          aliskanlik_id: id,
          yapildi: !kart.classList.contains('yapildi'),
        }),
      });
    }
    await kocYukle();
  } catch (err) { bildir(err.message, true); }
});

function kaliplariCiz(k) {
  const satirlar = [];
  (k?.erteleme || []).forEach((e) => satirlar.push(`
    <div class="kayit uyari-satir">
      <span class="k-deger">%${e.yuzde}</span>
      <span class="k-detay"><b>${gv(e.ad)}</b> — ${e.toplam} görevin
        ${e.kacan}'ı kaçtı, ${e.erteleme} kez ertelendi.
        ${e.tamam === 0 ? 'Hiç ilerlemedi; ya erken saate al ya arşive.' : ''}</span>
    </div>`));

  const u = k?.uyku;
  if (u?.yeterli_veri) {
    satirlar.push(`
      <div class="kayit">
        <span class="k-deger">${u.fark >= 0 ? '+' : ''}${u.fark}</span>
        <span class="k-detay">${u.esik} saatin altında uyuduğunda uyumun
          %${u.az_uyku_uyum}, üstünde %${u.bol_uyku_uyum}
          (${u.az_gun}/${u.bol_gun} gün).</span>
      </div>`);
  }

  const t = k?.tahmin;
  if (t?.sayi >= 3 && t.oran) {
    satirlar.push(`
      <div class="kayit">
        <span class="k-deger">${t.oran}×</span>
        <span class="k-detay">İşler tahmin ettiğinin ${t.oran} katı sürüyor
          (${t.sayi} ölçüm). Süre tahminlerin ${
            t.oran > 1 ? 'iyimser' : 'temkinli'}.</span>
      </div>`);
  }

  $('#kalip-liste').innerHTML = satirlar.length ? satirlar.join('')
    : '<p class="bos">Henüz örüntü çıkacak kadar veri yok. Birkaç hafta '
      + 'görev ve uyku kaydı biriksin.</p>';
}

function butceCiz(b) {
  if (!b) return;
  $('#butce-aylik').value = b.aylik_butce || '';
  const kart = (ad, deger, alt) => `
    <article class="yasam-kart">
      <div class="yk-bas"><span class="yk-ad">${gv(ad)}</span></div>
      <div class="yk-deger">${gv(deger)}<small>TL</small></div>
      <div class="yk-alt">${gv(alt)}</div>
    </article>`;
  $('#butce-ozet').innerHTML = [
    kart('Bu ay', b.toplam, b.aylik_butce
      ? `bütçenin %${b.yuzde}'i` : 'bütçe tanımlı değil'),
    kart('Kalan', b.kalan ?? '—', b.aylik_butce
      ? `${b.aylik_butce} TL bütçe` : '—'),
    kart('Günlük ort.', b.gunluk_ortalama, 'bu ay'),
    kart('Ay sonu tahmini', b.ay_sonu_tahmini,
      b.aylik_butce && b.ay_sonu_tahmini > b.aylik_butce
        ? 'bütçeyi aşacaksın' : 'bu hızla'),
  ].join('');

  $('#butce-kategori').innerHTML = b.kategoriler.length
    ? b.kategoriler.map((k) => `
      <div class="kayit${k.asildi ? ' uyari-satir' : ''}">
        <span class="k-tarih">${gv(k.kategori)}</span>
        <span class="k-deger">${k.harcanan} TL</span>
        <span class="k-detay">${k.butce
          ? `bütçe ${k.butce} TL · %${k.yuzde}${k.asildi ? ' — aşıldı' : ''}`
          : 'bütçe yok'}</span>
      </div>`).join('')
    : '<p class="bos">Bu ay harcama kaydı yok.</p>';
}

async function aliskanlikKaydet() {
  const ad = $('#ya-ad').value.trim();
  if (!ad) { bildir('Alışkanlık adı gerekli.', true); return; }
  try {
    await api('/api/aliskanlik', {
      method: 'POST',
      body: JSON.stringify({
        ad, tur: 'gunluk',
        hedef: Number($('#ya-hedef').value) || 7,
        saat: $('#ya-saat').value || null,
      }),
    });
    $('#ya-ad').value = '';
    $('#aliskanlik-form').classList.add('gizli');
    await kocYukle();
  } catch (e) { bildir(e.message, true); }
}

async function butceKaydet() {
  try {
    await api('/api/butce', {
      method: 'POST',
      body: JSON.stringify({ aylik: Number($('#butce-aylik').value) || 0 }),
    });
    bildir('Bütçe kaydedildi.');
    await kocYukle();
  } catch (e) { bildir(e.message, true); }
}

async function seansYap() {
  const d = $('#seans-yap');
  d.disabled = true;
  d.textContent = 'Değerlendiriyor…';
  try {
    const r = await api('/api/seans', { method: 'POST' });
    $('#rituel-kutu').classList.remove('gizli');
    $('#rituel-kutu').textContent = r.metin;
    $('#rituel-sorular').classList.add('gizli');
  } catch (e) {
    bildir(e.message, true);
  } finally {
    d.disabled = false;
    d.textContent = 'Haftalık seans';
  }
}

// ── Rapor ──────────────────────────────────────────────────

let raporAralik = 30;

async function raporYukle() {
  const d = await api(`/api/istatistik?gun=${raporAralik}`);
  const a = d.atolye, m = d.mentorluk, c = d.maliyet;

  const kart = (ad, deger, alt) => `
    <article class="yasam-kart">
      <div class="yk-bas"><span class="yk-ad">${gv(ad)}</span></div>
      <div class="yk-deger">${gv(deger)}</div>
      <div class="yk-alt">${gv(alt)}</div>
    </article>`;

  $('#rapor-kartlar').innerHTML = [
    kart('Baskı', a.baski_sayisi,
         a.basari_yuzde == null ? 'kapanan baskı yok'
           : `%${a.basari_yuzde} başarı · ${a.bitti} bitti`),
    kart('Yazıcı süresi', a.toplam_metni, `${a.suren} baskı sürüyor`),
    kart('Görev', `${m.tamam}/${m.toplam}`,
         m.uyum == null ? 'görev yok' : `%${m.uyum} uyum`),
    kart('Temiz gün', m.temiz_gun_serisi, 'üst üste tam uyum'),
    kart('Kaçan', m.kacirildi, `${m.ertelenen} erteleme`),
    kart('Yerel iş', c.yerel_oran == null ? '—' : `%${c.yerel_oran}`,
         `${c.yerel_biten_is} yerel · ${c.claude_a_yukselen} Claude`),
    kart('Claude', c.toplam_birim, `${c.eylem_sayisi} eylem`),
    kart('Dosya', d.dosyalar.bekleyen, `${d.dosyalar.biten} bitti`),
  ].join('');

  $('#rapor-yazicilar').innerHTML = a.yazicilar.length
    ? a.yazicilar.map((y) => `
      <div class="kayit">
        <span class="k-tarih">${gv(y.ad)}</span>
        <span class="k-tur">${gv(y.filament || '—')}</span>
        <span class="k-deger">${gv(y.donem_metni)}</span>
        <span class="k-detay">${y.donem_baski} baskı · ömür ${
          gv(y.omur_metni)} / ${y.omur_baski} baskı · doluluk %${
          y.mesgul_yuzde}</span>
        <span></span>
      </div>`).join('')
    : '<p class="bos">Yazıcı yok.</p>';

  const enYuksek = Math.max(1, ...m.seri.map((g) => g.toplam));
  $('#rapor-egri').innerHTML = m.seri.map((g) => `
    <div class="egri-gun" title="${g.tarih}: ${g.tamam}/${g.toplam}">
      <div class="egri-cubuk" style="height:${
        Math.round(100 * g.toplam / enYuksek)}%">
        <span style="height:${g.toplam ? Math.round(100 * g.tamam / g.toplam) : 0}%"></span>
      </div>
    </div>`).join('');

  $('#rapor-kacan').innerHTML = m.en_cok_kacan.length
    ? m.en_cok_kacan.map((k) => `
      <div class="kayit">
        <span class="k-deger">${k.n}×</span>
        <span class="k-detay">${gv(k.baslik)}</span>
        <span></span><span></span><span></span>
      </div>`).join('')
    : '<p class="bos">Kaçırılan iş yok.</p>';

  await ekranYukle();
  await yedekYukle();
  await gunlukYukle();
}

// ── ekran süresi ───────────────────────────────────────────

async function ekranYukle() {
  const d = await api(`/api/ekran?gun=${raporAralik}`);
  if (!d.destekleniyor) {
    $('#ekran-ozet').textContent = 'Ekran süresi yalnızca Windows\'ta ölçülüyor.';
    $('#ekran-liste').innerHTML = '';
    return;
  }
  if (!d.acik) {
    $('#ekran-ozet').textContent =
      'Kapalı. Ayarlar → Takvim, ekran, yedek bölümünden açabilirsin.';
    $('#ekran-liste').innerHTML = '';
    return;
  }
  $('#ekran-ozet').textContent =
    `Bugün ${d.bugun_metni} · son ${d.gun} günde ${d.toplam_metni} `
    + `(günlük ortalama ${d.gunluk_ortalama})`;
  $('#ekran-liste').innerHTML = d.donem.length
    ? d.donem.map((u) => `
      <div class="kayit">
        <span class="k-tarih">${gv(u.uygulama)}</span>
        <span class="k-deger">${gv(u.metin)}</span>
        <span class="k-detay">%${u.yuzde}${
          u.baslik ? ` · ${gv(u.baslik)}` : ''}</span>
      </div>`).join('')
    : '<p class="bos">Henüz ölçüm yok.</p>';
}

// ── yedekler ───────────────────────────────────────────────

function boyutMetni(bayt) {
  return bayt > 1048576 ? `${(bayt / 1048576).toFixed(1)} MB`
    : `${Math.round(bayt / 1024)} KB`;
}

async function yedekYukle() {
  const d = await api('/api/yedek');
  $('#yedek-ozet').textContent = d.son
    ? `${d.sayi} yedek · sonuncusu ${d.son.tarih}`
    : 'Henüz yedek yok.';
  $('#yedek-liste').innerHTML = d.yedekler.length
    ? d.yedekler.slice(0, 10).map((y) => `
      <div class="kayit">
        <span class="k-tarih">${gv(y.tarih)}</span>
        <span class="k-deger">${boyutMetni(y.boyut)}</span>
        <span class="k-detay">${gv(y.ad)}</span>
        <a class="mini" href="/api/yedek/indir/${encodeURIComponent(y.ad)}"
           download>İndir</a>
        <button class="mini" data-yedek="${gv(y.ad)}">Geri yükle</button>
      </div>`).join('')
    : '<p class="bos">Yedek yok.</p>';
}

document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-maliyet]');
  if (t) maliyetGir(Number(t.dataset.maliyet));
});

document.addEventListener('click', async (e) => {
  const t = e.target.closest('[data-yedek]');
  if (!t) return;
  if (!confirm(`"${t.dataset.yedek}" geri yüklensin mi?\n\n`
    + 'Şu anki veriler bu yedekle değiştirilir. Öncesinde güvenlik yedeği '
    + 'alınacak.')) return;
  try {
    const r = await api('/api/yedek/geri-yukle', {
      method: 'POST', body: JSON.stringify({ ad: t.dataset.yedek }),
    });
    bildir(`Geri yüklendi. Güvenlik yedeği: ${r.onceki_yedek}`);
    location.reload();
  } catch (err) { bildir(err.message, true); }
});

const GUNLUK_SIMGE = { hata: '⛔', uyari: '⚠️', bilgi: '·' };

async function gunlukYukle() {
  const s = $('#gunluk-seviye').value;
  const ara = $('#gunluk-ara').value.trim();
  const q = new URLSearchParams({ limit: '150' });
  if (s) q.set('seviye', s);
  if (ara) q.set('ara', ara);
  const d = await api(`/api/gunluk?${q}`);
  $('#gunluk-liste').innerHTML = d.kayitlar.length
    ? d.kayitlar.map((k) => `
      <div class="gunluk-satir ${gv(k.seviye)}">
        <span class="g-zaman">${new Date(k.zaman * 1000)
          .toLocaleString('tr-TR', { day: '2-digit', month: '2-digit',
                                     hour: '2-digit', minute: '2-digit',
                                     second: '2-digit' })}</span>
        <span class="g-seviye">${GUNLUK_SIMGE[k.seviye] || '·'}</span>
        <span class="g-kaynak">${gv(k.kaynak)}</span>
        <span class="g-olay">${gv(k.olay)}</span>
        <span class="g-mesaj">${gv(k.mesaj || '')}${
          k.sure_ms ? ` <em>${k.sure_ms} ms</em>` : ''}</span>
      </div>${k.veri ? `<pre class="g-veri">${
        gv(JSON.stringify(k.veri, null, 1))}</pre>` : ''}`).join('')
    : '<p class="bos">Kayıt yok.</p>';
}

// ── Yaşam ──────────────────────────────────────────────────

const YASAM_SIMGE = {
  uyku: '🌙', harcama: '₺', ogun: '🍽', spor: '🏃', su: '💧', ruh: '🙂',
};

async function yasamYukle() {
  const d = await api(`/api/yasam?gun=${yasamAralik}`);
  $('#yasam-kartlar').innerHTML = d.kartlar.map((k) => {
    // Başlıkta bugünün değeri durur. Bugün kayıt yoksa boş bir tire yerine
    // dönem ortalamasını göster — kart hep bir şey söylesin.
    const bugunVar = k.bugun != null && k.bugun !== 0;
    const deger = bugunVar ? k.bugun : (k.sayi ? k.ortalama : null);
    const etiket = bugunVar ? 'bugün' : (k.sayi ? `${yasamAralik} gün ort.` : '');
    return `
    <article class="yasam-kart ${k.durum}">
      <div class="yk-bas">
        <span class="yk-simge">${YASAM_SIMGE[k.tur] || '•'}</span>
        <span class="yk-ad">${gv(k.ad)}</span>
      </div>
      <div class="yk-deger">${
        deger != null ? gv(deger) : '—'}<small>${gv(k.birim)}</small></div>
      <div class="yk-alt">${
        k.sayi
          ? `${etiket} · ${k.sayi} kayıt`
          : 'kayıt yok'}${k.hedef ? ` · hedef ${k.hedef}` : ''}</div>
    </article>`;
  }).join('');

  $('#yasam-kayitlar').innerHTML = d.kayitlar.length
    ? d.kayitlar.map((k) => `
      <div class="kayit">
        <span class="k-tarih">${gv(ogun(k.tarih))}</span>
        <span class="k-tur">${YASAM_SIMGE[k.tur] || ''} ${gv(k.tur)}</span>
        <span class="k-deger">${gv(k.deger ?? '')} ${gv(k.birim || '')}</span>
        <span class="k-detay">${gv(k.detay || '')}</span>
        <button class="mini sil" data-yasam-sil="${k.id}" title="Sil">✕</button>
      </div>`).join('')
    : '<p class="bos">Henüz kayıt yok. Aşağıya konuşarak ya da yazarak ekle.</p>';
}

$('#yasam-kayitlar')?.addEventListener('click', async (e) => {
  const id = e.target.dataset?.yasamSil;
  if (!id) return;
  try {
    await api(`/api/yasam/${id}`, { method: 'DELETE' });
    await yasamYukle();
  } catch (err) { bildir(err.message, true); }
});

async function yasamMetinGonder(metin) {
  try {
    const d = await api('/api/yasam/metin', {
      method: 'POST', body: JSON.stringify({ metin }),
    });
    bildir('Kaydedildi: ' + d.ozet);
    await yasamYukle();
    return true;
  } catch (e) {
    bildir(e.message, true);
    return false;
  }
}

async function yasamAnalizAl() {
  const d = $('#yasam-yorum');
  d.classList.remove('gizli');
  d.textContent = 'Değerlendiriliyor…';
  try {
    const r = await api(`/api/yasam/analiz?gun=${yasamAralik}`);
    d.textContent = r.metin;
  } catch (e) {
    d.textContent = 'Değerlendirilemedi: ' + e.message;
  }
}

// ── bildirimler ────────────────────────────────────────────

const BILDIRIM_SIMGE = {
  gorev: '⏰', uyari: '⚠️', telafi: '🔁', kutlama: '✅',
  gun_basi: '🌅', gun_sonu: '🌇', bilgi: 'ℹ️',
};

async function bildirimleriYukle() {
  const { bildirimler } = await api('/api/bildirimler?limit=40');
  const okunmamis = bildirimler.filter((b) => !b.okundu).length;
  const rozet = $('#rozet-bildirim');
  rozet.textContent = okunmamis;
  rozet.classList.toggle('gizli', okunmamis === 0);

  $('#bildirim-govde').innerHTML = bildirimler.length
    ? bildirimler.map((b) => `
      <div class="bildirim-satir${b.okundu ? '' : ' yeni'}">
        <span class="bs-simge">${BILDIRIM_SIMGE[b.tur] || '•'}</span>
        <div>
          <strong>${gv(b.baslik)}</strong>
          <p>${gv(b.metin)}</p>
          <span class="bs-zaman">${new Date(b.zaman * 1000)
            .toLocaleString('tr-TR', { day: 'numeric', month: 'short',
                                       hour: '2-digit', minute: '2-digit' })}</span>
        </div>
      </div>`).join('')
    : '<p class="bos">Bildirim yok.</p>';
}

// ── yenileme ───────────────────────────────────────────────

async function panelleriYenile() {
  try {
    if (aktifSekme === 'bugun') await bugunYukle();
    else if (aktifSekme === 'plan') await haftaYukle();
    else if (aktifSekme === 'yasam') await yasamYukle();
    else if (aktifSekme === 'atolye') await atolyeYukle();
    else if (aktifSekme === 'rapor') await raporYukle();
    else if (aktifSekme === 'koc') await kocYukle();
    await bildirimleriYukle();
  } catch (e) {
    if (e.message !== 'parola gerekli') bildir(e.message, true);
  }
}

// ── Nova küresi ve konuşma akışı ───────────────────────────
//
// Uygulama her açıldığında yeni bir sohbet başlıyor. Sunucudaki geçmişi
// silmiyoruz — yalnızca bu oturumdan sonrasını gösteriyoruz. Geçmişi yok
// etmek geri alınamaz; görünümü sıfırlamak yeter.

let kure = null;
let novaOturum = Date.now() / 1000;
let calmaBaglami = null;
let calmaCozumleyici = null;

function kureKur() {
  const tuval = $('#nova-kure');
  if (!tuval || kure) return;
  kure = new NovaKure(tuval);
  kure.basla();
}

function kureDurum(durum, yazi, alt) {
  kure?.durumaGec(durum);
  if (yazi !== undefined) {
    const e = $('#kure-durum-yazi');
    if (e) e.textContent = yazi;
  }
  if (alt !== undefined) {
    const e = $('#kure-alt');
    if (e) e.textContent = alt;
  }
}

/** Çalan sesi küreye bağla — Nova konuşurken küre onunla nefes alsın. */
function calmayiGorsellestir(audio) {
  try {
    calmaBaglami = calmaBaglami
      || new (window.AudioContext || window.webkitAudioContext)();
    if (calmaBaglami.state === 'suspended') calmaBaglami.resume();
    if (!calmaCozumleyici) {
      calmaCozumleyici = calmaBaglami.createAnalyser();
      calmaCozumleyici.fftSize = 512;
      calmaCozumleyici.connect(calmaBaglami.destination);
    }
    const kaynak = calmaBaglami.createMediaElementSource(audio);
    kaynak.connect(calmaCozumleyici);
    kure?.bagla(calmaCozumleyici);
    return true;
  } catch {
    return false;                 // görselleştirme olmazsa ses yine çalsın
  }
}

function novaSatir(kim, metin) {
  const akis = $('#nova-akis');
  if (!akis || !metin) return;
  akis.querySelector('.bos')?.remove();
  const el = document.createElement('div');
  el.className = 'nova-satir ' + (kim === 'ben' ? 'ben' : 'nova');
  el.innerHTML = `<div class="kim">${kim === 'ben' ? 'Sen' : 'Nova'}</div>`
    + gv(metin).replace(/\n/g, '<br>');
  akis.appendChild(el);
  akis.scrollTop = akis.scrollHeight;
}

function novaSifirla() {
  novaOturum = Date.now() / 1000;
  const akis = $('#nova-akis');
  if (akis) {
    akis.innerHTML = '<p class="bos">Yeni sohbet. Dinlemeye başla ya da '
      + 'aşağıdan yaz.</p>';
  }
  kureDurum('bekliyor', 'Dinlemek için dokun',
            '“Hey Nova” de, gerisini ben hallederim');
}

// ── sürekli sesli mod ──────────────────────────────────────
//
// Mikrofona basmadan konuşabilmek için: mikrofon sürekli açık kalır, sesin
// enerjisi izlenir, konuşma başlayınca kayıt açılır, sustuğunda kapanıp
// yazıya çevrilir.
//
// Tarayıcıda hazır bir uyandırma sözcüğü motoru yok; ses zaten yazıya
// çevrildiği için sözcüğü metinde arıyoruz. Böylece ek bir kütüphane
// gerekmiyor ve her şey bu bilgisayarda kalıyor.
//
// Uyandırma sözcüğünden sonra kısa bir "konuşma penceresi" açılır; peş peşe
// söylediklerin için her seferinde "asistan" demen gerekmez.

// Konuşma tanıma "Nova"yı farklı yazabiliyor; hepsini kabul ediyoruz.
// "Hey" isteğe bağlı — tek başına "Nova" da uyandırır.
const UYANDIRMA = ['hey nova', 'hey nowa', 'heynova',
                   'nova', 'nowa', 'novaa', 'no va'];
const SESSIZLIK_MS = 600;      // bu kadar sessizlik = cümle bitti
// 1200 ms güvenliydi ama her cümleden sonra bir saniyeden fazla ölü
// bekleme demekti; kullanıcı bunu doğrudan gecikme olarak duyuyor.
const ASGARI_MS = 400;         // bundan kısa ses yok sayılır
const AZAMI_MS = 15000;        // güvenlik sınırı
const PENCERE_MS = 25000;      // uyandırmadan sonra serbest konuşma süresi

const surekli = {
  acik: false, akis: null, cozumleyici: null, kaydedici: null,
  parcalar: [], konusuyor: false, baslangic: 0, sonSes: 0,
  pencereSonu: 0, duraklat: false, zamanlayici: null, tabani: 0,
};

function _sadelestir(s) {
  return (s || '').toLocaleLowerCase('tr')
    .replaceAll('ı', 'i').replaceAll('İ', 'i')
    .replace(/[^a-zçğöşü0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
}

function uyandirmaVar(metin) {
  const d = _sadelestir(metin);
  return UYANDIRMA.some((k) => d.startsWith(k) || d.includes(' ' + k));
}

function uyandirmayiAt(metin) {
  const d = _sadelestir(metin);
  for (const k of UYANDIRMA) {
    const i = d.indexOf(k);
    if (i !== -1) return metin.slice(i + k.length).replace(/^[\s,.:!?]+/, '');
  }
  return metin;
}

function seritYaz(yazi, konusuyor = false) {
  const y = $('#dinleme-yazi');
  if (y) y.textContent = yazi;
  $('#dinleme-serit')?.classList.toggle('konusuyor', konusuyor);
}

async function surekliAc() {
  if (surekli.acik) return;
  try {
    surekli.akis = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true,
               autoGainControl: true },
    });
  } catch {
    bildir('Mikrofona erişilemedi. Tarayıcı iznini kontrol et.', true);
    return;
  }

  const ses = new (window.AudioContext || window.webkitAudioContext)();
  const kaynak = ses.createMediaStreamSource(surekli.akis);
  surekli.cozumleyici = ses.createAnalyser();
  surekli.cozumleyici.fftSize = 1024;
  kaynak.connect(surekli.cozumleyici);
  kureKur();
  kure?.bagla(surekli.cozumleyici);

  surekli.acik = true;
  surekli.tabani = 0;
  surekli.pencereSonu = 0;
  $('#surekli')?.classList.add('etkin');
  $('#surekli-yazi') && ($('#surekli-yazi').textContent = 'Dinliyor');
  $('#mikrofon').classList.add('dinliyor');
  $('#dinleme-serit')?.classList.remove('gizli');
  seritYaz('Dinliyorum — “Hey Nova” de');
  kureDurum('dinliyor', 'Dinliyorum', '“Hey Nova” de');
  surekli.zamanlayici = setInterval(_surekliTur, 100);
}

function surekliKapat() {
  if (!surekli.acik) return;
  surekli.acik = false;
  clearInterval(surekli.zamanlayici);
  try { surekli.kaydedici?.state === 'recording' && surekli.kaydedici.stop(); }
  catch { /* yoksay */ }
  surekli.akis?.getTracks().forEach((t) => t.stop());
  surekli.akis = null;
  surekli.konusuyor = false;
  $('#surekli')?.classList.remove('etkin');
  $('#surekli-yazi') && ($('#surekli-yazi').textContent = 'Sürekli dinle');
  $('#mikrofon').classList.remove('dinliyor', 'kayitta');
  $('#dinleme-serit')?.classList.add('gizli');
  kure?.bagla(null);
  kureDurum('bekliyor', 'Dinlemek için dokun',
            '“Hey Nova” de, gerisini ben hallederim');
}

/** Anlık ses şiddeti (0-1 arası kaba bir ölçü). */
function _siddet() {
  const n = surekli.cozumleyici.fftSize;
  const veri = new Uint8Array(n);
  surekli.cozumleyici.getByteTimeDomainData(veri);
  let toplam = 0;
  for (let i = 0; i < n; i++) {
    const x = (veri[i] - 128) / 128;
    toplam += x * x;
  }
  return Math.sqrt(toplam / n);
}

function _surekliTur() {
  if (!surekli.acik || surekli.duraklat) return;
  const s = _siddet();

  // İlk saniyelerde ortam gürültüsünü öğren; eşiği ona göre koy.
  surekli.tabani = surekli.tabani
    ? surekli.tabani * 0.995 + s * 0.005
    : s;
  const esik = Math.max(0.015, surekli.tabani * 2.5);
  const simdi = Date.now();

  if (s > esik) {
    surekli.sonSes = simdi;
    if (!surekli.konusuyor) _kayitAc(simdi);
    else if (simdi - surekli.baslangic > AZAMI_MS) _kayitKapa();
  } else if (surekli.konusuyor && simdi - surekli.sonSes > SESSIZLIK_MS) {
    _kayitKapa();
  }
}

function _kayitAc(simdi) {
  try {
    surekli.kaydedici = new MediaRecorder(surekli.akis);
  } catch {
    return;
  }
  surekli.parcalar = [];
  surekli.kaydedici.ondataavailable = (e) =>
    e.data.size && surekli.parcalar.push(e.data);
  surekli.kaydedici.onstop = _kayitBitti;
  surekli.kaydedici.start();
  surekli.konusuyor = true;
  surekli.baslangic = simdi;
  $('#mikrofon').classList.add('kayitta');
  seritYaz('Seni duyuyorum…', true);
  kureDurum('dinliyor', 'Seni duyuyorum…', '');
}

function _kayitKapa() {
  surekli.konusuyor = false;
  $('#mikrofon').classList.remove('kayitta');
  seritYaz('Anlıyorum…');
  kureDurum('dusunuyor', 'Anlıyorum…', '');
  try { surekli.kaydedici?.stop(); } catch { /* yoksay */ }
}

async function _kayitBitti() {
  const sure = Date.now() - surekli.baslangic;
  const blob = new Blob(surekli.parcalar, { type: 'audio/webm' });
  if (sure < ASGARI_MS || blob.size < 1500) return;

  try {
    const fd = new FormData();
    fd.append('ses', blob, 'kayit.webm');
    const d = await api('/api/stt', { method: 'POST', body: fd });
    const metin = (d.metin || '').trim();
    if (!metin) return;

    const pencereAcik = Date.now() < surekli.pencereSonu;
    if (!uyandirmaVar(metin) && !pencereAcik) {
      seritYaz('Dinliyorum — “Hey Nova” de');
      return;                                   // bize değildi
    }

    const komut = uyandirmaVar(metin) ? uyandirmayiAt(metin) : metin;
    if (komut.length < 2) {
      surekli.pencereSonu = Date.now() + PENCERE_MS;
      bildir('Dinliyorum.');
      return;
    }

    // Kendi sesimizi duymayalım: yanıt gelene kadar dinlemeyi durdur.
    surekli.duraklat = true;
    surekli.pencereSonu = Date.now() + PENCERE_MS;
    seritYaz('Düşünüyorum…');
    kureDurum('dusunuyor', 'Düşünüyorum…', '');
    novaSatir('ben', komut);
    try {
      await gonder(komut, true);
    } finally {
      setTimeout(() => {
        surekli.duraklat = false;
        if (surekli.acik) {
          seritYaz('Devam et, dinliyorum');
          kureDurum('dinliyor', 'Devam et', 'dinliyorum');
          kure?.bagla(surekli.cozumleyici);
        }
      }, 800);
    }
  } catch (e) {
    if (e.message !== 'parola gerekli') bildir(e.message, true);
  }
}

// ── ek ayarlar ─────────────────────────────────────────────
//
// app.js kendi ayarlarını çizdikten sonra buradakiler eklenir. Gruplayarak
// veriyoruz; tek uzun liste okunmuyor.

const AYAR_GRUPLARI = [
  ['Mentörlük', [
    ['anahtar', 'mentor_acik', 'Mentör açık',
     'Kapatınca plan denetimi, kaçırma ve telafi durur.'],
    ['saat', 'gun_baslangic', 'Gün başlangıcı',
     'İlk iş bloğu bu saatten önce yerleştirilmez.'],
    ['saat', 'gun_bitis', 'Gün bitişi',
     'Bu saatten sonra görev konmaz; akşam karnesi burada çıkar.'],
    ['secim', 'mentor_sertlik', 'Sertlik',
     'Yüksek: erteleme gerekçe ister ve karneye işler.',
     ['yuksek', 'orta', 'esnek']],
    ['sayi', 'gecikme_toleransi_dk', 'Gecikme toleransı (dk)',
     'Görev saatinden bu kadar sonra başlanmadıysa kaçırıldı sayılır.',
     { min: 0, step: 5 }],
    ['sayi', 'odak_blok_dk', 'Odak bloğu (dk)',
     'Tipik çalışma bloğunun uzunluğu.', { min: 15, step: 15 }],
    ['sayi', 'gunluk_azami_blok', 'Günde en fazla blok',
     'Plan bu sayıyı aşmaz; aşan işler sonraki güne kayar.',
     { min: 1, step: 1 }],
  ]],
  ['Koç', [
    ['secim', 'koc_tonu', 'Koç tonu',
     'Sert: yumuşatma yok, bahaneyi adıyla söyler.',
     ['sert', 'dengeli', 'yumusak']],
    ['anahtar', 'sabah_rituel', 'Sabah ritüeli',
     'Gün başlarken program ve tek kritik iş sorusu.'],
    ['anahtar', 'aksam_rituel', 'Akşam ritüeli',
     'Gün biterken üç soruluk değerlendirme.'],
    ['sayi', 'uyku_hedef', 'Uyku hedefi (saat)',
     'Bu eşiğin altı "az uyku" sayılır.', { min: 0, step: 0.5 }],
    ['sayi', 'butce_aylik', 'Aylık bütçe (TL)',
     '0 = bütçe takibi kapalı.', { min: 0, step: 100 }],
  ]],
  ['Atölye ve maliyet', [
    ['sayi', 'filament_kg_fiyat', 'Filament (TL/kg)',
     'Baskı maliyeti bu fiyattan hesaplanır.', { min: 0, step: 50 }],
    ['sayi', 'elektrik_kwh_fiyat', 'Elektrik (TL/kWh)',
     '', { min: 0, step: 0.5 }],
    ['sayi', 'yazici_watt', 'Yazıcı çekişi (W)',
     'Ortalama tüketim.', { min: 0, step: 10 }],
    ['sayi', 'iscilik_saat_fiyat', 'İşçilik (TL/saat)',
     '0 = maliyete katma.', { min: 0, step: 25 }],
    ['anahtar', 'klasor_takip', '3d Projeler klasörü',
     'Masaüstündeki klasörü izle ve dosyaları yerleştir.'],
  ]],
  ['Takvim, ekran, yedek', [
    ['metin', 'takvim_ics', 'Takvim ICS adresi',
     'Google/Outlook/Apple takviminin gizli ICS bağlantısı. Randevuların '
     + 'üstüne görev yazılmaz. Boş = kapalı.'],
    ['anahtar', 'ekran_takip', 'Ekran süresi takibi',
     'Öndeki uygulamayı ölçer. Tuş ya da içerik kaydedilmez, boşta geçen '
     + 'süre sayılmaz. Varsayılan kapalı.'],
    ['anahtar', 'yedek_acik', 'Otomatik yedek',
     'Günde bir kez veritabanı yedeği alır.'],
    ['sayi', 'yedek_saklama', 'Saklanacak yedek sayısı',
     'Eskiler silinir.', { min: 1, step: 1 }],
    ['anahtar', 'agir_is_yerel', 'Ağır işleri yerel model yapsın',
     'Plan ve yorumlar önce Ollama ile denenir; çıktı yetersizse Claude '
     + 'devreye girer.'],
  ]],
];

async function ayarKaydet(anahtar, deger) {
  await api('/api/ayarlar', {
    method: 'POST', body: JSON.stringify({ anahtar, deger: String(deger) }),
  });
  bildir('Kaydedildi');
}

async function sesAyarlariCiz() {
  const govde = $('#ayar-govde');
  if (!govde || govde.querySelector('.ses-ayar')) return;

  let d;
  try {
    d = await api('/api/ses/durum');
  } catch {
    return;
  }

  const kutu = document.createElement('div');
  kutu.className = 'ses-ayar';
  kutu.innerHTML = `
    <h4 class="ayar-grup">Ses</h4>
    <div class="ayar-satir">
      <div class="aciklama">Asistanın konuşacağı ses. Adına dokunup
        değiştirebilirsin. Referans kayıtları
        <code>data/ses-klon/</code> klasöründe — oraya yeni bir .wav
        koyarsan listede çıkar.${d.servis ? ''
          : ' <b>Ses servisi kapalı</b> — <code>.\ses_servisi.ps1</code>'}</div>
      <div class="ses-liste">
        ${d.sesler.length
          ? d.sesler.map((x) => `
            <label class="ses-secim${x.anahtar === d.secili ? ' secili' : ''}"
                   data-ses="${gv(x.anahtar)}">
              <input type="radio" name="ses" value="${gv(x.anahtar)}"${
                x.anahtar === d.secili ? ' checked' : ''} />
              <input class="ses-ad" type="text" value="${gv(x.ad)}"
                     data-ad="${gv(x.anahtar)}" maxlength="40" />
              <button class="mini" data-dinle="${gv(x.anahtar)}">Dinle</button>
            </label>`).join('')
          : '<p class="bos kucuk">Ses bulunamadı.</p>'}
      </div>
    </div>`;
  govde.appendChild(kutu);

  kutu.querySelectorAll('[name="ses"]').forEach((r) => {
    r.onchange = async () => {
      await api('/api/ses/sec', {
        method: 'POST', body: JSON.stringify({ anahtar: r.value }),
      });
      kutu.querySelectorAll('.ses-secim').forEach((e) =>
        e.classList.toggle('secili', e.dataset.ses === r.value));
      bildir('Ses değişti.');
    };
  });

  kutu.querySelectorAll('.ses-ad').forEach((g) => {
    // Ada tıklayınca seçim değişmesin
    g.onclick = (e) => e.preventDefault();
    g.onchange = async () => {
      try {
        await api('/api/ses/ad', {
          method: 'POST',
          body: JSON.stringify({ anahtar: g.dataset.ad, ad: g.value }),
        });
        bildir('Ad kaydedildi.');
      } catch (e) { bildir(e.message, true); }
    };
  });

  kutu.querySelectorAll('[data-dinle]').forEach((b) => {
    b.onclick = async (e) => {
      e.preventDefault();
      const eski = b.textContent;
      b.disabled = true;
      b.textContent = '…';
      try {
        const r = await fetch('/api/ses/dene', {
          method: 'POST', headers: basliklar(null),
          body: JSON.stringify({ referans: b.dataset.dinle }),
        });
        if (!r.ok) throw new Error('ses üretilemedi');
        seslendirmeyiKes();
        await _cal(await r.blob());
      } catch (err) {
        bildir(err.message, true);
      } finally {
        b.disabled = false;
        b.textContent = eski;
      }
    };
  });
}

function ekAyarlariCiz(ayarlar) {
  const govde = $('#ayar-govde');
  if (!govde || govde.querySelector('.ayar-grup')) return;

  for (const [grup, satirlar] of AYAR_GRUPLARI) {
    const baslik = document.createElement('h4');
    baslik.className = 'ayar-grup';
    baslik.textContent = grup;
    govde.appendChild(baslik);

    for (const [tur, anahtar, ad, aciklama, ek] of satirlar) {
      const satir = document.createElement('div');
      satir.className = 'ayar-satir';
      const deger = ayarlar[anahtar] ?? '';
      let alan;

      if (tur === 'anahtar') {
        satir.innerHTML = `<label class="onay-etiket">
            <input type="checkbox"${deger === '1' ? ' checked' : ''} />
            <span>${gv(ad)}</span></label>
          <div class="aciklama">${gv(aciklama)}</div>`;
        alan = satir.querySelector('input');
        alan.onchange = () => ayarKaydet(anahtar, alan.checked ? '1' : '0');
      } else if (tur === 'secim') {
        satir.innerHTML = `<label>${gv(ad)}</label>
          <div class="aciklama">${gv(aciklama)}</div>
          <select>${ek.map((s) =>
            `<option value="${s}"${s === deger ? ' selected' : ''}>${s}</option>`
          ).join('')}</select>`;
        alan = satir.querySelector('select');
        alan.onchange = () => ayarKaydet(anahtar, alan.value);
      } else {
        const tip = tur === 'saat' ? 'time' : tur === 'sayi' ? 'number' : 'text';
        const ozellik = tur === 'sayi'
          ? ` min="${ek.min}" step="${ek.step}"` : '';
        satir.innerHTML = `<label>${gv(ad)}</label>
          <div class="aciklama">${gv(aciklama)}</div>
          <input type="${tip}"${ozellik} value="${gv(deger)}" />`;
        alan = satir.querySelector('input');
        alan.onchange = () => ayarKaydet(anahtar, alan.value);
      }
      govde.appendChild(satir);
    }
  }
  sesAyarlariCiz();
}

// ── app.js kancaları ───────────────────────────────────────

// Yaşam sekmesindeyken yazılan/söylenen her şey kayda gider, sohbete değil.
// Not: gonder() gönder düğmesinden ve Enter'dan argümansız çağrılıyor —
// metni burada da yazı alanından okumak gerekiyor.
const _sohbeteGonder = gonder;
gonder = async function (metin, sesMi = false) {
  const m = (metin ?? $('#mesaj').value).trim();

  if (aktifSekme === 'yasam' && m) {
    $('#mesaj').value = '';
    $('#mesaj').style.height = 'auto';
    // Kayda çevrilemezse cümle sohbete düşsün, kaybolmasın.
    if (await yasamMetinGonder(m)) return;
    return _sohbeteGonder(m, sesMi);
  }

  // "<dosya adı> bitti" — hangi sekmede olursak olalım dosyayı taşı.
  // Eşleşme bulunmazsa ya da birden fazla aday çıkarsa sohbete devrediyoruz;
  // yanlış dosyayı "bitti" diye kaldırmak hiç kaldırmamaktan kötü.
  if (m && /\bbitti\b/i.test(m)) {
    try {
      const d = await api('/api/dosya/bitti-metin', {
        method: 'POST', body: JSON.stringify({ metin: m }),
      });
      if (d.ok) {
        $('#mesaj').value = '';
        $('#mesaj').style.height = 'auto';
        bildir(`“${d.dosya.ad}” Baskısı Bitenler'e taşındı.`);
        await panelleriYenile();
        if (aktifSekme === 'atolye') await dosyalariYukle();
        return;
      }
      if (d.secim_gerekli) {
        bildir('Birden fazla dosya eşleşti: '
          + d.adaylar.map((x) => x.ad).join(', ') + ' — hangisi?', true);
        return;
      }
    } catch { /* eşleşme yok; normal sohbete devam */ }
  }

  return _sohbeteGonder(metin, sesMi);
};

// ── akışlı seslendirme ─────────────────────────────────────
//
// Eski yol: bütün metin seslendirilir, sonra çalınır. Uzun cevapta 5-6 saniye
// sessizlik demek.
//
// Yeni yol: metin cümlelere bölünür, hepsi aynı anda istenir ama SIRAYLA
// çalınır. İlk cümle geldiği anda ses başlıyor; gerisi arkada üretiliyor.
// Beklenen süre, toplam süreden ilk cümlenin süresine iniyor.

const ES_ZAMANLI = 3;          // aynı anda kaç parça istensin

let calanSes = null;
let seslendirmeNo = 0;

function seslendirmeyiKes() {
  seslendirmeNo++;             // süren akışı geçersiz kıl
  try {
    calanSes?.pause();
    if (calanSes?.src) URL.revokeObjectURL(calanSes.src);
  } catch { /* yoksay */ }
  calanSes = null;
}

function _cal(blob) {
  return new Promise((bitti) => {
    const url = URL.createObjectURL(blob);
    const a = new Audio(url);
    calanSes = a;
    calmayiGorsellestir(a);
    const kapat = () => { URL.revokeObjectURL(url); bitti(); };
    a.onended = kapat;
    a.onerror = kapat;
    a.play().catch(kapat);
  });
}

async function _parcaIste(p) {
  try {
    const r = await fetch('/api/tts/parca', {
      method: 'POST', headers: basliklar(null), body: JSON.stringify(p),
    });
    return r.ok ? await r.blob() : null;
  } catch {
    return null;
  }
}

async function akisliSeslendir(metin) {
  if (!metin) return;
  novaSatir('nova', metin);
  if (!$('#sesli-yanit').checked) return;
  seslendirmeyiKes();
  kureDurum('konusuyor', 'Konuşuyorum', '');
  const benimNo = seslendirmeNo;

  let parcalar;
  try {
    const d = await api('/api/konus', {
      method: 'POST', body: JSON.stringify({ metin }),
    });
    parcalar = d.parcalar || [];
  } catch {
    return;
  }
  if (!parcalar.length || benimNo !== seslendirmeNo) return;

  // Kuyruğu önden doldur, biri bitince sıradakini iste — hem ilk ses erken
  // gelsin hem de sunucuyu gereksiz yere boğmayalım.
  const kuyruk = [];
  let sonraki = 0;
  const doldur = () => {
    while (kuyruk.length < ES_ZAMANLI && sonraki < parcalar.length) {
      kuyruk.push(_parcaIste(parcalar[sonraki++]));
    }
  };
  doldur();

  while (kuyruk.length) {
    const blob = await kuyruk.shift();
    if (benimNo !== seslendirmeNo) return;      // araya yeni konuşma girdi
    doldur();
    if (blob) await _cal(blob);
    if (benimNo !== seslendirmeNo) return;
  }
  calanSes = null;
  if (surekli.acik) {
    kure?.bagla(surekli.cozumleyici);
    kureDurum('dinliyor', 'Devam et', 'dinliyorum');
  } else {
    kureDurum('bekliyor', 'Dinlemek için dokun', '');
  }
}

// app.js'in tek parça seslendirmesini akışlı olanla değiştir; sürekli
// dinleme açıkken de kendi sesimizi duymayalım diye mikrofonu duraklat.
const _eskiSeslendir = seslendir;
seslendir = async function (metin) {
  if (!surekli.acik) return akisliSeslendir(metin);
  surekli.duraklat = true;
  try {
    await akisliSeslendir(metin);
  } finally {
    // Çalma gerçekten bittiğinde açıyoruz; tahmine gerek yok.
    setTimeout(() => { surekli.duraklat = false; }, 400);
  }
};

// app.js ayarları çizdikten sonra bizimkiler eklensin.
const _eskiAyarlariYukle = ayarlariYukle;
ayarlariYukle = async function () {
  await _eskiAyarlariYukle();
  ekAyarlariCiz(durum.ayarlar || {});
};

// Sunucu tarafındaki değişiklikler panellere de yansısın.
const _eskiOlaylariIsle = olaylariIsle;
olaylariIsle = async function (olaylar) {
  const ilgili = olaylar.some((o) =>
    ['gorev', 'bildirim', 'yasam', 'plan', 'proje', 'baski', 'yazici',
     'dosya', 'aliskanlik', 'rituel']
      .includes(o.tur));
  await _eskiOlaylariIsle(olaylar);
  if (ilgili) await panelleriYenile();
};

// ── bağlantılar ────────────────────────────────────────────

document.querySelectorAll('.sekme').forEach((d) => {
  d.onclick = () => sekmeSec(d.dataset.sekme);
});

$('#bugun-yenile').onclick = () => bugunYukle().catch((e) => bildir(e.message, true));
$('#gorev-ekle-ac').onclick = gorevFormAc;
$('#yg-kaydet').onclick = gorevKaydet;
$('#yg-iptal').onclick = () => $('#gorev-katman').classList.add('gizli');
$('#gorev-kapat').onclick = () => $('#gorev-katman').classList.add('gizli');

$('#plan-hafta').onclick = () => planUret('haftalik');
$('#plan-ay').onclick = () => planUret('aylik');

$('#proje-ekle-ac').onclick = () =>
  $('#proje-ekle-form').classList.toggle('gizli');
$('#yp-kaydet').onclick = hariciProjeKaydet;
$('#yp-iptal').onclick = () => $('#proje-ekle-form').classList.add('gizli');

$('#yazici-ekle-ac').onclick = () =>
  $('#yazici-ekle-form').classList.toggle('gizli');
$('#yz-kaydet').onclick = yaziciEkle;
$('#yz-iptal').onclick = () => $('#yazici-ekle-form').classList.add('gizli');
$('#yazici-ara').onclick = agdaAra;
$('#yb-kaydet').onclick = baskiBaslat;
$('#yb-iptal').onclick = () => $('#baski-katman').classList.add('gizli');
$('#baski-kapat').onclick = () => $('#baski-katman').classList.add('gizli');

$('#yasam-yenile').onclick = () => yasamYukle().catch((e) => bildir(e.message, true));
$('#yasam-analiz').onclick = yasamAnalizAl;
$('#yasam-aralik').onchange = (e) => {
  yasamAralik = Number(e.target.value) || 7;
  yasamYukle().catch((err) => bildir(err.message, true));
};

$('#nova-dinle').onclick = () => {
  if (surekli.acik) { surekliKapat(); $('#nova-dinle').textContent = 'Dinlemeye başla'; }
  else { surekliAc(); $('#nova-dinle').textContent = 'Dinlemeyi durdur'; }
};
$('#nova-yeni').onclick = novaSifirla;

$('#surekli').onclick = () =>
  (surekli.acik ? surekliKapat() : surekliAc());
$('#dinleme-kapat').onclick = surekliKapat;

$('#yedek-al').onclick = async () => {
  try {
    const r = await api('/api/yedek/al', { method: 'POST' });
    bildir(`Yedek alındı: ${r.ad}`);
    await yedekYukle();
  } catch (e) { bildir(e.message, true); }
};
$('#yedek-dokum').onclick = async () => {
  try {
    const r = await api('/api/yedek/disa-aktar', { method: 'POST' });
    bildir(`Döküm hazır: ${r.ad}`);
    await yedekYukle();
  } catch (e) { bildir(e.message, true); }
};

$('#rituel-sabah').onclick = () => rituelUret('sabah');
$('#rituel-aksam').onclick = () => rituelUret('aksam');
$('#seans-yap').onclick = seansYap;
$('#aliskanlik-ekle-ac').onclick = () =>
  $('#aliskanlik-form').classList.toggle('gizli');
$('#ya-kaydet').onclick = aliskanlikKaydet;
$('#ya-iptal').onclick = () => $('#aliskanlik-form').classList.add('gizli');
$('#butce-kaydet').onclick = butceKaydet;

$('#yd-kaydet').onclick = yaziciKaydet;
$('#yd-iptal').onclick = () => $('#yazici-katman').classList.add('gizli');
$('#yd-kapat').onclick = () => $('#yazici-katman').classList.add('gizli');
$('#kamera-kapat').onclick = kameraKapat;
$('#gunluk-yenile').onclick = () => gunlukYukle().catch((e) => bildir(e.message, true));
$('#gunluk-ara').onkeydown = (e) => { if (e.key === 'Enter') gunlukYukle(); };
$('#gunluk-seviye').onchange = () => gunlukYukle();
$('#rapor-aralik').onchange = (e) => {
  raporAralik = Number(e.target.value) || 30;
  raporYukle().catch((err) => bildir(err.message, true));
};

$('#bildirim-ac').onclick = async () => {
  $('#bildirim-katman').classList.remove('gizli');
  await bildirimleriYukle();
};
$('#bildirim-kapat').onclick = () => $('#bildirim-katman').classList.add('gizli');
$('#bildirim-temizle').onclick = async () => {
  await api('/api/bildirimler/okundu', {
    method: 'POST', body: JSON.stringify({ id: null }),
  });
  await bildirimleriYukle();
};

document.querySelectorAll('.katman').forEach((k) => {
  k.addEventListener('click', (e) => {
    if (e.target === k) k.classList.add('gizli');
  });
});

// ── açılış ─────────────────────────────────────────────────

(async function panelBaslat() {
  try {
    novaSifirla();
    await sekmeSec('nova');
    // app.js ayarları biz yüklenmeden çizmiş olabilir; tamamla.
    // Sayfa kapanırken mikrofonu bırak.
    window.addEventListener('beforeunload', surekliKapat);
    ekAyarlariCiz(durum.ayarlar || {});
    await bildirimleriYukle();
    setInterval(() => bildirimleriYukle().catch(() => {}), 60000);
  } catch (e) {
    if (e.message !== 'parola gerekli') bildir(e.message, true);
  }
})();
