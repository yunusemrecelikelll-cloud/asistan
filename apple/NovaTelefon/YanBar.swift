import NovaPaylasilan
import SwiftUI

/// Yan bar — diğer bölümlere ve ayarlara buradan geçiliyor.
///
/// Bölümlerin İÇERİĞİ sunucudan geliyor; burada iş mantığı yok. Masaüstü
/// arayüzü ile telefonun aynı şeyi göstermesinin sebebi bu: ikisi de tek
/// kaynağa bakıyor, ayrı bir eşitleme yok.
struct YanBar: View {

    @EnvironmentObject private var oturum: Oturum
    @EnvironmentObject private var role: SaatRolesi
    @Environment(\.dismiss) private var kapat

    var body: some View {
        NavigationStack {
            List {
                Section("Nova") {
                    satir("Bugün", "calendar", "bugün ne var")
                    satir("Plan", "list.bullet.rectangle", "planım ne")
                    satir("Projeler", "folder", "projelerim nasıl gidiyor")
                    satir("Atölye", "printer", "yazıcılar ne durumda")
                    satir("Yaşam", "heart", "bugünkü yaşam kaydım ne")
                    satir("Koç", "figure.run", "koç yorumu yap")
                }

                Section("Bağlantı") {
                    LabeledContent("Durum", value: oturum.durumYazisi)
                    LabeledContent("Yol", value: oturum.baglanti.tasiyiciAdi)
                    if let ms = oturum.sonGecikmeMs {
                        LabeledContent("Son ilk ses", value: "\(ms) ms")
                    }
                    LabeledContent("Saat",
                                   value: role.saatBagli ? "bağlı" : "yok")
                }

                Section {
                    NavigationLink {
                        AyarGorunumu()
                    } label: {
                        Label("Ayarlar", systemImage: "gearshape")
                    }
                    Button(role: .destructive) {
                        oturum.sohbetiSifirla()
                        kapat()
                    } label: {
                        Label("Sohbeti temizle", systemImage: "trash")
                    }
                }
            }
            .navigationTitle("NOVA")
            .navigationBarTitleDisplayMode(.inline)
        }
        .preferredColorScheme(.dark)
    }

    /// Bölümler ayrı ekranlar değil, hazır sorular. Sunucu zaten bu
    /// soruların hepsini yanıtlıyor; ayrı ekran yazmak aynı bilgiyi iki
    /// yerde tutmak olurdu.
    private func satir(_ ad: String, _ simge: String,
                       _ soru: String) -> some View {
        Button {
            oturum.metinGonder(soru)
            kapat()
        } label: {
            Label(ad, systemImage: simge)
        }
    }
}

struct AyarGorunumu: View {

    @EnvironmentObject private var oturum: Oturum
    @State private var yerel = Ayarlar.ortak.yerelSunucu
    @State private var uzak = Ayarlar.ortak.sunucu
    @State private var belirtec = Ayarlar.ortak.belirtec

    var body: some View {
        Form {
            Section {
                TextField("192.168.1.20:8770", text: $yerel)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            } header: {
                Text("Yerel ağ adresi")
            } footer: {
                Text("Evdeyken bu kullanılıyor. Tailscale üzerinden gitmek "
                     + "tur başına 20-60 ms ekliyor.")
            }

            Section {
                TextField("100.x.y.z:8770", text: $uzak)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            } header: {
                Text("Tailscale adresi")
            } footer: {
                Text("Dışarıdayken bu kullanılıyor. Yerel adrese "
                     + "ulaşılamazsa buraya düşülüyor.")
            }

            Section("Parola") {
                SecureField("Sunucu parolası", text: $belirtec)
            }

            Section {
                Button("Kaydet ve yeniden bağlan") {
                    Ayarlar.ortak.yerelSunucu = yerel
                    Ayarlar.ortak.sunucu = uzak
                    Ayarlar.ortak.belirtec = belirtec
                    oturum.basla()
                }
            }
        }
        .navigationTitle("Ayarlar")
    }
}
