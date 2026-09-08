import AVFoundation
import NovaPaylasilan
import SwiftUI

// Ayarlar'daki iki bölüm: NOVA hangi sesle konuşsun, arkada hangi model
// düşünsün. İkisi de sunucuda tutuluyor — telefon yalnızca gösteriyor ve
// yazıyor. Masaüstünden değiştirilince buradan da aynı şey görünüyor.

/// Ses seçimi — dinle, seç, yeniden adlandır.
///
/// "Dene" düğmesi şart: dört sesin adları kullanıcının kendi verdiği
/// adlar ("Kalın", "Yumuşak"…) ve hangisinin hangisi olduğu ancak
/// duyunca anlaşılıyor. Seçmeden önce dinleyebilmek, yanlış seçip
/// 30-40 saniye beklemekten iyi.
struct SesAyarBolumu: View {

    @State private var durum: SesDurumu?
    @State private var yukleniyor = true
    @State private var hata: String?

    /// Örneği sentezlenen ses. Sentez saniyeler sürüyor, düğme dönsün.
    @State private var denenen: String?
    @State private var secilen: String?
    /// Ses değişince sunucu ara sesleri yeniden üretiyor; o sürede hazır
    /// cevaplar devre dışı. Kullanıcı "bozuldu" sanmasın diye söylüyoruz.
    @State private var hazirlaniyor = false

    @State private var adDuzenlenen: Ses?
    @State private var yeniAd = ""

    /// Örnek klip için ayrı oynatıcı. Oturum'un çalarını kullanamıyoruz:
    /// o özel ve canlı turda meşgul olabiliyor.
    @State private var calar: AVAudioPlayer?

    var body: some View {
        Section {
            if let hata {
                Text(hata).font(.footnote).foregroundStyle(.red)
            }
            if yukleniyor && durum == nil {
                HStack { ProgressView(); Text("Yükleniyor…").padding(.leading, 8) }
            }
            ForEach(durum?.sesler ?? []) { s in
                satir(s)
            }
            if hazirlaniyor {
                Label("Yeni sesle hazırlanıyor — kısa cevaplar birkaç "
                      + "saniye sonra devreye girecek.",
                      systemImage: "hourglass")
                    .font(.caption).foregroundStyle(.secondary)
            }
        } header: {
            Text("Ses")
        } footer: {
            Text(altYazi)
        }
        .task { await yukle() }
        .alert("Sesi yeniden adlandır", isPresented: Binding(
            get: { adDuzenlenen != nil },
            set: { if !$0 { adDuzenlenen = nil } })
        ) {
            TextField("Ad", text: $yeniAd)
            Button("Vazgeç", role: .cancel) { adDuzenlenen = nil }
            Button("Kaydet") { Task { await adKaydet() } }
        }
    }

    private var altYazi: String {
        var p = ["NOVA bu sesle konuşuyor. Kalem simgesiyle ad değiştir."]
        if let d = durum, !d.servisAcik {
            p.append("Klon servisi şu an kapalı; sunucu hazır sese "
                     + "düşüyor. Seçim yine kaydediliyor.")
        }
        p.append("Ses değiştirince selamlaşma ve \"bir saniye\" gibi hazır "
                 + "klipler yeniden üretiliyor, 30-40 saniye sürüyor. O "
                 + "sürede konuşma çalışmaya devam ediyor, sadece o kadar "
                 + "hızlı başlamıyor.")
        return p.joined(separator: " ")
    }

