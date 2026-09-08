import NovaPaylasilan
import SwiftUI

/// Koç — ritüeller, alışkanlıklar, bütçe.
///
/// Mentör takvimi yönetiyor (ne zaman ne yapılacak); burası yorum katmanı.
/// Masaüstündeki koç sekmesinin telefon karşılığı.
struct KocGorunumu: View {

    @State private var koc: KocOzeti?
    @State private var aliskanliklar: [Aliskanlik] = []
    @State private var hata: String?
    @State private var yukleniyor = true

    var body: some View {
        List {
            if let hata {
                Text(hata).font(.footnote).foregroundStyle(.red)
            }

            if let s = koc?.sabah?.veri?.metin, !s.isEmpty {
                Section("Sabah ritüeli") {
                    Text(s).font(.subheadline)
                }
            }
            if let a = koc?.aksam?.veri?.metin, !a.isEmpty {
                Section("Akşam ritüeli") {
                    Text(a).font(.subheadline)
                }
            }

            aliskanlikBolumu
            butceBolumu

            if koc == nil && !yukleniyor && hata == nil {
                Text("Koç verisi yok.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Koç")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await yukle() }
        .task { await yukle() }
    }

    private var aliskanlikBolumu: some View {
        Section("Alışkanlıklar") {
            if aliskanliklar.isEmpty && !yukleniyor {
                Text("Alışkanlık tanımlı değil.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(aliskanliklar) { a in
                Button {
                    Task { await isaretle(a) }
                } label: {
                    HStack {
                        Image(systemName: a.yapildi
                              ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(a.yapildi ? .green : .secondary)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(a.ad)
                                .font(.subheadline)
                                .foregroundStyle(.primary)
                            HStack(spacing: 6) {
                                if let h = a.hedef, let b = a.buHafta {
                                    Text("bu hafta \(b)/\(h)")
                                }
                                if let s = a.seri, s > 0 {
                                    Text("· \(s) gün seri")
                                }
                            }
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var butceBolumu: some View {
        if let b = koc?.butce {
            Section("Bütçe") {
                satir("Bu ay", b.toplam, "TL")
                if let a = b.aylikButce, a > 0 {
                    satir("Aylık bütçe", a, "TL")
                    satir("Kalan", b.kalan, "TL")
                }
                satir("Günlük ortalama", b.gunlukOrtalama, "TL")
                satir("Ay sonu tahmini", b.aySonuTahmini, "TL")
            }
        }
    }

    private func satir(_ ad: String, _ d: Double?, _ birim: String) -> some View {
        HStack {
            Text(ad).font(.subheadline)
            Spacer()
            Text(d.map { "\(sayi($0)) \(birim)" } ?? "—")
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    private func sayi(_ d: Double) -> String {
        d == d.rounded() ? String(Int(d)) : String(format: "%.1f", d)
    }

    private func yukle() async {
        yukleniyor = true
        defer { yukleniyor = false }
        do {
            async let k = Api.ortak.koc()
            async let a = Api.ortak.aliskanliklar()
            let (kocD, alis) = try await (k, a)
            koc = kocD
            aliskanliklar = alis.aliskanliklar
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }

    private func isaretle(_ a: Aliskanlik) async {
        try? await Api.ortak.aliskanlikIsaret(a.id, yapildi: !a.yapildi)
        await yukle()
    }
}

/// Rapor — tüm projelerin durumu. Model kullanmıyor, yerel hesap.
struct RaporGorunumu: View {

    @State private var metin = ""
    @State private var hata: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let hata {
                    Text(hata).font(.footnote).foregroundStyle(.red)
                }
                Text(metin.isEmpty ? "Yükleniyor…" : metin)
                    .font(.system(size: 15))
                    .textSelection(.enabled)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .navigationTitle("Rapor")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await yukle() }
        .task { await yukle() }
    }

    private func yukle() async {
        do {
            metin = try await Api.ortak.rapor().metin
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }
}
