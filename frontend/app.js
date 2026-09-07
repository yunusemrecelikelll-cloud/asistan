'use strict';

const $ = (s) => document.querySelector(s);

const durum = {
  projeler: [],
  secili: null,
  ayarlar: {},
  izlenen: new Map(),   // eylem_id -> {proje}
  otomatik: [],         // otomatik devam açık projeler
  kayitta: false,
};

// ── yardımcılar ────────────────────────────────────────────

function belirtec() {
  try { return localStorage.getItem('asistan-belirtec') || ''; } catch { return ''; }
}

function basliklar(govde) {
  const h = {};
  if (!(govde instanceof FormData)) h['Content-Type'] = 'application/json';
  const b = belirtec();
  if (b) h['X-Asistan-Belirtec'] = b;
  return h;
}

async function api(yol, secenek = {}) {
  const r = await fetch(yol, { headers: basliklar(secenek.body), ...secenek });
  if (r.status === 401) {
    girisAc();
    throw new Error('parola gerekli');
  }
  if (!r.ok) {
    let m = r.statusText;
    try { m = (await r.json()).detail || m; } catch { /* yoksay */ }
    throw new Error(m);
  }
  return r.headers.get('content-type')?.includes('json') ? r.json() : r;
}

// ── giriş ──────────────────────────────────────────────────

function girisAc() { $('#giris-katman').classList.remove('gizli'); }

async function girisYap() {
  const p = $('#giris-parola').value.trim();
  if (!p) return;
  const dugme = $('#giris-dugme');
  dugme.disabled = true;
  try {
    const r = await fetch('/api/giris', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parola: p }),
    });
    if (!r.ok) throw new Error('Parola yanlış');
    const d = await r.json();
    try { localStorage.setItem('asistan-belirtec', d.belirtec); } catch { /* yoksay */ }
    $('#giris-katman').classList.add('gizli');
    $('#giris-hata').textContent = '';
    $('#giris-parola').value = '';
    baslat();
  } catch (e) {
    $('#giris-hata').textContent = e.message;
  } finally {
    dugme.disabled = false;
  }
}

let bildirimZaman;
function bildir(metin, hata = false) {
  const el = $('#bildirim');
  el.textContent = metin;
  el.classList.toggle('hata', hata);
  el.classList.remove('gizli');
  clearTimeout(bildirimZaman);
  bildirimZaman = setTimeout(() => el.classList.add('gizli'), hata ? 6000 : 3200);
}

function gunFarki(ts) {
  if (!ts) return null;
  return Math.floor((Date.now() / 1000 - ts) / 86400);
}

function zamanEtiketi(ts) {
  const g = gunFarki(ts);
  if (g === null) return 'hiç';
  if (g === 0) return 'bugün';
  if (g === 1) return 'dün';
  if (g < 30) return `${g} gün`;
  return `${Math.floor(g / 30)} ay`;
}

// ── projeler ───────────────────────────────────────────────

async function projeleriYukle(tara = false) {
  const d = await api(tara ? '/api/projeler/tara' : '/api/projeler', {
    method: tara ? 'POST' : 'GET',
  });
  durum.projeler = d.projeler;
  projeleriCiz();
  const o = d.ozet;
  $('#ozet').textContent =
    `${o.diskte_var} proje · son hafta ${o.son_hafta_aktif} aktif` +
    (o.kaydedilmemis_degisiklik ? ` · ${o.kaydedilmemis_degisiklik} kirli` : '');
}

function projeleriCiz() {
  const q = $('#proje-ara').value.trim().toLowerCase();
  const liste = $('#proje-liste');
  liste.innerHTML = '';

  const tumu = document.createElement('div');
  tumu.className = 'proje' + (durum.secili === null ? ' secili' : '');
  tumu.innerHTML = `<span class="ad">Tüm projeler</span>
                    <span class="rozet">${durum.projeler.length}</span>`;
  tumu.onclick = () => projeSec(null);
  liste.appendChild(tumu);

  durum.projeler
    .filter((p) => !q || p.ad.toLowerCase().includes(q))
    .forEach((p) => {
      const kirli = p.git_durumu?.degisiklik_sayisi || 0;
      const el = document.createElement('div');
      const otoAcik = durum.otomatik.some((o) => o.id === p.id);
      el.className = 'proje' + (durum.secili === p.id ? ' secili' : '')
                   + (p.var_mi ? '' : ' yok') + (otoAcik ? ' oto' : '');
      el.innerHTML = `
        <span class="ad" title="${p.yol}">${p.ad}</span>
        ${kirli ? `<span class="rozet kirli" title="kaydedilmemiş değişiklik">${kirli}</span>` : ''}
        <span class="bilgi">${zamanEtiketi(p.son_oturum)}</span>`;
      el.onclick = () => projeSec(p.id);
      liste.appendChild(el);
    });
}

