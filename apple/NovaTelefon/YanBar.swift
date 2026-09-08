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
                // Plan, projeler ve yaşam GERÇEK ekran. Eskiden bunlar da
                // hazır soruydu: bölüme dokununca sohbete bir cümle
                // gidiyor, cevabı model yazıyordu. Yani kullanıcı kendi
                // planını göremiyor, ancak modelin anlattığı kadarını
                // duyabiliyordu — ve model yanılabiliyordu. Veriyi
                // doğrudan göstermek hem doğru hem de dokunulabilir.
                Section("Nova") {
                    NavigationLink {
                        PlanGorunumu()
                    } label: {
                        Label("Plan", systemImage: "list.bullet.rectangle")
                    }
                    NavigationLink {
                        ProjelerGorunumu()
                    } label: {
                        Label("Projeler", systemImage: "folder")
                    }
                    NavigationLink {
                        YasamGorunumu()
                    } label: {
                        Label("Yaşam", systemImage: "heart")
                    }
                }

                // Bunların henüz ekranı yok; soru olarak duruyorlar.
                Section("Sor") {
                    satir("Atölye", "printer", "yazıcılar ne durumda")
                    satir("Koç", "figure.run", "koç yorumu yap")
                    satir("Rapor", "chart.bar", "genel durum raporu ver")
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
    @State private var parola = ""
    @State private var kaydediyor = false
    @State private var sonuc: String?
    @State private var bekleyenBildirim = 0

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

            Section {
                SecureField("Sunucu parolası", text: $parola)
            } header: {
                Text("Parola")
            } footer: {
                Text(Ayarlar.ortak.belirtec.isEmpty
                     ? "telefon.ps1 çalıştırınca yazdırılıyor."
                     : "Kayıtlı. Değiştirmek için yenisini yaz.")
            }

            Section {
                LabeledContent("Kurulu bildirim",
                               value: "\(bekleyenBildirim)")
                Text("Görevlerden 15 dakika önce, tam saatinde ve "
                     + "başlamadıysan 10 dakika sonra dürtülüyorsun.")
                    .font(.caption).foregroundStyle(.secondary)
            } header: {
                Text("Bildirimler")
            }

            Section {
                Button(kaydediyor ? "Bağlanıyor…" : "Kaydet ve yeniden bağlan") {
                    Task { await kaydet() }
                }
                .disabled(kaydediyor)
                if let sonuc {
                    Text(sonuc).font(.footnote)
                        .foregroundStyle(sonuc.hasPrefix("Bağlandı")
                                         ? .green : .red)
                }
            }
        }
        .task { bekleyenBildirim = await Bildirimler.ortak.bekleyenSayisi() }
        .navigationTitle("Ayarlar")
    }

    /// Adresleri yaz, parolayı belirtece çevir ve bağlantıyı GERÇEKTEN
    /// doğrula.
    ///
    /// "Kaydedildi" demek yetmiyor: yanlış adres ya da yanlış parola
    /// girildiğinde kullanıcı bunu ancak konuşmaya çalışınca anlıyordu.
    /// Kaydettikten sonra bir istek atıp sonucu burada söylüyoruz.
    private func kaydet() async {
        kaydediyor = true
        defer { kaydediyor = false }

        Ayarlar.ortak.yerelSunucu = yerel.trimmingCharacters(in: .whitespaces)
        Ayarlar.ortak.sunucu = uzak.trimmingCharacters(in: .whitespaces)

        let p = parola.trimmingCharacters(in: .whitespacesAndNewlines)
        if !p.isEmpty {
            do {
                // 64 karakterlik belirteci doğrudan yapıştırmış olabilir
                // (eski sürümde tek yol buydu); o zaman takas gerekmiyor.
                if p.count == 64, p.allSatisfy(\.isHexDigit) {
                    Ayarlar.ortak.belirtec = p
                } else {
                    Ayarlar.ortak.belirtec =
                        try await Api.ortak.girisYap(parola: p)
                }
                parola = ""
            } catch {
                sonuc = (error as? Api.Hata)?.errorDescription
                    ?? error.localizedDescription
                return
            }
        }

        do {
            _ = try await Api.ortak.bugun()
            oturum.basla()
            sonuc = "Bağlandı."
            bekleyenBildirim = await Bildirimler.ortak.bekleyenSayisi()
        } catch {
            sonuc = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }
}
