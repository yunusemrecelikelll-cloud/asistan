import NovaPaylasilan
import SwiftUI

// NOVA küresi — masaüstündeki `frontend/gorsel.js` ile AYNI algoritma.
//
// Önceki telefon sürümü aynı fikri taklit etmeye çalışıyordu ama yapısı
// bambaşkaydı: 22 enlem halkası, düz elips perspektifi, tek bir mor→altın
// tonu. Sonuç küre değil, üst üste binmiş elipslerdi; masaüstündekinden
// gözle görülür biçimde farklıydı.
//
// Buradaki sürüm masaüstünün yaptığını yapıyor:
//   • Küre yüzeyi değil, küreyi saran rastgele yönlü BÜYÜK ÇEMBERLER.
//     Her çember bir demet (birbirine yakın 3-5 iplikçik) hâlinde.
//   • Gerçek 3B döndürme + derinlik. Arkadaki iplikler sönük, öndekiler
//     parlak — hacim hissi buradan geliyor, elips basıklığından değil.
//   • Yedi renkli palet boyunca kayan renk; eğri kendi üzerinde de renk
//     değiştiriyor.
//   • Toplamsal karıştırma (.plusLighter): iplikler üst üste bindiğinde
//     beyaza patlıyor. Neon hissinin asıl kaynağı bu — tek geçişli düz
//     çizgi ne kadar parlak olursa olsun bunu vermiyor.
//   • Hâle, toz zerreleri, çekirdek parıltısı.
//
// Davranış kuralları değişmedi:
//   • Beklerken YALNIZCA döner. Şekil bozulması yok.
//   • Dinlerken hafif kıpırdar.
//   • Konuşurken dağılır; tutamlar savrulur, şiddet sese bağlı.
//
// Telefon bütçesi: masaüstü 90 şerit çiziyor, burada 13 demet var ve kare
// 30 fps'e sabitlendi. Ekran saatlerce açık kalabildiği için pil, birkaç
// iplikçikten daha önemli.

// MARK: - Palet

/// Referanstaki yelpaze. Macenta/pembe ve altın baskın, camgöbeği
/// tamamlayıcı, yeşil yalnızca vurgu — eşit ağırlıklı palet mavi-yeşil
/// bir küre veriyor.
private let novaRenkler: [SIMD3<Double>] = [
    SIMD3(255,  60, 200),   // macenta
    SIMD3(255, 120, 235),   // pembe
    SIMD3(120, 235, 255),   // camgöbeği
    SIMD3(255, 175,  70),   // altın
    SIMD3(255,  90, 190),   // macenta (ağırlık için tekrar)
    SIMD3( 90, 255, 165),   // yeşil (vurgu)
    SIMD3(170, 110, 255),   // mor
]

private func renkKaristir(_ t: Double) -> SIMD3<Double> {
    let n = novaRenkler.count
    var p = t.truncatingRemainder(dividingBy: 1)
    if p < 0 { p += 1 }
    p *= Double(n)
    let i = Int(p)
    let k = p - Double(i)
    let a = novaRenkler[i % n]
    let b = novaRenkler[(i + 1) % n]
    return a + (b - a) * k
}

private func renk(_ c: SIMD3<Double>, _ alfa: Double) -> Color {
    Color(.sRGB, red: c.x / 255, green: c.y / 255, blue: c.z / 255,
          opacity: alfa)
}

// MARK: - Gürültü ve vektörler

private func rastgele(_ tohum: Double) -> Double {
    let s = sin(tohum * 127.1) * 43758.5453
    return s - s.rounded(.down)
}

/// Beşinci derece yumuşatmalı değer gürültüsü. Kübik yumuşatmada dönüş
/// noktalarında hafif kırılma görünüyor ve su akışında göze batıyor.
private func gurultu(_ x: Double, _ tohum: Double) -> Double {
    let x0 = x.rounded(.down)
    let f = x - x0
    let u = f * f * f * (f * (f * 6 - 15) + 10)
    let a = rastgele(x0 + tohum * 31.7)
    let b = rastgele(x0 + 1 + tohum * 31.7)
    return a + (b - a) * u
}

/// İki oktav — hem büyük hem küçük dalga, su yüzeyi gibi.
private func akiskan(_ x: Double, _ tohum: Double) -> Double {
    gurultu(x, tohum) * 0.68 + gurultu(x * 2.3 + 11.3, tohum + 5) * 0.32
}

private func yon(_ t1: Double, _ t2: Double) -> SIMD3<Double> {
    let z = rastgele(t1) * 2 - 1
    let a = rastgele(t2) * 2 * .pi
    let r = max(0, 1 - z * z).squareRoot()
    return SIMD3(r * cos(a), r * sin(a), z)
}

