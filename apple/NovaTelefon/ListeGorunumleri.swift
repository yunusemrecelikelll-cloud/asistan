import NovaPaylasilan
import SwiftUI

/// Projeler — hangi işler var, hangisi diskte duruyor.
struct ProjelerGorunumu: View {

    @ObservedObject private var olaylar = Olaylar.ortak
    @State private var projeler: [Proje] = []
    @State private var yukleniyor = true
    @State private var hata: String?

    var body: some View {
        List {
            if let hata {
                Text(hata).font(.footnote).foregroundStyle(.red)
            }
            if projeler.isEmpty && !yukleniyor && hata == nil {
                Text("Proje bulunamadı.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            // Satıra dokununca projenin içi açılıyor: git durumu, brifing,
            // geçmiş oturumlar, düzenlenebilir not.
            ForEach(projeler) { p in
                NavigationLink {
                    ProjeDetayGorunumu(proje: p)
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        HStack {
                            Text(p.ad).font(.subheadline)
                            Spacer()
                            if !p.diskteVar {
                                Text("diskte yok")
                                    .font(.caption2).foregroundStyle(.orange)
                            } else if let n = p.oturumSayisi, n > 0 {
                                Text("\(n) oturum")
                                    .font(.caption2).foregroundStyle(.tertiary)
                            }
                        }
                        if let n = p.notMetni, !n.isEmpty {
                            Text(n)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                    .padding(.vertical, 1)
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Projeler")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await yukle() }
        .task { await yukle() }
        .onChange(of: olaylar.sayac) { _, _ in
            if olaylar.ilgilendirir(["proje"]) {
                Task { await yukle() }
            }
        }
    }

    private func yukle() async {
        yukleniyor = true
        defer { yukleniyor = false }
        do {
            projeler = try await Api.ortak.projeler()
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }
}

/// Yaşam — uyku, harcama, su, spor. Sunucudaki kartların aynısı.
struct YasamGorunumu: View {

    @State private var kartlar: [YasamKarti] = []
    @State private var hata: String?

    var body: some View {
        List {
            if let hata {
                Text(hata).font(.footnote).foregroundStyle(.red)
            }
            ForEach(kartlar) { k in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(k.ad).font(.subheadline)
                        if let h = k.hedef, h > 0 {
                            Text("hedef \(sayi(h)) \(k.birim ?? "")")
                                .font(.caption2).foregroundStyle(.tertiary)
                        }
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(k.bugun.map(sayi) ?? "—")
                            .font(.title3.weight(.semibold).monospacedDigit())
                            .foregroundStyle(renk(k))
                        if let o = k.ortalama {
                            Text("ort. \(sayi(o))")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(.vertical, 2)
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Yaşam")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await yukle() }
        .task { await yukle() }
    }

    private func yukle() async {
        do {
            kartlar = try await Api.ortak.yasam().kartlar
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }

    private func sayi(_ d: Double) -> String {
        d == d.rounded() ? String(Int(d)) : String(format: "%.1f", d)
    }

    private func renk(_ k: YasamKarti) -> Color {
        switch k.durum {
        case "iyi": .green
        case "kotu", "kötü": .red
        case "orta": .orange
        default: .primary
        }
    }
}
