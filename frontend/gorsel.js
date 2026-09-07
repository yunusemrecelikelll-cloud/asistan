'use strict';

/* NOVA küresi — sesle canlanan ışık iplikçikleri.
 *
 * Referanstaki görüntü tek bir küre yüzeyi değil: bir küre hacmini saran
 * yüzlerce ince ışık şeridi. Parlaklık, şeritlerin üst üste binmesinden
 * doğuyor; yoğunlaştıkları yerde beyaza patlıyor. Tek bir kapalı eğri
 * çizmek bu dokuyu vermiyor, o yüzden iplikçik yaklaşımı.
 *
 * Yapı:
 *   • Her iplikçik, küre üzerinde rastgele yönlendirilmiş bir büyük çember.
 *   • Yarıçapı gürültüyle dalgalanıyor — şeritlerin akışkan görünmesi
 *     bundan.
 *   • Bazı iplikçikler küreden dışarı taşıyor: referanstaki savrulan
 *     tutamlar.
 *   • Toplamsal karıştırma (lighter) + iki geçişli çizim = parlama.
 *
 * WebGL yerine 2B tuval: iOS Safari'de WebGL bağlamı arka plana alınınca
 * kaybolup geri gelmiyor, telefonda saatlerce açık duracak bir ekran için
 * bu kabul edilemez.
 */

// Referanstaki yelpaze: camgöbeği, macenta, yeşil, altın.
// Referansın ağırlığı: macenta/pembe ve altın baskın, camgöbeği
// tamamlayıcı, yeşil yalnızca vurgu. Eşit ağırlıklı palet yeşil-mavi bir
// küre veriyordu.
const NOVA_RENKLER = [
  [255,  60, 200],   // macenta
  [255, 120, 235],   // pembe
  [120, 235, 255],   // camgöbeği
  [255, 175,  70],   // altın
  [255,  90, 190],   // macenta (ağırlık için tekrar)
  [ 90, 255, 165],   // yeşil (vurgu)
  [170, 110, 255],   // mor
];

function _renkKaristir(t) {
  const n = NOVA_RENKLER.length;
  const p = (((t % 1) + 1) % 1) * n;
  const i = Math.floor(p);
  const k = p - i;
  const a = NOVA_RENKLER[i % n];
  const b = NOVA_RENKLER[(i + 1) % n];
  return [
    (a[0] + (b[0] - a[0]) * k) | 0,
    (a[1] + (b[1] - a[1]) * k) | 0,
    (a[2] + (b[2] - a[2]) * k) | 0,
  ];
}

function _rastgele(tohum) {
  const s = Math.sin(tohum * 127.1) * 43758.5453;
  return s - Math.floor(s);
}

function _gurultu(x, tohum) {
  const x0 = Math.floor(x);
  const f = x - x0;
  // Beşinci derece yumuşatma: kübik yumuşatmada dönüş noktalarında hafif
  // kırılma görünüyordu, su akışında bu göze batıyor.
  const u = f * f * f * (f * (f * 6 - 15) + 10);
  const a = _rastgele(x0 + tohum * 31.7);
  const b = _rastgele(x0 + 1 + tohum * 31.7);
  return a + (b - a) * u;
}

/** İki oktavlı gürültü — su yüzeyi gibi hem büyük hem küçük dalga. */
function _akiskan(x, tohum) {
  return _gurultu(x, tohum) * 0.68 + _gurultu(x * 2.3 + 11.3, tohum + 5) * 0.32;
}

/** Birim küre üzerinde rastgele bir yön. */
function _yon(t1, t2) {
  const z = _rastgele(t1) * 2 - 1;
  const a = _rastgele(t2) * Math.PI * 2;
  const r = Math.sqrt(Math.max(0, 1 - z * z));
  return [r * Math.cos(a), r * Math.sin(a), z];
}

function _capraz(a, b) {
  return [a[1] * b[2] - a[2] * b[1],
          a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0]];
}

function _normalle(v) {
  const u = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / u, v[1] / u, v[2] / u];
}


class NovaKure {
  constructor(tuval, secenek = {}) {
    this.tuval = tuval;
    this.ctx = tuval.getContext('2d', { alpha: true });
    this.cozumleyici = null;
    this.veri = null;
    this.calisiyor = false;
    this.zaman = Math.random() * 100;
    this.enerji = 0;
    this.hedefEnerji = 0;
    this.canlilik = 0;      // 0 = kusursuz küre, 1 = tamamen dağılmış
    this.donus = 0;         // dönüş zamanı akıştan bağımsız işliyor
    this.durum = 'bekliyor';

    // Telefonda daha az iplikçik: 90 şerit × 80 nokta her karede ~7000
    // parça demek ve zayıf cihazlarda kare düşüyor.
    const dar = Math.min(window.innerWidth, window.innerHeight) < 700;
    this.serit = secenek.serit ?? (dar ? 55 : 90);
    this.nokta = secenek.nokta ?? (dar ? 64 : 88);

    this._noktalar = [];
    this._seritKur();
    this._tozKur(dar ? 60 : 110);
    this._boyutla();
    this._boyutIzle();
  }

