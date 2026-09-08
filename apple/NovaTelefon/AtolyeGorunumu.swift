import NovaPaylasilan
import SwiftUI

/// Atölye — yazıcılar ve "3d Projeler" klasöründeki dosyalar.
///
/// Yan barda "Atölye" hazır bir soruydu: dokununca sohbete "yazıcılar ne
/// durumda" gidiyor, cevabı model yazıyordu. Yazıcı durumu tam olarak
/// modelin uydurmaması gereken şey — "boşta" ile "basılıyor" arasındaki
/// fark kullanıcıyı odaya kadar yürütüyor. Plan, Projeler ve Yaşam'da
/// olduğu gibi burada da veri doğrudan gösteriliyor.
///
/// İş mantığı yok: sayım da, ilerleme yüzdesi de sunucuda hesaplanıyor.
struct AtolyeGorunumu: View {

    @State private var yazicilar: [Yazici] = []
    @State private var dosyalar: Dosyalar?
    @State private var yukleniyor = true
    @State private var tariyor = false
    @State private var hata: String?

    var body: some View {
        List {
            if let hata {
                Text(hata).font(.footnote).foregroundStyle(.red)
            }
            yazicilarBolumu
            klasorBolumu
            bekleyenBolumu
            bitenBolumu
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Atölye")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await tara() }
                } label: {
                    if tariyor {
                        ProgressView()
                    } else {
                        Image(systemName: "arrow.clockwise.circle")
                    }
                }
                .disabled(tariyor)
            }
        }
        .refreshable { await yukle() }
        .task { await yukle() }
    }

    // MARK: - Bölümler

    private var yazicilarBolumu: some View {
        Section("Yazıcılar") {
            if yazicilar.isEmpty && !yukleniyor {
                Text("Kayıtlı yazıcı yok.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(yazicilar) { y in
                YaziciSatiri(yazici: y)
            }
        }
    }

    /// Klasör yoksa bunu söylemek şart: dosya listesi boş görünür ve
    /// "hiç dosya yok" ile "klasörü bulamadım" aynı şeye benzer.
    @ViewBuilder
    private var klasorBolumu: some View {
        if let d = dosyalar, !d.klasorVar {
            Section {
                Label("Klasör bulunamadı", systemImage: "folder.badge.questionmark")
                    .font(.subheadline).foregroundStyle(.orange)
                if let k = d.kok {
                    Text(k).font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
    }

    @ViewBuilder
    private var bekleyenBolumu: some View {
        let liste = dosyalar?.bekleyen ?? []
        Section("Bekleyen (\(liste.count))") {
            if liste.isEmpty && !yukleniyor {
                Text("Bekleyen dosya yok.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(liste) { d in
                DosyaSatiri(dosya: d)
                    .swipeActions(edge: .leading) {
                        Button {
                            Task { await bitti(d) }
                        } label: { Label("Bitti", systemImage: "checkmark") }
                        .tint(.green)
                    }
            }
        }
    }

    @ViewBuilder
    private var bitenBolumu: some View {
        let liste = dosyalar?.biten ?? []
        if !liste.isEmpty {
            Section("Biten (\(liste.count))") {
                ForEach(liste) { d in
                    DosyaSatiri(dosya: d, solgun: true)
                        .swipeActions(edge: .trailing) {
                            Button {
                                Task { await geri(d) }
                            } label: {
                                Label("Geri", systemImage: "arrow.uturn.backward")
                            }
                            .tint(.orange)
                        }
                }
            }
        }
    }

    // MARK: - Veri

    private func yukle() async {
        yukleniyor = true
        defer { yukleniyor = false }
        do {
            yazicilar = try await Api.ortak.atolye().yazicilar
            dosyalar = try await Api.ortak.dosyalar()
            hata = nil
        } catch {
            hata = mesaj(error)
        }
    }

    /// Klasörü yeniden tara. Yeni dilimlenmiş dosyalar ancak taramadan
    /// sonra listeye giriyor; sunucu kendi başına da tarıyor ama telefonu
    /// açan kişi genellikle "az önce kaydettim" durumunda oluyor.
    private func tara() async {
        tariyor = true
        defer { tariyor = false }
        do {
            _ = try await Api.ortak.dosyaTara()
            hata = nil
        } catch {
            hata = mesaj(error)
        }
        await yukle()
    }

    private func bitti(_ d: BaskiDosyasi) async {
        do {
            _ = try await Api.ortak.dosyaBitti(d.id)
            hata = nil
        } catch {
            hata = mesaj(error)
        }
        await yukle()
    }

    private func geri(_ d: BaskiDosyasi) async {
        do {
            _ = try await Api.ortak.dosyaGeri(d.id)
            hata = nil
        } catch {
            hata = mesaj(error)
        }
        await yukle()
    }

    private func mesaj(_ e: Error) -> String {
        (e as? Api.Hata)?.errorDescription ?? e.localizedDescription
    }
}

/// Tek yazıcı: adı, durumu, takılı filament ve üstündeki baskı.
struct YaziciSatiri: View {

    let yazici: Yazici

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(yazici.ad).font(.subheadline)
                if let m = yazici.model, !m.isEmpty {
                    Text(m).font(.caption2).foregroundStyle(.tertiary)
                }
                Spacer()
                Text(durumYazisi)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(durumRengi)
            }
            if let f = yazici.filamentYazisi {
                Text(f).font(.caption2).foregroundStyle(.secondary)
            }
            if let b = yazici.aktifBaski {
                baskiSatiri(b)
            }
        }
        .padding(.vertical, 2)
    }

    /// İlerleme çubuğu süreden hesaplanıyor, makineden okunmuyor. "kalan"
    /// yazısı bu yüzden tahmin; süresini geçmiş baskı 0 dk'da takılı kalır
    /// ve sunucu onu "bitti" diye işaretler.
    @ViewBuilder
    private func baskiSatiri(_ b: AktifBaski) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(b.ad).font(.caption)
                if let p = b.projeAd, !p.isEmpty {
                    Text(p).font(.caption2).foregroundStyle(.tertiary)
                }
                Spacer()
                if let k = b.ilerleme?.kalanDk {
                    Text(k <= 0 ? "süresi doldu" : "\(k) dk kaldı")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(k <= 0 ? Color.orange : Color.secondary)
                }
            }
            if let y = b.ilerleme?.yuzde {
                ProgressView(value: Double(min(100, max(0, y))), total: 100)
                    .tint(.blue)
            }
        }
        .padding(.top, 2)
    }

    private var durumYazisi: String {
        switch yazici.durum {
        case "basiliyor": "basılıyor"
        case "bos": "boşta"
        case "bakim": "bakımda"
        case "kapali": "kapalı"
        default: yazici.durum ?? "—"
        }
    }

    private var durumRengi: Color {
        switch yazici.durum {
        case "basiliyor": .blue
        case "bos": .green
        case "bakim": .orange
        case "kapali": .secondary
        default: .secondary
        }
    }
}

/// Tek dosya satırı — ad, boyut, bağlı olduğu proje.
struct DosyaSatiri: View {

    let dosya: BaskiDosyasi
    var solgun = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(dosya.gorunenAd)
                .font(.subheadline)
                .lineLimit(2)
                .foregroundStyle(solgun ? .secondary : .primary)
            HStack(spacing: 6) {
                if let b = dosya.boyutYazisi {
                    Text(b).font(.caption2.monospacedDigit())
                }
                if let p = dosya.projeAd, !p.isEmpty {
                    Text(p).font(.caption2)
                }
            }
            .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 1)
    }
}
