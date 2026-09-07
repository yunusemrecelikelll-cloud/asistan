import Foundation
import SwiftUI

/// Uygulamanın tek gerçeklik kaynağı. Telefon ve saat aynı sınıfı kullanıyor.
///
/// Buradaki akış tek bir amaca hizmet ediyor: kullanıcı konuşmayı bitirdiği
/// an ile ilk sesi duyduğu an arasındaki süreyi kısaltmak. Bunun için
///
///   • ses kaydı BİTMEDEN gönderiliyor (yükleme beklemesi yok),
///   • yanıt cümle cümle geliyor (bütün metnin bitmesi beklenmiyor),
///   • ses parçaları geldikçe sıraya konuyor (parça arası boşluk yok),
///   • bağlantı kalıcı (tur başına el sıkışma yok).
@MainActor
public final class Oturum: ObservableObject {

    public enum Hâl: Equatable {
        case bekliyor
        case dinliyor
        case dusunuyor
        case konusuyor
    }

    public struct Satir: Identifiable, Equatable {
        public let id = UUID()
        public let ben: Bool
        public var metin: String
        public let zaman: Date

        public init(ben: Bool, metin: String, zaman: Date = Date()) {
            self.ben = ben
            self.metin = metin
            self.zaman = zaman
        }
    }

    // MARK: - Arayüzün izlediği

    @Published public private(set) var hal: Hâl = .bekliyor
    @Published public private(set) var bagli = false
    @Published public private(set) var durumYazisi = "Bağlanıyor…"
    @Published public private(set) var satirlar: [Satir] = []
    /// 0…1 — küre bunu kullanıyor.
    @Published public private(set) var enerji: Float = 0
    /// Son turun ilk sesi kaç ms'de geldi (ayarlarda gösteriliyor).
    @Published public private(set) var sonGecikmeMs: Int?

    /// Sürekli dinleme açık mı ("Hey Nova" beklemek yerine hep açık).
    @Published public var surekliDinle = false {
        didSet { surekliDinle ? dinlemeyeBasla() : dinlemeyiBitir() }
    }

    // MARK: - İç

    public let baglanti: NovaBaglanti
    private let kayit = SesKayit()
    private let calar = SesCalar()
    private var turBaslangici: Date?
    private var ilkSesGeldi = false

    public init(tasiyici: Tasiyici = SoketTasiyici()) {
        baglanti = NovaBaglanti(tasiyici: tasiyici)
        baglantiyiBagla()
        kaydiBagla()
        calariBagla()
    }

    public func basla() {
        baglanti.ac()
    }

    // MARK: - Kullanıcı eylemleri

    public func metinGonder(_ metin: String) {
        let t = metin.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, bagli else { return }
        satirlar.append(Satir(ben: true, metin: t))
        turBasladi()
        baglanti.gonder(.metin(t, sesli: true))
    }

    public func dinlemeyeBasla() {
        guard bagli, !kayit.kaydediyor else { return }
        // Nova konuşurken kullanıcı düğmeye bastıysa sözünü kesiyoruz.
        calar.kes()
        kayit.izinIste { [weak self] izin in
            Task { @MainActor in
                guard let self else { return }
                guard izin else {
                    self.durumYazisi = "Mikrofon izni yok"
                    return
                }
                do {
                    self.baglanti.gonder(.sesBasla)
                    try self.kayit.basla()
                    self.hal = .dinliyor
                    self.durumYazisi = "Dinliyorum"
                } catch {
                    self.durumYazisi = "Mikrofon açılmadı"
                }
            }
        }
    }

    public func dinlemeyiBitir() {
        guard kayit.kaydediyor else { return }
        let bayt = kayit.bitir()
        guard bayt > 4_000 else {          // ~0,12 saniye; kazara dokunma
            hal = .bekliyor
            durumYazisi = "Hazır"
            return
        }
        turBasladi()
        // .pcm: sunucu WAV başlığını kendisi ekliyor. Ham göndermek,
        // kayıt sürerken yollayabilmemizin karşılığı.
        baglanti.gonder(.sesBitti(uzanti: ".pcm", sesli: true))
    }

    public func sustur() {
        calar.kes()
        hal = kayit.kaydediyor ? .dinliyor : .bekliyor
    }

    public func sohbetiSifirla() {
        satirlar.removeAll()
    }

    // MARK: - Bağlama

    private func turBasladi() {
        turBaslangici = Date()
        ilkSesGeldi = false
        hal = .dusunuyor
        durumYazisi = "Düşünüyorum"
        // Yanıt gelene kadar ~2 saniyemiz var; motoru şimdi kuralım ki ilk
        // ses parçası geldiğinde 50-150 ms'lik motor açılışını beklemeyelim.
        calar.hazirla()
    }

