import Foundation

/// Nova protokolünü konuşan katman. Baytları taşımayı `Tasiyici`ya bırakır.
///
/// Telefonda taşıyıcı doğrudan WebSocket; saatte ev ağının dışındayken
/// telefon rölesi. Protokol iki durumda da aynı olduğu için bu sınıf ve
/// üstündeki `Oturum` her iki uygulamada da değişmeden çalışıyor.
public final class NovaBaglanti {

    public enum Durum: Equatable {
        case kapali
        case baglaniyor
        case hazir(ses: String)
        case yetkisiz
        case hata(String)
    }

    // MARK: - Dışarıya bildirilenler

    public var durumDegisti: ((Durum) -> Void)?
    public var yaziGeldi: ((String) -> Void)?
    public var yanitGeldi: ((String, Bool) -> Void)?          // metin, kısmi mi
    public var sesParcasiGeldi: ((Data, String, Bool) -> Void)?
    // veri, biçim, dolgu mu (kullanıcı sustuktan sonraki "seni duydum")
    public var turBitti: (() -> Void)?
    public var olayGeldi: ((String, [String: Any]) -> Void)?

    public private(set) var durum: Durum = .kapali {
        didSet {
            guard durum != oldValue else { return }
            let d = durum
            DispatchQueue.main.async { self.durumDegisti?(d) }
        }
    }

    public var tasiyiciAdi: String { tasiyici.ad }

    /// Mevcut durumu yeniden bildir.
    ///
    /// `durum` yalnızca DEĞİŞTİĞİNDE haber veriyor. Telefonun saat için
    /// tuttuğu röle zaten açıkken saat yeniden bağlanmak istediğinde bu
    /// yüzden hiç `hazir` almıyor ve sonsuza kadar "Bağlanıyor…"da
    /// kalıyordu. Röle, saatten istek gelince bunu çağırıyor.
    public func durumuYinele() {
        let d = durum
        DispatchQueue.main.async { self.durumDegisti?(d) }
    }

    private var tasiyici: Tasiyici
    private var bekleyenBicim: String?
    private var bekleyenAra = false
    private var nabiz: Timer?

    public init(tasiyici: Tasiyici = SoketTasiyici()) {
        self.tasiyici = tasiyici
        bagla()
    }

    /// Taşıyıcıyı çalışırken değiştir (saat ev ağına girip çıkarken).
    public func tasiyiciyiDegistir(_ yeni: Tasiyici) {
        nabiz?.invalidate()
        nabiz = nil
        tasiyici.kapat()
        tasiyici = yeni
        bekleyenBicim = nil
        bekleyenAra = false
        bagla()
        ac()
    }

    private func bagla() {
        tasiyici.metinGeldi = { [weak self] d in self?.metinCercevesi(d) }
        tasiyici.ikiliGeldi = { [weak self] d in self?.ikiliCerceve(d) }
        tasiyici.durumDegisti = { [weak self] d in
            guard let self else { return }
            switch d {
            case .kapali:
                self.durum = .kapali
            case .acilliyor:
                self.durum = .baglaniyor
            case .acik:
                // Taşıyıcı açıldı; sunucu "hazir" diyene kadar hâlâ
                // bağlanıyoruz.
                self.durum = .baglaniyor
                // Röle üzerinden gidiyorsak kimlik doğrulamayı ve nabzı
                // telefon kendi bağlantısında zaten yapıyor. Saatte belirteç
                // yok — ayrıca yollamaya çalışmak boşuna trafik.
                guard self.tasiyici.sunucuyaDogrudan else { return }
                let b = Ayarlar.ortak.belirtec
                if !b.isEmpty { self.gonder(.giris(belirtec: b)) }
                self.nabziBaslat()
            case .hata(let m):
                self.durum = .hata(m)
            }
        }
    }

    // MARK: - Açma/kapama

    public func ac() { tasiyici.ac() }

    public func kapat() {
        nabiz?.invalidate()
        nabiz = nil
        tasiyici.kapat()
        durum = .kapali
    }

    // MARK: - Gönderme

    public func gonder(_ mesaj: Protokol.Giden) {
        tasiyici.yolla(mesaj.kodla())
    }

    /// Hazır kodlanmış çerçeveyi olduğu gibi geçir.
    ///
    /// Telefonun saat için yaptığı röle bunu kullanıyor: saatten gelen
    /// çerçeveyi çözüp yeniden kodlamak hem gereksiz hem de protokol
    /// büyüdükçe röleyi bozan bir bağımlılık olurdu.
    public func hamYolla(_ veri: Data) {
        tasiyici.yolla(veri)
    }

    /// Ses parçasını olduğu gibi gönder. Kayıt SÜRERKEN çağrılıyor:
    /// kullanıcı konuşmasını bitirdiğinde ses zaten sunucuda oluyor.
    public func sesGonder(_ veri: Data) {
        tasiyici.ikiliYolla(veri)
    }

    // MARK: - Çerçeve çözme

    private func metinCercevesi(_ veri: Data) {
        guard let gelen = Protokol.Gelen.coz(veri) else { return }
        switch gelen {
        case .hazir(let ses):
            durum = .hazir(ses: ses)
        case .yetkisiz:
            durum = .yetkisiz
        case .yazi(let m, _):
            DispatchQueue.main.async { self.yaziGeldi?(m) }
        case .yanit(let m, _, let kismi, _):
            DispatchQueue.main.async { self.yanitGeldi?(m, kismi) }
        case .parca(_, _, let bicim, _, let ara):
            bekleyenBicim = bicim          // ikili çerçeve BUNDAN sonra gelir
            bekleyenAra = ara
        case .bitti:
            DispatchQueue.main.async { self.turBitti?() }
        case .olay(let tur, let d):
            DispatchQueue.main.async { self.olayGeldi?(tur, d) }
        case .nabiz:
            break
        case .hata(let m):
            durum = .hata(m)
        }
    }

    private func ikiliCerceve(_ veri: Data) {
        let bicim = bekleyenBicim ?? "audio/wav"
        let ara = bekleyenAra
        bekleyenBicim = nil
        bekleyenAra = false
        DispatchQueue.main.async {
            self.sesParcasiGeldi?(veri, bicim, ara)
        }
    }

    private func nabziBaslat() {
        DispatchQueue.main.async {
            self.nabiz?.invalidate()
            // Yol üzerindeki NAT ve yönlendiriciler sessiz bağlantıyı
            // düşürüyor; 20 saniyelik nabız kanalı açık tutuyor.
            self.nabiz = Timer.scheduledTimer(withTimeInterval: 20,
                                              repeats: true) { [weak self] _ in
                self?.gonder(.nabiz)
            }
        }
    }
}