function projeSec(id) {
  durum.secili = id;
  const p = durum.projeler.find((x) => x.id === id);
  $('#baslik').textContent = p ? p.ad : 'Tüm projeler';
  $('#alt-baslik').textContent = p
    ? p.yol + (p.var_mi ? '' : '  (klasör diskte yok)')
    : 'Komut vermek için bir proje seç.';

  $('#proje-arac').classList.toggle('gizli', !p || !p.var_mi);
  $('#brifing-kutu').classList.add('gizli');
  if (p) {
    const oto = durum.otomatik.find((o) => o.id === p.id);
    $('#oto-anahtar').checked = !!oto;
    $('#oto-bilgi').textContent = oto
      ? `${Math.round(oto.aralik / 60)} dk aralık · ${oto.sayac}/${oto.azami} tur`
      : '';
  }
  projeleriCiz();
}

// ── sohbet ─────────────────────────────────────────────────

function balonEkle(rol, metin, kaynak) {
  const akis = $('#akis');
  const bos = akis.querySelector('.bos');
  if (bos) bos.remove();

  const el = document.createElement('div');
  el.className = `balon ${rol}`;
  const etiket = { kullanici: 'Sen', asistan: 'Asistan', sistem: '' }[rol] ?? rol;
  el.innerHTML =
    (etiket ? `<div class="rol">${etiket}</div>` : '') +
    `<div class="govde"></div>`;
  el.querySelector('.govde').textContent = metin;
  if (kaynak) {
    const k = document.createElement('span');
    k.className = 'kaynak';
    k.textContent = { ollama: 'yerel model', claude: 'Claude', yerel: 'yerel hesap' }[kaynak] || kaynak;
    el.appendChild(k);
  }
  akis.appendChild(el);
  akis.scrollTop = akis.scrollHeight;
  return el;
}

async function mesajlariYukle() {
  const { mesajlar } = await api('/api/mesajlar');
  const akis = $('#akis');
  akis.innerHTML = '';
  if (!mesajlar.length) {
    akis.innerHTML = `<div class="bos">
      Merhaba. Projelerini takip ediyorum.<br>
      <b>"Projelerimin durumu ne?"</b> diye sor,<br>
      <b>"JSPS'te testleri çalıştır"</b> de,<br>
      ya da mikrofona basıp konuş.
    </div>`;
    return;
  }
  mesajlar.forEach((m) => balonEkle(
    m.rol === 'kullanici' ? 'kullanici' : 'asistan', m.metin, m.kaynak));
}

async function seslendir(metin) {
  if (!$('#sesli-yanit').checked || !metin) return;
  try {
    const r = await fetch('/api/tts', {
      method: 'POST',
      headers: basliklar(null),
      body: JSON.stringify({ metin }),
    });
    if (!r.ok) return;
    const url = URL.createObjectURL(await r.blob());
    const a = new Audio(url);
    a.onended = () => URL.revokeObjectURL(url);
    a.play().catch(() => URL.revokeObjectURL(url));
  } catch { /* ses isteğe bağlı, sessizce geç */ }
}