    private func baglantiyiBagla() {
        baglanti.durumDegisti = { [weak self] d in
            Task { @MainActor in
                guard let self else { return }
                switch d {
                case .hazir:
                    self.bagli = true
                    self.durumYazisi = "Hazır"
                    if self.surekliDinle { self.dinlemeyeBasla() }
                case .baglaniyor:
                    self.bagli = false
                    self.durumYazisi = "Bağlanıyor…"
                case .yetkisiz:
                    self.bagli = false
                    self.durumYazisi = "Parola geçersiz"
                case .kapali:
                    self.bagli = false
                    self.durumYazisi = "Bağlı değil"
                case .hata(let m):
                    self.bagli = false
                    self.durumYazisi = "Bağlantı yok — \(m)"
                }
            }
        }

        baglanti.yaziGeldi = { [weak self] metin in
            Task { @MainActor in
                guard let self, !metin.isEmpty else { return }
                self.satirlar.append(Satir(ben: true, metin: metin))
            }
        }

        baglanti.yanitGeldi = { [weak self] metin, kismi in
            Task { @MainActor in
                guard let self else { return }
                // Kısmi yanıt ilk cümle: kullanıcı sesi beklemeden okusun.
                // Tam yanıt geldiğinde aynı satırı yerinde güncelliyoruz ki
                // ekranda cümle iki kez görünmesin.
                if let son = self.satirlar.last, !son.ben {
                    self.satirlar[self.satirlar.count - 1].metin = metin
                } else {
                    self.satirlar.append(Satir(ben: false, metin: metin))
                }
                if kismi { self.durumYazisi = "Yanıtlıyor" }
            }
        }

        baglanti.sesParcasiGeldi = { [weak self] veri, bicim, ara in
            Task { @MainActor in
                guard let self else { return }
                // Biçim SUNUCUDAN geliyor ve önemli: ses klonu düştüğünde
                // sunucu sessizce edge-tts'e geçip mp3 yolluyor. Eskiden bu
                // alan atılıyordu, çalar da WAV varsayıp parçayı sessizce
                // düşürüyordu — telefonda hiç ses çıkmıyordu.
                guard self.calar.sirayaEkle(veri, bicim: bicim) else { return }
                // Dolgu sesi gecikme ölçümüne KATILMIYOR. Katsaydı ekranda
                // hep ~300 ms görürdük ve gerçek gecikme görünmez olurdu —
                // oysa o rakam tam da ayarlamak için orada duruyor.
                if !ara, !self.ilkSesGeldi, let t = self.turBaslangici {
                    self.ilkSesGeldi = true
                    self.sonGecikmeMs = Int(Date().timeIntervalSince(t) * 1000)
                }
                self.hal = .konusuyor
                self.durumYazisi = ara ? "Düşünüyorum" : "Konuşuyorum"
            }
        }

        baglanti.turBitti = { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                // Ses hiç çalmadıysa (sessiz yanıt, çözülemeyen parça)
                // `calar.bitti` tetiklenmiyor. Sürekli dinlemeyi yeniden
                // kuran tek yer orasıydı; kip böyle turlarda ölüyordu.
                if !self.calar.caliyor {
                    self.hal = .bekliyor
                    self.durumYazisi = "Hazır"
                    if self.surekliDinle { self.dinlemeyeBasla() }
                }
            }
        }
    }

    private func kaydiBagla() {
        kayit.parcaHazir = { [weak self] veri in
            self?.baglanti.sesGonder(veri)
        }
        kayit.seviyeDegisti = { [weak self] s in
            Task { @MainActor in
                guard let self, self.hal == .dinliyor else { return }
                self.enerji = s
            }
        }
        kayit.kesintiyeUgradi = { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                self.hal = .bekliyor
                self.enerji = 0
                self.durumYazisi = "Kayıt kesildi"
            }
        }
        kayit.sessizlikAlgilandi = { [weak self] in
            Task { @MainActor in
                guard let self, self.kayit.kaydediyor else { return }
                self.dinlemeyiBitir()
            }
        }
    }

    private func calariBagla() {
        calar.seviyeDegisti = { [weak self] s in
            Task { @MainActor in
                guard let self, self.hal == .konusuyor else { return }
                self.enerji = s
            }
        }
        calar.bitti = { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                self.enerji = 0
                if self.hal == .konusuyor {
                    self.hal = .bekliyor
                    self.durumYazisi = "Hazır"
                    // Karşılıklı konuşma: Nova sustuğu an tekrar dinlemeye
                    // geçiyoruz, kullanıcının düğmeye basması gerekmiyor.
                    if self.surekliDinle { self.dinlemeyeBasla() }
                }
            }
        }
    }
}
