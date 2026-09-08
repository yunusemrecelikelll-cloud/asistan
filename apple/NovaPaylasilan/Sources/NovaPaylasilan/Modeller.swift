import Foundation

/// Sunucudan gelen kayıtların Swift karşılığı.
///
/// Alanların çoğu isteğe bağlı (`?`) — bilerek. Sunucu yeni bir alan
/// eklediğinde ya da bir alanı boş bıraktığında uygulamanın çözümlemesi
/// tamamen düşmesin. Ekranda gösterdiğimizden fazlasını modellemiyoruz.

public struct Gorev: Decodable, Identifiable, Equatable, Sendable {
    public let id: Int
    public let baslik: String
    public let tarih: String
    public let saat: String
    public let sureDk: Int?
    public let durum: String
    public let oncelik: Int?
    public let zorunlu: Bool?
    public let ayrinti: String?
    public let projeId: Int?
    public let projeAd: String?
    public let erteleme: Int?

    enum CodingKeys: String, CodingKey {
        case id, baslik, tarih, saat, durum, oncelik, zorunlu, ayrinti,
             erteleme
        case sureDk = "sure_dk"
        case projeId = "proje_id"
        case projeAd = "proje_ad"
    }

    /// Görev saatinin bugünkü tam tarihi. Bildirim kurmak için.
    public var zaman: Date? {
        let b = DateFormatter()
        b.locale = Locale(identifier: "tr_TR")
        b.dateFormat = "yyyy-MM-dd HH:mm"
        b.timeZone = .current
        return b.date(from: "\(tarih) \(saat)")
    }

    public var bekliyor: Bool { durum == "bekliyor" || durum == "basladi" }
    public var tamam: Bool { durum == "tamam" }
    public var kacirildi: Bool { durum == "kacirildi" }
}

public struct Karne: Decodable, Equatable, Sendable {
    public let toplam: Int
    public let tamam: Int
    public let kacirildi: Int
    public let kalan: Int
    public let uyum: Double?
}

public struct Gun: Decodable, Equatable, Sendable {
    public let tarih: String
    public let gun: String
    public let saat: String
    public let gorevler: [Gorev]
    public let siradaki: Gorev?
    public let karne: Karne
}

public struct HaftaGunu: Decodable, Identifiable, Equatable, Sendable {
    public let tarih: String
    public let gun: String
    public let gorevler: [Gorev]?
    public var id: String { tarih }
}

public struct Hafta: Decodable, Equatable, Sendable {
    public let baslangic: String
    public let bitis: String
    public let gunler: [HaftaGunu]
}

public struct Proje: Decodable, Identifiable, Equatable, Sendable {
    public let id: Int
    public let ad: String
    public let yol: String?
    public let varMi: Bool?
    public let oturumSayisi: Int?
    public let notMetni: String?
    public let durum: String?

    enum CodingKeys: String, CodingKey {
        case id, ad, yol, durum
        case varMi = "var_mi"
        case oturumSayisi = "oturum_sayisi"
        case notMetni = "not_metni"
    }
}

public struct YasamKarti: Decodable, Identifiable, Equatable, Sendable {
    public let tur: String
    public let ad: String
    public let birim: String?
    public let bugun: Double?
    public let ortalama: Double?
    public let hedef: Double?
    public let durum: String?
    public var id: String { tur }
}

public struct YasamOzeti: Decodable, Equatable, Sendable {
    public let kartlar: [YasamKarti]
}

public struct KocOzeti: Decodable, Equatable, Sendable {
    public let tarih: String?
}

/// Yeni görev gövdesi — POST /api/gorev
public struct YeniGorev: Encodable, Sendable {
    public var baslik: String
    public var tarih: String
    public var saat: String
    public var sureDk: Int
    public var projeId: Int?
    public var ayrinti: String?
    public var oncelik: Int
    public var zorunlu: Bool

    enum CodingKeys: String, CodingKey {
        case baslik, tarih, saat, ayrinti, oncelik, zorunlu
        case sureDk = "sure_dk"
        case projeId = "proje_id"
    }

    public init(baslik: String, tarih: String, saat: String,
                sureDk: Int = 60, projeId: Int? = nil,
                ayrinti: String? = nil, oncelik: Int = 2,
                zorunlu: Bool = true) {
        self.baslik = baslik
        self.tarih = tarih
        self.saat = saat
        self.sureDk = sureDk
        self.projeId = projeId
        self.ayrinti = ayrinti
        self.oncelik = oncelik
        self.zorunlu = zorunlu
    }
}

public enum Bicim {
    /// "2026-09-08" — sunucunun beklediği tarih biçimi.
    public static func tarih(_ d: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: d)
    }

    public static func saat(_ d: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "HH:mm"
        return f.string(from: d)
    }
}