function onayKutusu(d) {
  const akis = $('#akis');
  const bos = akis.querySelector('.bos');
  if (bos) bos.remove();

  const el = document.createElement('div');
  el.className = 'onay';
  el.dataset.id = d.taslak_id;
  el.innerHTML = `
    <div class="bas">
      <span>${d.proje} · onayını bekliyor</span>
      <span>#${d.taslak_id}</span>
    </div>
    <div class="ham">Senin isteğin: ${d.ham}</div>
    <textarea spellcheck="false"></textarea>
    <div class="dugmeler">
      <button class="birincil">Gönder</button>
      <button class="ikincil">İptal</button>
      <span class="ipucu">Göndermeden önce düzenleyebilirsin · Ctrl+Enter</span>
    </div>`;

  const alan = el.querySelector('textarea');
  alan.value = d.detayli;
  const gonderD = el.querySelector('.birincil');
  const iptalD = el.querySelector('.ikincil');

  const kapat = () => el.remove();

  gonderD.onclick = async () => {
    gonderD.disabled = true;
    gonderD.textContent = 'Gönderiliyor…';
    try {
      const r = await api('/api/taslak/onayla', {
        method: 'POST',
        body: JSON.stringify({ taslak_id: d.taslak_id, detayli: alan.value }),
      });
      kapat();
      balonEkle('asistan', r.yanit, 'claude');
      seslendir(r.yanit);
      if (r.eylem_id) eylemIzle(r.eylem_id, r.proje);
    } catch (e) {
      gonderD.disabled = false;
      gonderD.textContent = 'Gönder';
      bildir(e.message, true);
    }
  };

  iptalD.onclick = async () => {
    try { await api(`/api/taslak/${d.taslak_id}/iptal`, { method: 'POST' }); }
    catch { /* yoksay */ }
    kapat();
    balonEkle('sistem', 'Görev iptal edildi, hiçbir şey gönderilmedi.');
  };

  alan.onkeydown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); gonderD.click(); }
    if (e.key === 'Escape') { e.preventDefault(); iptalD.click(); }
  };

  akis.appendChild(el);
  akis.scrollTop = akis.scrollHeight;
  alan.focus();
  alan.setSelectionRange(alan.value.length, alan.value.length);
}

async function gonder(metin, sesMi = false) {
  metin = (metin ?? $('#mesaj').value).trim();
  if (!metin) return;
  $('#mesaj').value = '';
  $('#mesaj').style.height = 'auto';
  balonEkle('kullanici', metin);
  $('#gonder').disabled = true;

  const bekle = balonEkle('sistem', 'görev hazırlanıyor…');
  try {
    const d = await api('/api/taslak', {
      method: 'POST',
      body: JSON.stringify({ metin, ses_mi: sesMi, proje_id: durum.secili }),
    });
    bekle.remove();

    if (d.tur === 'onay_bekliyor') {
      onayKutusu(d);
      seslendir(d.yanit);
    } else if (d.tur === 'gonderildi') {
      balonEkle('asistan', d.yanit, 'claude');
      seslendir(d.yanit);
      if (d.eylem_id) eylemIzle(d.eylem_id, d.proje);
    } else {
      balonEkle('asistan', d.yanit, 'yerel');
      seslendir(d.yanit);
    }
  } catch (e) {
    bekle.remove();
    balonEkle('sistem', 'Hata: ' + e.message);
    bildir(e.message, true);
  } finally {
    $('#gonder').disabled = false;
    $('#mesaj').focus();
  }
}

// ── çalışan eylemler ───────────────────────────────────────

function seritCiz() {
  const serit = $('#eylem-serit');
  serit.innerHTML = '';
  if (!durum.izlenen.size) { serit.classList.add('gizli'); return; }
  serit.classList.remove('gizli');
  for (const [eid, bilgi] of durum.izlenen) {
    const el = document.createElement('div');
    el.className = 'eylem';
    el.innerHTML = `<span class="donen"></span>
      <span class="yazi">${bilgi.proje || 'proje'} · çalışıyor…</span>
      <button class="iptal">iptal</button>`;
    el.querySelector('.iptal').onclick = async () => {
      await api(`/api/eylem/${eid}/iptal`, { method: 'POST' });
      durum.izlenen.delete(eid);
      seritCiz();
    };
    serit.appendChild(el);
  }
}

function eylemIzle(eid, proje) {
  durum.izlenen.set(eid, { proje });
  seritCiz();

  const tik = async () => {
    let d;
    try { d = await api(`/api/eylem/${eid}`); }
    catch { durum.izlenen.delete(eid); seritCiz(); return; }

    if (d.durum === 'calisiyor') { setTimeout(tik, 2500); return; }

    durum.izlenen.delete(eid);
    seritCiz();
    projeleriYukle();
    maliyetiYenile();

    if (d.durum === 'tamam') {
      const metin = d.cikti?.trim() || 'İş bitti ama bir çıktı dönmedi.';
      balonEkle('asistan', `${d.proje_ad}: ${metin}`, 'claude');
      seslendir(`${d.proje_ad} projesindeki iş bitti. ${metin}`);
    } else if (d.durum === 'iptal') {
      balonEkle('sistem', `${d.proje_ad}: iptal edildi.`);
    } else {
      balonEkle('sistem', `${d.proje_ad}: hata — ${d.hata || 'bilinmeyen'}`);
      bildir('Komut hata verdi', true);
    }
  };
  setTimeout(tik, 2500);
}

