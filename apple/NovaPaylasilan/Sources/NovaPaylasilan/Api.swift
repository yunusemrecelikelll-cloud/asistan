import Foundation

/// Sunucunun HTTP ucları — plan, projeler, yaşam.
///
/// Sesli tur kalıcı WebSocket üzerinden gidiyor; orada her milisaniye
/// önemli. Buradaki işler ise ekran açılınca bir kez okunan listeler:
/// HTTP hem daha basit hem de bağlantı koptuğunda tek bir isteği yeniden
/// denemek yetiyor.
///
/// Adres seçimi soketle aynı mantıkta: önce yerel ağ, tutmazsa Tailscale.
/// Hangisinin çalıştığını hatırlıyoruz, her istekte baştan denemiyoruz.
public actor Api {

    public static let ortak = Api()

    public enum Hata: LocalizedError {
        case adresYok
        case yetkisiz
        case sunucu(Int, String)
        case ag(String)

        public var errorDescription: String? {
            switch self {
            case .adresYok: "Sunucu adresi girilmemiş."
            case .yetkisiz: "Parola geçersiz."
            case .sunucu(let k, let m): "Sunucu hatası \(k): \(m)"
            case .ag(let m): "Bağlantı yok — \(m)"
            }
        }
    }

    /// Son çalışan taban adres. Bir kez bulunca ona sadık kalıyoruz.
    private var calisan: URL?

    private let oturum: URLSession = {
        let y = URLSessionConfiguration.default
        y.timeoutIntervalForRequest = 12
        y.waitsForConnectivity = false
        y.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: y)
    }()

    private func adresler() -> [URL] {
        var l: [URL] = []
        if let u = calisan { l.append(u) }
        for a in [Ayarlar.ortak.yerelHttpAdresi, Ayarlar.ortak.httpAdresi] {
            if let a, !l.contains(a) { l.append(a) }
        }
        return l
    }

    // MARK: - Ham istek

    /// - Parameter zamanAsimi: Varsayılan 12 sn kısa isteklere göre. Ses
    ///   örneği sentezlemek gibi uzun süren uçlar bunu uzatıyor; yoksa
    ///   sunucu daha cevabı üretmeden istek düşüyor.
    private func istek(_ yol: String, metot: String = "GET",
                       govde: Data? = nil,
                       zamanAsimi: TimeInterval? = nil) async throws -> Data {
        let hedefler = adresler()
        guard !hedefler.isEmpty else { throw Hata.adresYok }

        var sonHata: Error = Hata.ag("bilinmeyen")
        for taban in hedefler {
            var r = URLRequest(url: taban.appendingPathComponent(yol))
            r.httpMethod = metot
            r.httpBody = govde
            if let zamanAsimi { r.timeoutInterval = zamanAsimi }
            if govde != nil {
                r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            }
            let b = Ayarlar.ortak.belirtec
            if !b.isEmpty {
                r.setValue(b, forHTTPHeaderField: "x-asistan-belirtec")
            }
            do {
                let (veri, yanit) = try await oturum.data(for: r)
                let kod = (yanit as? HTTPURLResponse)?.statusCode ?? 0
                if kod == 401 { throw Hata.yetkisiz }
                guard (200..<300).contains(kod) else {
                    throw Hata.sunucu(kod, String(data: veri.prefix(200),
                                                  encoding: .utf8) ?? "")
                }
                calisan = taban            // bu adres tuttu, bir dahakine önce bu
                return veri
            } catch let h as Hata {
                if case .yetkisiz = h { throw h }   // adres değiştirmek çare değil
                sonHata = h
            } catch {
                sonHata = Hata.ag(error.localizedDescription)
            }
        }
        calisan = nil
        throw sonHata
    }

    private func coz<T: Decodable>(_ tur: T.Type, _ yol: String,
                                   metot: String = "GET",
                                   govde: Data? = nil) async throws -> T {
        let veri = try await istek(yol, metot: metot, govde: govde)
        do {
            return try JSONDecoder().decode(T.self, from: veri)
        } catch {
            throw Hata.sunucu(200, "yanıt çözülemedi: \(error)")
        }
    }

    // MARK: - Giriş

    /// Parolayı belirtece çevir.
    ///
    /// Sunucu ham parolayı kabul etmiyor; beklediği şey `sha256(tuz +
    /// parola)`. Ayarlardaki alan "Parola" diyordu ama yazılanı olduğu
    /// gibi belirteç sanıp yolluyordu, dolayısıyla parolasını doğru giren
    /// herkes "Parola geçersiz" alıyordu. Takası sunucu yapıyor, biz
    /// yalnızca soruyoruz.
    ///
    /// Bu istekte belirteç başlığı GÖNDERİLMİYOR — zaten elimizde yok.
    /// `/api/giris` parola korumasından muaf (auth.SERBEST).
    public func girisYap(parola: String) async throws -> String {
        struct Yanit: Decodable { let belirtec: String }
        let govde = try JSONEncoder().encode(["parola": parola])
        let veri = try await istek("api/giris", metot: "POST", govde: govde)
        guard let y = try? JSONDecoder().decode(Yanit.self, from: veri) else {
            throw Hata.yetkisiz
        }
        return y.belirtec
    }

    // MARK: - Plan

    public func bugun() async throws -> Gun {
        try await coz(Gun.self, "api/bugun")
    }

    public func hafta() async throws -> Hafta {
        try await coz(Hafta.self, "api/hafta")
    }

    public func gorevler(tarih: String) async throws -> [Gorev] {
        struct Sarmal: Decodable { let gorevler: [Gorev] }
        return try await coz(Sarmal.self, "api/gorevler?tarih=\(tarih)").gorevler
    }

    @discardableResult
    public func gorevBasla(_ id: Int) async throws -> Data {
        try await istek("api/gorev/\(id)/basla", metot: "POST")
    }

    @discardableResult
    public func gorevTamamla(_ id: Int) async throws -> Data {
        try await istek("api/gorev/\(id)/tamamla", metot: "POST")
    }

    @discardableResult
    public func gorevErtele(_ id: Int, gerekce: String = "") async throws -> Data {
        let g = try JSONEncoder().encode(["gerekce": gerekce])
        return try await istek("api/gorev/\(id)/ertele", metot: "POST", govde: g)
    }

    @discardableResult
    public func gorevSil(_ id: Int) async throws -> Data {
        try await istek("api/gorev/\(id)", metot: "DELETE")
    }

    @discardableResult
    public func gorevEkle(_ y: YeniGorev) async throws -> Data {
        try await istek("api/gorev", metot: "POST",
                        govde: try JSONEncoder().encode(y))
    }

    // MARK: - Projeler

    public func projeler() async throws -> [Proje] {
        struct Sarmal: Decodable { let projeler: [Proje] }
        return try await coz(Sarmal.self, "api/projeler").projeler
    }

    public func projeDetay(_ id: Int) async throws -> ProjeDetay {
        try await coz(ProjeDetay.self, "api/projeler/\(id)")
    }

    @discardableResult
    public func projeNot(_ id: Int, not: String) async throws -> Data {
        let g = try JSONEncoder().encode(["not_metni": not])
        return try await istek("api/projeler/\(id)/not", metot: "POST",
                               govde: g)
    }

    // MARK: - Yaşam

    public func yasam() async throws -> YasamOzeti {
        try await coz(YasamOzeti.self, "api/yasam")
    }

    /// Serbest cümleyle kayıt: "dün 6 saat uyudum, kahveye 45 lira verdim".
    @discardableResult
    public func yasamMetin(_ metin: String) async throws -> Data {
        let g = try JSONEncoder().encode(["metin": metin])
        return try await istek("api/yasam/metin", metot: "POST", govde: g)
    }

    // MARK: - Atölye

    public func atolye() async throws -> Atolye {
        try await coz(Atolye.self, "api/atolye")
    }

    public func dosyalar() async throws -> Dosyalar {
        try await coz(Dosyalar.self, "api/dosyalar")
    }

    @discardableResult
    public func dosyaTara() async throws -> Data {
        try await istek("api/dosyalar/tara", metot: "POST")
    }

    @discardableResult
    public func dosyaBitti(_ id: Int) async throws -> Data {
        let g = try JSONEncoder().encode(["dosya_id": id])
        return try await istek("api/dosya/bitti", metot: "POST", govde: g)
    }

    @discardableResult
    public func dosyaGeri(_ id: Int) async throws -> Data {
        let g = try JSONEncoder().encode(["dosya_id": id])
        return try await istek("api/dosya/geri", metot: "POST", govde: g)
    }

    // MARK: - Koç

    public func koc() async throws -> KocOzeti {
        try await coz(KocOzeti.self, "api/koc")
    }

    public func aliskanliklar() async throws -> AliskanlikOzeti {
        try await coz(AliskanlikOzeti.self, "api/aliskanliklar")
    }

    @discardableResult
    public func aliskanlikIsaret(_ id: Int, yapildi: Bool) async throws -> Data {
        struct G: Encodable {
            let aliskanlik_id: Int
            let yapildi: Bool
        }
        let g = try JSONEncoder().encode(G(aliskanlik_id: id,
                                           yapildi: yapildi))
        return try await istek("api/aliskanlik/isaret", metot: "POST",
                               govde: g)
    }

    // MARK: - Rapor

    public func rapor() async throws -> Rapor {
        try await coz(Rapor.self, "api/rapor")
    }

    // MARK: - Ses

    public func sesDurum() async throws -> SesDurumu {
        try await coz(SesDurumu.self, "api/ses/durum")
    }

    @discardableResult
    public func sesSec(_ anahtar: String) async throws -> Data {
        let g = try JSONEncoder().encode(["anahtar": anahtar])
        return try await istek("api/ses/sec", metot: "POST", govde: g)
    }

    @discardableResult
    public func sesAd(_ anahtar: String, ad: String) async throws -> Data {
        let g = try JSONEncoder().encode(["anahtar": anahtar, "ad": ad])
        return try await istek("api/ses/ad", metot: "POST", govde: g)
    }

    /// Örnek cümleyi bu sesle seslendir — seçmeden önce dinlemek için.
    /// WAV verisi döner.
    ///
    /// Sentez saniyeler sürebiliyor, o yüzden zaman aşımı uzun.
    public func sesDene(_ anahtar: String) async throws -> Data {
        let g = try JSONEncoder().encode(["referans": anahtar])
        return try await istek("api/ses/dene", metot: "POST", govde: g,
                               zamanAsimi: 45)
    }

    // MARK: - Sunucu ayarları

    public func sunucuAyarlari() async throws -> SunucuAyarlari {
        try await coz(SunucuAyarlari.self, "api/ayarlar")
    }

    @discardableResult
    public func ayarYaz(_ anahtar: String, _ deger: String) async throws -> Data {
        let g = try JSONEncoder().encode(["anahtar": anahtar, "deger": deger])
        return try await istek("api/ayarlar", metot: "POST", govde: g)
    }
}