  _seritKur() {
    // Referanstaki doku tek tel değil, DEMET: onlarca neredeyse paralel
    // iplikçik bir arada akıyor ve şerit (kurdele) izlenimi veriyor. Tek
    // tellerle çizince tel kafes gibi duruyordu.
    this.seritler = [];
    const demet = Math.max(16, Math.round(this.serit / 3.2));
    for (let i = 0; i < demet; i++) {
      const u = _normalle(_yon(i + 0.3, i + 7.1));
      let v = _normalle(_capraz(u, _yon(i + 13.7, i + 21.3)));
      if (!isFinite(v[0])) v = [0, 1, 0];
      const eksen = _normalle(_capraz(u, v));
      const enlem = _rastgele(i + 29.1) * 1.5 - 0.75;
      this.seritler.push({
        u, v, eksen, enlem,
        halkaR: Math.sqrt(Math.max(0.05, 1 - enlem * enlem)),
        renkHiz: 0.10 + _rastgele(i + 43.9) * 0.25,
        // Demetteki iplik sayısı: kalın şeritler ile ince tutamlar bir arada
        iplik: 4 + Math.floor(_rastgele(i + 31.7) * 5),
        aralik: 0.010 + _rastgele(i + 37.1) * 0.020,
        hiz: 0.20 + _rastgele(i + 5.5) * 0.45,
        dalga: 0.05 + _rastgele(i + 9.9) * 0.13,
        // Renkleri palete EŞİT dağıt: rastgele bırakınca hepsi
        // yelpazenin aynı bölgesine düşüp mavi-yeşil bir küre çıkıyordu.
        renk: (i / demet + _rastgele(i + 11.1) * 0.08) % 1,
        tutam: _rastgele(i + 17.4) < 0.45,
        tutamAci: _rastgele(i + 19.2) * Math.PI * 2,
        kalinlik: 0.35 + _rastgele(i + 23.6) * 0.5,
      });
    }
  }

  _tozKur(n) {
    this.toz = Array.from({ length: n }, (_, i) => ({
      x: _rastgele(i + 41.1) * 2 - 1,
      y: _rastgele(i + 43.3) * 2 - 1,
      z: _rastgele(i + 47.7) * 2 - 1,
      boyut: 0.4 + _rastgele(i + 51.9) * 1.5,
      faz: _rastgele(i + 53.1) * Math.PI * 2,
      renk: _rastgele(i + 59.3),
    }));
  }

  _boyutIzle() {
    const g = () => this._boyutla();
    window.addEventListener('resize', g);
    if (window.ResizeObserver) {
      this._gozlemci = new ResizeObserver(g);
      this._gozlemci.observe(this.tuval);
    }
  }

  _boyutla() {
    const oran = Math.min(window.devicePixelRatio || 1, 2);
    const k = this.tuval.getBoundingClientRect();
    if (!k.width || !k.height) return;
    this.tuval.width = Math.round(k.width * oran);
    this.tuval.height = Math.round(k.height * oran);
    this.ctx.setTransform(oran, 0, 0, oran, 0, 0);
    this.g = k.width;
    this.y = k.height;
  }

  bagla(cozumleyici) {
    this.cozumleyici = cozumleyici;
    this.veri = cozumleyici
      ? new Uint8Array(cozumleyici.frequencyBinCount) : null;
  }

  durumaGec(durum) { this.durum = durum; }

  basla() {
    if (this.calisiyor) return;
    this.calisiyor = true;
    const dongu = () => {
      if (!this.calisiyor) return;
      this._kare();
      this._istek = requestAnimationFrame(dongu);
    };
    dongu();
  }

  dur() {
    this.calisiyor = false;
    if (this._istek) cancelAnimationFrame(this._istek);
  }

  _sesOku() {
    if (!this.cozumleyici || !this.veri) {
      // Sessizken de hafif bir nefes: donmuş bir küre ölü görünüyor.
      this.hedefEnerji = this.durum === 'dusunuyor' ? 0.22 : 0.07;
      return this._bant || (this._bant = new Array(16).fill(0.1));
    }
    this.cozumleyici.getByteFrequencyData(this.veri);
    const bant = 16;
    const adim = Math.max(1, Math.floor(this.veri.length / bant / 2));
    const bantlar = [];
    let toplam = 0;
    for (let i = 0; i < bant; i++) {
      let s = 0;
      for (let j = 0; j < adim; j++) s += this.veri[i * adim + j] || 0;
      const d = (s / adim) / 255;
      bantlar.push(d);
      toplam += d;
    }
    this.hedefEnerji = Math.min(1, (toplam / bant) * 2.4);
    return bantlar;
  }