    private func satir(_ s: Ses) -> some View {
        HStack(spacing: 10) {
            Image(systemName: s.anahtar == durum?.secili
                  ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(s.anahtar == durum?.secili
                                 ? Color.accentColor : Color.secondary)
            VStack(alignment: .leading, spacing: 1) {
                Text(s.ad).font(.subheadline)
                if !s.hazirMi {
                    Text("hazır klipler yok")
                        .font(.caption2).foregroundStyle(.tertiary)
                }
            }
            Spacer(minLength: 0)
            if secilen == s.anahtar {
                ProgressView().controlSize(.small)
            }
            Button {
                adDuzenlenen = s
                yeniAd = s.ad
            } label: {
                Image(systemName: "pencil")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(.secondary)
            Button {
                Task { await dene(s) }
            } label: {
                if denenen == s.anahtar {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: "play.circle")
                }
            }
            .buttonStyle(.borderless)
            .disabled(denenen != nil)
        }
        // Satırın tamamı seçim için dokunulabilir olsun; düğmeler
        // .borderless olduğu için kendi dokunuşlarını kendileri yutuyor.
        .contentShape(Rectangle())
        .onTapGesture { Task { await sec(s) } }
    }

    // MARK: - Eylemler

    private func yukle() async {
        yukleniyor = true
        defer { yukleniyor = false }
        do {
            durum = try await Api.ortak.sesDurum()
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }

    private func sec(_ s: Ses) async {
        guard s.anahtar != durum?.secili, secilen == nil else { return }
        secilen = s.anahtar
        defer { secilen = nil }
        do {
            try await Api.ortak.sesSec(s.anahtar)
            hata = nil
            await yukle()
            hazirlaniyor = true
            // Sunucu ara sesleri arka planda üretiyor; bitişini bildiren
            // bir uç yok, o yüzden notu süreyle kaldırıyoruz.
            Task {
                try? await Task.sleep(for: .seconds(40))
                hazirlaniyor = false
            }
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }

    private func dene(_ s: Ses) async {
        denenen = s.anahtar
        defer { denenen = nil }
        do {
            let veri = try await Api.ortak.sesDene(s.anahtar)
            calar = try AVAudioPlayer(data: veri)
            sesiDuyulurYap()
            calar?.play()
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }

    /// Sesli tur açıkken oturumun kategorisine dokunma; kapalıyken telefon
    /// sessizdeyse örnek hiç duyulmuyordu.
    private func sesiDuyulurYap() {
        let o = AVAudioSession.sharedInstance()
        guard o.category != .playAndRecord else { return }
        try? o.setCategory(.playback, mode: .default)
        try? o.setActive(true)
    }

    private func adKaydet() async {
        guard let s = adDuzenlenen else { return }
        let ad = yeniAd.trimmingCharacters(in: .whitespacesAndNewlines)
        adDuzenlenen = nil
        guard !ad.isEmpty else { return }
        do {
            try await Api.ortak.sesAd(s.anahtar, ad: ad)
            await yukle()
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }
}

/// Sohbetin arkasındaki model.
///
/// Yerel model ölçülerek bırakıldı: bağlamda DURAN veriyi görmezden
/// geliyordu — proje listesi istemin içindeyken "aktif projelerinle ilgili
/// bilgiye ulaşamadım" diyordu. Yine de seçenek olarak duruyor; ağ yokken
/// ya da kota dolduğunda çalışan tek şey o.
struct ModelAyarBolumu: View {

    @State private var ayarlar: SunucuAyarlari?
    @State private var hata: String?
    @State private var yaziyor = false

    @State private var saglayici = "claude"
    @State private var model = "sonnet"

    /// Ölçülen değerler; kullanıcı karar verebilsin diye gösteriliyor.
    private static let notlar: [String: String] = [
        "sonnet": "ilk cümle ~6,6 sn · soru başına ~0,050 birim",
        "opus": "ilk cümle ~7,3 sn · ~0,142 birim · daha derin akıl yürütme",
        "haiku": "en ucuz ve en hızlı · basit sorular için",
    ]

    var body: some View {
        Section {
            if let hata {
                Text(hata).font(.footnote).foregroundStyle(.red)
            }
            Picker("Sağlayıcı", selection: $saglayici) {
                Text("Claude").tag("claude")
                Text("Yerel model").tag("yerel")
            }
            .onChange(of: saglayici) { _, yeni in
                Task { await yaz("sohbet_saglayici", yeni) }
            }

            if saglayici == "claude" {
                Picker("Model", selection: $model) {
                    ForEach(ayarlar?.claudeModelleri ?? ["haiku", "sonnet", "opus"],
                            id: \.self) { m in
                        Text(m.capitalized).tag(m)
                    }
                }
                .onChange(of: model) { _, yeni in
                    Task { await yaz("sohbet_claude_modeli", yeni) }
                }
                if let n = Self.notlar[model] {
                    Text(n).font(.caption).foregroundStyle(.secondary)
                }
                if let l = ayarlar?.limit { kota(l) }
            } else {
                Text("ilk cümle ~16,8 sn · ücretsiz · cevaplar güvenilmez")
                    .font(.caption).foregroundStyle(.secondary)
            }

            if yaziyor {
                HStack { ProgressView().controlSize(.small)
                    Text("Kaydediliyor…").font(.caption)
                        .foregroundStyle(.secondary) }
            }
        } header: {
            Text("Yapay zekâ modeli")
        } footer: {
            Text("Sohbete hangi modelin cevap vereceği. Değişiklik hemen "
                 + "geçerli, sunucuyu yeniden başlatmak gerekmiyor.")
        }
        .task { await yukle() }
    }

    private func kota(_ l: Limit) -> some View {
        let kalan = l.kalan ?? 0
        let limit = l.limit ?? 0
        return HStack {
            Text("Bugün kalan").font(.caption)
            Spacer()
            Text(String(format: "%.2f / %.2f birim", kalan, limit))
                .font(.caption.monospacedDigit())
                .foregroundStyle(l.asildi.deger(false) ? .red : .secondary)
        }
    }

    private func yukle() async {
        do {
            let a = try await Api.ortak.sunucuAyarlari()
            ayarlar = a
            saglayici = a.deger("sohbet_saglayici", "claude")
            model = a.deger("sohbet_claude_modeli", "sonnet")
            hata = nil
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }

    private func yaz(_ anahtar: String, _ deger: String) async {
        // Ekran ilk dolarken Picker'lar da değişiyor; o değişimleri geri
        // yazmanın anlamı yok.
        guard let a = ayarlar, a.deger(anahtar, "") != deger else { return }
        yaziyor = true
        defer { yaziyor = false }
        do {
            try await Api.ortak.ayarYaz(anahtar, deger)
            await yukle()
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }
}