// ── ses kaydı ──────────────────────────────────────────────

let kaydedici = null;
let parcalar = [];

async function kaydaBasla() {
  if (durum.kayitta) return;
  try {
    const akis = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    kaydedici = new MediaRecorder(akis);
    parcalar = [];
    kaydedici.ondataavailable = (e) => e.data.size && parcalar.push(e.data);
    kaydedici.onstop = async () => {
      akis.getTracks().forEach((t) => t.stop());
      const blob = new Blob(parcalar, { type: 'audio/webm' });
      if (blob.size < 1200) { bildir('Kayıt çok kısa'); return; }
      $('#mikrofon').classList.add('isliyor');
      try {
        const fd = new FormData();
        fd.append('ses', blob, 'kayit.webm');
        const d = await api('/api/stt', { method: 'POST', body: fd });
        if (d.metin) gonder(d.metin, true);
        else bildir('Ses anlaşılamadı');
      } catch (e) {
        bildir('Konuşma tanıma hatası: ' + e.message, true);
      } finally {
        $('#mikrofon').classList.remove('isliyor');
      }
    };
    kaydedici.start();
    durum.kayitta = true;
    $('#mikrofon').classList.add('kayitta');
  } catch {
    bildir('Mikrofona erişilemedi. Tarayıcı iznini kontrol et.', true);
  }
}

function kaydiBitir() {
  if (!durum.kayitta) return;
  durum.kayitta = false;
  $('#mikrofon').classList.remove('kayitta');
  try { kaydedici?.stop(); } catch { /* yoksay */ }
}

// ── ayarlar ────────────────────────────────────────────────

const AYAR_TANIM = [
  ['sohbet_modeli', 'Sohbet modeli (yerel)',
   'Günlük konuşma ve tavsiye. Ücretsiz, bu bilgisayarda çalışır.', 'ollama_modelleri'],
  ['komut_modeli', 'Komut modeli (Claude)',
   'Projelerde iş yapan model. Claude Max aboneliğin üzerinden çalışır, ' +
   'ayrı API ücreti çıkmaz.', 'claude_modelleri'],
  ['akil_modeli', 'Akıl yürütme modeli (Claude)',
   'Ağır düşünme isteyen sorular için. Yine abonelik üzerinden.',
   'claude_modelleri'],
  ['stt_modeli', 'Konuşma tanıma modeli',
   'Büyük model daha isabetli, biraz daha yavaş.', 'stt_modelleri'],
  ['izin_kipi', 'Claude yetkisi',
   'acceptEdits: dosya yazar, kabuk komutları için izin ister (varsayılan). ' +
   'bypassPermissions: kabuk komutlarını da sormadan çalıştırır — tam yetki, ' +
   'testleri/derlemeyi de yapabilir. manual: hiçbir şey yapamaz, sadece okur.',
   'izin_kipleri'],
];

// Sayı ile girilen ayarlar
const SAYI_AYAR = [
  ['gunluk_limit', 'Günlük kullanım sınırı',
   'Claude Max aboneliğin olduğu için bu bir fatura değil; kaçak bir döngünün ' +
   'abonelik kotanı tüketmesine karşı emniyet freni. Aşılınca komut gönderilmez. ' +
   '0 = sınırsız.',
   { min: 0, step: 0.5 }],
  ['komut_azami_tur', 'Komut başına azami tur',
   'Claude bir komutta en fazla kaç adım atsın. Düşük değer maliyeti azaltır, karmaşık işleri yarıda kesebilir.',
   { min: 1, step: 1 }],
];