  /** Şeklin ne kadar bozulacağı. Boştayken sıfır: küre kusursuz yuvarlak
   *  kalsın ve yalnızca dönsün. Konuşurken tavan yapsın — dağılma hissi
   *  buradan geliyor. */
  _canlilikHedefi() {
    // Üst sınır 1: bunun ötesinde tutamlar ekrandan taşıyor ve küre
    // dağılmış değil, kaybolmuş görünüyor.
    if (this.durum === 'konusuyor') return Math.min(1, 0.45 + this.enerji * 0.7);
    if (this.durum === 'dinliyor') return Math.min(0.6, 0.08 + this.enerji * 0.5);
    if (this.durum === 'dusunuyor') return 0.20;
    return 0;                       // bekliyor: sadece dönüş
  }

  _kare() {
    const { ctx } = this;
    if (!this.g || !this.y) { this._boyutla(); return; }

    const bantlar = this._sesOku();
    // Yükselirken hızlı, düşerken yavaş: konuşma böyle hissettiriyor.
    const k = this.hedefEnerji > this.enerji ? 0.32 : 0.06;
    this.enerji += (this.hedefEnerji - this.enerji) * k;
    // Canlılık yavaş değişsin: ani geçiş suyu değil, elektriği andırıyor.
    const hc = this._canlilikHedefi();
    this.canlilik += (hc - this.canlilik) * (hc > this.canlilik ? 0.10 : 0.035);
    // Akış zamanı canlılıkla hızlanıyor; dönüş zamanı sabit tempoda.
    this.zaman += 0.0022 + this.canlilik * 0.016;
    this.donus += 0.0032 + this.enerji * 0.004;

    // Referansta zemin saf siyah; koyu lacivert üstünde neon sönük
    // duruyor.
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, this.g, this.y);
    const mx = this.g / 2, my = this.y / 2;
    // Tutamlar açıldığında taşmasın diye yarıçapı biraz kısıyoruz.
    const R = Math.min(this.g, this.y) * 0.29;

