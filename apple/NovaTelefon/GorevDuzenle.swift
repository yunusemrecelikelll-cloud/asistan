import NovaPaylasilan
import SwiftUI

/// Yeni görev ekleme.
///
/// Sunucudaki mentör planı kendisi üretiyor ama araya elle iş sokmak
/// gerekiyor — "şunu da bugün yapayım" demek için masaüstüne gitmek
/// zorunda kalmayasın diye.
struct GorevDuzenle: View {

    let varsayilanTarih: String
    let bitince: () -> Void

    @Environment(\.dismiss) private var kapat

    @State private var baslik = ""
    @State private var ayrinti = ""
    @State private var tarih = Date()
    @State private var saat = Date()
    @State private var sureDk = 60
    @State private var oncelik = 2
    @State private var zorunlu = true
    @State private var projeId: Int?
    @State private var projeler: [Proje] = []
    @State private var kaydediyor = false
    @State private var hata: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Ne yapılacak?", text: $baslik, axis: .vertical)
                        .lineLimit(1...3)
                    TextField("Ayrıntı (isteğe bağlı)", text: $ayrinti,
                              axis: .vertical)
                        .lineLimit(1...4)
                }

                Section("Ne zaman") {
                    DatePicker("Gün", selection: $tarih,
                               displayedComponents: .date)
                    DatePicker("Saat", selection: $saat,
                               displayedComponents: .hourAndMinute)
                    Picker("Süre", selection: $sureDk) {
                        ForEach([15, 30, 45, 60, 90, 120, 180], id: \.self) {
                            Text("\($0) dakika").tag($0)
                        }
                    }
                }

                Section("Nasıl") {
                    Picker("Öncelik", selection: $oncelik) {
                        Text("Kritik").tag(1)
                        Text("Normal").tag(2)
                        Text("Düşük").tag(3)
                    }
                    .pickerStyle(.segmented)
                    Toggle("Zorunlu", isOn: $zorunlu)
                    // Zorunlu işler kaçırılınca mentör otomatik telafi
                    // görevi yazıyor; kullanıcı bunu bilerek seçebilmeli.
                    if zorunlu {
                        Text("Kaçırılırsa telafi görevi açılır.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }

                Section("Proje") {
                    Picker("Proje", selection: $projeId) {
                        Text("Yok").tag(Int?.none)
                        ForEach(projeler) { p in
                            Text(p.ad).tag(Int?.some(p.id))
                        }
                    }
                }

                if let hata {
                    Text(hata).font(.footnote).foregroundStyle(.red)
                }
            }
            .navigationTitle("Yeni görev")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("İptal") { kapat() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Ekle") { Task { await kaydet() } }
                        .disabled(baslik.trimmingCharacters(
                            in: .whitespaces).isEmpty || kaydediyor)
                }
            }
            .task {
                if let t = tarihCoz(varsayilanTarih) { tarih = t }
                projeler = (try? await Api.ortak.projeler()) ?? []
            }
        }
    }

    private func tarihCoz(_ s: String) -> Date? {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.date(from: s)
    }

    private func kaydet() async {
        kaydediyor = true
        defer { kaydediyor = false }
        let y = YeniGorev(
            baslik: baslik.trimmingCharacters(in: .whitespacesAndNewlines),
            tarih: Bicim.tarih(tarih),
            saat: Bicim.saat(saat),
            sureDk: sureDk,
            projeId: projeId,
            ayrinti: ayrinti.isEmpty ? nil : ayrinti,
            oncelik: oncelik,
            zorunlu: zorunlu)
        do {
            try await Api.ortak.gorevEkle(y)
            bitince()
            kapat()
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }
}
