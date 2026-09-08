import NovaPaylasilan
import SwiftUI

/// Bir projenin içi: git durumu, brifing, geçmiş oturumlar ve not.
///
/// Projeler listesi yalnızca adı ve "diskte var mı"yı gösteriyordu;
/// dokununca hiçbir şey olmuyordu. Oysa sunucu `/api/projeler/{id}`
/// altında çalışmaya devam etmek için gereken her şeyi tutuyor — dalın
/// kirli olup olmadığı, son commit, önceki oturumların başlıkları,
/// modelin hazırladığı brifing. Telefonda bunları görememek, projeye
/// bilgisayar başına geçmeden bakılamaması demekti.
///
/// Not düzenlenebilir: kullanıcının akla gelen bir şeyi projeye
/// iliştirebildiği tek yer burası.
struct ProjeDetayGorunumu: View {

    let proje: Proje

    @ObservedObject private var olaylar = Olaylar.ortak
    @State private var detay: ProjeDetay?
    @State private var yukleniyor = true
    @State private var hata: String?

    @State private var not = ""
    /// Sunucudan gelen son not. Kaydet düğmesi yalnızca gerçekten
    /// değiştiğinde etkin olsun diye tutuluyor.
    @State private var kayitliNot = ""
    @State private var kaydediliyor = false
    @FocusState private var notOdakta: Bool

    var body: some View {
        List {
            if let hata {
                Text(hata).font(.footnote).foregroundStyle(.red)
            }
            if let d = detay {
                durumBolumu(d)
                if let g = d.gitDurumu { gitBolumu(g) }
                if let b = d.brifing, !b.isEmpty { metinBolumu("Brifing", b) }
                if let o = d.ozet, !o.isEmpty { metinBolumu("Özet", o) }
                notBolumu
                oturumBolumu(d)
            } else if yukleniyor {
                HStack { ProgressView(); Text("Yükleniyor…").padding(.leading, 8) }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(proje.ad)
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await yukle() }
        .task { await yukle() }
        .onChange(of: olaylar.sayac) { _, _ in
            // Not kutusu açıkken tazeleme yazdığını silerdi.
            if olaylar.ilgilendirir(["proje"]) && !notOdakta {
                Task { await yukle() }
            }
        }
    }

    // MARK: - Bölümler

    private func durumBolumu(_ d: ProjeDetay) -> some View {
        Section {
            HStack {
                Label(d.diskteVar ? "Diskte" : "Diskte yok",
                      systemImage: d.diskteVar ? "internaldrive" : "questionmark.folder")
                    .font(.subheadline)
                    // Color olarak yazmak şart: `.primary` HierarchicalShapeStyle,
                    // `.orange` Color; ternary'de tip birleşmiyor.
                    .foregroundStyle(d.diskteVar ? Color.primary : Color.orange)
                Spacer()
                if let n = d.oturumSayisi, n > 0 {
                    Text("\(n) oturum")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if let y = d.yol, !y.isEmpty {
                Text(y)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
    }

    private func gitBolumu(_ g: GitDurumu) -> some View {
        Section("Git") {
            HStack {
                Label(g.dal ?? "—", systemImage: "arrow.triangle.branch")
                    .font(.subheadline)
                Spacer()
                if g.kirli.deger(false) {
                    // Kaç dosyanın değiştiği, "kirli" demekten daha çok şey
                    // söylüyor: 1 dosya ile 40 dosya aynı şey değil.
                    Text(g.degisen.map { "\($0) değişik" } ?? "kirli")
                        .font(.caption).foregroundStyle(.orange)
                } else {
                    Text("temiz").font(.caption).foregroundStyle(.green)
                }
            }
            if let c = g.sonCommit, !c.isEmpty {
                Text(c)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
    }

    private func metinBolumu(_ baslik: String, _ metin: String) -> some View {
        Section(baslik) {
            Text(metin)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
    }

    private var notBolumu: some View {
        Section("Not") {
            TextEditor(text: $not)
                .font(.subheadline)
                .frame(minHeight: 80)
                .focused($notOdakta)
            HStack {
                if kaydediliyor { ProgressView().controlSize(.small) }
                Spacer()
                Button("Kaydet") { Task { await notKaydet() } }
                    .disabled(kaydediliyor || not == kayitliNot)
            }
        }
    }

    private func oturumBolumu(_ d: ProjeDetay) -> some View {
        let basliklar = d.basliklar ?? []
        return Section("Geçmiş oturumlar (\(basliklar.count))") {
            if basliklar.isEmpty {
                Text("Bu projede kayıtlı oturum yok.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(Array(basliklar.enumerated()), id: \.offset) { _, b in
                Text(b).font(.subheadline)
            }
        }
    }

    // MARK: - Veri

    private func yukle() async {
        yukleniyor = true
        defer { yukleniyor = false }
        do {
            let d = try await Api.ortak.projeDetay(proje.id)
            detay = d
            let gelen = d.notMetni ?? ""
            // Kullanıcı yazmaya başladıysa üstüne yazma.
            if not == kayitliNot { not = gelen }
            kayitliNot = gelen
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }

    private func notKaydet() async {
        kaydediliyor = true
        defer { kaydediliyor = false }
        do {
            try await Api.ortak.projeNot(proje.id, not: not)
            kayitliNot = not
            notOdakta = false
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }
}