    this._halo(mx, my, R);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    this._tozCiz(mx, my, R);
    this._seritCiz(mx, my, R, bantlar);
    this._cekirdek(mx, my, R);
    ctx.restore();
  }

  _halo(mx, my, R) {
    const { ctx } = this;
    const [r, g, b] = _renkKaristir(this.zaman * 0.04);
    const d = ctx.createRadialGradient(mx, my, R * 0.3, mx, my, R * 3.2);
    d.addColorStop(0, `rgba(${r},${g},${b},${0.14 + this.enerji * 0.18})`);
    d.addColorStop(0.5, `rgba(${r},${g},${b},0.03)`);
    d.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = d;
    ctx.fillRect(0, 0, this.g, this.y);
  }

  /** Küreyi yavaşça döndür — derinlik hissi buradan geliyor. */
  _dondur(p) {
    const a = this.donus * 0.75;                    // Y ekseni
    const b = Math.sin(this.donus * 0.34) * 0.38;   // hafif X salınımı
    const ca = Math.cos(a), sa = Math.sin(a);
    const x1 = p[0] * ca + p[2] * sa;
    const z1 = -p[0] * sa + p[2] * ca;
    const cb = Math.cos(b), sb = Math.sin(b);
    return [x1, p[1] * cb - z1 * sb, p[1] * sb + z1 * cb];
  }

  _seritCiz(mx, my, R, bantlar) {
    const { ctx } = this;
    const n = this.nokta;
    // Bütün bozulma canlılıkla çarpılıyor: boştayken tam olarak sıfır.
    const c = this.canlilik;
    const genlik = c * (0.10 + this.enerji * 0.22);
    const parca = 4;
    const parcaNokta = Math.ceil(n / parca);
    ctx.lineCap = 'round';

    for (let si = 0; si < this.seritler.length; si++) {
      const s = this.seritler[si];
      const bant = bantlar[si % bantlar.length] || 0;

      for (let j = 0; j < s.iplik; j++) {
        // İpliği demetin ortasından kaydır: enlem ve yarıçap birlikte
        // kayınca iplikler kürede paralel bir bant çiziyor.
        const k = (j - (s.iplik - 1) / 2);
        const enlem = s.enlem + k * s.aralik * 1.8;
        const halkaR = Math.sqrt(Math.max(0.04, 1 - enlem * enlem));
        const radKay = k * s.aralik * 0.5;
        const tohum = si * 100 + j;

        const p2 = [];
        let onToplam = 0;
        for (let i = 0; i <= n; i++) {
          const t = (i / n) * Math.PI * 2;
          const gu = _akiskan(t * 1.4 + this.zaman * s.hiz, si);
          // Demetin tamamı aynı dalgayı izliyor, iplikler yalnızca hafifçe
          // ayrışıyor — birlikte akmalarının sırrı bu.
          const ince = _akiskan(t * 2.8 + this.zaman * s.hiz * 1.3, tohum);
          let rad = 1 + radKay
            + (gu - 0.5) * (s.dalga * c + genlik)
            + (ince - 0.5) * 0.05 * c
            + bant * genlik * 0.9;

          // Savrulan tutamlar yalnızca konuşurken açılıyor; boştayken küre
          // toparlı kalsın.
          if (s.tutam && c > 0.05) {
            const d = Math.cos(t - s.tutamAci);
            if (d > 0.35) {
              const kk = (d - 0.35) / 0.65;
              rad += kk * kk * c * (0.22 + this.enerji * 0.48)
                     * (0.5 + j / s.iplik);
            }
          }

          const ct = Math.cos(t) * halkaR, st = Math.sin(t) * halkaR;
          const q = this._dondur([
            (s.u[0] * ct + s.v[0] * st + s.eksen[0] * enlem) * rad,
            (s.u[1] * ct + s.v[1] * st + s.eksen[1] * enlem) * rad,
            (s.u[2] * ct + s.v[2] * st + s.eksen[2] * enlem) * rad,
          ]);
          p2.push([mx + q[0] * R, my + q[1] * R, (q[2] + 1) / 2]);
          onToplam += p2[i][2];
        }
        const on = onToplam / (n + 1);

        // İki geçiş yetiyor: geniş renkli hâle + ince beyaz çekirdek.
        // Üçüncü ara geçiş kare süresini iki katına çıkarıyordu ve
        // gözle ayırt edilmiyordu.
        for (let gecis = 0; gecis < 2; gecis++) {
          for (let b = 0; b < parca; b++) {
            const bas2 = b * parcaNokta;
            const bit = Math.min(n, bas2 + parcaNokta);
            if (bit <= bas2) continue;
            let [cr, cg, cb] = _renkKaristir(
              this.zaman * 0.03 * s.renkHiz + s.renk + b * 0.075
              + j * 0.012);
            if (gecis === 1) {          // çekirdek: beyaza çek
              cr = (cr + 460) / 2.9 | 0; cg = (cg + 460) / 2.9 | 0;
              cb = (cb + 460) / 2.9 | 0;
            }
            ctx.beginPath();
            ctx.moveTo(p2[bas2][0], p2[bas2][1]);
            for (let i = bas2 + 1; i <= bit; i++) ctx.lineTo(p2[i][0], p2[i][1]);

            const g = 0.55 + this.enerji * 0.65;
            const alfa = gecis === 0 ? (0.030 + on * 0.070) * g
                                     : (0.050 + on * 0.130) * g;
            ctx.strokeStyle = `rgba(${cr},${cg},${cb},${alfa.toFixed(3)})`;
            ctx.lineWidth = gecis === 0 ? s.kalinlik * 5.0
                                        : s.kalinlik * (0.30 + on * 0.45);
            ctx.stroke();
          }
        }
      }
    }
  }

  _tozCiz(mx, my, R) {
    const { ctx } = this;
    for (const t of this.toz) {
      const p = this._dondur([t.x, t.y, t.z]);
      const nefes = 1.35 + Math.sin(this.zaman * 1.3 + t.faz) * 0.12
                    + this.enerji * 0.5;
      const x = mx + p[0] * R * nefes;
      const y = my + p[1] * R * nefes;
      const on = (p[2] + 1) / 2;
      const [r, g, b] = _renkKaristir(this.zaman * 0.05 + t.renk);
      ctx.fillStyle = `rgba(${r},${g},${b},${(0.06 + on * 0.22
        + this.enerji * 0.22).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(x, y, t.boyut * (0.6 + on * 0.8), 0, Math.PI * 2);
      ctx.fill();
    }
  }

  _cekirdek(mx, my, R) {
    const { ctx } = this;
    const r = R * (0.55 + this.enerji * 0.18);
    const d = ctx.createRadialGradient(mx, my, 0, mx, my, r);
    d.addColorStop(0, `rgba(255,255,255,${(0.06 + this.enerji * 0.10).toFixed(2)})`);
    d.addColorStop(0.35, 'rgba(200,230,255,0.04)');
    d.addColorStop(1, 'rgba(150,200,255,0)');
    ctx.fillStyle = d;
    ctx.beginPath();
    ctx.arc(mx, my, r, 0, Math.PI * 2);
    ctx.fill();
  }
}

window.NovaKure = NovaKure;