async function ayarlariYukle() {
  const d = await api('/api/ayarlar');
  durum.ayarlar = d.ayarlar;
  $('#sesli-yanit').checked = d.ayarlar.sesli_yanit === '1';

  const govde = $('#ayar-govde');
  govde.innerHTML = '';
  for (const [anahtar, baslik, aciklama, kaynak] of AYAR_TANIM) {
    const secenekler = d[kaynak] || [];
    const satir = document.createElement('div');
    satir.className = 'ayar-satir';
    satir.innerHTML = `<label>${baslik}</label>
      <div class="aciklama">${aciklama}</div>
      <select data-anahtar="${anahtar}">
        ${secenekler.map((s) =>
          `<option value="${s}"${s === d.ayarlar[anahtar] ? ' selected' : ''}>${s}</option>`
        ).join('')}
      </select>`;
    satir.querySelector('select').onchange = async (e) => {
      await api('/api/ayarlar', {
        method: 'POST',
        body: JSON.stringify({ anahtar, deger: e.target.value }),
      });
      bildir('Kaydedildi');
    };
    govde.appendChild(satir);
  }

  for (const [anahtar, baslik, aciklama, ozellik] of SAYI_AYAR) {
    const satir = document.createElement('div');
    satir.className = 'ayar-satir';
    satir.innerHTML = `<label>${baslik}</label>
      <div class="aciklama">${aciklama}</div>
      <input type="number" min="${ozellik.min}" step="${ozellik.step}"
             value="${d.ayarlar[anahtar] ?? ''}" />`;
    const alan = satir.querySelector('input');
    alan.onchange = async () => {
      await api('/api/ayarlar', {
        method: 'POST',
        body: JSON.stringify({ anahtar, deger: alan.value }),
      });
      bildir('Kaydedildi');
      maliyetiYenile();
    };
    govde.appendChild(satir);
  }

  if (d.limit) {
    const bilgi = document.createElement('div');
    bilgi.className = 'aciklama';
    bilgi.style.marginTop = '4px';
    bilgi.textContent = d.limit.limit
      ? `Son 24 saatte ${d.limit.harcanan.toFixed(2)} birim kullanıldı, ` +
        `${d.limit.kalan.toFixed(2)} kaldı.`
      : 'Kullanım sınırı kapalı.';
    govde.appendChild(bilgi);
  }
}

async function maliyetiYenile() {
  try {
    const d = await api('/api/saglik');
    $('#saglik-nokta').className = 'nokta ' + (d.ollama ? 'iyi' : 'kotu');
    $('#saglik-nokta').title = d.ollama ? 'Ollama çalışıyor' : 'Ollama kapalı';
    durum.otomatik = d.otomatik?.acik_projeler || [];
    const m = d.maliyet;
    const el = $('#maliyet');
    el.title = 'Abonelik kullanımı (liste fiyatı karşılığı). ' +
               'Claude Max ile faturaya dönüşmez.';
    el.textContent = m.toplam
      ? `bugün ${m.son_24s.toFixed(2)} birim`
      : '';
    if (d.limit?.asildi) {
      el.textContent += '  (sınır doldu)';
      el.style.color = 'var(--kirmizi)';
    } else {
      el.style.color = '';
    }
  } catch { /* yoksay */ }
}

// ── olay bağlama ───────────────────────────────────────────

$('#gonder').onclick = () => gonder();
$('#tara').onclick = async () => {
  bildir('Projeler taranıyor…');
  await projeleriYukle(true);
  bildir('Tarama bitti');
};
$('#proje-ara').oninput = projeleriCiz;
$('#temizle').onclick = async () => {
  await api('/api/sohbet/temizle', { method: 'POST' });
  mesajlariYukle();
};
$('#sesli-yanit').onchange = (e) =>
  api('/api/ayarlar', {
    method: 'POST',
    body: JSON.stringify({ anahtar: 'sesli_yanit', deger: e.target.checked ? '1' : '0' }),
  });

$('#ozetle').onclick = async () => {
  const n = durum.projeler.filter((p) => p.var_mi).length;
  if (!confirm(
        `${n} projenin her birine ASISTAN-OZET.md yazdırılacak.

` +
        `Sırayla gider, proje başına yaklaşık yarım ila iki birim tüketir. ` +
        `Günlük sınır dolarsa kalanlar atlanır.

Başlansın mı?`)) return;
  try {
    const d = await api('/api/toplu/ozet', {
      method: 'POST', body: JSON.stringify({}),
    });
    balonEkle('sistem', `${d.proje_sayisi} projede özet güncellemesi başladı.`);
    topluIzle();
  } catch (e) { bildir(e.message, true); }
};