private func capraz(_ a: SIMD3<Double>, _ b: SIMD3<Double>) -> SIMD3<Double> {
    SIMD3(a.y * b.z - a.z * b.y,
          a.z * b.x - a.x * b.z,
          a.x * b.y - a.y * b.x)
}

private func normalle(_ v: SIMD3<Double>) -> SIMD3<Double> {
    let u = (v.x * v.x + v.y * v.y + v.z * v.z).squareRoot()
    return u < 1e-9 ? SIMD3(0, 1, 0) : v / u
}

// MARK: - Sabit geometri

/// Bir iplikçik demeti: küre üzerinde rastgele yönlendirilmiş büyük çember.
private struct Serit {
    let u: SIMD3<Double>          // çemberin düzlemindeki iki eksen
    let v: SIMD3<Double>
    let eksen: SIMD3<Double>      // düzlemin normali
    let enlem: Double
    let halkaR: Double
    let renk: Double
    let renkHiz: Double
    let iplik: Int
    let aralik: Double
    let hiz: Double
    let dalga: Double
    let tutam: Bool               // konuşurken savrulan tutam mı
    let tutamAci: Double
    let kalinlik: Double
}

private struct Toz {
    let konum: SIMD3<Double>
    let boyut: Double
    let faz: Double
    let renk: Double
}

/// Tohumlu üretim: her açılışta aynı küre çıkıyor ve `static` olduğu için
/// SwiftUI görünümü yeniden kurduğunda baştan hesaplanmıyor.
private enum Geometri {

    static let seritler: [Serit] = {
        let demet = 13
        return (0..<demet).map { i in
            let f = Double(i)
            let u = normalle(yon(f + 0.3, f + 7.1))
            let v = normalle(capraz(u, yon(f + 13.7, f + 21.3)))
            let eksen = normalle(capraz(u, v))
            let enlem = rastgele(f + 29.1) * 1.5 - 0.75
            return Serit(
                u: u, v: v, eksen: eksen, enlem: enlem,
                halkaR: max(0.05, 1 - enlem * enlem).squareRoot(),
                // Renkleri palete EŞİT dağıt: rastgele bırakınca hepsi
                // yelpazenin aynı bölgesine düşüyor.
                renk: (f / Double(demet) + rastgele(f + 11.1) * 0.08)
                    .truncatingRemainder(dividingBy: 1),
                renkHiz: 0.10 + rastgele(f + 43.9) * 0.25,
                iplik: 3 + Int(rastgele(f + 31.7) * 3),
                aralik: 0.010 + rastgele(f + 37.1) * 0.020,
                hiz: 0.20 + rastgele(f + 5.5) * 0.45,
                dalga: 0.05 + rastgele(f + 9.9) * 0.13,
                tutam: rastgele(f + 17.4) < 0.45,
                tutamAci: rastgele(f + 19.2) * 2 * .pi,
                kalinlik: 0.35 + rastgele(f + 23.6) * 0.5)
        }
    }()

    static let tozlar: [Toz] = (0..<48).map { i in
        let f = Double(i)
        return Toz(konum: SIMD3(rastgele(f + 41.1) * 2 - 1,
                                rastgele(f + 43.3) * 2 - 1,
                                rastgele(f + 47.7) * 2 - 1),
                   boyut: 0.4 + rastgele(f + 51.9) * 1.5,
                   faz: rastgele(f + 53.1) * 2 * .pi,
                   renk: rastgele(f + 59.3))
    }
}

// MARK: - Görünüm

struct KureGorunumu: View {

    let hal: Oturum.Hâl
    let enerji: Float

    /// Canlılık 0…1. 0 = kusursuz küre, yalnızca dönüyor. 1 = dağılmış.
    @State private var canlilik: Double = 0
    /// Sesin yumuşatılmış hâli. Yükselirken hızlı, düşerken yavaş —
    /// konuşma böyle hissettiriyor.
    @State private var ses: Double = 0
    /// Akış ve dönüş ayrı saatler: ses kesilince akış durur, dönüş sürer.
    @State private var akis: Double = 0
    @State private var donus: Double = 0
    @State private var sonKare: Date?

    /// Sessizken bile hafif bir nefes: donmuş bir küre ölü görünüyor.
    private var hedefSes: Double {
        let taban: Double = hal == .dusunuyor ? 0.22 : 0.07
        return max(taban, min(1, Double(enerji)))
    }

    private var hedefCanlilik: Double {
        switch hal {
        case .konusuyor: min(1.0, 0.45 + ses * 0.7)
        case .dinliyor: min(0.6, 0.08 + ses * 0.5)
        case .dusunuyor: 0.20
        case .bekliyor: 0
        }
    }

