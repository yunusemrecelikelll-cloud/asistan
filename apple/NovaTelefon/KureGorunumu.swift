import NovaPaylasilan
import SwiftUI

/// NOVA küresi — masaüstündeki `frontend/gorsel.js` ile aynı kurallar.
///
/// Davranış kuralları (kullanıcının istediği gibi):
///   • Beklerken YALNIZCA döner. Şekil bozulması yok, dağılma yok.
///   • Dinlerken hafif kıpırdar.
///   • Konuşurken ÇOK dağılır; hareket sesin şiddetine bağlı.
///   • Deformasyon su gibi akar — iki oktavlı gürültü, sert köşe yok.
///
/// Çizim iki geçişli: önce geniş renkli parıltı, sonra ince beyaza yakın
/// çekirdek. Neon hissi bu ikiliden geliyor; tek geçişle çizince sadece
/// "renkli çizgi" oluyor.
struct KureGorunumu: View {

    let hal: Oturum.Hâl
    let enerji: Float

    /// Canlılık 0…1. Hedefe yumuşak yaklaşıyor ki ses kesildiğinde küre
    /// aniden donmasın, suyun durulması gibi yavaşça toplansın.
    @State private var canlilik: Double = 0

    private var hedefCanlilik: Double {
        switch hal {
        case .konusuyor: min(1.0, 0.45 + Double(enerji) * 0.7)
        case .dinliyor: min(0.6, 0.08 + Double(enerji) * 0.5)
        case .dusunuyor: 0.20
        case .bekliyor: 0.0
        }
    }

    var body: some View {
        TimelineView(.animation) { zaman in
            Canvas { ciz, boy in
                let t = zaman.date.timeIntervalSinceReferenceDate
                ciz.fill(Path(CGRect(origin: .zero, size: boy)),
                         with: .color(.black))
                cizKure(&ciz, boy: boy, t: t)
            }
            .onChange(of: zaman.date) { _, _ in
                // Kare başına yaklaşma; 0.08 deneyerek bulundu: daha hızlısı
                // sıçrıyor, daha yavaşı sesin gerisinde kalıyor.
                canlilik += (hedefCanlilik - canlilik) * 0.08
            }
        }
        .background(.black)
    }

    private func cizKure(_ ciz: inout GraphicsContext, boy: CGSize,
                         t: Double) {
        let merkez = CGPoint(x: boy.width / 2, y: boy.height / 2)
        let yaricap = min(boy.width, boy.height) * 0.36
        let donus = t * 0.35                 // dönüş her zaman, canlılıktan bağımsız
        let c = canlilik

        let seritSayisi = 22
        for i in 0..<seritSayisi {
            let k = Double(i) / Double(seritSayisi - 1)
            let enlem = (k - 0.5) * .pi * 0.94
            let halkaR = yaricap * cos(enlem)
            let yMerkez = merkez.y + yaricap * sin(enlem)

            // Bir "demet": birbirine yakın 3 filaman. Tek çizgi yerine demet
            // çizmek küreye referanstaki tel yumağı dokusunu veriyor.
            for f in 0..<3 {
                let kayma = Double(f - 1) * 0.012 * yaricap
                var yol = Path()
                let adim = 44
                for a in 0...adim {
                    let acu = Double(a) / Double(adim) * 2 * .pi
                    let dalga = akiskan(acu: acu, enlem: enlem, t: t,
                                        tohum: Double(f))
                    let r = halkaR + kayma + dalga * c * yaricap * 0.42
                    let x = merkez.x + cos(acu + donus) * r
                    // Perspektif: arkadaki yay hafif basık görünsün
                    let y = yMerkez + sin(acu + donus) * r * 0.30
                    a == 0 ? yol.move(to: CGPoint(x: x, y: y))
                           : yol.addLine(to: CGPoint(x: x, y: y))
                }
                yol.closeSubpath()

                let ton = 0.80 - k * 0.22      // mor → macenta → altın uçları
                let renk = Color(hue: ton, saturation: 0.9, brightness: 1.0)

                // 1. geçiş: geniş, saydam renkli parıltı
                ciz.stroke(yol, with: .color(renk.opacity(0.18 + c * 0.22)),
                           lineWidth: 3.2 + c * 2.4)
                // 2. geçiş: ince, beyaza yakın çekirdek
                ciz.stroke(yol,
                           with: .color(Color(hue: ton, saturation: 0.25,
                                              brightness: 1.0,
                                              opacity: 0.55 + c * 0.4)),
                           lineWidth: 0.8)
            }
        }
    }

    /// İki oktavlı yumuşak gürültü — su yüzeyi gibi aksın diye.
    ///
    /// Gerçek Perlin gürültüsü yerine sinüs toplamı: gözle ayırt edilmiyor,
    /// tabloya ihtiyaç duymuyor ve saatte de bedava.
    private func akiskan(acu: Double, enlem: Double, t: Double,
                         tohum: Double) -> Double {
        let a = sin(acu * 2 + t * 1.30 + enlem * 3 + tohum)
        let b = sin(acu * 5 - t * 0.85 + enlem * 1.7 + tohum * 2.1)
        return a * 0.62 + b * 0.38
    }
}
