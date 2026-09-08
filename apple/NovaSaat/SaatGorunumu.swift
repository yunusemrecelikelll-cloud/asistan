import NovaPaylasilan
import SwiftUI

/// Saat ekranı. Tek iş yapar: konuş, dinle.
///
/// Saatte liste, sekme, ayar yok — bilekte okunacak metin değil, söylenecek
/// söz var. Ekranın ortası kürenin küçük hâli, altında son konuşulanlar.
/// Dijital Taç ile geriye kaydırılabiliyor.
struct SaatGorunumu: View {

    @EnvironmentObject private var oturum: Oturum

    var body: some View {
        VStack(spacing: 6) {
            baslik
            kure
            son
            dugme
        }
        .padding(.horizontal, 6)
    }

    private var baslik: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(oturum.bagli ? Color.green : Color.orange)
                .frame(width: 6, height: 6)
            Text(oturum.bagli ? "telefon üzerinden" : oturum.durumYazisi)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            if let ms = oturum.sonGecikmeMs {
                Spacer(minLength: 2)
                Text("\(ms) ms")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }
        }
    }

    private var kure: some View {
        KucukKure(hal: oturum.hal, enerji: oturum.enerji)
            .frame(height: 62)
    }

    private var son: some View {
        ScrollViewReader { kaydir in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 4) {
                    ForEach(oturum.satirlar) { s in
                        Text(s.metin)
                            .font(.system(size: 13))
                            .foregroundStyle(s.ben ? .secondary : .primary)
                            .frame(maxWidth: .infinity,
                                   alignment: s.ben ? .trailing : .leading)
                            .id(s.id)
                    }
                }
            }
            .onChange(of: oturum.satirlar.count) { _, _ in
                if let sonu = oturum.satirlar.last {
                    withAnimation { kaydir.scrollTo(sonu.id, anchor: .bottom) }
                }
            }
        }
    }

    private var dugme: some View {
        Button {
            if oturum.hal == .dinliyor {
                oturum.dinlemeyiBitir()
            } else if oturum.hal == .konusuyor {
                oturum.sustur()
            } else {
                // Ekran konuşmanın ortasında sönmesin. Kayıt bitince
                // oturum kapanıyor (aşağıdaki onChange).
                EkranAcik.ortak.basla()
                oturum.dinlemeyeBasla()
            }
        } label: {
            Label(dugmeYazisi, systemImage: dugmeSimgesi)
                .font(.system(size: 14, weight: .semibold))
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .tint(dugmeRengi)
        .disabled(!oturum.bagli)
        .onChange(of: oturum.hal) { _, yeni in
            // Tur bittiğinde bırak: uzatılmış oturumu gereğinden uzun
            // tutmak saatin pilini yer. Nova konuşurken de açık kalıyor,
            // çünkü kullanıcı cevabı ekranda okuyor olabilir.
            if yeni == .bekliyor { EkranAcik.ortak.bitir() }
        }
    }

    private var dugmeYazisi: String {
        switch oturum.hal {
        case .dinliyor: "Bitir"
        case .konusuyor: "Sustur"
        case .dusunuyor: "…"
        case .bekliyor: "Konuş"
        }
    }

    private var dugmeSimgesi: String {
        switch oturum.hal {
        case .dinliyor: "stop.fill"
        case .konusuyor: "speaker.slash.fill"
        case .dusunuyor: "ellipsis"
        case .bekliyor: "mic.fill"
        }
    }

    private var dugmeRengi: Color {
        switch oturum.hal {
        case .dinliyor: .red
        case .konusuyor: .orange
        default: .purple
        }
    }
}

/// Kürenin saat sürümü — masaüstündeki neon küreden esinlenmiş, ama
/// bilekte pil yakmayacak kadar sade. Bir Canvas, birkaç halka.
struct KucukKure: View {

    let hal: Oturum.Hâl
    let enerji: Float

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { zaman in
            Canvas { ciz, boy in
                let t = zaman.date.timeIntervalSinceReferenceDate
                let merkez = CGPoint(x: boy.width / 2, y: boy.height / 2)
                let yaricap = min(boy.width, boy.height) / 2 - 4
                // Bekleme hâlinde yalnızca dönüyor; dağılma sadece ses varken.
                let canlilik = hal == .bekliyor ? 0.0 : Double(enerji)

                for i in 0..<7 {
                    let k = Double(i) / 6.0
                    let enlem = (k - 0.5) * .pi
                    let r = yaricap * cos(enlem)
                    let y = merkez.y + yaricap * sin(enlem) * 0.85
                    let sapma = canlilik * yaricap * 0.28
                        * sin(t * 3 + Double(i) * 1.7)

                    var yol = Path()
                    yol.addEllipse(in: CGRect(
                        x: merkez.x - r - sapma, y: y - r * 0.22,
                        width: (r + sapma) * 2, height: r * 0.44))

                    let ton = 0.78 - k * 0.18       // mor → macenta
                    ciz.stroke(
                        yol,
                        with: .color(Color(hue: ton, saturation: 0.85,
                                           brightness: 1.0,
                                           opacity: 0.35 + canlilik * 0.5)),
                        lineWidth: 1.0 + canlilik * 1.4)
                }
            }
            .rotationEffect(.degrees(
                (zaman.date.timeIntervalSinceReferenceDate * 18)
                    .truncatingRemainder(dividingBy: 360)))
        }
    }
}
