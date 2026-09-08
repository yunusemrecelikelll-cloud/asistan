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

    private func istek(_ yol: String, metot: String = "GET",
                       govde: Data? = nil) async throws -> Data {
        let hedefler = adresler()
        guard !hedefler.isEmpty else { throw Hata.adresYok }

        var sonHata: Error = Hata.ag("bilinmeyen")
        for taban in hedefler {
            var r = URLRequest(url: taban.appendingPathComponent(yol))
            r.httpMethod = metot
            r.httpBody = govde
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

    // MARK: - Yaşam

    public func yasam() async throws -> YasamOzeti {
        try await coz(YasamOzeti.self, "api/yasam")
    }

    // MARK: - Koç

    public func koc() async throws -> KocOzeti {
        try await coz(KocOzeti.self, "api/koc")
    }
}
