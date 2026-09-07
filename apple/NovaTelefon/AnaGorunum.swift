import NovaPaylasilan
import SwiftUI

/// Telefonun ana ekranı: küre, sohbet dökümü, konuşma düğmesi.
///
/// Yan bar (kullanıcının istediği gibi) sürükleyerek açılıyor ve diğer
/// bölümlere oradan geçiliyor. Ana ekran bilerek tek işe odaklı: konuşmak.
struct AnaGorunum: View {

    @EnvironmentObject private var oturum: Oturum
    @EnvironmentObject private var role: SaatRolesi

    @State private var yanBar = false
    @State private var yaziliMod = false
    @State private var taslak = ""

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()
                icerik
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { yanBar = true } label: {
                        Image(systemName: "line.3.horizontal")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { yaziliMod.toggle() } label: {
                        Image(systemName: yaziliMod ? "mic" : "keyboard")
                    }
                }
            }
            .toolbarBackground(.black, for: .navigationBar)
            .navigationTitle("NOVA")
            .navigationBarTitleDisplayMode(.inline)
        }
        .preferredColorScheme(.dark)
        .sheet(isPresented: $yanBar) { YanBar() }
    }

    private var icerik: some View {
        VStack(spacing: 0) {
            durumSatiri
            KureGorunumu(hal: oturum.hal, enerji: oturum.enerji)
                .frame(height: 240)
            dokum
            if yaziliMod { yaziAlani } else { konusmaDugmesi }
        }
    }

    private var durumSatiri: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(oturum.bagli ? .green : .orange)
                .frame(width: 7, height: 7)
            Text(oturum.durumYazisi)
                .font(.caption)
                .foregroundStyle(.secondary)
            if role.saatBagli {
                Image(systemName: "applewatch")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let ms = oturum.sonGecikmeMs {
                // Gecikmeyi göstermek süs değil: ev ağı ile Tailscale
                // arasındaki farkı kullanıcı anında görüyor.
                Text("ilk ses \(ms) ms")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal)
        .padding(.top, 4)
    }

    private var dokum: some View {
        ScrollViewReader { kaydir in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(oturum.satirlar) { s in
                        HStack {
                            if s.ben { Spacer(minLength: 40) }
                            Text(s.metin)
                                .font(.system(size: 15))
                                .padding(.horizontal, 12)
                                .padding(.vertical, 8)
                                .background(
                                    RoundedRectangle(cornerRadius: 14)
                                        .fill(s.ben
                                              ? Color.white.opacity(0.08)
                                              : Color.purple.opacity(0.18)))
                                .foregroundStyle(s.ben ? .secondary : .primary)
                            if !s.ben { Spacer(minLength: 40) }
                        }
                        .id(s.id)
                    }
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            }
            .onChange(of: oturum.satirlar.count) { _, _ in
                if let sonu = oturum.satirlar.last {
                    withAnimation { kaydir.scrollTo(sonu.id, anchor: .bottom) }
                }
            }
        }
    }

    private var konusmaDugmesi: some View {
        VStack(spacing: 10) {
            Toggle("Sürekli dinle", isOn: $oturum.surekliDinle)
                .font(.caption)
                .tint(.purple)
                .padding(.horizontal, 40)

            Button {
                switch oturum.hal {
                case .dinliyor: oturum.dinlemeyiBitir()
                case .konusuyor: oturum.sustur()
                default: oturum.dinlemeyeBasla()
                }
            } label: {
                ZStack {
                    Circle()
                        .fill(dugmeRengi.opacity(0.22))
                        .frame(width: 78, height: 78)
                    Circle()
                        .stroke(dugmeRengi, lineWidth: 2)
                        .frame(width: 78, height: 78)
                        .scaleEffect(1 + CGFloat(oturum.enerji) * 0.18)
                    Image(systemName: dugmeSimgesi)
                        .font(.system(size: 28, weight: .medium))
                        .foregroundStyle(dugmeRengi)
                }
            }
            .disabled(!oturum.bagli)
            .padding(.bottom, 18)
        }
    }

    private var yaziAlani: some View {
        HStack(spacing: 8) {
            TextField("Yaz…", text: $taslak, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...4)
                .onSubmit(gonder)
            Button(action: gonder) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
            }
            .disabled(taslak.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding()
    }

    private func gonder() {
        oturum.metinGonder(taslak)
        taslak = ""
    }

    private var dugmeRengi: Color {
        switch oturum.hal {
        case .dinliyor: .red
        case .konusuyor: .orange
        case .dusunuyor: .yellow
        case .bekliyor: .purple
        }
    }

    private var dugmeSimgesi: String {
        switch oturum.hal {
        case .dinliyor: "stop.fill"
        case .konusuyor: "speaker.wave.2.fill"
        case .dusunuyor: "ellipsis"
        case .bekliyor: "mic.fill"
        }
    }
}