    var body: some View {
        // 30 fps: ekran saatlerce açık kalabiliyor, 60 fps'in gözle farkı
        // bu görüntüde yok ama pilde var.
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: false)) { zaman in
            Canvas(opaque: true, rendersAsynchronously: false) { ciz, boy in
                ciz.fill(Path(CGRect(origin: .zero, size: boy)),
                         with: .color(.black))

                let merkez = CGPoint(x: boy.width / 2, y: boy.height / 2)
                // Tutamlar açıldığında ekrandan taşmasın diye yarıçap kısık.
                let R = min(boy.width, boy.height) * 0.29

                hale(&ciz, boy: boy, merkez: merkez, R: R)

                // Toplamsal karıştırma: üst üste binen iplikler beyaza
                // patlıyor. Neon hissi buradan geliyor.
                ciz.blendMode = .plusLighter
                tozCiz(&ciz, merkez: merkez, R: R)
                seritCiz(&ciz, merkez: merkez, R: R)
                cekirdek(&ciz, merkez: merkez, R: R)
            }
            .onChange(of: zaman.date) { _, yeni in
                ilerlet(yeni)
            }
        }
        .background(.black)
    }

    // MARK: - Zaman

    /// Kare süresine göre ilerlet. Sabit kare artışı yerine gerçek geçen
    /// süre: 30 fps'e düşen bir cihazda küre yavaşlamasın.
    private func ilerlet(_ simdi: Date) {
        let onceki = sonKare ?? simdi.addingTimeInterval(-1.0 / 30)
        // Üst sınır: uygulama arka plandan dönünce tek karede saatler
        // ilerlemesin, küre sıçramasın.
        let dt = min(0.05, max(0.001, simdi.timeIntervalSince(onceki)))
        sonKare = simdi

        func yaklas(_ simdiki: Double, _ hedef: Double, _ k: Double) -> Double {
            // Kare hızından bağımsız yaklaşma.
            simdiki + (hedef - simdiki) * (1 - pow(1 - k, dt * 60))
        }

        ses = yaklas(ses, hedefSes, hedefSes > ses ? 0.32 : 0.06)
        let hc = hedefCanlilik
        canlilik = yaklas(canlilik, hc, hc > canlilik ? 0.10 : 0.035)

        akis += (0.13 + canlilik * 0.96) * dt
        donus += (0.19 + ses * 0.24) * dt
    }

    /// Küreyi döndür — derinlik hissi buradan geliyor.
    private func dondur(_ p: SIMD3<Double>) -> SIMD3<Double> {
        let a = donus * 0.75                     // Y ekseni
        let b = sin(donus * 0.34) * 0.38         // hafif X salınımı
        let ca = cos(a), sa = sin(a)
        let x1 = p.x * ca + p.z * sa
        let z1 = -p.x * sa + p.z * ca
        let cb = cos(b), sb = sin(b)
        return SIMD3(x1, p.y * cb - z1 * sb, p.y * sb + z1 * cb)
    }

    // MARK: - Katmanlar

    private func hale(_ ciz: inout GraphicsContext, boy: CGSize,
                      merkez: CGPoint, R: CGFloat) {
        let c = renkKaristir(akis * 0.04)
        ciz.fill(
            Path(CGRect(origin: .zero, size: boy)),
            with: .radialGradient(
                Gradient(stops: [
                    .init(color: renk(c, 0.14 + ses * 0.18), location: 0),
                    .init(color: renk(c, 0.03), location: 0.5),
                    .init(color: .clear, location: 1),
                ]),
                center: merkez,
                startRadius: R * 0.3,
                endRadius: R * 3.2))
    }

    private func tozCiz(_ ciz: inout GraphicsContext, merkez: CGPoint,
                        R: CGFloat) {
        for t in Geometri.tozlar {
            let p = dondur(t.konum)
            let nefes = 1.35 + sin(akis * 1.3 + t.faz) * 0.12 + ses * 0.5
            let x = merkez.x + p.x * R * nefes
            let y = merkez.y + p.y * R * nefes
            let on = (p.z + 1) / 2
            let c = renkKaristir(akis * 0.05 + t.renk)
            let r = t.boyut * (0.6 + on * 0.8)
            ciz.fill(Path(ellipseIn: CGRect(x: x - r, y: y - r,
                                            width: r * 2, height: r * 2)),
                     with: .color(renk(c, 0.06 + on * 0.22 + ses * 0.22)))
        }
    }

    private func seritCiz(_ ciz: inout GraphicsContext, merkez: CGPoint,
                          R: CGFloat) {
        let nokta = 56
        let parca = 3                 // eğri boyunca renk değişimi için
        let c = canlilik
        // Bütün bozulma canlılıkla çarpılıyor: boştayken tam olarak sıfır.
        let genlik = c * (0.10 + ses * 0.22)
        let parcaNokta = Int((Double(nokta) / Double(parca)).rounded(.up))

        for (si, s) in Geometri.seritler.enumerated() {
            for j in 0..<s.iplik {
                // İpliği demetin ortasından kaydır: enlem ve yarıçap
                // birlikte kayınca iplikler kürede paralel bir bant çiziyor.
                let k = Double(j) - Double(s.iplik - 1) / 2
                let enlem = s.enlem + k * s.aralik * 1.8
                let halkaR = max(0.04, 1 - enlem * enlem).squareRoot()
                let radKay = k * s.aralik * 0.5
                let tohum = Double(si * 100 + j)

                var nok = [CGPoint](); nok.reserveCapacity(nokta + 1)
                var onToplam = 0.0

                for i in 0...nokta {
                    let t = Double(i) / Double(nokta) * 2 * .pi
                    let gu = akiskan(t * 1.4 + akis * s.hiz, Double(si))
                    // Demetin tamamı aynı dalgayı izliyor, iplikler yalnızca
                    // hafifçe ayrışıyor — birlikte akmalarının sırrı bu.
                    let ince = akiskan(t * 2.8 + akis * s.hiz * 1.3, tohum)
                    var rad = 1 + radKay
                        + (gu - 0.5) * (s.dalga * c + genlik)
                        + (ince - 0.5) * 0.05 * c

                    // Savrulan tutamlar yalnızca konuşurken açılıyor.
                    if s.tutam && c > 0.05 {
                        let d = cos(t - s.tutamAci)
                        if d > 0.35 {
                            let kk = (d - 0.35) / 0.65
                            rad += kk * kk * c * (0.22 + ses * 0.48)
                                * (0.5 + Double(j) / Double(s.iplik))
                        }
                    }

                    let ct = cos(t) * halkaR, st = sin(t) * halkaR
                    let q = dondur(SIMD3(
                        (s.u.x * ct + s.v.x * st + s.eksen.x * enlem) * rad,
                        (s.u.y * ct + s.v.y * st + s.eksen.y * enlem) * rad,
                        (s.u.z * ct + s.v.z * st + s.eksen.z * enlem) * rad))
                    nok.append(CGPoint(x: merkez.x + q.x * R,
                                       y: merkez.y + q.y * R))
                    onToplam += (q.z + 1) / 2
                }
                let on = onToplam / Double(nokta + 1)
                let guc = 0.55 + ses * 0.65

                for b in 0..<parca {
                    let bas = b * parcaNokta
                    let bit = min(nokta, bas + parcaNokta)
                    if bit <= bas { continue }

                    var yol = Path()
                    yol.move(to: nok[bas])
                    for i in (bas + 1)...bit { yol.addLine(to: nok[i]) }

                    let ton = akis * 0.03 * s.renkHiz + s.renk
                        + Double(b) * 0.075 + Double(j) * 0.012
                    let taban = renkKaristir(ton)

                    // İki geçiş yetiyor: geniş renkli hâle + ince beyaza
                    // yakın çekirdek. Üçüncü ara geçiş kare süresini iki
                    // katına çıkarıyor ve gözle ayırt edilmiyor.
                    ciz.stroke(yol,
                               with: .color(renk(taban,
                                                 (0.030 + on * 0.070) * guc)),
                               style: StrokeStyle(lineWidth: s.kalinlik * 5.0,
                                                  lineCap: .round))
                    // Çekirdeği beyaza çek.
                    let cekirdekRenk = (taban + SIMD3(460, 460, 460)) / 2.9
                    ciz.stroke(yol,
                               with: .color(renk(cekirdekRenk,
                                                 (0.050 + on * 0.130) * guc)),
                               style: StrokeStyle(
                                   lineWidth: s.kalinlik * (0.30 + on * 0.45),
                                   lineCap: .round))
                }
            }
        }
    }

    private func cekirdek(_ ciz: inout GraphicsContext, merkez: CGPoint,
                          R: CGFloat) {
        let r = R * (0.55 + ses * 0.18)
        ciz.fill(
            Path(ellipseIn: CGRect(x: merkez.x - r, y: merkez.y - r,
                                   width: r * 2, height: r * 2)),
            with: .radialGradient(
                Gradient(stops: [
                    .init(color: .white.opacity(0.06 + ses * 0.10), location: 0),
                    .init(color: Color(.sRGB, red: 200 / 255, green: 230 / 255,
                                       blue: 1, opacity: 0.04),
                          location: 0.35),
                    .init(color: .clear, location: 1),
                ]),
                center: merkez, startRadius: 0, endRadius: r))
    }
}