function topluIzle() {
  const tik = async () => {
    let d;
    try { d = await api('/api/toplu'); } catch { return; }
    if (d.calisiyor) {
      const serit = $('#eylem-serit');
      serit.classList.remove('gizli');
      let el = serit.querySelector('.toplu');
      if (!el) {
        el = document.createElement('div');
        el.className = 'eylem toplu';
        el.innerHTML = `<span class="donen"></span><span class="yazi"></span>
                        <button class="iptal">durdur</button>`;
        el.querySelector('.iptal').onclick = () =>
          api('/api/toplu/durdur', { method: 'POST' }).catch(() => {});
        serit.appendChild(el);
      }
      el.querySelector('.yazi').textContent =
        `${d.etiket}: ${d.sira}/${d.toplam} · ${d.suanki || ''}`;
      setTimeout(tik, 3000);
      return;
    }
    $('#eylem-serit').querySelector('.toplu')?.remove();
    if (!$('#eylem-serit').children.length) $('#eylem-serit').classList.add('gizli');
    if (d.bitti) {
      bildir(`Toplu iş bitti: ${d.tamam} tamam, ${d.hata} hata, ${d.atlanan} atlandı`);
      mesajlariYukle();
      maliyetiYenile();
    }
  };
  setTimeout(tik, 1500);
}

$('#rapor').onclick = async () => {
  try {
    const d = await api('/api/rapor' + (durum.secili ? `?proje_id=${durum.secili}` : ''));
    balonEkle('asistan', d.metin, 'yerel');
    seslendir(d.metin);
  } catch (e) { bildir(e.message, true); }
};

$('#brifing-ac').onclick = async () => {
  const kutu = $('#brifing-kutu');
  if (!kutu.classList.contains('gizli')) { kutu.classList.add('gizli'); return; }
  try {
    const d = await api(`/api/projeler/${durum.secili}/brifing`);
    kutu.textContent = d.brifing || 'Brifing çıkarılamadı.';
    kutu.classList.remove('gizli');
  } catch (e) { bildir(e.message, true); }
};

$('#brifing-derin').onclick = async () => {
  if (!durum.secili) return;
  try {
    const d = await api(`/api/projeler/${durum.secili}/brifing/derin`, { method: 'POST' });
    balonEkle('sistem', `${d.proje}: derin inceleme başlatıldı, Claude projeyi okuyor…`);
    eylemIzle(d.eylem_id, d.proje);
  } catch (e) { bildir(e.message, true); }
};

$('#oto-anahtar').onchange = async (e) => {
  if (!durum.secili) return;
  const acik = e.target.checked;
  try {
    await api(`/api/projeler/${durum.secili}/otomatik`, {
      method: 'POST',
      body: JSON.stringify({ acik, aralik: 900, azami: 8 }),
    });
    bildir(acik ? 'Otomatik devam açıldı' : 'Otomatik devam kapatıldı');
    await maliyetiYenile();
    projeSec(durum.secili);
    if (acik) {
      balonEkle('sistem',
        'Otomatik devam açık. Her 15 dakikada bir sıradaki adımı belirleyip ' +
        'çalıştıracağım; üst üste en fazla 8 tur sonra kendini kapatır.');
    }
  } catch (err) {
    e.target.checked = !acik;
    bildir(err.message, true);
  }
};

$('#ayarlar-ac').onclick = () => $('#ayar-katman').classList.remove('gizli');
$('#ayarlar-kapat').onclick = () => $('#ayar-katman').classList.add('gizli');
$('#ayar-katman').onclick = (e) => {
  if (e.target.id === 'ayar-katman') $('#ayar-katman').classList.add('gizli');
};

const mesajAlan = $('#mesaj');
mesajAlan.oninput = () => {
  mesajAlan.style.height = 'auto';
  mesajAlan.style.height = Math.min(mesajAlan.scrollHeight, 160) + 'px';
};
mesajAlan.onkeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); gonder(); }
};

// Mikrofon: basılı tut
const mik = $('#mikrofon');
mik.onmousedown = kaydaBasla;
mik.onmouseup = kaydiBitir;
mik.onmouseleave = () => durum.kayitta && kaydiBitir();
mik.ontouchstart = (e) => { e.preventDefault(); kaydaBasla(); };
mik.ontouchend = (e) => { e.preventDefault(); kaydiBitir(); };

// Boşluk tuşu: yazı alanı dışındayken bas-konuş
document.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && !e.repeat &&
      document.activeElement !== mesajAlan &&
      !$('#ayar-katman').matches(':not(.gizli)')) {
    e.preventDefault();
    kaydaBasla();
  }
  if (e.key === 'Escape') $('#ayar-katman').classList.add('gizli');
});
document.addEventListener('keyup', (e) => {
  if (e.code === 'Space' && durum.kayitta) { e.preventDefault(); kaydiBitir(); }
});

// ── canlı akış ─────────────────────────────────────────────
// Uzun yoklama. Telefondan ya da otomatik kipten gelen her değişiklik
// buradan düşer; iki taraf da aynı sunucu durumunu gösterir.

let sonOlayId = 0;
let akisDurdu = false;

async function akisDongusu() {
  while (!akisDurdu) {
    try {
      const d = await api(`/api/olaylar?since=${sonOlayId}`);
      if (d.sifirla) { sonOlayId = d.son_id; await tamYenile(); continue; }
      sonOlayId = d.son_id;
      if (d.olaylar?.length) await olaylariIsle(d.olaylar);
    } catch (e) {
      if (e.message === 'parola gerekli') return;
      await new Promise((r) => setTimeout(r, 4000));   // ağ koptu, bekle
    }
  }
}

async function tamYenile() {
  await mesajlariYukle();
  await projeleriYukle();
  await maliyetiYenile();
}

async function olaylariIsle(olaylar) {
  let mesajDegisti = false, projeDegisti = false;
  for (const o of olaylar) {
    if (o.tur === 'mesaj' || o.tur === 'sohbet_temizlendi') mesajDegisti = true;
    if (o.tur === 'eylem') {
      projeDegisti = true;
      if (o.durum && o.durum !== 'calisiyor') mesajDegisti = true;
    }
    if (o.tur === 'taslak' && o.durum === 'bekliyor') {
      // Telefondan gelen taslak burada da onaya çıksın
      try {
        const { taslaklar } = await api('/api/taslaklar');
        const t = taslaklar.find((x) => x.id === o.taslak_id);
        if (t && !document.querySelector(`.onay[data-id="${t.id}"]`)) {
          onayKutusu({ taslak_id: t.id, proje: t.proje_ad, proje_id: t.proje_id,
                       ham: t.ham, detayli: t.detayli });
        }
      } catch { /* yoksay */ }
    }
    if (o.tur === 'taslak' && o.durum !== 'bekliyor') {
      document.querySelector(`.onay[data-id="${o.taslak_id}"]`)?.remove();
    }
    if (o.tur === 'otomatik') projeDegisti = true;
    if (o.tur === 'toplu') topluIzle();
  }
  if (mesajDegisti) await mesajlariYukle();
  if (projeDegisti) { await projeleriYukle(); await maliyetiYenile(); }
}

// ── mobil menü ─────────────────────────────────────────────

function menuAc(ac) {
  const yan = $('#yan');
  yan.classList.toggle('acik', ac);
  let perde = $('#perde');
  if (ac && !perde) {
    perde = document.createElement('div');
    perde.id = 'perde';
    perde.onclick = () => menuAc(false);
    document.body.appendChild(perde);
  } else if (!ac && perde) {
    perde.remove();
  }
}

$('#menu').onclick = () => menuAc(!$('#yan').classList.contains('acik'));

// Projeye dokununca mobilde paneli kapat
$('#proje-liste').addEventListener('click', () => {
  if (window.innerWidth <= 820) menuAc(false);
});

$('#giris-dugme').onclick = girisYap;
$('#giris-parola').onkeydown = (e) => { if (e.key === 'Enter') girisYap(); };

// Servis çalışanı — ana ekrana eklenebilmesi için
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

// ── başlat ─────────────────────────────────────────────────

async function baslat() {
  try {
    await ayarlariYukle();
    await projeleriYukle();
    await mesajlariYukle();
    await maliyetiYenile();
    topluIzle();
    sonOlayId = (await api('/api/olaylar?since=-1')).son_id;
    akisDongusu();
    const { taslaklar } = await api('/api/taslaklar');
    taslaklar.forEach((t) => onayKutusu({
      taslak_id: t.id, proje: t.proje_ad, proje_id: t.proje_id,
      ham: t.ham, detayli: t.detayli,
    }));
    setInterval(maliyetiYenile, 30000);
  } catch (e) {
    if (e.message !== 'parola gerekli') bildir('Başlatma hatası: ' + e.message, true);
  }
}

baslat();
